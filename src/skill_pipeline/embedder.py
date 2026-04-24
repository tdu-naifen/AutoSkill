from __future__ import annotations

import os

import numpy as np

EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5")

_model = None


def get_model():
    """Lazy-load and cache the sentence-transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)
    return _model


def embed_text(text: str) -> np.ndarray:
    """Embed a single text string."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return np.asarray(embedding, dtype=np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts."""
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return np.asarray(embeddings, dtype=np.float32)
