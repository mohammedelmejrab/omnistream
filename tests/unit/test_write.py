from datetime import UTC, datetime, timedelta

from omnistream.graph.write import FactWriter
from omnistream.models import RawItem, Source
from omnistream.store.memory import InMemoryStore

FIXED = datetime(2026, 6, 1, tzinfo=UTC)
T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = T1 + timedelta(days=100)
T3 = T1 + timedelta(days=200)


def item(published_at=T2, url="https://x.test/a") -> RawItem:
    return RawItem(
        source_id="s1", url=url, title="T", text="body", published_at=published_at
    )


def source(sid="s1", credibility=0.5) -> Source:
    return Source(
        id=sid, type="rss", url="https://x.test/feed", credibility=credibility
    )


def setup() -> tuple[InMemoryStore, FactWriter]:
    store = InMemoryStore()
    return store, FactWriter(store, clock=lambda: FIXED)


async def write(
    w, obj="acme", rel="CEO_OF", excl=False, vf=None, it=None, h="h1", src=None
):
    return await w.write(
        "alice", rel, obj, excl, vf, "b1", it or item(), h, src or source()
    )


async def test_new_fact_has_full_provenance():
    store, w = setup()
    it = item(published_at=T2, url="https://x.test/story")
    assert await write(w, it=it, src=source(credibility=0.8)) == "created"
    (f,) = await store.list_facts("b1")
    assert f.id
    assert f.subject_id == "alice"
    assert f.relation == "CEO_OF"
    assert f.object_id == "acme"
    assert f.bubble_id == "b1"
    assert f.source_id == "s1"
    assert f.source_url == it.url
    assert f.credibility == 0.8
    assert f.source_count == 1
    assert f.evidence_hashes == ["h1"]
    assert f.valid_from == it.published_at
    assert f.valid_to is None
    assert f.status == "VERIFIED"
    assert f.ingested_at == FIXED


async def test_valid_from_falls_back_to_clock():
    store, w = setup()
    await write(w, it=item(published_at=None))
    (f,) = await store.list_facts("b1")
    assert f.valid_from == FIXED


async def test_explicit_valid_from_wins():
    store, w = setup()
    await write(w, vf=T1)
    (f,) = await store.list_facts("b1")
    assert f.valid_from == T1


async def test_corroboration_increments_source_count_and_max_credibility():
    store, w = setup()
    await write(w, h="h1", src=source("s1", 0.5))
    assert await write(w, h="h2", src=source("s2", 0.9)) == "merged"
    (f,) = await store.list_facts("b1")
    assert f.source_count == 2
    assert f.credibility == 0.9
    assert f.evidence_hashes == ["h1", "h2"]
    assert f.status == "VERIFIED"


async def test_corroboration_never_lowers_credibility():
    store, w = setup()
    await write(w, h="h1", src=source("s1", 0.9))
    await write(w, h="h2", src=source("s2", 0.3))
    (f,) = await store.list_facts("b1")
    assert f.credibility == 0.9


async def test_retry_same_hash_is_idempotent():
    store, w = setup()
    await write(w, h="h1")
    assert await write(w, h="h1") == "merged"
    (f,) = await store.list_facts("b1")
    assert f.source_count == 1
    assert f.evidence_hashes == ["h1"]


async def test_exclusive_new_fact_supersedes_older():
    store, w = setup()
    await write(w, obj="acme", excl=True, it=item(T1), h="h1")
    assert await write(w, obj="globex", excl=True, it=item(T2), h="h2") == "superseded"
    by_obj = {f.object_id: f for f in await store.list_facts("b1")}
    assert by_obj["acme"].status == "HISTORICAL"
    assert by_obj["acme"].valid_to == T2
    assert by_obj["globex"].status == "VERIFIED"
    assert by_obj["globex"].valid_to is None


async def test_late_arriving_exclusive_fact_is_stored_historical():
    store, w = setup()
    await write(w, obj="globex", excl=True, it=item(T2), h="h2")
    assert await write(w, obj="acme", excl=True, it=item(T1), h="h1") == "created"
    by_obj = {f.object_id: f for f in await store.list_facts("b1")}
    assert by_obj["globex"].status == "VERIFIED"
    assert by_obj["globex"].valid_to is None
    late = by_obj["acme"]
    assert late.status == "HISTORICAL"
    assert late.valid_from == T1
    assert late.valid_to == T2
    assert late.source_count == 1
    assert late.evidence_hashes == ["h1"]
    assert late.source_id == "s1"
    assert late.ingested_at == FIXED


async def test_mixed_actives_historicize_older_and_bound_incoming():
    store, w = setup()
    await write(w, obj="acme", excl=True, it=item(T1), h="h1")
    # second active written non-exclusively so both are VERIFIED simultaneously
    await write(w, obj="globex", excl=False, it=item(T3), h="h3")
    assert await write(w, obj="initech", excl=True, it=item(T2), h="h2") == "superseded"
    by_obj = {f.object_id: f for f in await store.list_facts("b1")}
    assert by_obj["acme"].status == "HISTORICAL"
    assert by_obj["acme"].valid_to == T2
    assert by_obj["globex"].status == "VERIFIED"
    assert by_obj["globex"].valid_to is None
    assert by_obj["initech"].status == "HISTORICAL"
    assert by_obj["initech"].valid_from == T2
    assert by_obj["initech"].valid_to == T3


async def test_retry_late_arriving_fact_does_not_duplicate():
    store, w = setup()
    await write(w, obj="globex", excl=True, it=item(T2), h="h2")
    await write(w, obj="acme", excl=True, it=item(T1), h="h1")
    assert await write(w, obj="acme", excl=True, it=item(T1), h="h1") == "merged"
    facts = await store.list_facts("b1")
    assert len(facts) == 2


async def test_non_exclusive_relation_keeps_both_verified():
    store, w = setup()
    await write(w, obj="a", rel="ACQUIRED", excl=False, it=item(T1), h="h1")
    assert (
        await write(w, obj="b", rel="ACQUIRED", excl=False, it=item(T2), h="h2")
        == "created"
    )
    facts = await store.list_facts("b1")
    assert {f.status for f in facts} == {"VERIFIED"}
    assert len(facts) == 2


async def test_same_object_merges_even_when_exclusive():
    store, w = setup()
    await write(w, excl=True, it=item(T1), h="h1")
    assert (
        await write(w, excl=True, it=item(T2), h="h2", src=source("s2", 0.7))
        == "merged"
    )
    (f,) = await store.list_facts("b1")
    assert f.status == "VERIFIED"
    assert f.source_count == 2


async def test_naive_valid_from_assumed_utc():
    store, w = setup()
    await write(w, vf=datetime(2026, 1, 1))
    (f,) = await store.list_facts("b1")
    assert f.valid_from == T1
    assert f.valid_from.tzinfo is not None


async def test_supersession_is_per_bubble():
    store, w = setup()
    await w.write(
        "alice", "CEO_OF", "acme", True, None, "news", item(T1), "h1", source()
    )
    await w.write(
        "alice", "CEO_OF", "globex", True, None, "finance", item(T2), "h2", source()
    )
    (news,) = await store.list_facts("news")
    (fin,) = await store.list_facts("finance")
    assert news.status == "VERIFIED"
    assert news.valid_to is None
    assert fin.status == "VERIFIED"
