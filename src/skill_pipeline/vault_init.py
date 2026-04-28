"""Initialize output directory as an Obsidian vault with AutoSkill plugin."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

PLUGIN_SOURCE = Path(__file__).parent.parent.parent / "obsidian-plugin"
# = project_root/obsidian-plugin/


def init_vault(output_dir: Path) -> None:
    """Ensure output_dir has .obsidian/ with the autoskill plugin installed.

    Safe to call multiple times — only creates what's missing.
    """
    output_dir = Path(output_dir)
    obsidian_dir = output_dir / ".obsidian"
    plugin_dir = obsidian_dir / "plugins" / "autoskill"

    obsidian_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Copy plugin files if source exists
    for filename in ("main.js", "manifest.json", "styles.css"):
        src = PLUGIN_SOURCE / filename
        dest = plugin_dir / filename
        if src.exists() and not dest.exists():
            shutil.copy2(src, dest)

    # Create/update community-plugins.json
    cp_path = obsidian_dir / "community-plugins.json"
    plugins = []
    if cp_path.exists():
        try:
            plugins = json.loads(cp_path.read_text(encoding="utf-8"))
        except Exception:
            plugins = []
    if "autoskill" not in plugins:
        plugins.append("autoskill")
        cp_path.write_text(json.dumps(plugins, indent=2), encoding="utf-8")

    # Ensure standard vault dirs exist
    for subdir in ("skills", "knowledge", "templates", "knowledge-docs", "proposals"):
        (output_dir / subdir).mkdir(exist_ok=True)
