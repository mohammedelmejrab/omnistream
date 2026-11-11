from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from graphiti_core.nodes import EpisodeType
from pydantic import BaseModel

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.graph.chunks import ChunkStore
from omnistream.graph.graphiti_client import ENTITY_TYPES
from omnistream.graph.linker import GlobalEntityLinker
from omnistream.graph.ops import EdgeState
from omnistream.graph.writer import (
    BubbleSummary,
    GraphWriter,
    corroborate,
)
from omnistream.models import Bubble, Source
from tests.conftest import FakeEmbedder, FakeLLM
from tests.unit.test_linker import FakeGlobalStore

TEXT = "Alice Smith became CEO of Acme Corp in Berlin. " * 6
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def node(name, labels=("Entity", "Person"), new=True, uuid=None):
    return SimpleNamespace(
        uuid=uuid or f"n-{name}",
        name=name,
        labels=list(labels),
        attributes={},
        name_embedding=None,
        created_at=datetime.now(UTC) + timedelta(seconds=1 if new else -3600),
    )


def edge(uuid, src, dst, episodes, **kw):
    return SimpleNamespace(
        uuid=uuid,
        source_node_uuid=src,
        target_node_uuid=dst,
        episodes=episodes,
        **kw,
    )


class FakeGraphiti:
    def __init__(self, nodes, edges):
        self.nodes, self.edges = nodes, edges
        self.calls: list[dict] = []

    async def add_episode(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            episode=SimpleNamespace(uuid=f"ep{len(self.calls)}"),
            nodes=self.nodes,
            edges=self.edges,
        )


class FakeOps:
    def __init__(self):
        self.episodes: dict = {}
        self.edges: dict[str, dict] = {}
        self.grounded: dict[str, bool] = {}
        self.status_calls: list[list[str]] = []
        self.facts = ["Alice leads Acme"]

    async def recover_episode(self, item_id, group_id):
        return None

    async def tag_episode(self, uuid, item_id, source_url, credibility, source_id):
        self.episodes[uuid] = (item_id, source_url, credibility, source_id)

    async def get_edge_states(self, uuids):
        return {
            u: EdgeState(
                self.edges.get(u, {}).get("item_ids", []),
                self.edges.get(u, {}).get("source_ids", []),
                self.edges.get(u, {}).get("credibilities", []),
                self.edges.get(u, {}).get("grounded"),
                self.edges.get(u, {}).get("published_at"),
            )
            for u in uuids
        }

    async def set_edge_props(self, uuid, props):
        self.edges.setdefault(uuid, {}).update(props)

    async def set_edge_statuses(self, uuids):
        self.status_calls.append(uuids)

    async def set_node_grounded(self, uuid, grounded):
        self.grounded[uuid] = grounded

    async def recent_facts(self, group_id, limit):
        return self.facts


def make_item(id="item1"):
    return ItemRow(
        id=id,
        source_id="s1",
        url="https://x.test/a",
        title="Alice at Acme",
        published_at=NOW,
    )


def make_source(id="s1", cred=0.5):
    return Source(id=id, type="rss", url="https://x.test/f", credibility=cred)


async def build(tmp_path, graphiti, llm=None, **settings):
    repo = Repository()
    for b in ("news", "finance"):
        await repo.create_bubble(
            Bubble(id=b, name=b, description=f"{b} d", updated_at=NOW)
        )
    ops, gstore = FakeOps(), FakeGlobalStore()
    emb = FakeEmbedder()
    st = Settings(data_dir=str(tmp_path), **settings)
    writer = GraphWriter(
        graphiti,
        ops,
        GlobalEntityLinker(gstore, emb, 0.88, 90),
        ChunkStore(str(tmp_path), emb, st.chunk_tokens),
        repo,
        st,
        llm,
    )
    return writer, ops, gstore, repo


def test_corroborate_formula_distinct_sources():
    ids, creds, conf = corroborate(EdgeState(), "a", 0.5)
    assert (ids, conf) == (["a"], 0.5)
    ids, creds, conf = corroborate(EdgeState([], ids, creds), "b", 0.9)
    assert ids == ["a", "b"]
    assert conf == pytest.approx(1 - 0.5 * 0.1)
    # Same source again does not count twice.
    ids, creds, conf = corroborate(EdgeState([], ids, creds), "a", 0.5)
    assert len(ids) == 2 and conf == pytest.approx(0.95)


async def test_add_episode_arguments(tmp_path):
    g = FakeGraphiti([], [])
    w, *_ = await build(tmp_path, g)
    await w.write(make_item(), TEXT, ["news"], make_source())
    call = g.calls[0]
    assert call["name"] == "Alice at Acme"
    assert call["episode_body"] == TEXT
    assert call["source"] == EpisodeType.text
    assert call["reference_time"] == NOW
    assert call["group_id"] == "news"
    assert call["entity_types"] is ENTITY_TYPES
    import json

    assert json.loads(call["source_description"]) == {
        "item_id": "item1",
        "url": "https://x.test/a",
        "credibility": 0.5,
        "source_id": "s1",
    }


async def test_full_write_flags_links_and_edges(tmp_path):
    alice, acme = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    ghost = node("Zanzibar Holdings", ("Entity", "Organization"))
    old = node("Berlin", ("Entity", "Location"), new=False)
    edges = [
        edge("e1", alice.uuid, acme.uuid, ["ep1"], invalid_at=None, expired_at=None),
        edge("e2", ghost.uuid, acme.uuid, ["ep1"]),
        edge("e3", alice.uuid, old.uuid, ["ep0"], expired_at=NOW),  # only invalidated
    ]
    g = FakeGraphiti([alice, acme, ghost, old], edges)
    w, ops, gstore, repo = await build(tmp_path, g)
    res = await w.write(make_item(), TEXT, ["news"], make_source(cred=0.6))

    assert ops.episodes["ep1"] == ("item1", "https://x.test/a", 0.6, "s1")
    # grounding: only new nodes checked; ungrounded flagged, never removed
    assert ops.grounded == {alice.uuid: True, acme.uuid: True, ghost.uuid: False}
    assert res.entities_new == 3 and res.entities_ungrounded == 1
    # global links for every new entity, none for the existing one
    assert {e for e, _ in gstore.links} == {alice.uuid, acme.uuid, ghost.uuid}
    # ledger: asserted edges carry item ids; e3 untouched except status
    assert ops.edges["e1"]["published_at"] == NOW
    assert ops.edges["e2"]["published_at"] == NOW
    assert ops.edges["e1"]["item_ids"] == ["item1"]
    assert ops.edges["e1"]["grounded"] is True
    assert ops.edges["e2"]["grounded"] is False
    assert "e3" not in ops.edges
    assert ops.edges["e1"]["source_count"] == 1
    assert ops.edges["e1"]["confidence"] == pytest.approx(0.6)
    # temporal re-check covers invalidated edges too
    assert ops.status_calls == [["e1", "e2", "e3"]]
    assert res.edges == 2 and res.chunks >= 1
    assert await repo.episodes_since_summary("news") == 1
    assert await repo.episodes_since_summary("finance") == 0


async def test_every_asserted_edge_has_item_id(tmp_path):
    a, b = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    g = FakeGraphiti([a, b], [edge(f"e{i}", a.uuid, b.uuid, ["ep1"]) for i in range(3)])
    w, ops, *_ = await build(tmp_path, g)
    await w.write(make_item(), TEXT, ["news"], make_source())
    assert all(e["item_ids"] == ["item1"] for e in ops.edges.values())


async def test_second_source_corroborates_and_keeps_item_ids(tmp_path):
    a, b = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    e = edge("e1", a.uuid, b.uuid, ["ep1"])
    g = FakeGraphiti([a, b], [e])
    w, ops, *_ = await build(tmp_path, g)
    await w.write(make_item("item1"), TEXT, ["news"], make_source("s1", 0.5))
    g.nodes = [
        node("Alice Smith", new=False, uuid=a.uuid),
        node("Acme Corp", ("Entity", "Organization"), new=False, uuid=b.uuid),
    ]
    g.edges = [edge("e1", a.uuid, b.uuid, ["ep1", "ep2"])]
    await w.write(make_item("item2"), TEXT, ["news"], make_source("s2", 0.9))
    got = ops.edges["e1"]
    assert got["item_ids"] == ["item1", "item2"]
    assert got["source_ids"] == ["s1", "s2"] and got["source_count"] == 2
    assert got["confidence"] == pytest.approx(1 - 0.5 * 0.1)


async def test_ungrounded_edge_is_not_promoted(tmp_path):
    a, b = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    g = FakeGraphiti([a, b], [edge("e1", a.uuid, b.uuid, ["ep1"])])
    w, ops, *_ = await build(tmp_path, g)
    ops.edges["e1"] = {"grounded": False}
    await w.write(make_item(), TEXT, ["news"], make_source())
    assert ops.edges["e1"]["grounded"] is False


async def test_multi_bubble_writes_one_episode_each(tmp_path):
    g = FakeGraphiti([], [])
    w, _, _, repo = await build(tmp_path, g)
    res = await w.write(make_item(), TEXT, ["news", "finance"], make_source())
    assert [c["group_id"] for c in g.calls] == ["news", "finance"]
    assert len(res.episode_uuids) == 2
    assert await repo.episodes_since_summary("finance") == 1


async def test_summary_refresh_at_threshold_touches_only_auto_summary(tmp_path):
    llm = FakeLLM({BubbleSummary: BubbleSummary(summary="Fresh overview")})
    w, _ops, _, repo = await build(
        tmp_path, FakeGraphiti([], []), llm, summary_refresh_episodes=2, llm_model="m"
    )
    await w.write(make_item("i1"), TEXT, ["news"], make_source())
    assert llm.calls == []
    await w.write(make_item("i2"), TEXT, ["news"], make_source())
    assert len(llm.calls) == 1
    assert "Alice leads Acme" in llm.calls[0][1]
    b = await repo.get_bubble("news")
    assert b.auto_summary == "Fresh overview"
    assert b.description == "news d"
    assert await repo.episodes_since_summary("news") == 0


async def test_summary_failure_does_not_fail_write(tmp_path):
    def boom(_):
        raise RuntimeError("llm down")

    llm = FakeLLM({BubbleSummary: boom})
    w, *_ = await build(tmp_path, FakeGraphiti([], []), llm, summary_refresh_episodes=1)
    await w.write(make_item(), TEXT, ["news"], make_source())  # no raise


def test_bubble_summary_is_pydantic():
    assert issubclass(BubbleSummary, BaseModel)


async def test_asserted_edges_use_ingestion_reference_when_item_date_missing(tmp_path):
    alice, acme = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    graphiti = FakeGraphiti(
        [alice, acme], [edge("dated", alice.uuid, acme.uuid, ["ep1"])]
    )
    writer, ops, *_ = await build(tmp_path, graphiti)
    item = make_item()
    item.published_at = None
    await writer.write(item, TEXT, ["news"], make_source())
    assert ops.edges["dated"]["published_at"] == graphiti.calls[0]["reference_time"]


@pytest.mark.parametrize(
    "dates",
    [(NOW, NOW - timedelta(days=10)), (NOW - timedelta(days=10), NOW), (NOW, NOW)],
)
async def test_corroboration_keeps_newest_primary_provenance(tmp_path, dates):
    g = FakeGraphiti([], [edge("e", "a", "b", ["ep1", "ep2"])])
    w, ops, _, repo = await build(tmp_path, g)
    try:
        for n, date in enumerate(dates):
            item = make_item(f"i{n}")
            item.published_at = date
            await w.write(item, TEXT, ["news"], make_source(f"s{n}", 0.5))
        state = ops.edges["e"]
        assert state["published_at"] == max(dates)
        assert state["item_id"] == ("i1" if dates[1] > dates[0] else "i0")
        assert state["item_ids"] == ["i0", "i1"]
        assert state["source_count"] == 2
        assert state["confidence"] == pytest.approx(0.75)
    finally:
        await repo.close()
        w.chunks._client.close()


async def test_retry_resumes_committed_episode_and_reprocesses_original_new_nodes(
    tmp_path,
):
    from unittest.mock import AsyncMock

    a, b = node("Alice Smith"), node("Acme Corp", ("Entity", "Organization"))
    g = FakeGraphiti([a, b], [edge("e1", a.uuid, b.uuid, ["ep1"])])
    writer, ops, store, repo = await build(tmp_path, g)
    original_link = writer._linker.link
    writer._linker.link = AsyncMock(side_effect=RuntimeError("linker unavailable"))
    with pytest.raises(RuntimeError, match="linker unavailable"):
        await writer.write(make_item(), TEXT, ["news"], make_source())
    committed = SimpleNamespace(
        episode=SimpleNamespace(uuid="ep1", created_at=NOW),
        nodes=g.nodes,
        edges=g.edges,
    )
    # Simulate a retry long after extraction; these nodes still need linking.
    for n in g.nodes:
        n.created_at = NOW + timedelta(seconds=1)
    ops.recover_episode = AsyncMock(return_value=committed)
    writer._linker.link = original_link
    result = await writer.write(make_item(), TEXT, ["news"], make_source())
    assert len(g.calls) == 1
    assert result.entities_new == 2
    assert ops.edges["e1"]["item_id"] == "item1"
    assert ops.edges["e1"]["published_at"] == NOW
    assert ops.edges["e1"]["grounded"] is True
    assert {entity for entity, _ in store.links} == {a.uuid, b.uuid}
    assert await writer.chunks.count("news") > 0
    await repo.close()
