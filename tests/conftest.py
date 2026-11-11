"""Shared fixtures and constants. Later tasks add fakes here."""

import asyncio
import hashlib
import math
import random
from collections.abc import Callable

from pydantic import BaseModel

DIM = 8  # embedding dimension used by tests


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else list(v)


class FakeEmbedder:
    """Deterministic embedder. Table lookup is casefolded; unknown text gets a
    unit vector seeded from sha256(text). All vectors are L2-normalized."""

    def __init__(self, table: dict[str, list[float]] | None = None, dim: int = 8):
        self.dim = dim
        self.table = {k.casefold(): _unit(v) for k, v in (table or {}).items()}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        key = text.casefold()
        if key in self.table:
            return list(self.table[key])
        seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
        rng = random.Random(seed)
        return _unit([rng.gauss(0, 1) for _ in range(self.dim)])


class FakeLLM:
    """Stands in for LLMClient. responses maps schema type -> BaseModel instance
    or callable(user) -> BaseModel (which may raise, e.g. LLMError)."""

    def __init__(
        self,
        responses: dict[type, Callable[[str], BaseModel] | BaseModel],
        delay: float = 0.0,
    ):
        self.responses = responses
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def parse(self, model, system, user, schema, max_tokens=4096):
        self.calls.append((model, user))
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        resp = self.responses[schema]
        if isinstance(resp, BaseModel):
            return resp
        return resp(user)
