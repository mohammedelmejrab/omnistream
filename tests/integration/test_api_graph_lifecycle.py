"""Neo4j regression: recovery repairs only the crashed episode's time window."""

from pathlib import Path

import pytest

from omnistream.models import Source
from omnistream.router.bubbles import BubbleLifecycle
from tests.conftest import FakeEmbedder
from tests.integration.test_graph_writer_neo4j import (
    TEXT_1,
    env,  # noqa: F401 - shared recorded Graphiti fixture
    item,
    neo4j_container,  # noqa: F401 - required by env
    src,
)

pytestmark = pytest.mark.integration


async def test_api_graph_recovery_window_and_delete_lifecycle(env, tmp_path):  # noqa: F811
    writer, graphiti, _ = env
    await writer.write(item("crashed", "first"), TEXT_1, ["news"], src("s", 0.8))
    driver = graphiti.driver
    await driver.execute_query(
        "MATCH (ep:Episodic {group_id:'news'}) SET ep.created_at=datetime()-duration({hours:2}) "
        "WITH ep CREATE (:Episodic {uuid:'next-episode', group_id:'news', created_at:ep.created_at+duration({hours:1})}) "
        "WITH ep MATCH (a:Entity {group_id:'news'}), (b:Entity {group_id:'news'}) "
        "WHERE a.uuid < b.uuid WITH ep,a,b LIMIT 1 "
        "CREATE (a)-[:RELATES_TO {uuid:'stale-invalid', group_id:'news', fact:'stale', status:'VERIFIED', invalid_at:ep.created_at+duration({minutes:1})}]->(b), "
        "(a)-[:RELATES_TO {uuid:'stale-expired', group_id:'news', fact:'expired', status:'VERIFIED', expired_at:ep.created_at+duration({minutes:2})}]->(b), "
        "(a)-[:RELATES_TO {uuid:'earlier', group_id:'news', status:'VERIFIED', invalid_at:ep.created_at-duration({minutes:1})}]->(b), "
        "(a)-[:RELATES_TO {uuid:'later', group_id:'news', status:'VERIFIED', invalid_at:ep.created_at+duration({minutes:61})}]->(b), "
        "(a)-[:RELATES_TO {uuid:'other-group', group_id:'finance', status:'VERIFIED', invalid_at:ep.created_at+duration({minutes:1})}]->(b)"
    )
    recovered = await writer.ops.recover_episode("crashed", "news")
    assert recovered is not None
    records, _, _ = await driver.execute_query(
        "MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $ids RETURN r.uuid AS id,r.status AS status",
        ids=["stale-invalid", "stale-expired", "earlier", "later", "other-group"],
    )
    assert {r["id"]: r["status"] for r in records} == {
        "stale-invalid": "HISTORICAL",
        "stale-expired": "HISTORICAL",
        "earlier": "VERIFIED",
        "later": "VERIFIED",
        "other-group": "VERIFIED",
    }
    assert "stale" not in await writer.ops.recent_facts("news", 20)
    # Graph map counts distinct globals even if multiple local nodes link to one.
    await driver.execute_query(
        "MATCH (n:Entity {group_id:'news'}) WITH n LIMIT 1 "
        "CREATE (n)-[:SAME_AS]->(g:GlobalEntity {uuid:'shared-global', name:'Shared entity'}), "
        "(:Entity {uuid:'finance-local',name:'Finance alias',group_id:'finance'})-[:SAME_AS]->(g)"
    )
    assert (await writer.ops.bubble_map())[0]["value"] >= 1
    current_graph = await writer.ops.bubble_graph("news")
    assert current_graph["nodes"]
    hidden = {"stale-invalid", "stale-expired", "earlier", "later", "other-group"}
    assert not hidden.intersection(edge["id"] for edge in current_graph["edges"])
    history = await writer.ops.bubble_graph("news", include_historical=True)
    assert {"stale-invalid", "stale-expired"}.issubset(
        edge["id"] for edge in history["edges"]
    )
    repo = writer._repo
    await repo.upsert_source(
        Source(id="sole", type="rss", url="https://test.local/rss", bubble_ids=["news"])
    )
    await repo.mark_seen("keep-hash", "sole")
    original = tmp_path / "original.txt"
    original.write_text("Stored original remains.")
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), None, writer.ops, writer.chunks)
    counts = await lifecycle.counts("news")
    assert counts["entities"] > 0 and counts["chunks"] > 0
    await lifecycle.delete("news")
    assert await repo.get_bubble("news") is None
    assert not (await repo.get_source("sole")).enabled
    assert await repo.has_seen("keep-hash") and Path(original).exists()
    assert await writer.chunks.count("news") == 0
    assert await writer.ops.group_counts("news") == {
        "entities": 0,
        "episodes": 0,
        "facts": 0,
    }
    rows, _, _ = await driver.execute_query(
        "MATCH (g:GlobalEntity) WHERE NOT ()-[:SAME_AS]->(g) RETURN count(g) AS n"
    )
    assert rows[0]["n"] == 0
