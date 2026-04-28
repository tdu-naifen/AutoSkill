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


from typing import Protocol


class EmbedStrategy(Protocol):
    """Protocol for embedding strategies."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerStrategy:
    """Uses the existing sentence-transformer model."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts).tolist()


class OpenAICompatibleStrategy:
    """Calls an OpenAI-compatible /v1/embeddings endpoint (oMLX, LM Studio, Ollama, etc.)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1111",
        model: str = "text-embedding-nomic-embed-text-v1.5",
        api_key: str = "test",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self.base_url}/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            # Sort by index to ensure correct order
            data.sort(key=lambda x: x["index"])
            return [d["embedding"] for d in data]


_strategy: EmbedStrategy | None = None


def set_strategy(strategy: EmbedStrategy) -> None:
    """Set the global embedding strategy."""
    global _strategy
    _strategy = strategy


def get_strategy() -> EmbedStrategy:
    """Get the current embedding strategy, defaulting to SentenceTransformerStrategy."""
    global _strategy
    if _strategy is None:
        _strategy = SentenceTransformerStrategy()
    return _strategy
