from datetime import UTC, datetime, timedelta

import pytest

from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.ingest.pipeline import ItemProcessor
from omnistream.llm import LLMError
from omnistream.models import Bubble, Source
from omnistream.router.bubbles import BubbleLifecycle, BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeChunks, FakeEmbedder, FakeLifecycleOps, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeWriter:
    def __init__(self):
        self.calls = []

    async def write(self, item, text, bubble_ids, source):
        self.calls.append((item.id, text, bubble_ids, source.id))


async def setup(tmp_path, response, source_bubbles=(), item_bubbles=()):
    repo = Repository()
    svc = BubbleService(repo, FakeEmbedder())
    await svc.create(Bubble(id="news", name="News", description="n"))
    await repo.upsert_source(
        Source(id="s", type="rss", url="u", bubble_ids=list(source_bubbles))
    )
    p = tmp_path / "t.txt"
    p.write_text("Body of the article", encoding="utf-8")
    await repo.create_item(
        ItemRow(
            id="i1",
            source_id="s",
            url="https://x/1",
            title="T",
            text_path=str(p),
            bubble_ids=list(item_bubbles),
            published_at=NOW,
        )
    )
    llm = FakeLLM({BubbleChoice: response})
    writer = FakeWriter()
    router = Router(llm, "m", FakeEmbedder())
    return repo, ItemProcessor(repo, router, writer), writer, router, llm


async def test_routed_item_is_written_with_stamps(tmp_path):
    repo, proc, writer, _, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=["news"], confidence=0.9)
    )
    await proc.process_item("i1")
    item = await repo.get_item("i1")
    assert item.status == "written" and item.route_confidence == 0.9
    assert item.bubble_ids == ["news"]
    assert item.routed_at and item.extracted_at and item.written_at
    assert writer.calls == [("i1", "Body of the article", ["news"], "s")]


async def test_low_confidence_is_unsorted_and_not_written(tmp_path):
    repo, proc, writer, _, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=["news"], confidence=0.2)
    )
    await proc.process_item("i1")
    item = await repo.get_item("i1")
    assert item.status == "unsorted" and item.routed_at and item.written_at is None
    assert writer.calls == []


async def test_explicit_item_bubbles_bypass_router(tmp_path):
    repo, proc, writer, _, llm = await setup(
        tmp_path,
        BubbleChoice(bubble_ids=[], confidence=0.0),
        item_bubbles=["news"],
    )
    await proc.process_item("i1")
    assert llm.calls == []
    assert writer.calls[0][2] == ["news"]
    assert (await repo.get_item("i1")).route_confidence == 1.0


async def test_llm_error_propagates_for_retry(tmp_path):
    def boom(user):
        raise LLMError("down")

    repo, proc, writer, _, _ = await setup(tmp_path, boom)
    with pytest.raises(LLMError):
        await proc.process_item("i1")
    assert writer.calls == []
    assert (await repo.get_item("i1")).status != "unsorted"


class FlakyWriter(FakeWriter):
    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = fail_on

    async def write(self, item, text, bubble_ids, source):
        if bubble_ids == [self.fail_on]:
            self.fail_on = None
            raise RuntimeError("neo4j down")
        await super().write(item, text, bubble_ids, source)


async def test_retry_skips_written_bubbles_and_keeps_router_confidence(tmp_path):
    repo, proc, _, router, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=["news", "sci"], confidence=0.8)
    )
    await BubbleService(repo, FakeEmbedder()).create(
        Bubble(id="sci", name="Sci", description="s")
    )
    writer = FlakyWriter(fail_on="sci")
    proc = ItemProcessor(repo, router, writer)
    with pytest.raises(RuntimeError):
        await proc.process_item("i1")
    assert (await repo.get_item("i1")).written_bubble_ids == ["news"]
    await proc.process_item("i1")
    item = await repo.get_item("i1")
    assert [c[2] for c in writer.calls] == [["news"], ["sci"]]
    assert item.status == "written" and item.route_confidence == 0.8
    assert item.written_bubble_ids == ["news", "sci"]


async def test_unknown_item_is_ignored(tmp_path):
    _, proc, writer, _, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=[], confidence=0)
    )
    await proc.process_item("nope")
    assert writer.calls == []


async def test_backfill_requeues_only_recent_items_routed_to_new_bubble(tmp_path):
    repo, _, _, router, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=["sci"], confidence=0.9)
    )
    old = tmp_path / "old.txt"
    old.write_text("old body")
    await repo.create_item(
        ItemRow(
            id="old",
            source_id="s",
            text_path=str(old),
            status="written",
            published_at=datetime.now(UTC) - timedelta(days=60),
        )
    )
    await repo.update_item(
        "i1", status="unsorted", published_at=datetime.now(UTC) - timedelta(days=2)
    )
    life = BubbleLifecycle(
        repo, FakeEmbedder(), router, FakeLifecycleOps(), FakeChunks()
    )
    created = await life.create(
        Bubble(id="sci", name="Sci", description="science"), backfill_days=30
    )
    assert created.id == "sci"
    i1 = await repo.get_item("i1")
    assert i1.status == "queued" and i1.bubble_ids == ["sci"]
    assert (await repo.get_item("old")).status == "written"
    assert [j.item_id for j in await repo.list_jobs("queued")] == ["i1"]


async def test_no_backfill_by_default(tmp_path):
    repo, _, _, router, _ = await setup(
        tmp_path, BubbleChoice(bubble_ids=["sci"], confidence=0.9)
    )
    await repo.update_item("i1", status="unsorted")
    life = BubbleLifecycle(
        repo, FakeEmbedder(), router, FakeLifecycleOps(), FakeChunks()
    )
    await life.create(Bubble(id="sci", name="Sci", description="s"))
    assert (await repo.get_item("i1")).status == "unsorted"
