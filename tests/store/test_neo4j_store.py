import pytest

from tests.conftest import DIM

pytestmark = pytest.mark.integration


async def test_init_schema_is_idempotent(neo4j_container):
    from omnistream.store.neo4j_store import Neo4jStore

    s = Neo4jStore(
        neo4j_container.get_connection_url(),
        neo4j_container.username,
        neo4j_container.password,
        embed_dim=DIM,
    )
    try:
        await s.init_schema()
        await s.init_schema()
    finally:
        await s.close()
