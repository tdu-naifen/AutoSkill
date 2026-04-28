"""Two-tier document tagging: fast path (neighbor inheritance) + LLM path."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

FAST_PATH_THRESHOLD = float(os.getenv("FAST_PATH_THRESHOLD", "0.9"))
MAX_TAGS = int(os.getenv("MAX_TAGS", "20"))


@dataclass
class TagResult:
    tags: list[str]
    method: str  # "inherited" | "llm"
    confidence: float
    neighbor_tags: list[str] = field(default_factory=list)


async def tag_document(
    doc_embedding: list[float],
    doc_text: str,
    store,  # KnowledgeStore
    fast_threshold: float = FAST_PATH_THRESHOLD,
    max_tags: int = MAX_TAGS,
) -> TagResult:
    """Two-tier tagging.

    1. Query top-5 neighbors from ChromaDB
    2. If max similarity > fast_threshold → inherit shared tags
    3. Else → call LLM with doc text + neighbor tags
    """
    neighbors = store.get_neighbors(doc_embedding, n=5)

    # Collect neighbor tags
    neighbor_tags: list[str] = []
    max_similarity = 0.0
    for n in neighbors:
        meta = n.get("metadata", {})
        tags_str = meta.get("tags", "")
        if tags_str:
            neighbor_tags.extend(t.strip() for t in tags_str.split(",") if t.strip())
        # ChromaDB returns distance (lower = more similar for cosine)
        dist = n.get("distance", 1.0)
        similarity = 1.0 - dist  # convert distance to similarity
        max_similarity = max(max_similarity, similarity)

    # Deduplicate neighbor tags
    neighbor_tags = list(dict.fromkeys(neighbor_tags))

    # Fast path
    if max_similarity >= fast_threshold and neighbor_tags:
        # Inherit the most common tags from neighbors
        from collections import Counter
        tag_counts = Counter()
        for n in neighbors:
            meta = n.get("metadata", {})
            tags_str = meta.get("tags", "")
            if tags_str:
                for t in tags_str.split(","):
                    t = t.strip()
                    if t:
                        tag_counts[t] += 1
        tags = [t for t, _ in tag_counts.most_common(max_tags)]
        logger.info("Fast path: inherited %d tags (similarity=%.3f)", len(tags), max_similarity)
        return TagResult(tags=tags, method="inherited", confidence=max_similarity, neighbor_tags=neighbor_tags)

    # LLM path
    tags = await _llm_tag(doc_text, neighbor_tags, max_tags)
    logger.info("LLM path: assigned %d tags", len(tags))
    return TagResult(tags=tags, method="llm", confidence=max_similarity, neighbor_tags=neighbor_tags)


TAG_PROMPT = """\
You are a document tagger. Assign up to {max_tags} tags to this document.

Tags should be:
- Flat, lowercase, kebab-case (e.g. "react-hooks", "state-management", "api-design")
- Use domain-topic prefix format when applicable (e.g. "python-testing", "aws-lambda")
- Specific and descriptive, not generic

Existing tags from similar documents (reuse these when applicable):
{neighbor_tags}

Document text (first 3000 chars):
{doc_text}

Respond with ONLY a JSON array of tag strings. Example: ["react-hooks", "state-management", "frontend-patterns"]
"""


async def _llm_tag(doc_text: str, neighbor_tags: list[str], max_tags: int) -> list[str]:
    """Call LLM to assign tags."""
    import json
    from skill_pipeline.core.llm import llm_call, clean_json

    prompt = TAG_PROMPT.format(
        max_tags=max_tags,
        neighbor_tags=", ".join(neighbor_tags[:30]) if neighbor_tags else "(none — create new tags)",
        doc_text=doc_text[:3000],
    )

    try:
        resp = await llm_call(prompt)
        cleaned = clean_json(resp)
        tags = json.loads(cleaned)
        if isinstance(tags, list):
            return [str(t).strip().lower().replace(" ", "-") for t in tags[:max_tags] if t]
    except Exception:
        logger.warning("LLM tagging failed, returning empty tags", exc_info=True)

    return []


def write_frontmatter_tags(
    file_path: Path,
    tags: list[str],
    source_type: str,
    chunk_count: int,
) -> None:
    """Insert/update YAML frontmatter in the file with tags."""
    path = Path(file_path)
    if not path.exists() or path.suffix.lower() not in (".md", ".txt"):
        return  # Only write frontmatter to text-based files

    content = path.read_text(encoding="utf-8")

    new_fm = {
        "tags": tags,
        "indexed": str(date.today()),
        "source_type": source_type,
        "chunks": chunk_count,
    }

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                existing_fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                existing_fm = {}
            existing_fm.update(new_fm)
            fm_str = yaml.dump(existing_fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
            content = f"---\n{fm_str}\n---{parts[2]}"
        else:
            fm_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
            content = f"---\n{fm_str}\n---\n\n{content}"
    else:
        fm_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
        content = f"---\n{fm_str}\n---\n\n{content}"

    path.write_text(content, encoding="utf-8")
