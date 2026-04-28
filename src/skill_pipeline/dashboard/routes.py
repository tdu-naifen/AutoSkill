"""FastAPI router — serves skill graph, embeddings, and pipeline status."""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from skill_pipeline.core import store
from skill_pipeline.knowledge.chromadb_store import SkillStore

logger = logging.getLogger(__name__)

router = APIRouter()

_umap_cache: dict[str, Any] = {"hash": None, "result": []}


@router.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@router.get("/api/status")
async def get_status():
    from skill_pipeline.core.progress import get_status
    return get_status()


@router.get("/api/pipeline-status")
async def get_pipeline_status():
    """Return unified pipeline status: what's being processed, queue, recent."""
    from skill_pipeline.core.progress import get_status
    status = get_status()
    # Also include proposal count
    try:
        from skill_pipeline.proposals.evaluator import list_pending_proposals
        from .app import output_dir
        proposals = list_pending_proposals(Path(output_dir))
        status["pending_proposals"] = len(proposals)
    except Exception:
        status["pending_proposals"] = 0
    return status


@router.get("/api/skills")
async def get_skills():
    """Return parsed skills list."""
    return SkillStore().get_all_with_metadata()


@router.get("/api/pairs")
async def get_pairs():
    """Return similarity pairs."""
    path = store.get_state_dir() / "pairs.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


@router.get("/api/knowledge")
async def get_knowledge():
    """Return extracted shared knowledge."""
    path = store.get_state_dir() / "knowledge.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@router.get("/api/graph")
async def get_graph():
    """Return a D3-compatible graph: nodes (skills + knowledge) and links."""
    state = store.get_state_dir()

    skills = SkillStore().get_all_with_metadata()

    knowledge = {}
    knowledge_path = state / "knowledge.json"
    if knowledge_path.exists():
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))

    pairs = []
    pairs_path = state / "pairs.json"
    if pairs_path.exists():
        pairs = json.loads(pairs_path.read_text(encoding="utf-8"))

    # Build nodes
    nodes = []
    seen_ids: set[str] = set()
    for s in skills:
        nodes.append({
            "id": s["name"],
            "type": "skill",
            "description": s.get("description", "")[:120],
            "sub_files": s.get("sub_file_count", 0),
        })
        seen_ids.add(s["name"])
        # Template nodes
        for tpl in [t for t in s.get("templates", "").split(",") if t.strip()]:
            tpl = tpl.strip()
            tpl_id = f"t:{tpl}"
            if tpl_id not in seen_ids:
                seen_ids.add(tpl_id)
                nodes.append({
                    "id": tpl_id,
                    "type": "template",
                    "description": f"Output template from {s['name']}",
                })

    for topic, kdata in knowledge.items():
        nodes.append({
            "id": f"k:{topic}",
            "type": "knowledge",
            "description": kdata.get("description", "")[:120],
            "skills": kdata.get("skills", []),
        })

    # Build links
    links = []
    # Similarity links between skills
    for p in pairs:
        links.append({
            "source": p["skill_a"],
            "target": p["skill_b"],
            "type": "similar",
            "score": p["score"],
        })

    # Knowledge links
    for topic, kdata in knowledge.items():
        for sk_name in kdata.get("skills", []):
            links.append({
                "source": sk_name,
                "target": f"k:{topic}",
                "type": "knowledge",
            })

    # Template links
    for s in skills:
        for tpl in [t.strip() for t in s.get("templates", "").split(",") if t.strip()]:
            links.append({
                "source": s["name"],
                "target": f"t:{tpl}",
                "type": "template",
            })

    return {"nodes": nodes, "links": links}


@router.get("/api/embeddings")
async def get_embeddings():
    """Return UMAP-projected skill + knowledge embeddings for 3D scatter."""
    state = store.get_state_dir()
    knowledge_path = state / "knowledge.json"

    skill_store = SkillStore()
    names, embeddings = skill_store.get_all_embeddings()
    skills = skill_store.get_all_with_metadata()

    if len(names) < 2:
        return []

    # Embed knowledge topics and combine
    knowledge = {}
    if knowledge_path.exists():
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))

    if knowledge:
        from skill_pipeline.core import embedder
        k_texts = []
        k_names = []
        k_descs = []
        for topic, kdata in knowledge.items():
            k_names.append(topic)
            k_descs.append(kdata.get("description", "")[:120])
            text = f"search_document: {topic}: {kdata.get('description', '')}\n{kdata.get('content', '')[:4000]}"
            k_texts.append(text)
        k_embeddings = embedder.embed_texts(k_texts)
        all_embeddings = np.vstack([embeddings, k_embeddings])
    else:
        all_embeddings = embeddings
        k_names = []
        k_descs = []

    emb_hash = hashlib.md5(all_embeddings.tobytes()).hexdigest()
    if _umap_cache["hash"] == emb_hash:
        return _umap_cache["result"]

    try:
        import umap
        reducer = umap.UMAP(n_components=3, random_state=42)
        projected = reducer.fit_transform(all_embeddings)
    except ImportError:
        mean = all_embeddings.mean(axis=0)
        centered = all_embeddings - mean
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        projected = centered @ vt[:3].T

    results = []
    # Build a name->metadata lookup
    skill_meta = {s["name"]: s for s in skills}
    for i, name in enumerate(names):
        if i >= projected.shape[0]:
            break
        meta = skill_meta.get(name, {})
        results.append({
            "id": name,
            "x": float(projected[i, 0]),
            "y": float(projected[i, 1]),
            "z": float(projected[i, 2]),
            "name": name,
            "type": "skill",
            "description": meta.get("description", "")[:120],
        })

    offset = len(names)
    for i, name in enumerate(k_names):
        idx = offset + i
        if idx >= projected.shape[0]:
            break
        results.append({
            "id": f"k:{name}",
            "x": float(projected[idx, 0]),
            "y": float(projected[idx, 1]),
            "z": float(projected[idx, 2]),
            "name": name,
            "type": "knowledge",
            "description": k_descs[i],
        })

    _umap_cache["hash"] = emb_hash
    _umap_cache["result"] = results
    return results


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    from .app import ws_clients

    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)
