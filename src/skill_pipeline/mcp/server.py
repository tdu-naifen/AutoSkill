"""MCP server for Claude Code integration — exposes knowledge graph + proposals."""
from __future__ import annotations

import logging
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

def create_server(vault_root: str, chroma_dir: str | None = None) -> FastMCP:
    """Create and configure the MCP server."""
    mcp = FastMCP("autoskill", instructions="AutoSkill knowledge graph — search documents, browse tags, manage skill proposals.")

    _vault = Path(vault_root)

    def _proposal_to_skill(name: str, proposal_text: str) -> str:
        """Convert a proposal markdown to a SKILL.md format string."""
        import yaml

        fm = {}
        body = proposal_text
        if proposal_text.startswith("---"):
            parts = proposal_text.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()

        skill_fm = {
            "name": name,
            "description": fm.get("summary", body[:200]),
            "proposal_type": fm.get("proposal_type", "reference"),
            "proposed_from": fm.get("proposed_from", ""),
        }

        fm_str = yaml.dump(skill_fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
        return f"---\n{fm_str}\n---\n\n{body}\n"

    @mcp.tool()
    def search_knowledge(query: str, n_results: int = 5) -> list[dict]:
        """Search the knowledge graph for relevant documents.

        Args:
            query: Natural language search query
            n_results: Number of results to return (default 5)
        """
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
        from skill_pipeline.core.embedder import get_strategy

        store_kwargs = {}
        if chroma_dir:
            store_kwargs["persist_dir"] = Path(chroma_dir)
        store = KnowledgeStore(**store_kwargs)
        strategy = get_strategy()

        embedding = strategy.embed([query])[0]
        results = store.query(embedding, n_results=n_results)

        items = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                dist = results["distances"][0][i] if results.get("distances") else 0
                items.append({
                    "text": doc[:500],
                    "path": meta.get("doc_id", ""),
                    "title": meta.get("title", ""),
                    "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                    "source_type": meta.get("source_type", ""),
                    "similarity": round(1.0 - dist, 3),
                })
        return items

    @mcp.tool()
    def get_document(path: str) -> dict:
        """Get full document content and metadata by vault path."""
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
        store_kwargs = {}
        if chroma_dir:
            store_kwargs["persist_dir"] = Path(chroma_dir)
        store = KnowledgeStore(**store_kwargs)

        chunks = store.get_document_chunks(path)
        if not chunks or not chunks.get("documents"):
            return {"error": f"Document not found: {path}"}

        text = "\n\n".join(chunks["documents"])
        meta = chunks["metadatas"][0] if chunks.get("metadatas") else {}
        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]

        return {
            "text": text,
            "path": path,
            "title": meta.get("title", ""),
            "tags": tags,
            "source_type": meta.get("source_type", ""),
            "chunk_count": len(chunks["documents"]),
        }

    @mcp.tool()
    def list_proposals() -> list[dict]:
        """List pending skill proposals."""
        from skill_pipeline.proposals.evaluator import list_pending_proposals
        proposals = list_pending_proposals(_vault)
        return [{
            "name": p.name,
            "type": p.proposal_type,
            "source_path": p.source_path,
            "confidence": p.confidence,
        } for p in proposals]

    @mcp.tool()
    def get_proposal(name: str) -> dict:
        """Get full proposal details by name."""
        import yaml
        path = _vault / "proposals" / f"{name}.md"
        if not path.exists():
            return {"error": f"Proposal not found: {name}"}

        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                return {**fm, "name": name, "body": parts[2].strip()}
        return {"name": name, "body": text}

    @mcp.tool()
    def decide_proposal(name: str, accepted: bool) -> dict:
        """Accept or reject a skill proposal.

        On accept: returns full skill content in SKILL.md format for Claude to save,
        then deletes the local proposal file.
        On reject: deletes the local proposal file.

        Returns:
            dict with keys:
            - status: "accepted" | "rejected"
            - skill_content: (only on accept) full SKILL.md content ready to save
            - name: proposal name
        """
        from skill_pipeline.proposals.tracker import record_decision

        path = _vault / "proposals" / f"{name}.md"
        if not path.exists():
            return {"error": f"Proposal not found: {name}"}

        text = path.read_text(encoding="utf-8")
        result = {"name": name, "status": "accepted" if accepted else "rejected"}

        if accepted:
            skill_content = _proposal_to_skill(name, text)
            result["skill_content"] = skill_content

        # Record decision in tracker (adjusts threshold)
        record_decision(name, accepted)

        # Delete the local proposal file
        path.unlink()

        return result

    @mcp.tool()
    def browse_tags(prefix: str = "") -> list[dict]:
        """List all tags with document counts, optionally filtered by prefix."""
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
        from collections import Counter

        store_kwargs = {}
        if chroma_dir:
            store_kwargs["persist_dir"] = Path(chroma_dir)
        store = KnowledgeStore(**store_kwargs)

        all_data = store._collection.get()
        tag_counts = Counter()
        if all_data and all_data.get("metadatas"):
            for meta in all_data["metadatas"]:
                tags_str = meta.get("tags", "")
                for t in tags_str.split(","):
                    t = t.strip()
                    if t and (not prefix or t.startswith(prefix)):
                        tag_counts[t] += 1  # counts chunks, not docs — approximate

        return [{"tag": t, "document_count": c} for t, c in tag_counts.most_common()]

    @mcp.tool()
    def search_by_tag(tag: str, n_results: int = 10) -> list[dict]:
        """Find all documents with a specific tag."""
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore

        store_kwargs = {}
        if chroma_dir:
            store_kwargs["persist_dir"] = Path(chroma_dir)
        store = KnowledgeStore(**store_kwargs)

        results = store._collection.get(where={"tags": {"$contains": tag}})

        docs = {}
        if results and results.get("metadatas"):
            for i, meta in enumerate(results["metadatas"]):
                doc_id = meta.get("doc_id", "")
                if doc_id not in docs:
                    docs[doc_id] = {
                        "path": doc_id,
                        "title": meta.get("title", ""),
                        "source_type": meta.get("source_type", ""),
                        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                    }

        return list(docs.values())[:n_results]

    return mcp
