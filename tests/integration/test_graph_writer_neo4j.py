"""GraphWriter against real Neo4j (testcontainers) with a recorded-style stub LLM.

The stub is an OpenAI-compatible client returning canned JSON per Graphiti prompt
type, so the run is deterministic and offline.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.graph.chunks import ChunkStore
from omnistream.graph.graphiti_client import (
    BgeEmbedderClient,
    LocalCrossEncoder,
)
from omnistream.graph.linker import GlobalEntityLinker
from omnistream.graph.ops import Neo4jGraphOps
from omnistream.graph.writer import GraphWriter
from omnistream.models import Bubble, Source
from tests.conftest import FakeEmbedder

pytestmark = pytest.mark.integration

DIM = 8
NOW = datetime(2026, 3, 1, tzinfo=UTC)
TEXT_1 = (
    "Alice Smith became CEO of Acme Corp in Berlin this week. "
    "Acme Corp previously said it was owned by Beta Group until January 2026. " * 3
)
TEXT_2 = "Reuters confirms Alice Smith is now CEO of Acme Corp. " * 4
TEXT_3 = "Acme Corporation reported record earnings in New York. " * 4

# Entity type ids: 0 Entity, 1 Person, 2 Organization, 3 Location
EXTRACTIONS = {
    "Alice Smith became CEO": {
        "extracted_entities": [
            {"name": "Alice Smith", "entity_type_id": 1},
            {"name": "Acme Corp", "entity_type_id": 2},
            {"name": "Beta Group", "entity_type_id": 2},
            {"name": "Zanzibar Holdings", "entity_type_id": 2},  # not in the text
        ],
        "edges": [
            {
                "source_entity_name": "Alice Smith",
                "target_entity_name": "Acme Corp",
                "relation_type": "CEO_OF",
                "fact": "Alice Smith is the CEO of Acme Corp",
            },
            {
                "source_entity_name": "Beta Group",
                "target_entity_name": "Acme Corp",
                "relation_type": "OWNS",
                "fact": "Beta Group owned Acme Corp until January 2026",
            },
            {
                "source_entity_name": "Zanzibar Holdings",
                "target_entity_name": "Acme Corp",
                "relation_type": "PARTNERS_WITH",
                "fact": "Zanzibar Holdings partners with Acme Corp",
            },
        ],
    },
    "Reuters confirms": {
        "extracted_entities": [
            {"name": "Alice Smith", "entity_type_id": 1},
            {"name": "Acme Corp", "entity_type_id": 2},
        ],
        "edges": [
            {
                "source_entity_name": "Alice Smith",
                "target_entity_name": "Acme Corp",
                "relation_type": "CEO_OF",
                "fact": "Alice Smith is the CEO of Acme Corp",
            }
        ],
    },
    "Acme Corporation reported": {
        "extracted_entities": [{"name": "Acme Corporation", "entity_type_id": 2}],
        "edges": [],
    },
}
VALID = "2026-03-01T00:00:00Z"
for _body in EXTRACTIONS.values():
    for _e in _body["edges"]:
        _e.setdefault("valid_at", VALID)
        _e.setdefault("invalid_at", None)
# Facts with an end date: Graphiti stores invalid_at -> status HISTORICAL.
EXTRACTIONS["Alice Smith became CEO"]["edges"][1]["invalid_at"] = "2026-01-31T00:00:00Z"


class StubOpenAI:
    """OpenAI-compatible client: canned JSON keyed by Graphiti response schema."""

    def __init__(self):
        self.titles: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _canned(self, prompt: str) -> dict:
        import re

        m = re.search(
            r"<(TEXT|CURRENT_MESSAGE|CURRENT MESSAGE)>(.*?)</\1>", prompt, re.DOTALL
        )
        episode = m.group(2) if m else prompt
        for marker, body in EXTRACTIONS.items():
            if marker in episode:
                return body
        raise AssertionError(f"no canned extraction for prompt: {prompt[-400:]}")

    async def _create(self, *, messages, **_kw):
        prompt = "\n".join(m["content"] for m in messages)
        for title in (
            "ExtractedEntities",
            "ExtractedEdges",
            "EdgeTimestamps",
            "EdgeDuplicate",
            "NodeResolutions",
            "SummarizedEntities",
        ):
            if f'"title": "{title}"' in prompt:
                break
        else:
            raise AssertionError(f"unexpected Graphiti prompt: {prompt[:400]}")
        self.titles.append(title)
        if title == "ExtractedEntities":
            return self._reply(
                {"extracted_entities": self._canned(prompt)["extracted_entities"]}
            )
        if title == "ExtractedEdges":
            return self._reply({"edges": self._canned(prompt)["edges"]})
        if title == "EdgeTimestamps":
            return self._reply({"valid_at": None, "invalid_at": None})
        if title == "EdgeDuplicate":
            return self._reply({"duplicate_facts": [0], "contradicted_facts": []})
        if title == "NodeResolutions":
            return self._reply({"entity_resolutions": []})
        return self._reply({"summaries": []})

    @staticmethod
    def _reply(body: dict):
        msg = SimpleNamespace(content=json.dumps(body))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.fixture(scope="module")
def neo4j_container():
    from testcontainers.community.neo4j import Neo4jContainer

    with Neo4jContainer("neo4j:5.26-community") as c:
        yield c


@pytest.fixture
async def env(neo4j_container, tmp_path):
    from graphiti_core import Graphiti
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    emb = FakeEmbedder(dim=DIM)
    stub = StubOpenAI()
    graphiti = Graphiti(
        neo4j_container.get_connection_url(),
        neo4j_container.username,
        neo4j_container.password,
        llm_client=OpenAIGenericClient(
            LLMConfig(api_key="x", model="stub"),
            client=stub,
            structured_output_mode="json_object",
        ),
        embedder=BgeEmbedderClient(emb),
        cross_encoder=LocalCrossEncoder(emb),
    )
    await graphiti.driver.execute_query("MATCH (n) DETACH DELETE n")
    await graphiti.build_indices_and_constraints()
    ops = Neo4jGraphOps(graphiti.driver, DIM)
    await ops.ensure_schema()
    repo = Repository()
    for b in ("news", "finance"):
        await repo.create_bubble(
            Bubble(id=b, name=b, description=f"{b} d", updated_at=NOW)
        )
    settings = Settings(data_dir=str(tmp_path))
    writer = GraphWriter(
        graphiti,
        ops,
        GlobalEntityLinker(ops, emb, 0.88, 90),
        ChunkStore(str(tmp_path), emb, settings.chunk_tokens),
        repo,
        settings,
    )
    yield writer, graphiti, stub
    await graphiti.driver.execute_query("MATCH (n) DETACH DELETE n")
    await graphiti.close()


def item(id, title):
    return ItemRow(
        id=id, source_id="s", url=f"https://x.test/{id}", title=title, published_at=NOW
    )


def src(id, cred):
    return Source(id=id, type="rss", url="https://x.test/f", credibility=cred)


async def q(graphiti, query, **params):
    records, _, _ = await graphiti.driver.execute_query(query, **params)
    return [dict(r) for r in records]


async def test_episode_write_provenance_grounding_links_and_confidence(env):
    writer, graphiti, stub = env
    await writer.write(item("it1", "Alice at Acme"), TEXT_1, ["news"], src("s1", 0.5))
    await writer.write(
        item("it2", "Reuters on Alice"), TEXT_2, ["news"], src("s2", 0.9)
    )
    await writer.write(
        item("it3", "Acme earnings"), TEXT_3, ["finance"], src("s3", 0.7)
    )

    # Episode nodes carry the ledger.
    eps = await q(
        graphiti, "MATCH (e:Episodic) RETURN e.item_id AS i, e.source_url AS u"
    )
    assert sorted(e["i"] for e in eps) == ["it1", "it2", "it3"]
    assert all(e["u"].startswith("https://x.test/") for e in eps)

    # Every fact has item_id(s): the ledger rule.
    edges = await q(
        graphiti,
        "MATCH ()-[r:RELATES_TO]->() RETURN r.fact AS fact, r.item_ids AS item_ids, "
        "r.source_count AS sc, r.confidence AS conf, r.grounded AS grounded, "
        "r.status AS status",
    )
    assert len(edges) == 3
    assert all(e["item_ids"] for e in edges)
    by_fact = {e["fact"]: e for e in edges}

    # Corroboration: CEO fact asserted by two distinct sources.
    ceo = by_fact["Alice Smith is the CEO of Acme Corp"]
    assert sorted(ceo["item_ids"]) == ["it1", "it2"]
    assert ceo["sc"] == 2
    assert ceo["conf"] == pytest.approx(1 - (1 - 0.5) * (1 - 0.9))
    assert ceo["grounded"] is True and ceo["status"] == "VERIFIED"

    # Temporal: the fact with invalid_at is HISTORICAL.
    owns = by_fact["Beta Group owned Acme Corp until January 2026"]
    assert owns["status"] == "HISTORICAL" and owns["sc"] == 1
    assert owns["conf"] == pytest.approx(0.5)

    # Grounding: hallucinated entity flagged, edge too; nothing deleted.
    ghost = await q(
        graphiti, "MATCH (n:Entity {name: 'Zanzibar Holdings'}) RETURN n.grounded AS g"
    )
    assert ghost == [{"g": False}]
    assert by_fact["Zanzibar Holdings partners with Acme Corp"]["grounded"] is False
    real = await q(
        graphiti, "MATCH (n:Entity {name: 'Alice Smith'}) RETURN n.grounded AS g"
    )
    assert real == [{"g": True}]

    # SAME_AS: every entity linked; Acme in both bubbles shares one GlobalEntity.
    unlinked = await q(
        graphiti,
        "MATCH (n:Entity) WHERE NOT (n)-[:SAME_AS]->(:GlobalEntity) RETURN n.name AS n",
    )
    assert unlinked == []
    acme = await q(
        graphiti,
        "MATCH (n:Entity)-[:SAME_AS]->(g:GlobalEntity {type: 'Organization'}) "
        "WHERE n.name STARTS WITH 'Acme' "
        "RETURN g.uuid AS g, collect(DISTINCT n.group_id) AS groups, g.aliases AS aliases",
    )
    assert len(acme) == 1
    assert sorted(acme[0]["groups"]) == ["finance", "news"]
    assert "Acme Corporation" in acme[0]["aliases"]

    # Chunks in per-bubble collections; vector index live.
    client = writer._chunks._client
    assert {c.name for c in client.list_collections()} == {
        "bubble_news",
        "bubble_finance",
    }
    got = client.get_collection("bubble_news").get(include=["metadatas"])
    assert got["ids"]
    assert {m["item_id"] for m in got["metadatas"]} == {"it1", "it2"}
    assert "ExtractedEntities" in stub.titles


async def test_bubble_delete_removes_all_derived_data(env):
    from omnistream.router.bubbles import BubbleLifecycle

    writer, graphiti, _ = env
    await writer.write(item("it1", "Alice at Acme"), TEXT_1, ["news"], src("s1", 0.5))
    await writer.write(
        item("it3", "Acme earnings"), TEXT_3, ["finance"], src("s3", 0.7)
    )
    life = BubbleLifecycle(
        writer._repo, FakeEmbedder(dim=DIM), None, writer.ops, writer.chunks
    )
    counts = await life.counts("news")
    assert counts["episodes"] == 1 and counts["entities"] > 0 and counts["chunks"] > 0
    await life.delete("news")

    assert await life.counts("news") == {
        "episodes": 0, "entities": 0, "facts": 0, "chunks": 0, "sources": 0,
    }  # fmt: skip
    assert await q(graphiti, "MATCH (n {group_id: 'news'}) RETURN n") == []
    # SAME_AS from the deleted group's entities is gone and no GlobalEntity is orphaned.
    assert (
        await q(
            graphiti, "MATCH (g:GlobalEntity) WHERE NOT ()-[:SAME_AS]->(g) RETURN g"
        )
        == []
    )
    # News-only GlobalEntities are gone; the Acme one shared with finance survives.
    remaining = await q(graphiti, "MATCH (g:GlobalEntity) RETURN g.type AS t")
    assert remaining == [{"t": "Organization"}]
    assert await q(graphiti, "MATCH (:Entity)-[r:SAME_AS]->() RETURN r") != []
    # Chroma collection dropped for news, kept for finance.
    names = {c.name for c in writer._chunks._client.list_collections()}
    assert names == {"bubble_finance"}
    # The other bubble is untouched.
    assert (await life.counts("finance"))["episodes"] == 1


async def test_retry_recovers_committed_episode_without_reextracting(env, monkeypatch):
    from unittest.mock import AsyncMock

    writer, graphiti, _ = env
    link = writer._linker.link
    monkeypatch.setattr(
        writer._linker, "link", AsyncMock(side_effect=RuntimeError("link unavailable"))
    )
    with pytest.raises(RuntimeError, match="link unavailable"):
        await writer.write(
            item("retry-item", "Alice at Acme"), TEXT_1, ["news"], src("s1", 0.5)
        )
    # Also recover the crash window between Graphiti commit and provenance tagging.
    await q(graphiti, "MATCH (ep:Episodic) REMOVE ep.item_id")
    monkeypatch.setattr(writer._linker, "link", link)
    monkeypatch.setattr(
        graphiti, "add_episode", AsyncMock(side_effect=AssertionError("must resume"))
    )
    restarted = GraphWriter(
        graphiti,
        writer.ops,
        writer._linker,
        writer.chunks,
        writer._repo,
        writer._settings,
    )
    await restarted.write(
        item("retry-item", "Alice at Acme"), TEXT_1, ["news"], src("s1", 0.5)
    )
    records = await q(
        graphiti,
        "MATCH ()-[r:RELATES_TO]->() RETURN r.item_id AS item, r.grounded AS grounded",
    )
    assert records and all(
        r["item"] == "retry-item" and isinstance(r["grounded"], bool) for r in records
    )
    unlinked = await q(
        graphiti,
        "MATCH (n:Entity) WHERE NOT (n)-[:SAME_AS]->(:GlobalEntity) RETURN n.uuid AS id",
    )
    assert not unlinked
    assert await writer.chunks.count("news") > 0

    # A later unrelated expiration in this group must not be recovered or retagged.
    await q(
        graphiti,
        "CREATE (a:Entity {uuid: 'unrelated-a', group_id: 'news'}), "
        "(b:Entity {uuid: 'unrelated-b', group_id: 'news'}), "
        "(a)-[:RELATES_TO {uuid: 'unrelated-edge', group_id: 'news', "
        "episodes: ['another-episode'], expired_at: datetime() + duration('P1D')}]->(b)",
    )
    recovered = await writer.ops.recover_episode("retry-item", "news")
    assert "unrelated-edge" not in {edge.uuid for edge in recovered.edges}
    before = await q(graphiti, "MATCH (g:GlobalEntity) RETURN count(g) AS count")
    for node in recovered.nodes:
        await writer._linker.link(node.uuid, node.name, "Entity", embedding=[0.0] * DIM)
    assert (
        await q(graphiti, "MATCH (g:GlobalEntity) RETURN count(g) AS count") == before
    )
