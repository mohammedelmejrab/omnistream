"""Hybrid retrieval: dense vector search + BM25 keyword search fused with RRF.

This is a helper beyond the spec's pure-vector ``classic`` mode (which queries
Chroma); it exists because the milestone asked for sparse+dense fusion.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from omnistream.config import Settings, get_settings
from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.fusion import ranks_from_scores, reciprocal_rank_fusion
from omnistream.retrieval.sparse import BM25Index


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    score: float
    dense_rank: int | None
    sparse_rank: int | None


class HybridRetriever:
    """Thread-safe in-memory hybrid index over text chunks.

    ``min_dense_similarity`` is inclusive (``>=``). When ``None`` (default),
    dense hits must have strictly positive similarity, so chunks sharing no
    signal with the query are not returned.
    """

    def __init__(
        self,
        embedder: EmbeddingService,
        *,
        settings: Settings | None = None,
        rrf_k: int | None = None,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
        min_dense_similarity: float | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.embedder = embedder
        self.rrf_k = settings.rrf_k if rrf_k is None else rrf_k
        self.weights = {"dense": dense_weight, "sparse": sparse_weight}
        self.min_dense_similarity = min_dense_similarity
        self._lock = threading.RLock()
        self._ids: list[str] = []
        self._row: dict[str, int] = {}
        self._texts: dict[str, str] = {}
        self._matrix = np.zeros((0, embedder.dimension), dtype=np.float32)
        self._bm25 = BM25Index()

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)

    def add(self, chunks: Mapping[str, str]) -> None:
        """Insert or replace chunks atomically: on any error nothing changes."""
        chunks = dict(chunks)
        for cid, text in chunks.items():
            if not isinstance(text, str):
                raise TypeError(f"chunk {cid!r} must be str, got {type(text).__name__}")
        if not chunks:
            return
        # Encode outside the lock (slow), then commit everything under it.
        vectors = self.embedder.embed_documents(list(chunks.values()))
        with self._lock:
            # Re-check membership under the lock so concurrent adds of the
            # same id never create duplicate rows.
            matrix = self._matrix.copy()
            ids = list(self._ids)
            row = dict(self._row)
            extra: list[np.ndarray] = []
            for cid, vec in zip(chunks, vectors, strict=True):
                if cid in row:
                    matrix[row[cid]] = vec
                else:
                    row[cid] = len(ids)
                    ids.append(cid)
                    extra.append(vec)
            if extra:
                matrix = np.vstack([matrix, np.asarray(extra, dtype=np.float32)])
            self._bm25.add(chunks)  # inputs already validated; cannot fail midway
            self._matrix, self._ids, self._row = matrix, ids, row
            self._texts.update(chunks)

    def dense_search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        with self._lock:
            ids, matrix = self._ids, self._matrix
        if not ids:
            return []  # don't load the model / call the encoder for an empty index
        q = self.embedder.embed_query(query)
        sims = self.embedder.cosine_similarity(q, matrix)
        if self.min_dense_similarity is None:
            keep = sims > 0
        else:
            keep = sims >= self.min_dense_similarity
        order = sorted(np.flatnonzero(keep), key=lambda i: (-float(sims[i]), int(i)))
        return [(ids[i], float(sims[i])) for i in order[:top_k]]

    def sparse_search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        with self._lock:
            return self._bm25.search(query, top_k)

    def search(
        self, query: str, top_k: int = 10, candidates: int = 50
    ) -> list[RetrievedChunk]:
        dense = self.dense_search(query, candidates)
        sparse = self.sparse_search(query, candidates)
        fused = reciprocal_rank_fusion(
            {"dense": ranks_from_scores(dense), "sparse": ranks_from_scores(sparse)},
            k=self.rrf_k,
            weights=self.weights,
            top_n=top_k,
        )
        with self._lock:
            texts = dict(self._texts)
        return [
            RetrievedChunk(
                id=r.id,
                text=texts[r.id],
                score=r.score,
                dense_rank=r.ranks.get("dense"),
                sparse_rank=r.ranks.get("sparse"),
            )
            for r in fused
        ]
