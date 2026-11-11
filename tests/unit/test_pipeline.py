import asyncio
from datetime import UTC, datetime

from omnistream.graph.extract import Extractor
from omnistream.graph.resolve import EntityResolver
from omnistream.graph.write import FactWriter
from omnistream.ingest.normalize import content_hash
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.llm import LLMError
from omnistream.models import (
    Bubble,
    ExtractedTriple,
    Extraction,
    RawItem,
    Source,
)
from omnistream.router.route import BubbleChoice, Router
from omnistream.store.memory import InMemoryStore
from tests.conftest import FakeEmbedder, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TEXT = "Alice became CEO of Acme Corp this week."


def triple(**kw) -> ExtractedTriple:
    base = {
        "subject": "Alice",
        "subject_type": "Person",
        "relation": "CEO_OF",
        "object": "Acme Corp",
        "object_type": "Organization",
    }
    return ExtractedTriple(**{**base, **kw})


def item(text=TEXT, url="https://x.test/a") -> RawItem:
    return RawItem(source_id="s1", url=url, title="Headline", text=text)


def source() -> Source:
    return Source(id="s1", type="rss", url="https://x.test/feed")


async def setup(extraction=None, bubbles=("news", "finance"), delay=0.0):
    store = InMemoryStore()
    for b in bubbles:
        await store.create_bubble(
            Bubble(id=b, name=b, description=f"{b} topics", updated_at=NOW)
        )
    fake = FakeLLM(
        {
            BubbleChoice: BubbleChoice(bubble_ids=list(bubbles)),
            Extraction: extraction or Extraction(triples=[triple()]),
        },
        delay=delay,
    )
    pipe = IngestPipeline(
        store,
        Router(fake, "m"),
        Extractor(fake, "m"),
        EntityResolver(store, FakeEmbedder(), 0.9, 90),
        FactWriter(store, clock=lambda: NOW),
        grounding_threshold=85,
    )
    return store, fake, pipe


async def test_happy_path_writes_facts_to_all_routed_bubbles():
    store, _, pipe = await setup()
    it = item()
    res = await pipe.process(it, source())
    assert res.status == "ingested"
    assert res.item_hash == content_hash(it.url, it.text)
    assert res.bubble_ids == ["news", "finance"]
    assert res.facts_created == 2
    assert res.dropped_ungrounded == 0
    facts_news = await store.list_facts("news")
    facts_finance = await store.list_facts("finance")
    assert len(facts_news) == 1
    assert len(facts_finance) == 1
    assert facts_news[0].subject_id == facts_finance[0].subject_id
    assert facts_news[0].object_id == facts_finance[0].object_id
    assert await store.has_seen(res.item_hash)


async def test_duplicate_item_skipped_before_llm():
    _, fake, pipe = await setup()
    await pipe.process(item(), source())
    n = len(fake.calls)
    res = await pipe.process(item(), source())
    assert res.status == "duplicate"
    assert len(fake.calls) == n


async def test_concurrent_duplicate_items_processed_once():
    _, fake, pipe = await setup(delay=0.01)
    r = await asyncio.gather(
        pipe.process(item(), source()), pipe.process(item(), source())
    )
    assert sorted(x.status for x in r) == ["duplicate", "ingested"]
    assert len(fake.calls) == 2  # one route + one extract


async def test_empty_text_returns_empty():
    store, fake, pipe = await setup()
    it = item(text="  \n ")
    res = await pipe.process(it, source())
    assert res.status == "empty"
    assert res.item_hash == content_hash(it.url, it.text)
    assert not await store.has_seen(res.item_hash)
    assert fake.calls == []


async def test_unrouted_item_not_marked_seen():
    store, fake, pipe = await setup(bubbles=())
    res = await pipe.process(item(), source())
    assert res.status == "unrouted"
    assert not await store.has_seen(res.item_hash)
    assert fake.calls == []


async def test_ungrounded_triples_counted_and_not_written():
    ext = Extraction(
        triples=[triple(), triple(subject="Zorblax Quux", object="Globex Inc")]
    )
    store, _, pipe = await setup(ext, bubbles=("news",))
    res = await pipe.process(item(), source())
    assert res.status == "ingested"
    assert res.dropped_ungrounded == 1
    assert res.facts_created == 1
    assert len(await store.list_facts("news")) == 1


async def test_item_with_no_triples_is_marked_seen():
    store, _, pipe = await setup(Extraction(triples=[]))
    res = await pipe.process(item(), source())
    assert res.status == "ingested"
    assert res.facts_created == 0
    assert await store.has_seen(res.item_hash)


async def test_merge_and_supersede_counters():
    store, fake, pipe = await setup(
        Extraction(triples=[triple(exclusive=True)]), bubbles=("news",)
    )
    r1 = await pipe.process(item(), source())
    assert (r1.facts_created, r1.facts_merged, r1.facts_superseded) == (1, 0, 0)

    # same triple from a different item -> merged
    r2 = await pipe.process(item(url="https://x.test/b"), source())
    assert (r2.facts_created, r2.facts_merged, r2.facts_superseded) == (0, 1, 0)

    # new object for an exclusive relation, later valid_from -> superseded
    text3 = "Alice is now CEO of Globex Inc, after Acme Corp."
    fake.responses[Extraction] = Extraction(
        triples=[
            triple(
                object="Globex Inc",
                exclusive=True,
                valid_from=datetime(2026, 3, 1, tzinfo=UTC),
            )
        ]
    )
    r3 = await pipe.process(item(text=text3, url="https://x.test/c"), source())
    assert (r3.facts_created, r3.facts_merged, r3.facts_superseded) == (1, 0, 1)
    statuses = sorted(f.status for f in await store.list_facts("news"))
    assert statuses == ["HISTORICAL", "VERIFIED"]


async def test_llm_failure_returns_failed_and_does_not_mark_seen():
    store, fake, pipe = await setup(bubbles=("news",))

    def boom(_user):
        raise LLMError("down")

    fake.responses[Extraction] = boom
    it = item()
    res = await pipe.process(it, source())
    h = content_hash(it.url, it.text)
    assert res.status == "failed"
    assert res.item_hash == h
    assert "LLMError" in (res.error or "")
    assert not await store.has_seen(h)

    fake.responses[Extraction] = Extraction(triples=[triple()])
    res2 = await pipe.process(it, source())
    assert res2.status == "ingested"


async def test_process_many_is_sequential_and_ordered():
    _, _, pipe = await setup(bubbles=("news",))
    items = [item(), item(), item(url="https://x.test/z")]
    out = await pipe.process_many(items, source())
    assert [r.status for r in out] == ["ingested", "duplicate", "ingested"]
