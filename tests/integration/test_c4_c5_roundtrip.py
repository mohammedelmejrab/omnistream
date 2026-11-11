"""Read real Graphiti saves and C4 stamps through all C5 graph adapters."""

import asyncio
from datetime import UTC, datetime

import numpy as np
import pytest
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from neo4j import GraphDatabase

from omnistream.embed import SentenceTransformerEmbedder
from omnistream.graph.chunks import ChunkStore
from omnistream.graph.linker import GlobalEntityLinker
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.graph.ops import Neo4jGraphOps
from omnistream.retrieval.classic import ClassicRetriever
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from tests.integration.test_graph_writer_neo4j import neo4j_container  # noqa: F401

pytestmark = pytest.mark.integration
PAST = datetime(2020, 1, 1, tzinfo=UTC)
CHANGE = datetime(2021, 1, 1, tzinfo=UTC)


async def test_writer_shape_query_roundtrip(neo4j_container, embedder, tmp_path):  # noqa: F811
    container = neo4j_container
    driver = Neo4jDriver(
        container.get_connection_url(), container.username, container.password
    )
    sync = GraphDatabase.driver(
        container.get_connection_url(), auth=(container.username, container.password)
    )
    chunks = ChunkStore(
        str(tmp_path), SentenceTransformerEmbedder("unused", service=embedder), 300
    )
    try:
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        ops = Neo4jGraphOps(driver, 384)
        await ops.ensure_schema()
        await ops.ensure_schema()  # idempotent, configured dimensions
        linker = GlobalEntityLinker(
            ops, SentenceTransformerEmbedder("unused", service=embedder), 0.88, 90
        )
        nodes = []
        for ident, name, kind, group in [
            ("a", "Acme", "Organization", "news"),
            ("af", "Acme", "Organization", "finance"),
            ("old", "Alice", "Person", "finance"),
            ("new", "Bob", "Person", "finance"),
        ]:
            vec = embedder.embed_documents([name])[0].tolist()
            node = EntityNode(
                uuid=ident,
                name=name,
                labels=["Entity", kind],
                group_id=group,
                name_embedding=vec,
                summary="",
                created_at=PAST,
            )
            await node.save(driver)
            await ops.set_node_grounded(ident, True)
            await linker.link(ident, name, kind, vec)
            nodes.append(node)
        for ident, target, valid, invalid in [
            ("old-fact", "old", PAST, CHANGE),
            ("new-fact", "new", CHANGE, None),
        ]:
            episode = EpisodicNode(
                uuid="ep-" + ident,
                name=ident,
                group_id="finance",
                source=EpisodeType.text,
                source_description="source",
                content=ident,
                valid_at=valid,
                created_at=valid,
            )
            await episode.save(driver)
            await ops.tag_episode(
                episode.uuid, "item-" + ident, "https://source/" + ident, 0.9, "source"
            )
            edge = EntityEdge(
                uuid=ident,
                source_node_uuid="af",
                target_node_uuid=target,
                group_id="finance",
                name="HAS_CEO",
                fact="Acme has CEO " + target,
                valid_at=valid,
                invalid_at=invalid,
                created_at=valid,
                episodes=[episode.uuid],
                fact_embedding=embedder.embed_documents(["Acme CEO"])[0].tolist(),
            )
            await edge.save(driver)
            await ops.set_edge_props(
                ident,
                {
                    "grounded": True,
                    "item_id": "item-" + ident,
                    "item_ids": ["item-" + ident],
                    "published_at": valid,
                    "confidence": 0.9,
                    "credibility": 0.9,
                    "source_count": 1,
                },
            )
            await ops.set_edge_statuses([ident])
        await driver.execute_query("CALL db.awaitIndexes()")
        store = Neo4jGraphStore(sync)
        graph = await asyncio.to_thread(
            store.expand, ["a"], bubbles=["news"], time_scope=None
        )
        assert [f.id for f in graph.facts] == ["new-fact"]
        assert graph.same_as == (("a", "af"),)
        assert graph.entities["a"].global_id == graph.entities["af"].global_id
        assert graph.entities["new"].type == "Person"
        assert "old" not in graph.entities
        assert graph.facts[0].item_ids == ("item-new-fact",)
        assert graph.facts[0].published_at == CHANGE
        assert not (await asyncio.to_thread(store.neighbors, "a", 1)).facts
        assert [f.id for f in await asyncio.to_thread(store.facts_about, "af")] == [
            "new-fact"
        ]
        past = TimeScope(PAST, PAST)
        history = await asyncio.to_thread(
            store.expand, ["a"], bubbles=["news"], time_scope=past
        )
        assert [f.id for f in history.facts] == ["old-fact"]
        retriever = OwnRetriever(store, embedder)
        result = await asyncio.to_thread(retriever.retrieve, "Acme", bubbles=["news"])
        assert [f.fact.id for f in result.facts] == ["new-fact"]
        assert result.facts[0].path == ("a", "af")  # nearest fact endpoint
        assert result.facts[0].fact.object_id == "new"
        assert result.facts[0].fact.item_id == "item-new-fact"
        assert (
            len(
                await asyncio.to_thread(
                    store.seed_by_embedding,
                    embedder.embed_query("Acme"),
                    bubbles=["news"],
                )
            )
            == 1
        )
        # Legacy edges use the episode date when published_at/valid_at are absent.
        await driver.execute_query(
            "MATCH ()-[r:RELATES_TO {uuid:'new-fact'}]->() REMOVE r.published_at, r.valid_at"
        )
        assert (await asyncio.to_thread(store.facts_about, "af"))[
            0
        ].published_at == CHANGE
        await chunks.add(
            "news", "chunk-item", "Acme has CEO Bob", "https://source/chunk", None
        )
        classic = ClassicRetriever(chunks._client, embedder)
        baseline = await asyncio.to_thread(
            classic.retrieve, "Acme CEO", bubbles=["news"]
        )
        assert baseline.chunks[0].item_id == "chunk-item"
        assert baseline.chunks[0].published_at is None
        np.testing.assert_allclose(
            embedder.embed_documents(["Acme"])[0], nodes[0].name_embedding
        )
    finally:
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        await driver.close()
        sync.close()
        chunks._client.close()
