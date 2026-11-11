"""Live Neo4jGraphStore and OwnRetriever tests against the real Neo4j server.

Run with ``OMNISTREAM_LIVE_TESTS=1`` and ``NEO4J_PASSWORD`` set. Every test
writes into a fresh ``test-<uuid>`` group and deletes it afterwards; the
entity vector index is created only when missing and dropped again by whoever
created it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest
from neo4j import GraphDatabase

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever

pytestmark = pytest.mark.live

DIM = 384
NOW = datetime(2025, 5, 1, 12, 0, tzinfo=UTC)
INDEX = "entity_name_embedding"


def _delete_group(driver, *groups: str) -> None:
    for group in groups:
        driver.execute_query("MATCH ()-[r {group_id: $g}]-() DELETE r", g=group)
        driver.execute_query("MATCH (n {group_id: $g}) DETACH DELETE n", g=group)


def _unit(axis: int) -> list[float]:
    vector = np.zeros(DIM, dtype=float)
    vector[axis] = 1.0
    return vector.tolist()


@pytest.fixture(scope="module")
def live_settings():
    settings = Settings()
    if not settings.neo4j_password.get_secret_value():
        pytest.skip("NEO4J_PASSWORD not configured")
    return settings


@pytest.fixture(scope="module")
def driver(live_settings):
    neo4j_driver = GraphDatabase.driver(
        live_settings.neo4j_uri,
        auth=(
            live_settings.neo4j_user,
            live_settings.neo4j_password.get_secret_value(),
        ),
    )
    neo4j_driver.verify_connectivity()
    yield neo4j_driver
    neo4j_driver.close()


@pytest.fixture(scope="module")
def entity_vector_index(driver):
    """Ensure the 384-dim entity name vector index exists; drop it if we made it."""
    existing = {
        record["name"] for record in driver.execute_query("SHOW INDEXES YIELD name")[0]
    }
    created = INDEX not in existing
    if created:
        driver.execute_query(
            "CREATE VECTOR INDEX entity_name_embedding FOR (n:Entity) ON (n.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}"
        )
    yield INDEX
    if created:
        driver.execute_query("DROP INDEX entity_name_embedding IF EXISTS")


@pytest.fixture
def store_graph(driver, entity_vector_index):
    """A small two-bubble graph; yields (group, other, ids) and cleans up.

    Every node and edge UUID is unique to this run: ``Neo4jGraphStore.expand``
    matches seeds by UUID without group restriction, so fixed UUIDs let
    pre-existing nodes from concurrent or earlier runs contaminate results.
    ``ids`` maps the short names used in assertions to the generated UUIDs.
    """
    group = f"test-{uuid4().hex[:12]}"
    other = f"test-{uuid4().hex[:12]}"
    run = uuid4().hex[:12]
    ids = {
        "a": f"entity-a-{run}",
        "b": f"entity-b-{run}",
        "c": f"entity-c-{run}",
        "d": f"entity-d-{run}",
        "x": f"entity-x-{run}",
        "f1": f"fact-f1-{run}",
        "f2": f"fact-f2-{run}",
        "f3": f"fact-f3-{run}",
        "f4": f"fact-f4-{run}",
        "s1": f"same-as-s1-{run}",
    }
    driver.execute_query(
        """
        CREATE (a:Entity {uuid: $a, name: 'Zephyr Labs', type: 'Organization',
                          group_id: $group, name_embedding: $ea, aliases: ['Zephyr']})
        CREATE (b:Entity {uuid: $b, name: 'Helios Grid', type: 'Organization',
                          group_id: $group, name_embedding: $eb})
        CREATE (c:Entity {uuid: $c, name: 'Ada Kova', type: 'Person',
                          group_id: $group, name_embedding: $ec})
        CREATE (d:Entity {uuid: $d, name: 'Quantum Lab', type: 'Organization',
                          group_id: $group, name_embedding: $ed})
        CREATE (x:Entity {uuid: $x, name: 'Zephyr Labs Global', type: 'Organization',
                          group_id: $other, name_embedding: $ex})
        CREATE (a)-[:RELATES_TO {uuid: $f1, name: 'PARTNERS_WITH',
                fact: 'Zephyr Labs partners with Helios Grid', group_id: $group,
                item_id: 'item1', source_url: 'https://example.test/1',
                published_at: $published, valid_at: $valid, grounded: true,
                credibility: 0.9, confidence: 0.8, source_count: 2,
                fact_embedding: $fe1}]->(b)
        CREATE (a)-[:RELATES_TO {uuid: $f2, name: 'APPOINTS',
                fact: 'Zephyr Labs appoints Ada Kova as chief scientist', group_id: $group,
                item_id: 'item2', source_url: 'https://example.test/2',
                published_at: $published, valid_at: $valid, invalid_at: $invalid,
                grounded: true, credibility: 0.7, confidence: 0.6, source_count: 1}]->(c)
        CREATE (b)-[:RELATES_TO {uuid: $f3, name: 'FUNDS',
                fact: 'Helios Grid funds Ada Kova research', group_id: $group,
                item_id: 'item3', source_url: 'https://example.test/3',
                published_at: $published, valid_at: $valid, grounded: false,
                credibility: 0.5, confidence: 0.5, source_count: 1}]->(c)
        CREATE (c)-[:RELATES_TO {uuid: $f4, name: 'LEADS',
                fact: 'Ada Kova leads the Quantum Lab', group_id: $group,
                item_id: 'item4', source_url: 'https://example.test/4',
                published_at: $published, valid_at: $valid, grounded: true,
                credibility: 0.8, confidence: 0.7, source_count: 1}]->(d)
        CREATE (a)-[:SAME_AS {uuid: $s1}]->(x)
        """,
        group=group,
        other=other,
        **ids,
        ea=_unit(0),
        eb=_unit(1),
        ec=_unit(2),
        ed=_unit(4),
        ex=_unit(3),
        fe1=(
            (np.array([1.0, 1.0, 0.0, 0.0]) / np.sqrt(2.0)).tolist() + [0.0] * (DIM - 4)
        ),
        published=NOW - timedelta(days=2),
        valid=datetime(2025, 1, 1, tzinfo=UTC),
        invalid=datetime(2025, 6, 1, tzinfo=UTC),
    )
    yield group, other, ids
    _delete_group(driver, group, other)


@pytest.mark.live
def test_entities_and_seed_by_embedding(driver, entity_vector_index, store_graph):
    group, other, ids = store_graph
    store = Neo4jGraphStore(driver)
    a, b, c, d, x = (ids[key] for key in ("a", "b", "c", "d", "x"))

    entities = store.entities_in([group])
    assert {e.id for e in entities} == {a, b, c, d}
    by_id = {e.id: e for e in entities}
    assert by_id[a].bubble == group
    assert by_id[a].name == "Zephyr Labs"
    assert by_id[a].type == "Organization"
    assert by_id[a].aliases == ("Zephyr",)
    assert by_id[c].type == "Person"
    assert store.entities_in(["no-such-bubble"]) == []
    # Cross-bubble identity node lives in the other group.
    assert [e.id for e in store.entities_in([other])] == [x]

    # Vector seeding: only the query-identical entity passes the cosine filter.
    seeds = store.seed_by_embedding(
        np.asarray(_unit(0)), bubbles=[group], top_k=5, min_cosine=0.9
    )
    assert [(e.id, round(score, 4)) for e, score in seeds] == [(a, 1.0)]
    # A query in an empty bubble group returns nothing.
    assert (
        store.seed_by_embedding(np.asarray(_unit(0)), bubbles=["no-such-bubble"]) == []
    )
    # A dissimilar query is rejected by min_cosine.
    assert (
        store.seed_by_embedding(np.asarray(_unit(50)), bubbles=[group], min_cosine=0.9)
        == []
    )


@pytest.mark.live
def test_expand_neighbors_facts_about_and_embeddings(
    driver, entity_vector_index, store_graph
):
    group, _other, ids = store_graph
    store = Neo4jGraphStore(driver)
    a, b, c, d, x = (ids[key] for key in ("a", "b", "c", "d", "x"))
    f1, f2, f4 = (ids[key] for key in ("f1", "f2", "f4"))

    # Two hops from the seed: all grounded facts, the cross-bubble SAME_AS
    # link, and the other-bubble entity reachable through it.
    graph = store.expand([a], bubbles=[group], time_scope=None, max_hops=2)
    assert {f.id for f in graph.facts} == {f1, f2, f4}
    assert set(graph.entities) == {a, b, c, d, x}
    assert graph.same_as == ((a, x),)

    # One hop keeps the two direct facts but not the c->d fact; the
    # cross-bubble identity link still counts as a single hop.
    one_hop = store.expand([a], bubbles=[group], time_scope=None, max_hops=1)
    assert [f.id for f in one_hop.facts] == [f1, f2]
    assert set(one_hop.entities) == {a, b, c, x}
    assert one_hop.same_as == ((a, x),)

    # A time scope after f2's invalid_at drops f2 and everything only
    # reachable through it (traversal respects the validity window).
    scoped = store.expand(
        [a],
        bubbles=[group],
        time_scope=TimeScope(start=datetime(2025, 6, 15, tzinfo=UTC)),
        max_hops=2,
    )
    assert [f.id for f in scoped.facts] == [f1]

    # neighbors is the depth-bounded form of expand; the ungrounded b->c fact
    # never opens a path to c->d (which would need 3 hops anyway).
    assert [f.id for f in store.neighbors(b, 2).facts] == [f1, f2]

    # facts_about applies grounding and the validity window.
    about_b = store.facts_about(b, start=None, end=None)
    assert [f.id for f in about_b] == [f1]
    assert about_b[0].relation == "PARTNERS_WITH"
    assert about_b[0].text == "Zephyr Labs partners with Helios Grid"
    assert about_b[0].item_id == "item1"
    assert about_b[0].source_url == "https://example.test/1"
    assert about_b[0].published_at == NOW - timedelta(days=2)
    assert about_b[0].credibility == 0.9 and about_b[0].confidence == 0.8
    assert about_b[0].source_count == 2
    assert about_b[0].grounded is True
    assert (
        store.facts_about(
            b,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 6, 1, tzinfo=UTC),
        )
        == []
    )

    embeddings = store.fact_embeddings([f1, f2, "missing"])
    assert set(embeddings) == {f1}
    np.testing.assert_allclose(
        embeddings[f1],
        (np.array([1.0, 1.0, 0.0, 0.0]) / np.sqrt(2.0)).tolist() + [0.0] * (DIM - 4),
        atol=1e-6,
    )


@pytest.mark.live
def test_from_settings_connects_with_real_driver(live_settings):
    store = Neo4jGraphStore.from_settings(live_settings)
    try:
        entities = store.entities_in(["definitely-not-a-bubble"])
        assert entities == []
    finally:
        store.driver.close()


@pytest.mark.live
def test_own_retriever_end_to_end(driver, entity_vector_index, live_settings):
    group = f"test-{uuid4().hex[:12]}"
    run = uuid4().hex[:12]
    a, b, f1 = f"entity-own-a-{run}", f"entity-own-b-{run}", f"fact-own-{run}"
    embedder = EmbeddingService(live_settings)
    try:
        driver.execute_query(
            """
            CREATE (a:Entity {uuid: $a, name: 'Zephyr Labs', type: 'Organization',
                              group_id: $group, name_embedding: $ea})
            CREATE (b:Entity {uuid: $b, name: 'Helios Grid', type: 'Organization',
                              group_id: $group, name_embedding: $eb})
            CREATE (a)-[:RELATES_TO {uuid: $f1, name: 'ANNOUNCED',
                    fact: 'Zephyr Labs announced a partnership with Helios Grid',
                    group_id: $group, item_id: 'item1',
                    source_url: 'https://example.test/own/1',
                    published_at: $published, valid_at: $published,
                    grounded: true, credibility: 0.9, confidence: 0.9, source_count: 2}]->(b)
            """,
            group=group,
            a=a,
            b=b,
            f1=f1,
            ea=embedder.embed_documents(["Zephyr Labs"])[0].tolist(),
            eb=embedder.embed_documents(["Helios Grid"])[0].tolist(),
            published=NOW - timedelta(days=1),
        )
        store = Neo4jGraphStore(driver)
        retriever = OwnRetriever(store, embedder)
        result = retriever.retrieve(
            "What did Zephyr Labs announce?",
            bubbles=[group],
            top_k=5,
        )
        assert result.mode == "own"
        assert result.facts, "own retrieval returned no facts"
        fact = result.facts[0].fact
        assert fact.id == f1
        assert fact.subject_id == a and fact.object_id == b
        assert fact.bubble == group
        assert fact.item_id == "item1"
        assert fact.grounded is True
        assert result.facts[0].score > 0
        assert result.facts[0].path, "facts must carry a path from the seed"
    finally:
        _delete_group(driver, group)


@pytest.mark.live
def test_expand_uses_scoped_clause_without_deprecation_warnings(
    driver, entity_vector_index, store_graph
):
    """The expand query runs without Neo4j deprecation notifications.

    Neo4j 5.26 deprecates the importing WITH (``CALL { WITH paths ... }``) in
    favour of the 5.23+ scoped clause (``CALL (paths) { ... }``). Run the
    exact query the store uses and check the server's notifications; results
    are asserted against the store's expand output so semantics are unchanged.
    """
    from omnistream.graph.neo4j_store import _EXPAND_CYPHER

    group, _other, ids = store_graph
    a, b, c, d, x = (ids[key] for key in ("a", "b", "c", "d", "x"))
    f1, f2, f4 = (ids[key] for key in ("f1", "f2", "f4"))

    records, summary, _ = driver.execute_query(
        _EXPAND_CYPHER,
        seed_ids=[a],
        max_hops=2,
        max_edges=500,
        start=None,
        end=None,
    )
    deprecations = [
        status
        for status in summary.gql_status_objects
        if status.raw_classification == "DEPRECATION"
        and status.raw_severity == "WARNING"
    ]
    assert deprecations == [], (
        f"expand query triggered deprecation warnings: {deprecations}"
    )

    rows = list(records)
    assert len(rows) == 1
    row = rows[0]
    assert {item["fact"]["uuid"] for item in row["facts"]} == {f1, f2, f4}
    assert {node["uuid"] for node in row["entities"]} == {a, b, c, d, x}
    assert row["same_as"] == [[a, x]]

    # The store returns the same expansion from the same seed.
    graph = Neo4jGraphStore(driver).expand(
        [a], bubbles=[group], time_scope=None, max_hops=2
    )
    assert {f.id for f in graph.facts} == {f1, f2, f4}
    assert set(graph.entities) == {a, b, c, d, x}
    assert graph.same_as == ((a, x),)
