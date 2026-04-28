"""ChromaDB-backed vector store for the knowledge graph and skill pipeline."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from skill_pipeline.core.store import get_state_dir

CHROMA_DIR = get_state_dir() / "chromadb"

_client = None


def get_chroma_client(persist_dir: Path = CHROMA_DIR):
    """Singleton ChromaDB PersistentClient."""
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(persist_dir))
    return _client


class KnowledgeStore:
    """Persistent vector store wrapping a ChromaDB collection."""

    def __init__(
        self,
        persist_dir: Path = CHROMA_DIR,
        collection_name: str = "knowledge",
    ):
        self._client = get_chroma_client(persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        doc_id: str,
        chunks: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        """Upsert document chunks with their embeddings and metadata."""
        ids = [f"{doc_id}::chunk_{i}" for i in range(len(chunks))]
        self._collection.upsert(
            ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas
        )

    def query(
        self,
        embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
    ) -> dict:
        """Query the collection by embedding vector."""
        kwargs: dict = {"query_embeddings": [embedding], "n_results": n_results}
        if where:
            kwargs["where"] = where
        return self._collection.query(**kwargs)

    def get_neighbors(self, embedding: list[float], n: int = 5) -> list[dict]:
        """Return the nearest neighbor chunks as a list of dicts."""
        results = self.query(embedding, n_results=n)
        neighbors = []
        if results and results.get("metadatas"):
            for i, meta in enumerate(results["metadatas"][0]):
                neighbors.append(
                    {
                        "metadata": meta,
                        "document": (
                            results["documents"][0][i] if results.get("documents") else ""
                        ),
                        "distance": (
                            results["distances"][0][i] if results.get("distances") else 0
                        ),
                    }
                )
        return neighbors

    def get_document_chunks(self, doc_id: str) -> dict:
        """Retrieve all chunks belonging to a specific document."""
        return self._collection.get(where={"doc_id": doc_id})

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks for a document."""
        existing = self._collection.get(where={"doc_id": doc_id})
        if existing and existing.get("ids"):
            self._collection.delete(ids=existing["ids"])

    def list_documents(self) -> list[str]:
        """Return sorted list of unique document IDs in the store."""
        results = self._collection.get(include=["metadatas"])
        doc_ids: set[str] = set()
        if results and results.get("metadatas"):
            for meta in results["metadatas"]:
                if "doc_id" in meta:
                    doc_ids.add(meta["doc_id"])
        return sorted(doc_ids)

    def update_tags(self, doc_id: str, tags: list[str]) -> None:
        """Update tags metadata on all chunks of a document."""
        existing = self._collection.get(where={"doc_id": doc_id})
        if existing and existing.get("ids"):
            tags_str = ", ".join(tags)
            self._collection.update(
                ids=existing["ids"],
                metadatas=[{**m, "tags": tags_str} for m in existing["metadatas"]],
            )

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        return self._collection.count()


class SkillStore:
    """One-doc-per-skill ChromaDB collection for the skill dedup pipeline."""

    def __init__(self, persist_dir: Path = CHROMA_DIR):
        client = get_chroma_client(persist_dir)
        self._collection = client.get_or_create_collection(
            name="skills",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_skill(self, name: str, embedding: list[float], text: str, metadata: dict) -> None:
        """Upsert a single skill."""
        self._collection.upsert(
            ids=[name],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )

    def delete_skills(self, names: list[str]) -> None:
        """Delete skills by name."""
        if names:
            self._collection.delete(ids=names)

    def list_skill_names(self) -> set[str]:
        """Return set of all skill names."""
        result = self._collection.get(include=[])
        return set(result["ids"]) if result["ids"] else set()

    def get_all_embeddings(self) -> tuple[list[str], np.ndarray]:
        """Return (names, embeddings_matrix) for all skills."""
        result = self._collection.get(include=["embeddings"])
        names = result["ids"]
        if not names:
            return [], np.empty((0, 768), dtype=np.float32)
        return names, np.array(result["embeddings"], dtype=np.float32)

    def get_all_with_metadata(self) -> list[dict]:
        """Return all skills as list of dicts."""
        result = self._collection.get(include=["metadatas", "documents"])
        out = []
        for i, sid in enumerate(result["ids"]):
            meta = result["metadatas"][i] if result["metadatas"] else {}
            out.append({"name": sid, **meta})
        return out

    def count(self) -> int:
        return self._collection.count()
