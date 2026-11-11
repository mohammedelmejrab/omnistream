"""Live end-to-end Graphiti test: real Neo4j, OpenRouter LLM, local embeddings.

Run with ``OMNISTREAM_LIVE_TESTS=1`` and ``NEO4J_PASSWORD`` set. Ingests a few
short episodes into a fresh ``test-<uuid>`` group, stamps the C4 provenance
attributes, retrieves through ``GraphitiRetriever`` and deletes the group
afterwards. LLM usage is kept to a handful of tiny episodes.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from neo4j import GraphDatabase
from pydantic import ValidationError

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.graphiti_mode import GraphitiCoreSearcher, GraphitiRetriever

pytestmark = pytest.mark.live
pytest.importorskip("graphiti_core")

from graphiti_core.nodes import EpisodeType

EPISODES = [
    (
        "OmniCorp launches Vortex chip",
        "OmniCorp, a technology company, announced the launch of its Vortex quantum chip on 6 January 2025.",
        datetime(2025, 1, 6, 12, 0, tzinfo=UTC),
    ),
    (
        "OmniCorp appoints chief scientist",
        "Alice Chen was appointed chief scientist of OmniCorp in February 2025.",
        datetime(2025, 2, 10, 12, 0, tzinfo=UTC),
    ),
    (
        "OmniCorp opens Lisbon campus",
        "OmniCorp opened a new research campus in Lisbon in March 2025.",
        datetime(2025, 3, 3, 12, 0, tzinfo=UTC),
    ),
]

# DeepSeek occasionally answers graphiti's schema-injection prompt by echoing
# the JSON schema instead of filling it (a valid-JSON response that fails
# graphiti's response-model parsing). Retrying the same episode is safe:
# node/edge resolution dedupes against what a failed attempt already wrote,
# and the group is deleted wholesale at the end anyway.
INGEST_ATTEMPTS = 3


async def add_episode_with_retry(graphiti, *, name, body, reference_time, group_id):
    last_error: Exception | None = None
    for _ in range(INGEST_ATTEMPTS):
        try:
            return await graphiti.add_episode(
                name=name,
                episode_body=body,
                source_description="OmniStream live test feed",
                reference_time=reference_time,
                source=EpisodeType.text,
                group_id=group_id,
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


@pytest.fixture(scope="module")
def live_settings():
    settings = Settings()
    if not settings.has_llm_credentials:
        pytest.skip("LLM_API_KEY not configured")
    if not settings.neo4j_password.get_secret_value():
        pytest.skip("NEO4J_PASSWORD not configured")
    return settings


def _delete_group(settings: Settings, group_id: str) -> None:
    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    ) as driver:
        driver.execute_query("MATCH ()-[r {group_id: $g}]-() DELETE r", g=group_id)
        driver.execute_query("MATCH (n {group_id: $g}) DETACH DELETE n", g=group_id)


def _group_count(settings: Settings, group_id: str) -> int:
    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    ) as driver:
        record = driver.execute_query(
            "MATCH (n {group_id: $g}) RETURN count(n) AS c", g=group_id
        )[0][0]
        return int(record["c"])


@pytest.mark.live
async def test_graphiti_end_to_end(live_settings):
    settings = live_settings
    group_id = f"test-{uuid4().hex[:12]}"
    embeddings = EmbeddingService(settings)
    searcher = GraphitiCoreSearcher.from_settings(settings, embeddings=embeddings)
    graphiti = searcher.graphiti
    retriever = GraphitiRetriever(searcher)
    try:
        await graphiti.build_indices_and_constraints()
        results = []
        for name, body, reference_time in EPISODES:
            results.append(
                await add_episode_with_retry(
                    graphiti,
                    name=name,
                    body=body,
                    reference_time=reference_time,
                    group_id=group_id,
                )
            )
        # The C4 graph writer stamps grounding and provenance on every fact
        # and persists them; do the same here so retrieval sees them.
        for index, result in enumerate(results, 1):
            for edge in result.edges:
                edge.attributes.update(
                    {
                        "grounded": True,
                        "item_id": f"live-item-{index}",
                        "source_url": f"https://example.test/feed/{index}",
                        "credibility": 0.8,
                        "source_count": 1,
                    }
                )
                await graphiti.driver.entity_edge_ops.save(graphiti.driver, edge)

        total_edges = sum(len(result.edges) for result in results)
        assert total_edges > 0, "Graphiti extracted no facts from the episodes"
        assert all(
            edge.group_id == group_id for result in results for edge in result.edges
        )

        # Raw search returns real EntityEdge objects with the expected fields.
        edges = await searcher.search("OmniCorp", group_ids=[group_id], num_results=10)
        assert edges, "Graphiti search returned no edges"
        for edge in edges:
            assert edge.uuid and edge.fact and edge.name
            assert edge.group_id == group_id
            assert edge.source_node_uuid and edge.target_node_uuid
            assert edge.created_at is not None
            assert isinstance(edge.attributes, dict)
            assert {"item_id", "grounded", "source_url", "credibility"} <= set(
                edge.attributes
            )

        # The retriever maps those edges into spec-shaped facts with provenance.
        result = await retriever.aretrieve(
            "What did OmniCorp announce?", bubbles=[group_id]
        )
        assert result.mode == "graphiti"
        assert result.facts, "no facts survived the grounding/provenance mapping"
        for scored in result.facts:
            fact = scored.fact
            assert fact.bubble == group_id
            assert fact.item_id.startswith("live-item-")
            assert fact.relation and fact.text
            assert fact.subject_id and fact.object_id
            assert fact.published_at is not None
            assert fact.grounded is True
            assert 0 < scored.score <= 1
            assert scored.ranks["graphiti"] >= 1
        joined = " ".join(scored.fact.text for scored in result.facts).lower()
        assert "omnicorp" in joined or "vortex" in joined
        assert retriever.skipped_missing_provenance == 0

        # Other bubbles never leak in.
        assert not (
            await retriever.aretrieve(
                "OmniCorp",
                bubbles=[f"test-{uuid4().hex[:12]}"],
            )
        ).facts

        # Two consecutive SYNC retrieves against the same group. Each sync
        # call used to run on its own asyncio.run loop while the Graphiti
        # driver's pooled Neo4j connections stayed bound to the first
        # (closed) loop, so the second call could fail; the retriever now
        # serves all sync calls from one persistent background loop. A fresh
        # Graphiti instance is built inside a worker thread (never touched by
        # this test's event loop) so its driver binds exclusively to the
        # persistent loop, and the ingested group is reused without extra
        # LLM cost.
        def sync_retrieves() -> tuple:
            sync_retriever = GraphitiRetriever.from_settings(
                settings, embeddings=embeddings
            )
            try:
                first = sync_retriever.retrieve(
                    "What did OmniCorp announce?", bubbles=[group_id]
                )
                second = sync_retriever.retrieve(
                    "Who is the chief scientist of OmniCorp?", bubbles=[group_id]
                )
                return first, second
            finally:
                sync_retriever.close()

        first_sync, second_sync = await asyncio.to_thread(sync_retrieves)
        assert first_sync.mode == "graphiti" and first_sync.facts
        assert second_sync.mode == "graphiti" and second_sync.facts
        joined_sync = " ".join(
            scored.fact.text for scored in first_sync.facts + second_sync.facts
        ).lower()
        assert "omnicorp" in joined_sync or "vortex" in joined_sync

        # Cleanup leaves the group empty (graphiti-core 0.31.2 has no
        # delete-group helper, so tests delete by group_id directly).
        _delete_group(settings, group_id)
        assert _group_count(settings, group_id) == 0
    finally:
        _delete_group(settings, group_id)
        await retriever.aclose()
