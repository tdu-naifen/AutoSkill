"""Knowledge graph HTTP API routes for the Obsidian plugin."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Body

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# These will be set by the app factory
_vault_root: Path = Path(".")
_input_dir: Path = Path("input_skills")
_backend_name: str = "openai"


def configure(vault_root: Path, input_dir: Path = Path("input_skills"), backend_name: str = "openai") -> None:
    global _vault_root, _backend_name, _input_dir
    _vault_root = vault_root
    _input_dir = input_dir
    _backend_name = backend_name


@router.get("/health")
async def health():
    """Health check — returns status + doc count."""
    try:
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
        store = KnowledgeStore()
        return {
            "status": "ok",
            "chromadb": True,
            "documents": store.count(),
            "version": "0.1.0",
        }
    except Exception as e:
        return {"status": "error", "chromadb": False, "documents": 0, "version": "0.1.0", "error": str(e)}


@router.get("/inbox")
async def inbox_status():
    """Return inbox status."""
    inbox = _input_dir
    from skill_pipeline.knowledge.doc_parser import SUPPORTED_EXTENSIONS
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore

    pending = []
    if inbox.exists():
        pending = [f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]

    try:
        store = KnowledgeStore()
        total_chunks = store.count()
        total_docs = len(store.list_documents())
    except Exception:
        total_chunks = 0
        total_docs = 0

    return {
        "pending_files": len(pending),
        "processing": None,
        "last_indexed": None,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
    }


@router.get("/tags")
async def get_tags(prefix: str = ""):
    """List all tags with document counts."""
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
    from collections import Counter

    store = KnowledgeStore()
    all_data = store._collection.get()

    # Count tags per unique doc_id (not per chunk)
    tag_docs: dict[str, set] = {}
    if all_data and all_data.get("metadatas"):
        for meta in all_data["metadatas"]:
            doc_id = meta.get("doc_id", "")
            for t in meta.get("tags", "").split(","):
                t = t.strip()
                if t and (not prefix or t.startswith(prefix)):
                    if t not in tag_docs:
                        tag_docs[t] = set()
                    tag_docs[t].add(doc_id)

    return [{"tag": t, "document_count": len(docs)} for t, docs in sorted(tag_docs.items(), key=lambda x: -len(x[1]))]


@router.get("/tags/{tag_name}")
async def get_tag_documents(tag_name: str):
    """Get documents with a specific tag."""
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore

    store = KnowledgeStore()
    results = store._collection.get(where={"tags": {"$contains": tag_name}})

    docs = {}
    if results and results.get("metadatas"):
        for meta in results["metadatas"]:
            doc_id = meta.get("doc_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "path": doc_id,
                    "title": meta.get("title", ""),
                    "source_type": meta.get("source_type", ""),
                }

    return {"tag": tag_name, "documents": list(docs.values())}


@router.get("/proposals")
async def get_proposals():
    """List pending skill proposals."""
    from skill_pipeline.proposals.evaluator import list_pending_proposals
    proposals = list_pending_proposals(_vault_root)
    return [{
        "id": p.name,
        "name": p.name,
        "proposal_type": p.proposal_type,
        "summary": p.summary,
        "source_path": p.source_path,
        "confidence": p.confidence,
        "status": "pending",
        "created": "",
    } for p in proposals]


@router.post("/proposals/{proposal_id}/review")
async def review_proposal(proposal_id: str, body: dict = Body(...)):
    """Accept or reject a proposal."""
    import yaml
    from skill_pipeline.proposals.tracker import record_decision

    accepted = body.get("accepted", False)
    path = _vault_root / "proposals" / f"{proposal_id}.md"

    if not path.exists():
        return {"message": f"Proposal not found: {proposal_id}"}

    text = path.read_text(encoding="utf-8")
    new_status = "accepted" if accepted else "rejected"
    result = {"message": f"Proposal '{proposal_id}' {new_status}"}

    if accepted and text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body_text = parts[2].strip()
            skill_fm = {
                "name": proposal_id,
                "description": fm.get("summary", body_text[:200]),
                "proposal_type": fm.get("proposal_type", "reference"),
                "proposed_from": fm.get("proposed_from", ""),
            }
            fm_str = yaml.dump(skill_fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
            result["skill_content"] = f"---\n{fm_str}\n---\n\n{body_text}\n"

    record_decision(proposal_id, accepted)

    # Delete the local proposal file
    path.unlink()

    return result


@router.get("/search")
async def search(q: str, n: int = 10):
    """Search knowledge graph."""
    from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
    from skill_pipeline.core.embedder import get_strategy

    store = KnowledgeStore()
    strategy = get_strategy()

    embedding = strategy.embed([q])[0]
    results = store.query(embedding, n_results=n)

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


@router.post("/reindex")
async def reindex(body: dict = Body(...)):
    """Trigger re-indexing of a specific file."""
    file_path = body.get("path", "")
    if not file_path:
        return {"message": "No path provided"}

    full_path = _vault_root / file_path
    if not full_path.exists():
        return {"message": f"File not found: {file_path}"}

    try:
        from skill_pipeline.knowledge.doc_parser import parse_document
        from skill_pipeline.knowledge.chunker import chunk_document
        from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
        from skill_pipeline.core.embedder import get_strategy

        store = KnowledgeStore()
        strategy = get_strategy()

        # Delete existing
        store.delete_document(file_path)

        # Re-index
        doc = parse_document(full_path)
        chunks = chunk_document(doc.text)
        if not chunks:
            return {"message": f"No content in {file_path}"}

        chunk_texts = [c.text for c in chunks]
        embeddings = strategy.embed(chunk_texts)
        metadatas = [{
            "doc_id": file_path,
            "source_type": doc.source_type,
            "title": doc.title,
            "chunk_index": c.index,
            "tags": "",
        } for c in chunks]
        store.add_chunks(file_path, chunk_texts, embeddings, metadatas)

        return {"message": f"Re-indexed {file_path} ({len(chunks)} chunks)"}
    except Exception as e:
        return {"message": f"Re-index failed: {e}"}
