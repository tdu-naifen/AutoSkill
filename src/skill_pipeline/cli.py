"""CLI entry point for skill-pipeline."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import typer

from skill_pipeline.core.config import load_dotenv
load_dotenv()

app = typer.Typer(name="autoskill", help="AutoSkill — deduplicate AI agent skills.")


def _set_backend(name: str) -> None:
    """Configure the global embedding strategy from a backend name."""
    from skill_pipeline.core.embedder import (
        set_strategy,
        OpenAICompatibleStrategy,
        SentenceTransformerStrategy,
    )

    if name == "openai":
        set_strategy(OpenAICompatibleStrategy())
    else:
        set_strategy(SentenceTransformerStrategy())


@app.command()
def ingest(
    input_dir: Path = typer.Argument(..., help="Directory containing skills (with SKILL.md files)"),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory"),
) -> None:
    """Parse skills, find shared knowledge, write output."""

    async def _run() -> None:
        from skill_pipeline.vault_init import init_vault
        init_vault(output)
        from skill_pipeline.skills.pipeline import run_pipeline

        result = await run_pipeline(input_dir, output)
        if "error" in result:
            typer.echo(f"Error: {result['error']}")
        else:
            typer.echo(
                f"Done — {result['skills']} skills, "
                f"{result['knowledge_topics']} knowledge topics, "
                f"{result['similar_pairs']} similar pairs"
            )

    asyncio.run(_run())


@app.command()
def scan(
    input_dir: Path = typer.Argument(..., help="Directory to scan for skills"),
) -> None:
    """Scan and list skills found in input directory (dry run)."""
    from skill_pipeline.skills.parser import scan_input

    skills = scan_input(input_dir)
    typer.echo(f"Found {len(skills)} skills:\n")
    for s in skills:
        sub = f" ({len(s.sub_files)} sub-files)" if s.sub_files else ""
        desc = s.description[:80] if s.description else "(no description)"
        typer.echo(f"  {s.name}{sub}")
        typer.echo(f"    {desc}\n")


@app.command()
def dashboard(
    port: int = typer.Option(8420, "--port", "-p", help="Port for the dashboard server"),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory"),
) -> None:
    """Start the dashboard server."""
    import uvicorn
    from skill_pipeline.dashboard.app import create_app

    typer.echo(f"Starting dashboard on http://localhost:{port}")
    uvicorn.run(create_app(output=str(output)), host="0.0.0.0", port=port)


@app.command()
def status() -> None:
    """Print current pipeline status."""
    from skill_pipeline.core.progress import get_status

    s = get_status()
    typer.echo(f"Stage:    {s['stage']}")
    typer.echo(f"Progress: {s['files_done']}/{s['files_total']} ({s['pct']}%)")
    if s['message']:
        typer.echo(f"Message:  {s['message']}")
    if s['elapsed']:
        typer.echo(f"Elapsed:  {s['elapsed']}s")


@app.command()
def index(
    files: list[Path] = typer.Argument(..., help="Document files to index (md/pdf/html/docx/txt)"),
    vault: Path = typer.Option(".", "--vault", "-v", help="Vault root (for relative doc IDs)"),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory (Obsidian vault)"),
    backend: str = typer.Option(
        "sentence-transformer", "--backend", "-b", help="Embedding backend: 'sentence-transformer' or 'openai'"
    ),
) -> None:
    """Index documents into the knowledge graph."""
    from skill_pipeline.knowledge.doc_parser import SUPPORTED_EXTENSIONS
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
    from skill_pipeline.knowledge.indexer import index_file
    from skill_pipeline.core.embedder import get_strategy
    from skill_pipeline.core.progress import update as progress_update

    _set_backend(backend)
    strategy = get_strategy()
    store = KnowledgeStore()

    valid_files = [Path(f) for f in files if Path(f).exists() and Path(f).suffix.lower() in SUPPORTED_EXTENSIONS]
    progress_update(stage="indexing", files_total=len(valid_files), files_done=0, chunks_total=0,
                    message="Starting document indexing…", started_at=time.time())

    async def _index_all() -> int:
        indexed = 0
        total_chunks = 0
        for i, file_path in enumerate(files):
            file_path = Path(file_path)
            if not file_path.exists():
                typer.echo(f"Skipping {file_path} — not found")
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                typer.echo(f"Skipping {file_path} — unsupported type")
                continue

            progress_update(stage="indexing", current_file=file_path.name,
                            message=f"Parsing {file_path.name}…")

            try:
                result = await index_file(
                    file_path, store, strategy,
                    vault_root=vault, output_dir=output,
                    delete_first=False, evaluate_proposals=True,
                )
                if result is None:
                    typer.echo(f"Skipping {file_path} — no content")
                    continue

                if result.proposal_name:
                    typer.echo(f"  → Skill proposal: {result.proposal_name} → {result.proposal_path.name}")

                indexed += 1
                total_chunks += result.chunks
                progress_update(files_done=indexed, chunks_total=total_chunks)
                tags_str = ", ".join(result.tags[:5]) if result.tags else "(none)"
                typer.echo(f"  Indexed {file_path.name} ({result.chunks} chunks, tags: {tags_str} [{result.method}])")
            except Exception as e:
                typer.echo(f"  Error indexing {file_path}: {e}")
        return indexed

    indexed = asyncio.run(_index_all())
    progress_update(stage="done", message=f"Indexed {indexed} documents ({store.count()} total chunks)")
    typer.echo(f"\nDone — indexed {indexed} documents ({store.count()} total chunks)")


@app.command()
def reindex(
    files: list[Path] = typer.Argument(..., help="Files to re-index"),
    vault: Path = typer.Option(".", "--vault", "-v"),
    backend: str = typer.Option("sentence-transformer", "--backend", "-b"),
) -> None:
    """Re-index files already in the vault (delete old + re-index)."""
    from skill_pipeline.knowledge.doc_parser import SUPPORTED_EXTENSIONS
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
    from skill_pipeline.knowledge.indexer import index_file
    from skill_pipeline.core.embedder import get_strategy

    _set_backend(backend)
    strategy = get_strategy()
    store = KnowledgeStore()

    async def _reindex_all() -> int:
        reindexed = 0
        for file_path in files:
            file_path = Path(file_path)
            if not file_path.exists():
                typer.echo(f"Skipping {file_path} — not found")
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                typer.echo(f"Skipping {file_path} — unsupported type")
                continue

            try:
                result = await index_file(
                    file_path, store, strategy,
                    vault_root=vault, delete_first=True,
                    evaluate_proposals=False,
                )
                if result is None:
                    typer.echo(f"Skipping {file_path} — no content")
                    continue

                reindexed += 1
                tags_str = ", ".join(result.tags[:5]) if result.tags else "(none)"
                typer.echo(f"  Re-indexed {file_path.name} ({result.chunks} chunks, tags: {tags_str} [{result.method}])")
            except Exception as e:
                typer.echo(f"  Error re-indexing {file_path}: {e}")
        return reindexed

    reindexed = asyncio.run(_reindex_all())
    typer.echo(f"\nDone — re-indexed {reindexed} documents ({store.count()} total chunks)")


@app.command()
def watch(
    input_dir: Path = typer.Argument(
        "input_skills", help="Input directory to watch for skills and documents"
    ),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory (Obsidian vault)"),
    backend: str = typer.Option("sentence-transformer", "--backend", "-b"),
) -> None:
    """Watch input directory for new skills and documents, process continuously."""
    from skill_pipeline.knowledge.watcher import start_watcher
    from skill_pipeline.vault_init import init_vault

    _set_backend(backend)
    init_vault(output)
    typer.echo(f"Watching {input_dir} for skills and documents (output → {output})")
    asyncio.run(start_watcher(input_dir, output))


@app.command("mcp-serve")
def mcp_serve(
    vault: Path = typer.Argument(..., help="Vault root directory"),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport: stdio or sse"),
    backend: str = typer.Option("sentence-transformer", "--backend", "-b"),
) -> None:
    """Start the MCP server for Claude Code integration."""
    from skill_pipeline.mcp.server import create_server

    _set_backend(backend)
    server = create_server(vault_root=str(vault))
    server.run(transport=transport)


@app.command("init-vault")
def init_vault_cmd(
    output: Path = typer.Argument("output", help="Output directory to initialize as Obsidian vault"),
) -> None:
    """Initialize output directory as an Obsidian vault with AutoSkill plugin."""
    from skill_pipeline.vault_init import init_vault
    init_vault(output)
    typer.echo(f"Vault initialized at {output}/")
    typer.echo(f"  .obsidian/plugins/autoskill/ — plugin files")
    typer.echo(f"  Open {output}/ in Obsidian and enable the AutoSkill plugin.")


@app.command()
def proposals(
    output: Path = typer.Option("output", "--output", "-o"),
) -> None:
    """List pending skill proposals."""
    from skill_pipeline.proposals.evaluator import list_pending_proposals
    pending = list_pending_proposals(output)
    if not pending:
        typer.echo("No pending proposals.")
        return
    for p in pending:
        typer.echo(f"  [{p.confidence:.0%}] {p.name} ({p.proposal_type}) — from {p.source_path}")


if __name__ == "__main__":
    app()
