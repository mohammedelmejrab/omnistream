"""Shared fixtures and constants. Later tasks add fakes here."""

import pytest
import pytest_asyncio

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
