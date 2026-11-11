import threading
from dataclasses import replace
from datetime import datetime
from typing import Any

import numpy as np
import pytest

from omnistream.bubbles import AutoSummaryRefresher, Bubble, InMemoryBubbleCatalog

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


async def test_summary_refresh_delegates_to_c4():
    from unittest.mock import AsyncMock

    writer = AsyncMock()
    writer.maybe_refresh_summary.return_value = True
    assert await AutoSummaryRefresher(writer).maybe_refresh_summary("news") is True
    writer.maybe_refresh_summary.assert_awaited_once_with("news")
