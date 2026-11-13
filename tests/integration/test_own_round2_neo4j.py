"""Execute schema, bounded vector search, fallback and lexical queries on Neo4j."""

from datetime import UTC, datetime

import numpy as np
import pytest
from neo4j import GraphDatabase

from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.graph.ops import Neo4jGraphOps
from tests.integration.test_graph_writer_neo4j import neo4j_container  # noqa: F401

pytestmark = pytest.mark.integration


class AsyncAdapter:
    def __init__(self, driver):
        self.driver = driver

    async def execute_query(self, query, **params):
        return self.driver.execute_query(query, **params)


async def test_actual_schema_and_search(neo4j_container):  # noqa: F811
    c = neo4j_container
    with GraphDatabase.driver(
        c.get_connection_url(), auth=(c.username, c.password)
    ) as driver:
        ops = Neo4jGraphOps(
            AsyncAdapter(driver), 384, "custom_entities", "custom_facts"
        )
        await ops.ensure_schema()
        await ops.ensure_schema()
        driver.execute_query("CALL db.awaitIndexes()")
        v = [1.0] + [0.0] * 383
        driver.execute_query(
            "CREATE (a:Entity:Product {uuid:'a', name:'iPhone', group_id:'selected', name_embedding:$v}), (b:Entity:Organization {uuid:'b',name:'Acme',group_id:'selected',name_embedding:$v}), (c:Entity:Concept {uuid:'c',name:'role',group_id:'other',name_embedding:$v}), (a)-[:RELATES_TO {uuid:'ok',fact_embedding:$v,group_id:'selected',grounded:true}]->(b), (a)-[:RELATES_TO {uuid:'wrong',fact_embedding:$v,group_id:'other',grounded:true}]->(c), (a)-[:RELATES_TO {uuid:'invalid',fact_embedding:$v,group_id:'selected',grounded:true,invalid_at:$past}]->(b)",
            v=v,
            past=datetime(2000, 1, 1, tzinfo=UTC),
        )
        store = Neo4jGraphStore(
            driver, entity_index_name="custom_entities", fact_index_name="custom_facts"
        )
        query = np.array(v)
        for exact in (False, True):
            store.exact_search = exact
            hits = store.seed_by_fact_embedding(query, bubbles=["selected"], top_k=1)
            assert [e.id for e, _ in hits] == ["a", "b"]
            assert all(s == pytest.approx(1.0) for _, s in hits)
            assert (
                len(store.seed_by_embedding(query, bubbles=["selected"], top_k=2)) == 2
            )
        store.exact_search = False
        calls = []
        original_run = store._run

        def recording_run(query, **params):
            calls.append((query, params))
            return original_run(query, **params)

        store._run = recording_run
        assert (
            len(store.seed_by_fact_embedding(query, bubbles=["selected"], top_k=10))
            == 2
        )
        assert [p["fetch"] for q, p in calls if "queryRelationships" in q] == [
            50,
            150,
            250,
        ]
        assert all("count(candidate)" not in q for q, p in calls)
        assert [
            e.id for e in store.name_candidates("iphone", bubbles=["selected"])
        ] == ["a"]
        store.exact_search = False
        store.fact_index_name = "absent"
        assert len(store.seed_by_fact_embedding(query, bubbles=["selected"])) == 2
        assert store.search_paths[-1]["path"] == "fact_exact_missing_index"
        driver.execute_query(
            "CREATE VECTOR INDEX wrong_metric IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.other_embedding) OPTIONS {indexConfig: {`vector.dimensions`:384, `vector.similarity_function`:'euclidean'}}"
        )
        driver.execute_query("CALL db.awaitIndexes()")
        store.fact_index_name = "wrong_metric"
        with pytest.raises(ValueError, match="compatible cosine"):
            store.seed_by_fact_embedding(query, bubbles=["selected"])
