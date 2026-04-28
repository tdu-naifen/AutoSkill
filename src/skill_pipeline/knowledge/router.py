"""Route processed files from inbox to categorized vault directories."""
from __future__ import annotations

from pathlib import Path


def route_file(file_path: Path, vault_root: Path, source_type: str) -> Path:
    """Move a processed file from inbox/ to its categorized directory.

    Routing:
    - markdown, txt → vault_root/notes/
    - pdf, docx, html → vault_root/documents/

    Returns the new path.
    """
    if source_type in ("markdown", "txt"):
        dest_dir = vault_root / "notes"
    else:
        dest_dir = vault_root / "documents"

    dest_dir.mkdir(parents=True, exist_ok=True)
    return _safe_move(file_path, dest_dir)


def _safe_move(src: Path, dest_dir: Path) -> Path:
    """Move file to dest_dir, handling name collisions with numeric suffix."""
    dest = dest_dir / src.name
    if not dest.exists():
        src.rename(dest)
        return dest

    stem = src.stem
    suffix = src.suffix
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{stem}-{counter}{suffix}"
        counter += 1

    src.rename(dest)
    return dest
