from datetime import UTC, datetime

from omnistream.ingest.route import BubbleChoice, Router
from omnistream.llm import LLMError
from omnistream.models import Bubble, RawItem, Source
from tests.conftest import FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUBBLES = [
    Bubble(id=i, name=i.title(), description=f"{i} topics", updated_at=NOW)
    for i in ("news", "finance", "tech")
]


def item(**kw) -> RawItem:
    base = {"source_id": "s1", "url": "https://x.test/a", "title": "T", "text": "body"}
    return RawItem(**{**base, **kw})


def source(**kw) -> Source:
    base = {"id": "s1", "type": "rss", "url": "https://x.test/feed"}
    return Source(**{**base, **kw})


def router(resp) -> tuple[Router, FakeLLM]:
    fake = FakeLLM({BubbleChoice: resp})
    return Router(fake, "m"), fake


async def test_item_override_wins_and_skips_llm():
    r, fake = router(BubbleChoice(bubble_ids=["tech"]))
    out = await r.route(
        item(bubble_ids_override=["finance", "finance", "nope"]),
        source(bubble_ids=["news"]),
        BUBBLES,
    )
    assert out == ["finance"]
    assert fake.calls == []


async def test_unknown_only_override_falls_through():
    r, fake = router(BubbleChoice(bubble_ids=["tech"]))
    out = await r.route(item(bubble_ids_override=["nope"]), source(), BUBBLES)
    assert out == ["tech"]
    assert len(fake.calls) == 1


async def test_manual_source_skips_llm():
    r, fake = router(BubbleChoice(bubble_ids=["tech"]))
    out = await r.route(item(), source(auto_route=False, bubble_ids=["news", "x"]), BUBBLES)
    assert out == ["news"]
    assert fake.calls == []


async def test_manual_source_with_no_valid_ids_uses_llm():
    r, fake = router(BubbleChoice(bubble_ids=["tech"]))
    out = await r.route(item(), source(auto_route=False, bubble_ids=["x"]), BUBBLES)
    assert out == ["tech"]
    assert len(fake.calls) == 1


async def test_classifier_can_pick_multiple_bubbles():
    r, fake = router(BubbleChoice(bubble_ids=["news", "finance"]))
    out = await r.route(
        item(title="Bank collapse", text="A major bank collapsed today. " * 100),
        source(),
        BUBBLES,
    )
    assert out == ["news", "finance"]
    user = fake.calls[0][1]
    assert "news | News | news topics" in user
    assert "Title: Bank collapse" in user
    text = user.split("Text: ", 1)[1]
    assert len(text) == 1500


async def test_classifier_unknown_ids_filtered():
    r, _ = router(BubbleChoice(bubble_ids=["bogus", "tech", "tech"]))
    assert await r.route(item(), source(), BUBBLES) == ["tech"]


async def test_classifier_empty_falls_back_to_source_bubbles():
    r, _ = router(BubbleChoice(bubble_ids=[]))
    out = await r.route(item(), source(bubble_ids=["finance"]), BUBBLES)
    assert out == ["finance"]


async def test_classifier_error_falls_back_to_source_bubbles():
    def boom(user: str):
        raise LLMError("down")

    r, _ = router(boom)
    out = await r.route(item(), source(bubble_ids=["finance"]), BUBBLES)
    assert out == ["finance"]


async def test_unrouted_returns_empty():
    r, _ = router(BubbleChoice(bubble_ids=[]))
    assert await r.route(item(), source(), BUBBLES) == []


async def test_no_bubbles_returns_empty_without_llm_call():
    r, fake = router(BubbleChoice(bubble_ids=["tech"]))
    out = await r.route(item(bubble_ids_override=["tech"]), source(bubble_ids=["tech"]), [])
    assert out == []
    assert fake.calls == []
