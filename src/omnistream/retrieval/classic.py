"""Classic Chroma retrieval and indexing (spec 1.3, 6/C5 and 7)."""

from __future__ import annotations

import copy
import hashlib
import threading
import warnings
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import chromadb
from chromadb.errors import InternalError, NotFoundError

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Chunk, RetrievalResult, TimeScope, _utc

_CLIENT_LOCK = threading.RLock()


def make_chroma_client(path, *, hnsw_cache_size: int = 4096, settings=None):
    """Persistent client with a roomy reader cache before Rust bindings start.

    Chroma 1.5.x exposes the cache on the API instance, not Settings. Guard
    that private capability for other releases and warn if unavailable. A
    pre-existing system for this path is reused (its cache cannot be resized).
    No Chroma classes or caller-owned settings are mutated.
    The private APIs used here are verified for chromadb 1.5.x, so the project
    pins chromadb>=1.5,<1.6 for that reason.
    """
    from chromadb.api import ServerAPI
    from chromadb.api.shared_system_client import SharedSystemClient
    from chromadb.config import Settings, System

    if (
        isinstance(hnsw_cache_size, bool)
        or not isinstance(hnsw_cache_size, int)
        or hnsw_cache_size < 1
    ):
        raise ValueError("hnsw_cache_size must be a positive integer")
    configured = copy.deepcopy(settings or Settings())
    configured.is_persistent = True
    configured.persist_directory = str(path)
    with _CLIENT_LOCK:
        identifier = SharedSystemClient._get_identifier_from_settings(configured)
        existing = SharedSystemClient._identifier_to_system.get(identifier)
        if existing is not None:
            api = existing.instance(ServerAPI)
            if getattr(api, "hnsw_cache_size", None) != hnsw_cache_size:
                warnings.warn(
                    "Existing Chroma client cache cannot be resized; close it first",
                    RuntimeWarning,
                )
            return chromadb.PersistentClient(str(path), settings=configured)
        system = System(configured)
        api = system.instance(ServerAPI)
        if hasattr(api, "hnsw_cache_size"):
            api.hnsw_cache_size = hnsw_cache_size
        else:
            warnings.warn(
                f"Chroma {chromadb.__version__} has no hnsw_cache_size override; using its default",
                RuntimeWarning,
            )
        system.start()
        SharedSystemClient._populate_data_from_system(system)
        try:
            return chromadb.PersistentClient(str(path), settings=configured)
        except Exception:
            if SharedSystemClient._identifier_to_system.get(identifier) is system:
                SharedSystemClient._identifier_to_system.pop(identifier, None)
                system.stop()
            raise


def collection_name(bubble: str) -> str:
    """Stable collision-resistant Chroma name, including for Unicode bubble ids."""
    if not isinstance(bubble, str) or not bubble.strip():
        raise ValueError("bubble must be a non-empty string")
    return "bubble-" + hashlib.sha256(bubble.encode()).hexdigest()


def add_chunks(
    client: Any, embedder: EmbeddingService, bubble: str, chunks: Sequence[Chunk]
) -> None:
    """Upsert originals using local embeddings only (spec C4/C5)."""
    name = collection_name(bubble)
    if any(c.bubble != bubble or not c.item_id or not c.id for c in chunks):
        raise ValueError(
            "chunks must have ids, item provenance and the selected bubble"
        )
    if not chunks:
        return
    collection = client.get_or_create_collection(
        name,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )
    if (collection.metadata or {}).get("hnsw:space") != "cosine":
        raise ValueError("collection must use cosine space")
    metadata = []
    for chunk in chunks:
        entry = {"item_id": chunk.item_id, "bubble": bubble}
        if chunk.source_url is not None:
            entry["source_url"] = chunk.source_url
        if chunk.published_at is not None:
            entry["published_at"] = chunk.published_at.isoformat()
        metadata.append(entry)
    collection.upsert(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embedder.embed_documents([c.text for c in chunks]).tolist(),
        metadatas=metadata,
    )


class ClassicRetriever:
    """Global top 10 cosine chunks; ties sort by bubble then chunk id (C5).

    Request all candidates per collection so time filtering and boundary ties
    cannot discard eligible evidence. Appropriate for the spec's laptop scale.
    """

    mode = "classic"

    def __init__(self, client: Any, embedder: EmbeddingService) -> None:
        self.client = client
        self.embedder = embedder

    def retrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        limit = 10 if top_k is None else top_k
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(question, str):
            raise TypeError("question must be a string")
        if not question.strip() or not bubbles:
            return RetrievalResult(mode="classic")
        embedding = self.embedder.embed_query(question).tolist()
        chunks = []
        for bubble in sorted(set(bubbles)):
            try:
                collection = self.client.get_collection(
                    collection_name(bubble), embedding_function=None
                )
            except NotFoundError:
                continue
            if not collection.count():
                continue
            if (collection.metadata or {}).get("hnsw:space") != "cosine":
                raise ValueError("collection must use cosine space")
            for attempt in range(2):
                try:
                    result = collection.query(
                        query_embeddings=[embedding],
                        n_results=collection.count(),
                        include=["documents", "metadatas", "distances"],
                    )
                    break
                except InternalError as exc:
                    if "Nothing found on disk" not in str(exc):
                        raise
                    if attempt:
                        raise RuntimeError(
                            f"Chroma HNSW reader unavailable for bubble {bubble!r} after retry; "
                            "use make_chroma_client before indexing to prevent reader eviction"
                        ) from exc
                    collection = self.client.get_collection(
                        collection_name(bubble), embedding_function=None
                    )
            for ident, text, meta, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            ):
                meta = meta or {}
                if not meta.get("item_id") or meta.get("bubble", bubble) != bubble:
                    continue
                published = (
                    datetime.fromisoformat(meta["published_at"])
                    if meta.get("published_at")
                    else None
                )
                if time_scope is not None:
                    stamp = _utc(published)
                    if (
                        stamp is None
                        or (
                            time_scope.start is not None
                            and stamp < _utc(time_scope.start)
                        )
                        or (time_scope.end is not None and stamp > _utc(time_scope.end))
                    ):
                        continue
                chunks.append(
                    Chunk(
                        ident,
                        text or "",
                        meta["item_id"],
                        bubble,
                        meta.get("source_url"),
                        published,
                        1.0 - distance,
                    )
                )
        chunks.sort(key=lambda c: (-c.score, c.bubble, c.id))
        return RetrievalResult(mode="classic", chunks=tuple(chunks[:limit]))
