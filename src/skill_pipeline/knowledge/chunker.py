"""Paragraph-level document splitting for indexing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    """A chunk of text with positional metadata."""

    text: str
    index: int
    char_start: int
    char_end: int


def chunk_document(
    text: str, max_chunk_chars: int = 2000, overlap_chars: int = 200
) -> list[Chunk]:
    """Split text on paragraph boundaries (double newline).

    - Merge short paragraphs until max_chunk_chars
    - If a single paragraph exceeds max_chunk_chars, split at sentence boundaries
    - Add overlap from end of previous chunk
    """
    if not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    pos = 0

    for para in paragraphs:
        if current_len + len(para) > max_chunk_chars and current_parts:
            # Flush current chunk
            chunk_text = "\n\n".join(current_parts)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=len(chunks),
                    char_start=pos - current_len,
                    char_end=pos,
                )
            )
            # Overlap: keep last part if it fits
            if overlap_chars > 0 and current_parts:
                overlap_text = current_parts[-1]
                if len(overlap_text) <= overlap_chars:
                    current_parts = [overlap_text]
                    current_len = len(overlap_text)
                else:
                    current_parts = []
                    current_len = 0
            else:
                current_parts = []
                current_len = 0

        current_parts.append(para)
        current_len += len(para)
        pos += len(para) + 2  # +2 for \n\n

    # Flush remaining
    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        chunks.append(
            Chunk(
                text=chunk_text,
                index=len(chunks),
                char_start=pos - current_len,
                char_end=pos,
            )
        )

    return chunks
