"""Write Skills + Knowledge output structure.

output/
  skills/
    azure-cost/SKILL.md         → original skill, with knowledge refs added
    azure-diagnostics/SKILL.md
  knowledge/
    cost-patterns/KNOWLEDGE.md  → shared knowledge extracted from similar skills
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from skill_pipeline.parser import ParsedSkill


def write_output(
    skills: list[ParsedSkill],
    knowledge: dict[str, dict],
    output_dir: Path,
) -> None:
    """Write complete output."""
    output_dir = Path(output_dir)
    skills_dir = output_dir / "skills"
    knowledge_dir = output_dir / "knowledge"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    skills_dir.mkdir(parents=True, exist_ok=True)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    # Build reverse map: skill_name -> [knowledge_topics]
    skill_knowledge: dict[str, list[str]] = {}
    for topic, kdata in knowledge.items():
        for sk_name in kdata.get("skills", []):
            if sk_name not in skill_knowledge:
                skill_knowledge[sk_name] = []
            skill_knowledge[sk_name].append(topic)

    # Write skills
    for skill in skills:
        sk_dir = skills_dir / skill.name
        sk_dir.mkdir(parents=True, exist_ok=True)

        # Build frontmatter
        fm: dict = {
            "name": skill.name,
            "description": skill.description,
        }

        # Preserve original metadata fields
        for key in ("aliases", "context", "model", "allowed-tools", "hooks"):
            if key in skill.metadata:
                fm[key] = skill.metadata[key]

        # Add knowledge references
        k_refs = skill_knowledge.get(skill.name, [])
        if k_refs:
            fm["knowledge"] = [f"knowledge/{t}" for t in k_refs]

        # Add template references
        if skill.templates:
            fm["templates"] = [f"templates/{t}" for t in skill.templates]

        # Preserve original skill dependencies
        if "skills" in skill.metadata:
            fm["skills"] = skill.metadata["skills"]

        frontmatter = "---\n" + yaml.dump(
            fm, default_flow_style=False, sort_keys=False, allow_unicode=True
        ).rstrip() + "\n---"

        # Write SKILL.md with original content
        content = f"{frontmatter}\n\n{skill.content}\n"
        (sk_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # Write sub-files in their original relative paths
        for rel_path, sub_content in skill.sub_files.items():
            sub_file = sk_dir / rel_path
            sub_file.parent.mkdir(parents=True, exist_ok=True)
            sub_file.write_text(sub_content, encoding="utf-8")

    # Write knowledge
    for topic, kdata in sorted(knowledge.items()):
        k_dir = knowledge_dir / topic
        k_dir.mkdir(parents=True, exist_ok=True)

        fm = {
            "name": topic,
            "description": kdata.get("description", ""),
            "type": "knowledge",
            "referenced_by": kdata.get("skills", []),
        }

        frontmatter = "---\n" + yaml.dump(
            fm, default_flow_style=False, sort_keys=False, allow_unicode=True
        ).rstrip() + "\n---"

        body = kdata.get("content", "")
        heading = topic.replace("-", " ").title()
        content = f"{frontmatter}\n\n# {heading}\n\n{body}\n"
        (k_dir / "KNOWLEDGE.md").write_text(content, encoding="utf-8")

    # Write templates
    templates_dir = output_dir / "templates"
    all_templates: dict[str, tuple[str, list[str]]] = {}  # name -> (content, [skill_names])
    for skill in skills:
        for tpl_name, tpl_content in skill.templates.items():
            if tpl_name in all_templates:
                all_templates[tpl_name][1].append(skill.name)
            else:
                all_templates[tpl_name] = (tpl_content, [skill.name])

    for tpl_name, (tpl_content, tpl_skills) in sorted(all_templates.items()):
        t_dir = templates_dir / tpl_name
        t_dir.mkdir(parents=True, exist_ok=True)

        fm = {
            "name": tpl_name,
            "type": "template",
            "referenced_by": tpl_skills,
        }

        frontmatter = "---\n" + yaml.dump(
            fm, default_flow_style=False, sort_keys=False, allow_unicode=True
        ).rstrip() + "\n---"

        heading = tpl_name.replace("-", " ").title()
        content = f"{frontmatter}\n\n# {heading}\n\n{tpl_content}\n"
        (t_dir / "TEMPLATE.md").write_text(content, encoding="utf-8")
