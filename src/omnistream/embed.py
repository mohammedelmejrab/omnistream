import asyncio
from typing import Protocol


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector per input text."""
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        # Imported here so importing this module never pulls in torch.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(
            self._model.encode, texts, normalize_embeddings=True
        )
        return [[float(x) for x in v] for v in vectors]
