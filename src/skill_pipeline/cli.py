"""CLI entry point for skill-pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

# Load .env file if present
_env_file = Path.cwd() / ".env"
if _env_file.exists():
    import os
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

app = typer.Typer(name="autoskill", help="AutoSkill — deduplicate AI agent skills.")


@app.command()
def ingest(
    input_dir: Path = typer.Argument(..., help="Directory containing skills (with SKILL.md files)"),
    output: Path = typer.Option("output", "--output", "-o", help="Output directory"),
) -> None:
    """Parse skills, find shared knowledge, write output."""

    async def _run() -> None:
        from skill_pipeline.pipeline import run_pipeline

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
    from skill_pipeline.parser import scan_input

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
    from skill_pipeline.progress import get_status

    s = get_status()
    typer.echo(f"Stage:    {s['stage']}")
    typer.echo(f"Progress: {s['files_done']}/{s['files_total']} ({s['pct']}%)")
    if s['message']:
        typer.echo(f"Message:  {s['message']}")
    if s['elapsed']:
        typer.echo(f"Elapsed:  {s['elapsed']}s")


if __name__ == "__main__":
    app()
