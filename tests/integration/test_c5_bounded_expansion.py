"""Logical-hop semantics and measured Neo4j traversal cost."""

from datetime import UTC, datetime

import pytest
from neo4j import GraphDatabase

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.graph.neo4j_store import (
    _VALID,
    Neo4jGraphStore,
    _scope_parameters,
)
from tests.integration.test_graph_writer_neo4j import neo4j_container  # noqa: F401

pytestmark = pytest.mark.integration


def db_hits(plan):
    return plan.get("dbHits", 0) + sum(
        db_hits(child) for child in plan.get("children", [])
    )


class ProfileStore(Neo4jGraphStore):
    def __init__(self, driver):
        super().__init__(driver)
        self.hits = []

    def _run(self, query, **parameters):
        with self.driver.session(database=self.database) as session:
            result = session.run("PROFILE " + query, **parameters)
            rows = list(result)
            self.hits.append(db_hits(result.consume().profile))
            return rows


@pytest.fixture
def graph_driver(neo4j_container):  # noqa: F811
    container = neo4j_container
    with GraphDatabase.driver(
        container.get_connection_url(), auth=(container.username, container.password)
    ) as driver:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
            session.run(
                "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS UNIQUE"
            ).consume()
        yield driver
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()


def make_graph(driver, entities, edges, bridges):
    with driver.session() as session:
        session.run(
            "UNWIND $nodes AS n CREATE (e:Entity) SET e = n",
            nodes=[
                {"uuid": ident, "name": ident, "group_id": bubble}
                for ident, bubble in entities
            ],
        ).consume()
        session.run(
            "UNWIND $edges AS e MATCH (a:Entity {uuid:e[1]}), (b:Entity {uuid:e[2]}) CREATE (a)-[r:RELATES_TO]->(b) SET r.uuid=e[0], r.group_id=e[3], r.grounded=true, r.item_id='item', r.published_at=$date",
            edges=edges,
            date=datetime(2020, 1, 1, tzinfo=UTC),
        ).consume()
        for ident, members in bridges:
            session.run(
                "CREATE (g:GlobalEntity {uuid:$id}) WITH g UNWIND $members AS member MATCH (e:Entity {uuid:member}) CREATE (e)-[:SAME_AS]->(g)",
                id=ident,
                members=members,
            ).consume()


def test_hub_profile_is_bounded_and_capped(graph_driver):
    entities = [("hub", "news")]
    edges = []
    for i in range(200):
        neighbor = f"n{i:03}"
        entities.append((neighbor, "news"))
        edges.append([f"a{i:03}", "hub", neighbor, "news"])
        for j in range(10):
            leaf = f"l{i:03}-{j}"
            entities.append((leaf, "news"))
            edges.append([f"b{i:03}-{j}", neighbor, leaf, "news"])
    make_graph(graph_driver, entities, edges, [])
    store = ProfileStore(graph_driver)
    graph = store.expand(["hub"], bubbles=["news"], time_scope=None)
    assert len(graph.facts) == 500
    assert len(graph.entities) == 2201
    assert len(store.hits) == 2
    # Linear work over two deduplicated frontiers, well below path enumeration.
    assert sum(store.hits) < 150_000
    print(
        f"HUB PROFILE: per-hop db hits={store.hits}; total={sum(store.hits)}; entities={len(graph.entities)}; facts={len(graph.facts)}"
    )
    assert [f.id for f in graph.facts[:200]] == [f"a{i:03}" for i in range(200)]


def test_logical_bridges_exclusions_cap_and_old_semantics(graph_driver):
    make_graph(
        graph_driver,
        [
            ("a", "news"),
            ("b", "finance"),
            ("c", "finance"),
            ("d", "finance"),
            ("e", "research"),
            ("z", "research"),
        ],
        [
            ["bc", "b", "c", "finance"],
            ["cd", "c", "d", "finance"],
            ["ez", "e", "z", "research"],
        ],
        [("g1", ["a", "b"]), ("g2", ["b", "e"])],
    )
    store = Neo4jGraphStore(graph_driver)
    graph = store.expand(["a"], bubbles=["news"], time_scope=None)
    assert [f.id for f in graph.facts] == ["bc"]  # bridge + two facts exceeds two hops
    assert graph.same_as == (("a", "b"), ("b", "e"))  # two bridges
    assert set(graph.entities) == {"a", "b", "c", "e"}  # no GlobalEntity
    assert not store.expand(["a"], bubbles=["news"], time_scope=None, max_hops=1).facts
    assert (
        len(store.expand(["a"], bubbles=["news"], time_scope=None, max_edges=1).facts)
        == 1
    )
    assert not store.expand(["a"], bubbles=["news"], time_scope=None, max_edges=0).facts
    excluded = store.expand(
        ["a"], bubbles=["news"], time_scope=None, excluded_bubbles=["finance"]
    )
    assert (
        set(excluded.entities) == {"a"} and not excluded.facts and not excluded.same_as
    )
    assert not store.neighbors("a", 2, excluded_bubbles=["finance"]).facts
    assert not store.facts_about("b", excluded_bubbles=["finance"])
    # Independent previous whole-path definition, evaluated only on this small graph.
    old = (
        """MATCH p=(seed:Entity)-[:RELATES_TO|SAME_AS*0..4]-(endpoint:Entity)
    WHERE seed.uuid = 'a'
    AND length(p)-size([n IN nodes(p) WHERE n:GlobalEntity]) <= 2
    AND all(r IN relationships(p) WHERE type(r)='SAME_AS' OR ("""
        + _VALID
        + """))
    RETURN collect(p) AS paths"""
    )
    with graph_driver.session() as session:
        paths = session.run(old, **_scope_parameters(None)).single()["paths"]
    assert set(graph.entities) == {
        n["uuid"] for p in paths for n in p.nodes if "Entity" in n.labels
    }
    assert {f.id for f in graph.facts} == {
        r["uuid"] for p in paths for r in p.relationships if r.type == "RELATES_TO"
    }
    memory = InMemoryGraphStore(
        list(graph.entities.values()), graph.facts, graph.same_as
    )
    parity = memory.expand(["a"], bubbles=["news"], time_scope=None)
    assert parity == graph
    assert not memory.expand(
        ["a"], bubbles=["news"], time_scope=None, excluded_bubbles=["finance"]
    ).facts


def test_reader_schema_fresh_idempotent_and_dimension_mismatch(graph_driver):
    store = Neo4jGraphStore(graph_driver)
    with graph_driver.session() as session:
        session.run("DROP INDEX entity_name_embedding IF EXISTS").consume()
    store.ensure_schema(8)
    store.ensure_schema(8)
    import numpy as np

    assert store.seed_by_embedding(np.ones(8), bubbles=["news"]) == []
    with pytest.raises(ValueError, match="dimension is 8; expected 384"):
        store.ensure_schema(384)
    with graph_driver.session() as session:
        session.run("DROP INDEX entity_name_embedding").consume()


def test_bridged_fact_cap_is_global_and_deterministic(graph_driver):
    make_graph(
        graph_driver,
        [("a", "news"), ("b", "finance"), *[(f"n{i}", "finance") for i in range(520)]],
        [[f"f{i:03}", "b", f"n{i}", "finance"] for i in range(520)],
        [("g", ["a", "b"])],
    )
    store = Neo4jGraphStore(graph_driver)
    graph = store.expand(["a"], bubbles=["news"], time_scope=None)
    assert [f.id for f in graph.facts] == [f"f{i:03}" for i in range(500)]
    assert graph.same_as == (("a", "b"),)
    assert "g" not in graph.entities
