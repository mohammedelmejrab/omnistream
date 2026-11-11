"""Legacy direct path (dedup + routing only); the queue pipeline arrives in Task 7."""

from datetime import UTC, datetime

from omnistream.db import Repository
from omnistream.ingest.normalize import content_hash
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.models import Bubble, RawItem, Source
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeEmbedder, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TEXT = "Alice became CEO of Acme Corp this week. " * 3


def item(text=TEXT, url="https://x.test/a") -> RawItem:
    return RawItem(source_id="s1", url=url, title="Headline", text=text)


def source() -> Source:
    return Source(id="s1", type="rss", url="https://x.test/feed")


async def setup(choice: BubbleChoice | None = None):
    repo = Repository()
    for b in ("news", "finance"):
        await BubbleService(repo, FakeEmbedder()).create(
            Bubble(id=b, name=b, description=f"{b} topics", updated_at=NOW)
        )
    fake = FakeLLM(
        {BubbleChoice: choice or BubbleChoice(bubble_ids=["news"], confidence=0.9)}
    )
    return repo, IngestPipeline(repo, Router(fake, "m", FakeEmbedder()))


async def test_routed_item_is_ingested_and_marked_seen():
    repo, pipe = await setup()
    it = item()
    res = await pipe.process(it, source())
    assert res.status == "ingested"
    assert res.item_hash == content_hash(it.url, it.text)
    assert res.bubble_ids == ["news"]
    assert await repo.has_seen(res.item_hash)


async def test_duplicate_is_skipped():
    _, pipe = await setup()
    await pipe.process(item(), source())
    assert (await pipe.process(item(), source())).status == "duplicate"


async def test_empty_text():
    _, pipe = await setup()
    assert (await pipe.process(item(text="  "), source())).status == "empty"


async def test_low_confidence_is_unrouted():
    _, pipe = await setup(BubbleChoice(bubble_ids=["news"], confidence=0.1))
    assert (await pipe.process(item(), source())).status == "unrouted"
