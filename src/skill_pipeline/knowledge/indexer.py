"""Shared index_file() used by cli.py index, reindex, and knowledge/watcher.py."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    doc_id: str
    chunks: int
    tags: list[str]
    method: str
    proposal_name: str | None = None
    proposal_path: Path | None = None


async def index_file(
    file_path: Path,
    store,
    strategy,
    *,
    vault_root: Path = Path("."),
    output_dir: Path | None = None,
    delete_first: bool = False,
    evaluate_proposals: bool = True,
) -> IndexResult | None:
    """Parse → chunk → embed → store → tag → (optional) proposal pipeline for one file.

    Returns an IndexResult on success, or None if the file had no content.
    """
    from skill_pipeline.knowledge.doc_parser import parse_document
    from skill_pipeline.knowledge.chunker import chunk_document
    from skill_pipeline.knowledge.tagger import tag_document, write_frontmatter_tags

    doc = parse_document(file_path)
    chunks = chunk_document(doc.text)
    if not chunks:
        return None

    doc_id = str(file_path.relative_to(vault_root)) if vault_root != Path(".") else str(file_path)

    if delete_first:
        store.delete_document(doc_id)

    chunk_texts = [c.text for c in chunks]
    embeddings = strategy.embed(chunk_texts)

    metadatas = [
        {
            "doc_id": doc_id,
            "source_type": doc.source_type,
            "title": doc.title,
            "chunk_index": c.index,
            "tags": "",
        }
        for c in chunks
    ]

    store.add_chunks(doc_id, chunk_texts, embeddings, metadatas)

    # Tag
    mean_embedding = np.mean(np.array(embeddings), axis=0).tolist()
    tag_result = await tag_document(mean_embedding, doc.text, store)
    write_frontmatter_tags(file_path, tag_result.tags, doc.source_type, len(chunks))
    store.update_tags(doc_id, tag_result.tags)

    # Proposal
    proposal_name: str | None = None
    proposal_path: Path | None = None
    if evaluate_proposals and output_dir is not None:
        from skill_pipeline.proposals.evaluator import evaluate_for_proposal, write_proposal
        proposal = await evaluate_for_proposal(doc.text, file_path, tag_result.tags)
        if proposal:
            proposal_path = write_proposal(proposal, output_dir)
            proposal_name = proposal.name

    return IndexResult(
        doc_id=doc_id,
        chunks=len(chunks),
        tags=tag_result.tags,
        method=tag_result.method,
        proposal_name=proposal_name,
        proposal_path=proposal_path,
    )
