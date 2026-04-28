"""Evaluate documents for skill proposal generation."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from skill_pipeline.core.llm import llm_call, clean_json
from skill_pipeline.proposals.tracker import get_threshold

logger = logging.getLogger(__name__)


@dataclass
class SkillProposal:
    source_path: str
    proposal_type: str  # "behavioral" | "reference"
    name: str
    summary: str
    source_excerpts: str
    suggested_trigger: str
    confidence: float
    status: str = "pending"


EVAL_PROMPT = """\
You are evaluating whether a document should become a Claude Code skill — a reusable instruction that helps an AI coding assistant work better.

A good skill proposal is:
- A coding convention, style guide, or standard that the USER follows in THEIR projects
- A repeatable workflow the user does regularly (deploy, test, review)
- A design pattern or architectural decision specific to the user's stack

Do NOT propose skills for:
- External project documentation (CONTRIBUTING.md, README of other repos)
- Academic papers or research content
- Generic reference material (API docs, tutorials, specs)
- Letters, resumes, or non-technical documents
- Content that is informational but not actionable as a coding instruction

Document tags: {tags}

Document text (first 3000 chars):
{doc_text}

Be CONSERVATIVE. Only propose if this clearly contains reusable coding instructions.
Confidence should reflect how actionable and specific the content is as a Claude Code skill.
Most documents should NOT be proposed.

If proposable, respond with JSON:
{{
    "is_proposable": true,
    "confidence": 0.0-1.0,
    "proposal_type": "behavioral" or "reference",
    "name": "short-kebab-case-skill-name",
    "summary": "One paragraph describing what this skill would do",
    "source_excerpts": "Key excerpts (max 500 chars)",
    "suggested_trigger": "When should Claude use this skill"
}}

If NOT proposable, respond: {{"is_proposable": false}}
"""


async def evaluate_for_proposal(
    doc_text: str,
    doc_path: Path,
    tags: list[str],
) -> SkillProposal | None:
    """Evaluate a document for skill proposal generation.

    Returns a SkillProposal if confidence > progressive threshold, else None.
    """
    threshold = get_threshold()

    prompt = EVAL_PROMPT.format(
        tags=", ".join(tags) if tags else "(none)",
        doc_text=doc_text[:3000],
    )

    try:
        resp = await llm_call(prompt)
        cleaned = clean_json(resp)
        data = json.loads(cleaned)

        if not data.get("is_proposable", False):
            return None

        confidence = float(data.get("confidence", 0))
        if confidence < threshold:
            logger.info("Proposal for %s below threshold (%.2f < %.2f)", doc_path.name, confidence, threshold)
            return None

        return SkillProposal(
            source_path=str(doc_path),
            proposal_type=data.get("proposal_type", "reference"),
            name=data.get("name", doc_path.stem),
            summary=data.get("summary", ""),
            source_excerpts=data.get("source_excerpts", ""),
            suggested_trigger=data.get("suggested_trigger", ""),
            confidence=confidence,
        )
    except Exception:
        logger.warning("Proposal evaluation failed for %s", doc_path.name, exc_info=True)
        return None


def write_proposal(proposal: SkillProposal, output_dir: Path) -> Path:
    """Write proposal as markdown to proposals/."""
    proposals_dir = output_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    fm = {
        "proposed_from": proposal.source_path,
        "proposal_type": proposal.proposal_type,
        "created": str(date.today()),
        "status": "pending",
        "confidence": round(proposal.confidence, 2),
    }

    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()

    content = f"""---
{fm_str}
---

## Proposed Skill: {proposal.name}

**Type**: {proposal.proposal_type}

**Summary**: {proposal.summary}

**Source content**: {proposal.source_excerpts}

**Suggested trigger**: {proposal.suggested_trigger}
"""

    path = proposals_dir / f"{proposal.name}.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote skill proposal: %s", path)
    return path


def list_pending_proposals(output_dir: Path) -> list[SkillProposal]:
    """Read all pending proposals from proposals/."""
    proposals_dir = output_dir / "proposals"
    if not proposals_dir.exists():
        return []

    proposals = []
    for md_file in sorted(proposals_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1]) or {}
                    if fm.get("status") == "pending":
                        proposals.append(SkillProposal(
                            source_path=fm.get("proposed_from", ""),
                            proposal_type=fm.get("proposal_type", "reference"),
                            name=md_file.stem,
                            summary="",
                            source_excerpts="",
                            suggested_trigger="",
                            confidence=fm.get("confidence", 0),
                        ))
        except Exception:
            logger.warning("Failed to read proposal %s", md_file, exc_info=True)

    return proposals
