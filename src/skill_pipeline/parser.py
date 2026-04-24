"""Parse input skill directories — respect existing SKILL.md boundaries.

Scans for SKILL.md files to identify skill boundaries. Each directory containing
a SKILL.md is one skill. Sub-files are content within that skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ParsedSkill:
    """A single skill parsed from input."""
    name: str
    description: str
    source_dir: str
    skill_md_path: str
    # Frontmatter fields
    metadata: dict = field(default_factory=dict)
    # All content: SKILL.md body + sub-files
    content: str = ""
    # Sub-file contents keyed by relative path
    sub_files: dict[str, str] = field(default_factory=dict)
    # Templates detected from sub-files: {name: content}
    templates: dict[str, str] = field(default_factory=dict)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                return fm, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, text


def _is_template(file_path: Path, content: str) -> bool:
    """Check if a file is an output template — a file that instructs the agent to create output.

    Detects based on filename containing 'template' AND content having output indicators,
    or content that clearly instructs file creation using a template pattern.
    """
    content_lower = content.lower()
    has_template_name = "template" in file_path.stem.lower()

    # Check first heading for "template"
    has_template_heading = False
    for line in content.split("\n")[:10]:
        line = line.strip()
        if line.startswith("#") and "template" in line.lower():
            has_template_heading = True
            break

    if not has_template_name and not has_template_heading:
        return False

    # Must have output indicators — signs this is an output template
    output_indicators = (
        "create_file" in content_lower
        or "using this template" in content_lower
        or "use this template" in content_lower
        or "as a template" in content_lower
        or bool(re.search(r"(create|write|generate).*\.(md|json|yaml|yml)", content_lower))
        or bool(re.search(r"path.*output/", content_lower))
        or bool(re.search(r"\[.*\].*:.*\[.*\]", content[:500]))  # placeholder pattern like [name]: [value]
    )
    return output_indicators


def _template_name(file_path: Path, skill_name: str) -> str:
    """Derive a clean template name from the file path."""
    stem = file_path.stem.lower().replace("_", "-")
    # If stem already descriptive, use it; otherwise prefix with skill name
    if skill_name.lower() in stem:
        return stem
    return f"{skill_name}-{stem}"


def parse_skill_dir(skill_dir: Path) -> ParsedSkill:
    """Parse a single skill directory (one that contains SKILL.md)."""
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)

    name = fm.get("name", skill_dir.name)
    description = fm.get("description", "")

    # Collect sub-files (everything except SKILL.md)
    sub_files: dict[str, str] = {}
    templates: dict[str, str] = {}
    skip_names = {"SKILL.md"}

    for md_file in sorted(skill_dir.rglob("*.md")):
        if md_file.name in skip_names:
            # Include nested SKILL.md bodies (e.g. sub-skills)
            if md_file != skill_md:
                rel = str(md_file.relative_to(skill_dir))
                sub_fm, sub_body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
                sub_files[rel] = sub_body
            continue
        rel = str(md_file.relative_to(skill_dir))
        try:
            sub_text = md_file.read_text(encoding="utf-8")
            _, sub_body = _parse_frontmatter(sub_text)
            sub_files[rel] = sub_body
            # Detect templates
            if _is_template(md_file, sub_text):
                tpl_name = _template_name(md_file, name)
                templates[tpl_name] = sub_body
        except Exception:
            pass

    # Build full content: SKILL.md body + all sub-files
    all_content = [body]
    for rel_path, content in sorted(sub_files.items()):
        all_content.append(content)
    full_content = "\n\n".join(all_content)

    return ParsedSkill(
        name=name,
        description=description,
        source_dir=str(skill_dir),
        skill_md_path=str(skill_md),
        metadata=fm,
        content=full_content,
        sub_files=sub_files,
        templates=templates,
    )


def scan_input(input_dir: Path) -> list[ParsedSkill]:
    """Scan an input directory for all skills (directories containing SKILL.md).

    Handles nested structures like:
      skills/azure-kubernetes/SKILL.md
      skills/azure-kubernetes/azure-kubernetes-automatic-readiness/SKILL.md
    """
    input_dir = Path(input_dir)
    skill_dirs: list[Path] = []

    for skill_md in sorted(input_dir.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        # Skip if this skill_dir is a child of another skill_dir we already found
        # (nested skills are parsed as sub-files of their parent)
        is_nested = False
        for existing in skill_dirs:
            if skill_dir != existing and str(skill_dir).startswith(str(existing) + "/"):
                is_nested = True
                break
        if not is_nested:
            skill_dirs.append(skill_dir)

    skills = []
    seen_names: set[str] = set()

    for skill_dir in skill_dirs:
        try:
            skill = parse_skill_dir(skill_dir)
            # Deduplicate by name (e.g. .github/plugins/ vs skills/)
            if skill.name in seen_names:
                continue
            seen_names.add(skill.name)
            skills.append(skill)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to parse %s: %s", skill_dir, e)

    return skills
