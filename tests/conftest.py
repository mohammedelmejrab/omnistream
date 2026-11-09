"""Shared fixtures and constants. Later tasks add fakes here."""

import asyncio
import hashlib
import math
import random
from collections.abc import Callable

import pytest
import pytest_asyncio
from pydantic import BaseModel

from omnistream.store.memory import InMemoryStore

DIM = 8  # embedding dimension used by contract tests


@pytest.fixture(scope="session")
def neo4j_container():
    from testcontainers.community.neo4j import Neo4jContainer

    with Neo4jContainer("neo4j:5.26") as c:
        yield c


@pytest_asyncio.fixture(
    params=["memory", pytest.param("neo4j", marks=pytest.mark.integration)],
    ids=["memory", "neo4j"],
)
async def store(request):
    """GraphStore under test; the same contract suite runs against each backend."""
    if request.param == "memory":
        yield InMemoryStore()
    elif request.param == "neo4j":
        from omnistream.store.neo4j_store import Neo4jStore

        c = request.getfixturevalue("neo4j_container")
        s = Neo4jStore(
            c.get_connection_url(), c.username, c.password, embed_dim=DIM
        )
        await s.init_schema()
        await s._run("MATCH (n) DETACH DELETE n")
        try:
            yield s
        finally:
            await s.close()
    else:
        raise ValueError(f"unknown store param: {request.param}")


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
