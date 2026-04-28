"""Persistence layer for skill-pipeline state (.skill-pipeline/ in cwd)."""

from __future__ import annotations

import os
from pathlib import Path

STATE_DIR = Path(os.environ.get("SKILL_PIPELINE_DIR", Path.cwd() / ".skill-pipeline"))


def get_state_dir() -> Path:
    """Return (and lazily create) the state directory."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def _atomic_write_json(path: Path, data: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.rename(tmp, path)
