from datetime import UTC, datetime

import pytest

from omnistream.models import Bubble, Entity, Fact, Source
from tests.conftest import DIM

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def vec(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def entity(id: str, type: str = "ORG", emb: list[float] | None = None, **kw) -> Entity:
    return Entity(
        id=id, canonical_name=kw.pop("canonical_name", id), type=type,
        embedding=emb or vec(0), **kw,
    )


def fact(id: str, bubble: str = "news", subject: str = "e1", **kw) -> Fact:
    base = {
        "id": id, "subject_id": subject, "relation": "CEO_OF", "object_id": "e2",
        "bubble_id": bubble, "source_id": "s1", "source_url": "http://x",
        "credibility": 0.5, "evidence_hashes": ["h"], "valid_from": NOW,
        "ingested_at": NOW,
    }
    base.update(kw)
    return Fact(**base)


async def test_mark_seen_then_has_seen(store):
    assert not await store.has_seen("h1")
    await store.mark_seen("h1", "s1")
    assert await store.has_seen("h1")


async def test_mark_seen_idempotent(store):
    await store.mark_seen("h1", "s1")
    await store.mark_seen("h1", "s1")
    assert await store.has_seen("h1")


async def test_bubble_round_trip(store):
    b = Bubble(id="news", name="News", description="d", updated_at=NOW)
    await store.create_bubble(b)
    assert await store.get_bubble("news") == b
    assert await store.get_bubble("nope") is None
    assert await store.list_bubbles() == [b]


async def test_source_upsert_round_trip_and_overwrite(store):
    s = Source(id="s1", type="rss", url="http://feed", bubble_ids=["news"])
    await store.upsert_source(s)
    assert await store.get_source("s1") == s
    assert await store.get_source("nope") is None
    s2 = s.model_copy(update={"credibility": 0.9, "last_error": "boom"})
    await store.upsert_source(s2)
    assert await store.get_source("s1") == s2
    assert await store.list_sources() == [s2]


async def test_vector_search_returns_raw_cosine(store):
    await store.create_entity(entity("a", emb=vec(0)))
    same = await store.search_entities(vec(0), "ORG", 5)
    assert same[0][1] == pytest.approx(1.0, abs=1e-3)
    orth = await store.search_entities(vec(1), "ORG", 5)
    assert orth[0][1] == pytest.approx(0.0, abs=1e-3)


async def test_vector_search_sorted_descending_and_limited(store):
    await store.create_entity(entity("a", emb=vec(0)))
    await store.create_entity(entity("b", emb=[1.0, 1.0] + [0.0] * (DIM - 2)))
    await store.create_entity(entity("c", emb=vec(1)))
    res = await store.search_entities(vec(0), "ORG", 2)
    assert [e.id for e, _ in res] == ["a", "b"]
    assert res[0][1] > res[1][1]


async def test_vector_search_filters_by_type(store):
    await store.create_entity(entity("org", "ORG"))
    await store.create_entity(entity("prod", "PRODUCT"))
    res = await store.search_entities(vec(0), "ORG", 5)
    assert [e.id for e, _ in res] == ["org"]


async def test_add_alias_deduplicates_case_insensitive(store):
    await store.create_entity(entity("a", canonical_name="Acme Corp", aliases=["Apple"]))
    await store.add_alias("a", "apple")
    await store.add_alias("a", "APPLE")
    await store.add_alias("a", "acme corp")
    e = await store.get_entity("a")
    assert e.aliases == ["Apple"]


async def test_add_alias_adds_new_alias(store):
    await store.create_entity(entity("a"))
    await store.add_alias("a", "Alpha")
    assert (await store.get_entity("a")).aliases == ["Alpha"]


async def test_add_alias_unknown_entity_raises(store):
    with pytest.raises(KeyError):
        await store.add_alias("ghost", "x")


async def test_returned_entity_is_a_copy(store):
    await store.create_entity(entity("a"))
    (await store.get_entity("a")).aliases.append("mutated")
    assert (await store.get_entity("a")).aliases == []


async def test_find_active_facts_excludes_historical(store):
    await store.create_fact(fact("f1"))
    await store.create_fact(fact("f2", status="HISTORICAL", valid_to=NOW))
    active = await store.find_active_facts("news", "e1", "CEO_OF")
    assert [f.id for f in active] == ["f1"]


async def test_update_fact_persists(store):
    await store.create_fact(fact("f1"))
    upd = fact("f1", status="HISTORICAL", valid_to=NOW, source_count=3)
    await store.update_fact(upd)
    assert await store.find_active_facts("news", "e1", "CEO_OF") == []
    [got] = await store.list_facts("news")
    assert got.status == "HISTORICAL" and got.valid_to == NOW and got.source_count == 3


async def test_update_fact_unknown_raises(store):
    with pytest.raises(KeyError):
        await store.update_fact(fact("ghost"))


async def test_facts_are_namespaced_by_bubble(store):
    await store.create_fact(fact("f1", bubble="news"))
    assert await store.list_facts("finance") == []
    assert [f.id for f in await store.list_facts("news")] == ["f1"]


async def test_entities_shared_across_bubbles(store):
    await store.create_entity(entity("e1"))
    await store.create_fact(fact("f1", bubble="news"))
    await store.create_fact(fact("f2", bubble="finance"))
    for b in ("news", "finance"):
        [f] = await store.list_facts(b)
        assert (await store.get_entity(f.subject_id)).id == "e1"


async def test_vector_search_type_filter_applies_before_k(store):
    # 6 closer PRODUCTs saturate Neo4j's k*5 oversample for k=1.
    for i in range(6):
        await store.create_entity(
            entity(f"p{i}", "PRODUCT", emb=[1.0, 0.01 * i] + [0.0] * (DIM - 2))
        )
    org_emb = [1.0, 1.0] + [0.0] * (DIM - 2)
    await store.create_entity(entity("org", "ORG", emb=org_emb))
    res = await store.search_entities(vec(0), "ORG", 1)
    assert [e.id for e, _ in res] == ["org"]
    assert res[0][1] == pytest.approx(2**-0.5, abs=1e-3)
    assert await store.search_entities(vec(0), "ORG", 0) == []
