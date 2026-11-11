"""C1-C4 async embedding adapter over the shared :mod:`omnistream.embeddings`.

The C5 ``EmbeddingService`` is the single local embedding core (one model
instance, LRU cache, thread safety, BGE query/document distinction). The C4
ingestion modules speak the async ``Embedder`` protocol; ``SentenceTransformerEmbedder``
adapts the service to it using *document* encoding, which is the space the
ingestion path always embeds in.
"""

import asyncio
from typing import Protocol

from omnistream.embeddings import EmbeddingService


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector per input text."""
        ...


class SentenceTransformerEmbedder:
    """Async ``Embedder`` over the shared ``EmbeddingService`` (document space).

    The model is loaded lazily by the service on first use, so constructing
    this adapter never pulls in torch. Inject ``service`` in tests to share a
    deterministic encoder.
    """

    def __init__(
        self, model_name: str, *, service: EmbeddingService | None = None
    ) -> None:
        self.service = service or EmbeddingService(model_name=model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(self.service.embed_documents, texts)
        return [[float(x) for x in v] for v in vectors]
