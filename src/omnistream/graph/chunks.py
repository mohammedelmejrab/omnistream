"""Chunk store (spec C4): ~300-token chunks in Chroma, one collection per bubble."""

import asyncio
from datetime import datetime
from pathlib import Path

import chromadb

from omnistream.embed import Embedder
from omnistream.sources.documents import split_episodes


def collection_name(bubble_id: str) -> str:
    return f"bubble_{bubble_id}"


class ChunkStore:
    def __init__(self, data_dir: str, embedder: Embedder, chunk_tokens: int) -> None:
        self._client = chromadb.PersistentClient(path=str(Path(data_dir) / "chroma"))
        self._embedder = embedder
        self._chunk_tokens = chunk_tokens

    async def add(
        self,
        bubble_id: str,
        item_id: str,
        text: str,
        source_url: str,
        published_at: datetime | None,
    ) -> int:
        """Chunk, embed and upsert; returns the chunk count. Idempotent per item."""
        chunks = split_episodes(text, self._chunk_tokens)
        if not chunks:
            return 0
        embeddings = await self._embedder.embed(chunks)
        meta = {
            "item_id": item_id,
            "source_url": source_url,
            "published_at": published_at.isoformat() if published_at else "",
        }

        def upsert() -> None:
            col = self._client.get_or_create_collection(
                collection_name(bubble_id), metadata={"hnsw:space": "cosine"}
            )
            col.upsert(
                ids=[f"{item_id}:{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=embeddings,
                metadatas=[{**meta, "chunk": i} for i in range(len(chunks))],
            )

        await asyncio.to_thread(upsert)
        return len(chunks)

    async def count(self, bubble_id: str) -> int:
        def run() -> int:
            try:
                col = self._client.get_collection(collection_name(bubble_id))
            except Exception:  # noqa: BLE001 - chroma raises varying not-found types
                return 0
            return col.count()

        return await asyncio.to_thread(run)

    async def drop(self, bubble_id: str) -> None:
        """Delete the bubble's collection; a missing collection is fine."""

        def run() -> None:
            try:
                self._client.delete_collection(collection_name(bubble_id))
            except Exception:  # noqa: BLE001, S110 - missing collection is fine
                pass

        await asyncio.to_thread(run)
