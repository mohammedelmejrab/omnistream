import json

import httpx
import numpy as np
import pytest

from omnistream.llm import LLMClient, LLMError
from omnistream.retrieval.router import BubbleInfo, QueryRouter
from tests.conftest import load_llm_fixture

CATALOG = [
    BubbleInfo("news", "News", "EU ruling news", "secondary summary"),
    BubbleInfo("finance", "Finance", "share price finance"),
    BubbleInfo("research", "Research", "research papers"),
]


def router_for(reply, settings, embedder, mock_openai):
    client, transport = mock_openai(lambda body: reply)
    return QueryRouter(LLMClient(settings, client=client), embedder, CATALOG), transport


def test_recorded_fenced_reply(settings, embedder, mock_openai):
    fixture = load_llm_fixture("router_json")
    router, transport = router_for(
        httpx.Response(200, json=fixture["response"]), settings, embedder, mock_openai
    )
    result = router.route(fixture["request"]["messages"][-1]["content"])
    assert result.bubbles == ("news", "finance")
    assert result.strategy == "simple"
    assert result.time_scope is None
    assert not result.names_specific_item
    assert len(transport.requests) == 1
    data = json.loads(transport.bodies[0]["messages"][1]["content"])
    assert data["catalog"][0]["description"] == CATALOG[0].description
    assert data["catalog"][0]["auto_summary"] == "secondary summary"
    assert len(result.hints) == 3


@pytest.mark.parametrize(
    "reply",
    [
        {"bubbles": ["unknown", 2], "strategy": "bad", "names_specific_item": "true"},
        {"bubbles": "news"},
        [],
        None,
        7,
        {"bubbles": [], "strategy": []},
    ],
)
def test_invalid_shapes_fallback(reply, settings, embedder, mock_openai):
    router, _ = router_for(json.dumps(reply), settings, embedder, mock_openai)
    result = router.route("research papers")
    assert result.bubbles == ("research",)
    assert result.strategy == "simple"
    assert result.names_specific_item is False


def test_garbage_json_falls_back(settings, embedder, mock_openai):
    router, transport = router_for("not JSON", settings, embedder, mock_openai)
    assert router.route("share price finance").bubbles == ("finance",)
    assert len(transport.requests) == 1


def test_provider_error_propagates(settings, embedder):
    class Bad:
        def chat_json(self, messages):
            raise LLMError("no choices")

    with pytest.raises(LLMError, match="no choices"):
        QueryRouter(Bad(), embedder, CATALOG).route("q")


@pytest.mark.parametrize(
    "scope,valid",
    [
        ({"start": "2025-01-01", "end": None}, True),
        ({"start": None, "end": "2025-02-01T00:00:00Z"}, True),
        ({"start": "bad"}, False),
        ({"start": 3}, False),
        ({"start": "2025-02-01", "end": "2025-01-01"}, False),
        ([], False),
        ({"extra": 1}, False),
        ({}, False),
        ({"start": None, "end": None}, False),
        ({"start": None}, False),
    ],
)
def test_time_scope(scope, valid, settings, embedder, mock_openai):
    router, _ = router_for(
        json.dumps(
            {
                "bubbles": ["news", "news", "unknown"],
                "strategy": "multi_hop",
                "time_scope": scope,
                "names_specific_item": True,
            }
        ),
        settings,
        embedder,
        mock_openai,
    )
    result = router.route("during the review period")
    assert result.bubbles == ("news",)
    assert result.strategy == "multi_hop"
    assert result.names_specific_item
    assert (result.time_scope is not None) is valid


def test_overrides(settings, embedder, mock_openai):
    router, transport = router_for(
        '{"bubbles": ["news", "finance"]}', settings, embedder, mock_openai
    )
    assert router.route(
        "q", pins=["research", "research"], exclude=["finance"]
    ).bubbles == ("news", "research")
    assert router.route("news", exclude=["news", "finance"]).bubbles == ("research",)
    assert router.route("q", exclude=[b.id for b in CATALOG]).bubbles == ()
    count = len(transport.requests)
    with pytest.raises(ValueError, match="overlap"):
        router.route("q", pins=["news"], exclude=["news"])
    with pytest.raises(ValueError, match="unknown"):
        router.route("q", pins=["typo"])
    assert len(transport.requests) == count


def test_lazy_embeddings_and_precomputed(settings, embedder, encoder, mock_openai):
    client, _ = mock_openai(lambda _: "{}")
    vector = np.zeros(384)
    vector[0] = 1
    router = QueryRouter(
        LLMClient(settings, client=client),
        embedder,
        [
            BubbleInfo("a", "A", "must not embed", description_embedding=vector),
            CATALOG[0],
        ],
    )
    assert encoder.calls == []
    router.route("q")
    first = list(encoder.calls)
    router.route("q")
    assert encoder.calls == first
    assert not any("must not embed" in call for call in encoder.calls)


def test_empty_catalog(settings, embedder, mock_openai):
    client, transport = mock_openai(lambda _: "{}")
    assert (
        QueryRouter(LLMClient(settings, client=client), embedder, []).route("q").bubbles
        == ()
    )
    assert len(transport.requests) == 1


def test_live_catalog_router_preserves_injected_clock(embedder):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    class Catalog:
        def list(self):
            return [SimpleNamespace(to_bubble_info=lambda: CATALOG[0])]

    class Stub:
        def chat_json(self, messages):
            assert "2023-01-01" in messages[0]["content"]
            return {"bubbles": ["news"], "time_scope": {"end": "2024-12-07"}}

    router = QueryRouter(
        Stub(), embedder, Catalog(), now=lambda: datetime(2023, 1, 1, tzinfo=UTC)
    )
    assert router.route("Facts during December 7").time_scope.end.year == 2022


@pytest.mark.parametrize(
    "question,start,end",
    [
        ("What was committed on February 7?", None, None),
        ("What got committed on Feb 7?", None, None),
        *[
            (f"What {verb} on February 7?", None, None)
            for verb in ("were", "held", "valid", "effective")
        ],
        ("Who led X as of Feb 7?", "2026-02-07", "2026-02-07"),
        ("as of 7 Sept.", "2026-09-07", "2026-09-07"),
        ("as of 2025-02-07T12:00:00+03:00", "2025-02-07", "2025-02-07"),
        ("during February 29", "2024-02-29", "2024-02-29"),
        ("as of Sep. 7", "2026-09-07", "2026-09-07"),
        ("between October 1 and December 1", "2026-10-01", "2026-12-01"),
        ("between March 1 and April 1", "2026-03-01", "2026-04-01"),
        ("from December 1 to February 1", "2025-12-01", "2026-02-01"),
        ("between Q3 2024 and Q1 2025", "2024-07-01", "2025-03-31"),
        ("between 2024 and 2025", "2024-01-01", "2025-12-31"),
        ("news from Feb 7", None, None),
        ("as of 2025", "2025-12-31", "2025-12-31"),
        ("in 2025", "2025-01-01", "2025-12-31"),
        ("in March 2025", "2025-03-01", "2025-03-31"),
        ("in Q3 2025", "2025-07-01", "2025-09-30"),
        ("during third quarter", "2026-07-01", "2026-09-30"),
        ("during Q3", "2026-07-01", "2026-09-30"),
        ("during Q4", "2026-10-01", "2026-12-31"),
        ("before September 18", "2026-09-17", "2026-09-17"),
        ("prior to 2025-02-07", "2025-02-06", "2025-02-06"),
        ("after February 7", "2026-02-08", None),
        ("since February 7", "2026-02-07", None),
        ("until February 7", None, "2026-02-07"),
        ("till February 7", None, "2026-02-07"),
        ("during February 7", "2026-02-07", "2026-02-07"),
        ("immediately before the launch", None, None),
        ("immediately after the launch", None, None),
        *[(q, None, None) for q in ("currently", "now", "today", "at present")],
    ],
)
def test_deterministic_scope(question, start, end):
    from datetime import UTC, datetime

    from omnistream.retrieval.router import _parse_scope

    scope = _parse_scope(
        {"start": "2024-02-07", "end": "2024-04-01"},
        question,
        datetime(2026, 11, 12, tzinfo=UTC),
    )
    if start is None and end is None:
        assert scope is None
    else:
        assert tuple(
            b.date().isoformat() if b else None for b in (scope.start, scope.end)
        ) == (start, end)


def test_as_of_utc_day_end():
    from datetime import UTC, datetime

    from omnistream.retrieval.router import _parse_scope

    scope = _parse_scope(None, "as of Feb 7", datetime(2026, 11, 12, tzinfo=UTC))
    assert (
        scope.start == scope.end == datetime(2026, 2, 7, 23, 59, 59, 999999, tzinfo=UTC)
    )
