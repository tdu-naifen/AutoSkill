"""Shared pipeline progress state — persisted to .skill-pipeline/status.json for cross-process access."""

from __future__ import annotations

import json
import time
from pathlib import Path


def _status_path() -> Path:
    from skill_pipeline.store import get_state_dir
    return get_state_dir() / "status.json"


def _read() -> dict:
    p = _status_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"stage": "idle", "current_file": "", "files_done": 0, "files_total": 0,
            "chunks_total": 0, "message": "", "started_at": 0.0}


def _write(data: dict) -> None:
    p = _status_path()
    p.write_text(json.dumps(data), encoding="utf-8")


def get_status() -> dict:
    """Read current status (for dashboard)."""
    data = _read()
    elapsed = time.time() - data.get("started_at", 0) if data.get("started_at") else 0
    total = data.get("files_total", 0)
    done = data.get("files_done", 0)
    pct = min(100, int(done / total * 100)) if total > 0 else 0
    return {
        "stage": data.get("stage", "idle"),
        "current_file": data.get("current_file", ""),
        "files_done": done,
        "files_total": total,
        "chunks_total": data.get("chunks_total", 0),
        "pct": pct,
        "elapsed": round(elapsed, 1),
        "message": data.get("message", ""),
    }


def update(*, stage: str | None = None, current_file: str | None = None,
           files_done: int | None = None, files_total: int | None = None,
           chunks_total: int | None = None, message: str | None = None,
           started_at: float | None = None) -> None:
    """Update status fields (only non-None fields are written)."""
    data = _read()
    if stage is not None:
        data["stage"] = stage
    if current_file is not None:
        data["current_file"] = current_file
    if files_done is not None:
        data["files_done"] = files_done
    if files_total is not None:
        data["files_total"] = files_total
    if chunks_total is not None:
        data["chunks_total"] = chunks_total
    if message is not None:
        data["message"] = message
    if started_at is not None:
        data["started_at"] = started_at
    _write(data)


def reset() -> None:
    """Reset to idle."""
    _write({"stage": "idle", "current_file": "", "files_done": 0, "files_total": 0,
            "chunks_total": 0, "message": "", "started_at": 0.0})
