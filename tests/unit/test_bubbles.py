import json
import threading
from dataclasses import replace
from datetime import datetime
from typing import Any

import numpy as np
import pytest

from omnistream.bubbles import AutoSummaryRefresher, Bubble, InMemoryBubbleCatalog
from omnistream.retrieval.router import BubbleInfo, QueryRouter

OLD_SUMMARY = "old summary"
REFRESHED = "refreshed auto summary"
CREATED = datetime(2026, 1, 1, 12, 0, 0)
REFRESHED_AT = datetime(2026, 2, 1, 9, 30, 0)


class StubLLM:
    """Offline stand-in for ``LLMClient``: records prompts, returns one reply."""

    def __init__(self, reply: str = REFRESHED) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: Any, **kwargs: Any) -> str:
        self.calls.append([dict(message) for message in messages])
        return self.reply


class FlakyLLM:
    """Fails the first ``chat`` call, then succeeds (refresh retry test)."""

    def __init__(self, error: Exception | None = None, reply: str = REFRESHED) -> None:
        self.error = error or RuntimeError("provider down")
        self.reply = reply
        self.calls = 0

    def chat(self, messages: Any, **kwargs: Any) -> str:
        self.calls += 1
        if self.calls == 1:
            raise self.error
        return self.reply


def make_bubble(**overrides: Any) -> Bubble:
    fields: dict[str, Any] = {
        "id": "news",
        "name": "News",
        "description": "user-written news description",
        "description_embedding": np.full(384, 0.5, dtype=np.float32),
        "auto_summary": OLD_SUMMARY,
        "half_life_days": 30.0,
        "created_at": CREATED,
        "updated_at": CREATED,
    }
    fields.update(overrides)
    return Bubble(**fields)


def test_no_refresh_at_199():
    llm = StubLLM()
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm)
    for i in range(199):
        assert refresher.record_episodes("news", [f"episode-{i:03d}"]) is False
    assert llm.calls == []
    bubble = catalog.get("news")
    assert bubble.auto_summary == OLD_SUMMARY
    assert bubble.episodes_since_summary == 199
    assert bubble.updated_at == CREATED


def test_refresh_exactly_at_200():
    llm = StubLLM()
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm, now=lambda: REFRESHED_AT)
    for i in range(199):
        assert refresher.record_episodes("news", [f"episode-{i:03d}"]) is False
    assert refresher.record_episodes("news", ["episode-199"]) is True
    assert len(llm.calls) == 1  # exactly one LLM call per refresh
    bubble = catalog.get("news")
    assert bubble.auto_summary == REFRESHED
    assert bubble.episodes_since_summary == 0
    assert bubble.updated_at == REFRESHED_AT


def test_batch_crossing_threshold_carries_overflow():
    llm = StubLLM()
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm)
    episodes = [f"episode-{i:03d}" for i in range(205)]
    assert refresher.record_episodes("news", episodes) is True
    assert len(llm.calls) == 1
    bubble = catalog.get("news")
    assert bubble.auto_summary == REFRESHED
    assert bubble.episodes_since_summary == 5  # 205 - 200 overflow carried


def test_refresh_never_touches_description():
    llm = StubLLM()
    embedding = np.linspace(0.0, 1.0, 384).astype(np.float32)
    catalog = InMemoryBubbleCatalog([make_bubble(description_embedding=embedding)])
    refresher = AutoSummaryRefresher(catalog, llm)
    refresher.record_episodes("news", [f"episode-{i:03d}" for i in range(200)])
    bubble = catalog.get("news")
    assert bubble.description == "user-written news description"
    assert bubble.description_embedding is not None
    assert np.array_equal(bubble.description_embedding, embedding)
    assert bubble.id == "news"
    assert bubble.name == "News"
    assert bubble.created_at == CREATED


def test_prompt_uses_description_and_last_episodes_only():
    llm = StubLLM()
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm, max_episodes_in_prompt=50)
    episodes = [f"episode-{i:03d}" for i in range(220)]
    refresher.record_episodes("news", episodes)
    assert len(llm.calls) == 1
    content = "\n".join(message["content"] for message in llm.calls[0])
    assert "user-written news description" in content
    # The first boundary ends at episode 199, before the 20 overflow texts.
    for episode in episodes[150:200]:
        assert episode in content
    for episode in episodes[:150] + episodes[200:]:
        assert episode not in content


def test_llm_failure_keeps_old_summary_and_retries():
    llm = FlakyLLM(RuntimeError("provider down"))
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm)
    with pytest.raises(RuntimeError, match="provider down"):
        refresher.record_episodes("news", [f"episode-{i:03d}" for i in range(200)])
    bubble = catalog.get("news")
    assert bubble.auto_summary == OLD_SUMMARY
    assert bubble.episodes_since_summary >= 200  # stays at or above the threshold
    assert llm.calls == 1
    assert refresher.record_episodes("news", ["episode-200"]) is True
    bubble = catalog.get("news")
    assert bubble.auto_summary == REFRESHED
    assert bubble.episodes_since_summary == 1  # 201 - 200
    assert llm.calls == 2


def test_unknown_bubble_raises_keyerror():
    refresher = AutoSummaryRefresher(InMemoryBubbleCatalog([make_bubble()]), StubLLM())
    with pytest.raises(KeyError):
        refresher.record_episodes("missing", ["episode"])


@pytest.mark.parametrize("every", [0, -1, -200])
def test_invalid_every(every):
    with pytest.raises(ValueError, match="every"):
        AutoSummaryRefresher(InMemoryBubbleCatalog(), StubLLM(), every=every)


def test_concurrent_records_refresh_once_per_200():
    llm = StubLLM()
    catalog = InMemoryBubbleCatalog([make_bubble()])
    refresher = AutoSummaryRefresher(catalog, llm)

    def worker(start: int) -> None:
        for i in range(100):
            refresher.record_episodes("news", [f"episode-{start + i:04d}"])

    threads = [threading.Thread(target=worker, args=(k * 100,)) for k in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 400 episodes in total: exactly two refreshes, no extra LLM call.
    assert len(llm.calls) == 2
    bubble = catalog.get("news")
    assert bubble.auto_summary == REFRESHED
    assert bubble.episodes_since_summary == 0


def test_record_episodes_rejects_non_string_episodes():
    refresher = AutoSummaryRefresher(InMemoryBubbleCatalog([make_bubble()]), StubLLM())
    with pytest.raises(TypeError):
        refresher.record_episodes("news", ["fine", 42])
    with pytest.raises(TypeError):
        refresher.record_episodes("news", "single-episode-text")


def test_catalog_get_list_save():
    first, second = make_bubble(), make_bubble(id="finance", name="Finance")
    catalog = InMemoryBubbleCatalog([first, second])
    assert catalog.list() == (first, second)
    assert catalog.get("finance") is second
    catalog.save(Bubble(id="research", name="Research", description="research papers"))
    assert {b.id for b in catalog.list()} == {"news", "finance", "research"}
    with pytest.raises(KeyError):
        catalog.get("missing")


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": ""},
        {"name": " "},
        {"description": ""},
        {"half_life_days": 0},
        {"half_life_days": float("nan")},
        {"episodes_since_summary": -1},
        {"created_at": "2026-01-01"},
        {"description_embedding": [0.1, 0.2]},
    ],
)
def test_bubble_validation(overrides):
    with pytest.raises((ValueError, TypeError)):
        make_bubble(**overrides)


def test_to_bubble_info_round_trips_into_query_router(settings, embedder):
    class RouterLLM:
        def __init__(self) -> None:
            self.prompts: list[list[dict[str, str]]] = []

        def chat_json(self, messages: Any, **kwargs: Any) -> dict:
            self.prompts.append([dict(message) for message in messages])
            return {"bubbles": ["news"], "strategy": "simple"}

    llm = RouterLLM()
    catalog = InMemoryBubbleCatalog([make_bubble(auto_summary=OLD_SUMMARY)])
    refresher = AutoSummaryRefresher(catalog, StubLLM(reply=REFRESHED))
    refresher.record_episodes("news", [f"episode-{i:03d}" for i in range(200)])

    bubble = catalog.get("news")
    info = bubble.to_bubble_info()
    assert isinstance(info, BubbleInfo)
    assert info.auto_summary == REFRESHED
    assert info.description == "user-written news description"
    assert np.array_equal(info.description_embedding, bubble.description_embedding)

    router = QueryRouter(llm, embedder, [info])
    decision = router.route("news question")
    assert decision.bubbles == ("news",)
    payload = json.loads(llm.prompts[0][1]["content"])
    assert payload["catalog"][0]["auto_summary"] == REFRESHED
    assert payload["catalog"][0]["description"] == "user-written news description"
    assert payload["catalog"][0]["id"] == "news"


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_refresh_preserves_edits_and_increments_during_llm(fails, legacy):
    storage = InMemoryBubbleCatalog([make_bubble()])
    embedding = np.full(384, 0.75, dtype=np.float32)

    class LegacyCatalog:
        get = storage.get
        save = storage.save
        list = storage.list

    class EditingLLM:
        def chat(self, messages, **kwargs):
            current = storage.get("news")
            storage.save(
                replace(
                    current,
                    description="new user edit",
                    description_embedding=embedding,
                    episodes_since_summary=current.episodes_since_summary + 7,
                )
            )
            if fails:
                raise RuntimeError("provider down")
            return REFRESHED

    refresher = AutoSummaryRefresher(
        LegacyCatalog() if legacy else storage, EditingLLM()
    )
    if fails:
        with pytest.raises(RuntimeError, match="provider down"):
            refresher.record_episodes("news", ["episode"] * 200)
    else:
        assert refresher.record_episodes("news", ["episode"] * 200) is True
    bubble = storage.get("news")
    assert bubble.description == "new user edit"
    assert bubble.description_embedding is embedding
    assert bubble.episodes_since_summary == (207 if fails else 7)
    assert bubble.auto_summary == (OLD_SUMMARY if fails else REFRESHED)


@pytest.mark.parametrize("count, remainder", [(600, 0), (650, 50)])
def test_large_batch_refreshes_each_boundary(count, remainder):
    catalog = InMemoryBubbleCatalog([make_bubble()])
    llm = StubLLM()
    refresher = AutoSummaryRefresher(catalog, llm)
    episodes = [f"episode-{i:03d}" for i in range(count)]
    assert refresher.record_episodes("news", episodes) is True
    assert len(llm.calls) == 3
    assert catalog.get("news").episodes_since_summary == remainder
    for call, boundary in zip(llm.calls, (200, 400, 600)):
        content = call[1]["content"]
        included = [episode for episode in episodes if episode in content]
        assert included == episodes[boundary - 50 : boundary]


def test_large_batch_failure_keeps_success_and_retries_remaining_boundaries():
    catalog = InMemoryBubbleCatalog([make_bubble()])

    class SecondCallFails(StubLLM):
        def chat(self, messages, **kwargs):
            super().chat(messages, **kwargs)
            if len(self.calls) == 2:
                raise RuntimeError("second boundary failed")
            return f"summary-{len(self.calls)}"

    llm = SecondCallFails()
    refresher = AutoSummaryRefresher(catalog, llm)
    with pytest.raises(RuntimeError, match="second boundary failed"):
        refresher.record_episodes("news", [f"episode-{i:03d}" for i in range(600)])
    bubble = catalog.get("news")
    assert bubble.auto_summary == "summary-1"
    assert bubble.episodes_since_summary == 400
    assert len(llm.calls) == 2
    assert refresher.record_episodes("news", ["overflow"]) is True
    assert len(llm.calls) == 4
    assert llm.calls[1] == llm.calls[2]  # Retry the failed boundary exactly.
    assert "episode-599" in llm.calls[3][1]["content"]
    assert "overflow" not in llm.calls[3][1]["content"]
    assert catalog.get("news").auto_summary == "summary-4"
    assert catalog.get("news").episodes_since_summary == 1


def test_recursive_record_episodes_raises_and_can_retry():
    catalog = InMemoryBubbleCatalog([make_bubble()])

    class RecursiveLLM:
        def chat(self, messages, **kwargs):
            refresher.record_episodes("news", ["recursive episode"])
            return REFRESHED

    refresher = AutoSummaryRefresher(catalog, RecursiveLLM())
    with pytest.raises(RuntimeError, match="recursive record_episodes"):
        refresher.record_episodes("news", ["episode"] * 200)
    assert catalog.get("news").episodes_since_summary == 200
    refresher.llm = StubLLM()
    assert refresher.record_episodes("news", []) is True
    assert catalog.get("news").episodes_since_summary == 0


def test_catalog_update_is_atomic():
    catalog = InMemoryBubbleCatalog([make_bubble()])
    start = threading.Barrier(4)

    def worker():
        start.wait()
        for _ in range(100):
            catalog.update(
                "news",
                lambda current: replace(
                    current, episodes_since_summary=current.episodes_since_summary + 1
                ),
            )

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert catalog.get("news").episodes_since_summary == 400
    result = catalog.update("news", lambda current: replace(current, name="Edited"))
    assert result is catalog.get("news")
    with pytest.raises(KeyError):
        catalog.update("missing", lambda current: current)
