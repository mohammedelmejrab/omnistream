from datetime import UTC, datetime

import pytest

from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.llm import LLMError
from omnistream.models import Bubble, RawItem, Source
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeEmbedder, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
# Axis-aligned vectors: item "Bank" is closest to finance, then news, tech, sport.
TABLE = {
    "news: news topics": [1, 0, 0, 0],
    "finance: finance topics": [0, 1, 0, 0],
    "tech: tech topics": [0, 0, 1, 0],
    "sport: sport topics": [0, 0, 0, 1],
    "T\nbody": [0.3, 0.9, 0.1, 0.0],
}
EMB = FakeEmbedder(TABLE, dim=4)


async def bubbles() -> list[Bubble]:
    svc = BubbleService(Repository(), EMB)
    return [
        await svc.create(
            Bubble(id=i, name=i, description=f"{i} topics", updated_at=NOW)
        )
        for i in ("news", "finance", "tech", "sport")
    ]


def item(**kw) -> RawItem:
    base = {"source_id": "s1", "url": "https://x.test/a", "title": "T", "text": "body"}
    return RawItem(**{**base, **kw})


def source(**kw) -> Source:
    return Source(**{"id": "s1", "type": "rss", "url": "https://x.test/f", **kw})


def router(resp, **kw) -> tuple[Router, FakeLLM]:
    fake = FakeLLM({BubbleChoice: resp})
    return Router(fake, "m", EMB, **kw), fake


async def test_item_override_is_fixed_and_skips_llm():
    r, fake = router(BubbleChoice(bubble_ids=["tech"], confidence=0.9))
    d = await r.route(
        item(bubble_ids_override=["finance", "nope"]),
        source(bubble_ids=["news"]),
        await bubbles(),
    )
    assert (d.bubble_ids, d.confidence, d.unsorted) == (["finance"], 1.0, False)
    assert fake.calls == []


async def test_source_bubbles_are_fixed_and_skip_llm():
    r, fake = router(BubbleChoice(bubble_ids=["tech"], confidence=0.9))
    d = await r.route(item(), source(bubble_ids=["news"]), await bubbles())
    assert (d.bubble_ids, d.confidence) == (["news"], 1.0)
    assert fake.calls == []


async def test_llm_sees_only_top_3_candidates_with_secondary_hint():
    bs = await bubbles()
    bs[1] = bs[1].model_copy(update={"auto_summary": "banks and markets"})
    r, fake = router(BubbleChoice(bubble_ids=["finance", "news"], confidence=0.8))
    d = await r.route(item(), source(), bs)
    assert d.bubble_ids == ["finance", "news"]
    assert d.confidence == 0.8 and not d.unsorted
    user = fake.calls[0][1]
    assert "finance | finance | finance topics | banks and markets" in user
    assert "sport |" not in user  # fourth-ranked bubble is not a candidate


async def test_text_limited_to_2000_chars():
    r, fake = router(BubbleChoice(bubble_ids=["news"], confidence=0.9))
    await r.route(item(text="x" * 5000), source(), await bubbles())
    assert len(fake.calls[0][1].split("Text: ", 1)[1]) == 2000


async def test_ids_outside_candidates_are_dropped():
    r, _ = router(BubbleChoice(bubble_ids=["sport", "tech", "bogus"], confidence=0.9))
    d = await r.route(item(), source(), await bubbles())
    assert d.bubble_ids == ["tech"]  # sport is rank 4, not a candidate


@pytest.mark.parametrize(
    "choice",
    [
        BubbleChoice(bubble_ids=["news"], confidence=0.49),
        BubbleChoice(bubble_ids=[], confidence=0.9),
        BubbleChoice(bubble_ids=["bogus"], confidence=0.9),
    ],
)
async def test_low_confidence_or_empty_is_unsorted(choice):
    r, _ = router(choice)
    d = await r.route(item(), source(), await bubbles())
    assert d.unsorted and d.bubble_ids == []


async def test_threshold_boundary_is_inclusive():
    r, _ = router(BubbleChoice(bubble_ids=["news"], confidence=0.5))
    assert not (await r.route(item(), source(), await bubbles())).unsorted


async def test_llm_error_propagates_for_retry():
    def boom(user: str):
        raise LLMError("down")

    r, _ = router(boom)
    with pytest.raises(LLMError):
        await r.route(item(), source(), await bubbles())


async def test_no_bubbles_is_unsorted_without_llm_call():
    r, fake = router(BubbleChoice(bubble_ids=["tech"], confidence=0.9))
    assert (await r.route(item(), source(), [])).unsorted
    assert fake.calls == []


async def test_bubble_service_embeds_on_create_and_description_change():
    repo = Repository()
    svc = BubbleService(repo, EMB)
    b = await svc.create(Bubble(id="news", name="news", description="news topics"))
    assert b.description_embedding == (await EMB.embed(["news: news topics"]))[0]
    b2 = await svc.update("news", description="finance topics")
    assert b2.description_embedding != b.description_embedding
    b3 = await svc.update("news", auto_summary="s")  # unrelated: embedding kept
    assert b3.description_embedding == b2.description_embedding


async def test_assign_unsorted_sets_bubbles_queues_and_enqueues():
    repo = Repository()
    await repo.create_item(ItemRow(id="i1", source_id="s", status="unsorted"))
    row = await repo.assign_unsorted("i1", ["news", "news", "tech"])
    assert (row.status, row.bubble_ids) == ("queued", ["news", "tech"])
    assert [j.item_id for j in await repo.list_jobs("queued")] == ["i1"]


async def test_assign_unsorted_rejects_other_status_and_empty():
    repo = Repository()
    await repo.create_item(ItemRow(id="i1", source_id="s", status="written"))
    with pytest.raises(ValueError):
        await repo.assign_unsorted("i1", ["news"])
    with pytest.raises(ValueError):
        await repo.assign_unsorted("i1", [])
    with pytest.raises(KeyError):
        await repo.assign_unsorted("zz", ["news"])
