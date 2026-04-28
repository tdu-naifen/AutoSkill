"""Skill dedup pipeline: parse → embed → find cross-skill similarity → extract shared knowledge.

Uses ChromaDB 'skills' collection for embedding storage (unified with knowledge graph)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

from skill_pipeline.core import embedder, progress
from skill_pipeline.core.store import get_state_dir, _atomic_write_json
from skill_pipeline.knowledge.chromadb_store import SkillStore
from skill_pipeline.skills.parser import ParsedSkill, scan_input

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))


def find_similar_pairs(
    skills: list[ParsedSkill],
    embeddings: np.ndarray,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[tuple[int, int, float]]:
    """Find all pairs of skills with cosine similarity above threshold."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normed = embeddings / norms
    sim_matrix = normed @ normed.T

    pairs = []
    n = len(skills)
    for i in range(n):
        for j in range(i + 1, n):
            score = float(sim_matrix[i, j])
            if score >= threshold:
                pairs.append((i, j, score))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


async def run_pipeline(
    input_dir: str | Path,
    output_dir: str | Path,
) -> dict:
    """Full pipeline with incremental support using ChromaDB for skill embeddings."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    progress.update(stage="parsing", started_at=time.time(), message="Scanning for skills...")

    # Phase 1: Parse
    skills = scan_input(input_dir)
    if not skills:
        progress.update(stage="error", message="No skills found")
        return {"error": "No skills found"}

    state_dir = get_state_dir()
    skill_store = SkillStore()

    # Load existing state from ChromaDB + JSON files
    existing_names = skill_store.list_skill_names()

    pairs_path = state_dir / "pairs.json"
    knowledge_path = state_dir / "knowledge.json"
    existing_pairs_data: list[dict] = []
    existing_knowledge: dict[str, dict] = {}

    if pairs_path.exists():
        existing_pairs_data = json.loads(pairs_path.read_text(encoding="utf-8"))
    if knowledge_path.exists():
        existing_knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))

    all_names = {s.name for s in skills}
    new_names = all_names - existing_names
    removed_names = existing_names - all_names

    if not new_names and not removed_names:
        progress.update(stage="done", message="No new or removed skills. Nothing to do.")
        return {"skills": len(skills), "knowledge_topics": len(existing_knowledge), "similar_pairs": len(existing_pairs_data)}

    logger.info("Incremental: %d new, %d removed, %d existing", len(new_names), len(removed_names), len(existing_names) - len(removed_names))

    # Delete removed skills from ChromaDB
    if removed_names:
        skill_store.delete_skills(list(removed_names))

    # Phase 2: Embed only new skills → upsert into ChromaDB
    new_skills = [s for s in skills if s.name in new_names]
    if new_skills:
        progress.update(
            stage="embedding",
            files_total=len(new_skills),
            files_done=0,
            message=f"Embedding {len(new_skills)} new skills (skipping {len(existing_names) - len(removed_names)} existing)...",
        )
        for idx, s in enumerate(new_skills):
            text = f"search_document: {s.name}: {s.description}\n{s.content[:8000]}"
            vec = embedder.embed_text(text)
            skill_store.upsert_skill(
                name=s.name,
                embedding=vec.tolist(),
                text=f"{s.name}: {s.description}\n{s.content[:500]}",
                metadata={
                    "description": s.description,
                    "source_dir": s.source_dir,
                    "sub_file_count": len(s.sub_files),
                    "content_length": len(s.content),
                    "templates": ",".join(s.templates.keys()),
                },
            )
            progress.update(files_done=idx + 1)

    # Fetch all embeddings from ChromaDB for similarity computation
    all_skill_names, embeddings = skill_store.get_all_embeddings()
    skill_by_name = {s.name: s for s in skills}
    ordered_skills = [skill_by_name[n] for n in all_skill_names if n in skill_by_name]
    skills = ordered_skills

    # Phase 3: Cross-skill similarity
    progress.update(stage="analyzing", message="Finding cross-skill similarities...")
    pairs = find_similar_pairs(skills, embeddings)
    logger.info("Found %d similar pairs above threshold %.2f", len(pairs), SIMILARITY_THRESHOLD)

    # Determine which pairs need LLM extraction
    existing_pair_set = {(p["skill_a"], p["skill_b"]) for p in existing_pairs_data}
    new_pairs = []
    old_pairs = []
    for i, j, score in pairs:
        a, b = skills[i].name, skills[j].name
        if (a, b) in existing_pair_set or (b, a) in existing_pair_set:
            old_pairs.append((i, j, score))
        else:
            new_pairs.append((i, j, score))

    logger.info("Incremental: %d new pairs to extract, %d already processed", len(new_pairs), len(old_pairs))

    # Phase 4: LLM extraction only for new pairs
    shared_knowledge: list[dict] = []
    if new_pairs:
        progress.update(
            stage="extracting",
            files_total=len(new_pairs),
            files_done=0,
            message=f"LLM extracting shared knowledge from {len(new_pairs)} new pairs (skipping {len(old_pairs)} existing)...",
        )
        from skill_pipeline.core.llm import llm_call, clean_json

        EXTRACT_PROMPT = """\
Two AI agent skills have overlapping content. Identify what knowledge they share.

SKILL A: {name_a}
Description: {desc_a}
Content sample:
{content_a}

SKILL B: {name_b}
Description: {desc_b}
Content sample:
{content_b}

If they share common knowledge (patterns, concepts, best practices), extract it.
If they are just loosely related but don't share actual reusable knowledge, say "none".

Respond with JSON only:
{{"shared_topic": "short-kebab-case-name or none", "shared_description": "what the shared knowledge covers", "shared_content": "the actual shared knowledge text, rewritten as a standalone reference"}}
"""
        for idx, (i, j, score) in enumerate(new_pairs):
            progress.update(files_done=idx, current_file=f"{skills[i].name} ↔ {skills[j].name}")

            prompt = EXTRACT_PROMPT.format(
                name_a=skills[i].name, desc_a=skills[i].description,
                content_a=skills[i].content[:1500],
                name_b=skills[j].name, desc_b=skills[j].description,
                content_b=skills[j].content[:1500],
            )

            try:
                content = await llm_call(prompt)
                cleaned = clean_json(content)
                data = json.loads(cleaned)

                topic = data.get("shared_topic", "none")
                if topic and topic != "none":
                    shared_knowledge.append({
                        "topic": topic,
                        "description": data.get("shared_description", ""),
                        "content": data.get("shared_content", ""),
                        "skills": [skills[i].name, skills[j].name],
                        "score": score,
                    })
                    logger.info("Found shared knowledge: %s (%s ↔ %s, score=%.3f)",
                               topic, skills[i].name, skills[j].name, score)
            except Exception:
                logger.warning("LLM extraction failed for %s ↔ %s", skills[i].name, skills[j].name, exc_info=True)

        progress.update(files_done=len(new_pairs))

    # Merge new knowledge into existing, remove knowledge referencing removed skills
    merged_knowledge = dict(existing_knowledge)
    for topic in list(merged_knowledge.keys()):
        kskills = merged_knowledge[topic].get("skills", [])
        merged_knowledge[topic]["skills"] = [s for s in kskills if s not in removed_names]
        if not merged_knowledge[topic]["skills"]:
            del merged_knowledge[topic]

    for sk in shared_knowledge:
        topic = sk["topic"]
        if topic in merged_knowledge:
            for s in sk["skills"]:
                if s not in merged_knowledge[topic]["skills"]:
                    merged_knowledge[topic]["skills"].append(s)
            if len(sk["content"]) > len(merged_knowledge[topic].get("content", "")):
                merged_knowledge[topic]["content"] = sk["content"]
        else:
            merged_knowledge[topic] = sk

    # Phase 5: Write output files
    progress.update(stage="writing", message="Writing skills and knowledge files...")
    from skill_pipeline.skills.writer import write_output
    write_output(skills, merged_knowledge, output_dir)

    # Save pairs + knowledge JSON (LLM-derived, not in ChromaDB)
    pairs_data = [
        {"skill_a": skills[i].name, "skill_b": skills[j].name, "score": round(score, 4)}
        for i, j, score in pairs
    ]
    _atomic_write_json(pairs_path, json.dumps(pairs_data, indent=2))
    _atomic_write_json(knowledge_path, json.dumps(merged_knowledge, indent=2))

    progress.update(
        stage="done",
        message=f"{len(skills)} skills, {len(merged_knowledge)} shared knowledge topics ({len(new_names)} new, {len(old_pairs)} cached)",
    )

    return {
        "skills": len(skills),
        "knowledge_topics": len(merged_knowledge),
        "similar_pairs": len(pairs),
        "new_skills": len(new_names),
        "cached_pairs": len(old_pairs),
    }
