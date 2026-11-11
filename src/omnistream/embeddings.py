"""Local text embedding service (bge-small-en-v1.5 via sentence-transformers)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

from omnistream.config import Settings, get_settings

# BGE v1.5 models recommend this instruction prefix for short retrieval queries.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# Known embedding models and their output dimensions. Changing the model
# requires re-indexing, so stores should persist ``index_signature``.
KNOWN_MODEL_DIMS = {"BAAI/bge-small-en-v1.5": 384}


class Encoder(Protocol):
    """The subset of the ``SentenceTransformer`` interface the service relies on."""

    def encode(self, sentences: list[str], **kwargs: Any) -> Any: ...


class EmbeddingError(RuntimeError):
    """Raised when the encoder returns unusable output."""


class EmbeddingService:
    """Turns text into L2-normalised float32 vectors.

    The underlying model is loaded lazily on first use, so constructing the
    service is cheap. Tests inject a deterministic ``encoder`` instead.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        encoder: Encoder | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
        query_instruction: str | None = BGE_QUERY_INSTRUCTION,
        cache_size: int = 1024,
    ) -> None:
        settings = settings or get_settings()
        self.model_name = model_name or settings.embedding_model
        self.dimension = dimension or settings.embedding_dim
        known = KNOWN_MODEL_DIMS.get(self.model_name)
        if known is not None and known != self.dimension:
            raise ValueError(
                f"{self.model_name} produces {known}-dim vectors, not {self.dimension}"
            )
        self.batch_size = batch_size or settings.embedding_batch_size
        self.device = settings.embedding_device
        self.query_instruction = query_instruction or ""
        self._encoder = encoder
        self._lock = threading.Lock()  # model initialisation
        self._cache_lock = threading.Lock()  # every cache read/write
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_size = max(0, cache_size)

    # ------------------------------------------------------------------ model
    @property
    def encoder(self) -> Encoder:
        if self._encoder is None:
            with self._lock:
                if self._encoder is None:
                    from sentence_transformers import SentenceTransformer

                    self._encoder = SentenceTransformer(
                        self.model_name, device=self.device
                    )
        return self._encoder

    # ------------------------------------------------------------- public API
    @property
    def index_signature(self) -> str:
        """Identifies the vector space; store it with an index and compare on load."""
        return f"{self.model_name}:{self.dimension}"

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed passages. Returns an array of shape ``(len(texts), dimension)``."""
        return self._embed(list(texts), prefix="")

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single search query (with the BGE instruction prefix)."""
        return self._embed([text], prefix=self.query_instruction)[0]

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(list(texts), prefix=self.query_instruction)

    @staticmethod
    def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Cosine similarity of one vector against each row of ``matrix``.

        ``query`` must be 1-D with shape ``(d,)``; ``matrix`` ``(n, d)`` (or 1-D
        ``(d,)`` for a single row, or empty). Zero vectors have similarity 0.
        Non-finite input raises ``ValueError`` rather than being masked.
        """
        q = np.asarray(query, dtype=np.float64)
        m = np.asarray(matrix, dtype=np.float64)
        if q.ndim != 1:
            raise ValueError(f"query must be 1-D, got shape {q.shape}")
        if not np.all(np.isfinite(q)):
            raise ValueError("cosine_similarity received a non-finite query")
        if m.ndim == 1 and m.size == 0:
            m = m.reshape(0, q.shape[0])  # bare empty list: no rows
        m = np.atleast_2d(m)
        if m.ndim != 2 or m.shape[1] != q.shape[0]:
            raise ValueError(
                f"matrix shape {m.shape} incompatible with query shape {q.shape}"
            )
        if m.shape[0] == 0:
            return np.zeros(0, dtype=np.float32)
        if not np.all(np.isfinite(m)):
            raise ValueError("cosine_similarity received non-finite matrix values")
        q_unit = _unit_rows(q[None, :])[0]
        sims = _unit_rows(m) @ q_unit
        return np.clip(sims, -1.0, 1.0).astype(np.float32)

    # --------------------------------------------------------------- internal
    def _embed(self, texts: list[str], *, prefix: str) -> np.ndarray:
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise TypeError(f"texts[{i}] must be str, got {type(text).__name__}")
        out = np.zeros((len(texts), self.dimension), dtype=np.float32)
        if not texts:
            return out

        # Blank strings map to the zero vector; they carry no meaning and
        # would otherwise waste a model call.
        pending: dict[str, list[int]] = {}
        for i, text in enumerate(texts):
            if not text.strip():
                continue
            key = prefix + text
            cached = self._cache_get(key)
            if cached is not None:
                out[i] = cached
            else:
                pending.setdefault(key, []).append(i)

        if pending:
            keys = list(pending)
            vectors = self._encode(keys)
            for key, vec in zip(keys, vectors, strict=True):
                self._cache_put(key, vec)
                for i in pending[key]:
                    out[i] = vec
        return out

    def _encode(self, inputs: list[str]) -> np.ndarray:
        raw = self.encoder.encode(
            inputs,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(raw, dtype=np.float64)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape != (len(inputs), self.dimension):
            raise EmbeddingError(
                f"encoder returned shape {vectors.shape}, expected {(len(inputs), self.dimension)}"
            )
        if not np.all(np.isfinite(vectors)):
            raise EmbeddingError("encoder returned non-finite values")
        return _unit_rows(vectors).astype(np.float32)

    def _cache_get(self, key: str) -> np.ndarray | None:
        if not self._cache_size:
            return None
        with self._cache_lock:
            vec = self._cache.get(key)
            if vec is not None:
                self._cache.move_to_end(key)
            return vec

    def _cache_put(self, key: str, vec: np.ndarray) -> None:
        if not self._cache_size:
            return
        vec = vec.copy()
        vec.setflags(write=False)  # callers get copies; cached vectors stay immutable
        with self._cache_lock:
            self._cache[key] = vec
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)


def _unit_rows(m: np.ndarray) -> np.ndarray:
    """L2-normalise rows without overflow (scale by max-abs first); zero rows stay zero."""
    m = np.asarray(m, dtype=np.float64)
    scale = np.max(np.abs(m), axis=1, keepdims=True)
    safe = np.where(scale > 0, scale, 1.0)
    scaled = m / safe
    norms = np.linalg.norm(scaled, axis=1, keepdims=True)
    return np.divide(scaled, norms, out=np.zeros_like(scaled), where=norms > 0)
