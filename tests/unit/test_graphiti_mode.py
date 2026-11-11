"""Deterministic fake Graphiti coverage for C5."""

import builtins
import threading
from datetime import datetime
from types import SimpleNamespace

import pytest

from omnistream.config import Settings
from omnistream.retrieval.graphiti_mode import GraphitiCoreSearcher, GraphitiRetriever
from omnistream.retrieval.models import TimeScope


def edge(i=1, **attrs):
    return SimpleNamespace(
        uuid=str(i),
        fact=f"fact{i}",
        name="leads",
        source_node_uuid="s",
        target_node_uuid=str(i),
        group_id="news",
        valid_at=datetime(2025, 1, 1),
        invalid_at=None,
        created_at=datetime(2025, 1, 2),
        episodes=[],
        attributes={
            "grounded": True,
            "item_id": f"item{i}",
            "source_url": "https://source",
            **attrs,
        },
    )


class Searcher:
    def __init__(self, edges):
        self.edges = edges
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.edges


def test_mapping_limit_and_filters():
    wrong = edge(4)
    wrong.group_id = "other"
    searcher = Searcher(
        [
            edge(1, grounded=False),
            edge(2, item_id=None),
            wrong,
            edge(3, credibility=0.8),
        ]
    )
    with GraphitiRetriever(searcher) as retriever:
        result = retriever.retrieve("q", bubbles=["news"])
        assert searcher.calls == [("q", {"group_ids": ["news"], "num_results": 60})]
        assert len(result.facts) == 1
        assert result.facts[0].score == 0.25
        assert result.facts[0].fact.item_id == "item3"
        assert result.facts[0].fact.credibility == 0.8
        assert retriever.skipped_missing_provenance == 1
        assert not retriever.retrieve(
            "q", bubbles=["news"], time_scope=TimeScope(end=datetime(2024, 1, 1))
        ).facts


def test_top_twenty_empty_and_invalid():
    with GraphitiRetriever(Searcher([edge(i) for i in range(30)])) as retriever:
        assert len(retriever.retrieve("q", bubbles=["news"]).facts) == 20
        assert len(retriever.retrieve("q", bubbles=["news"], top_k=2).facts) == 2
        assert not retriever.retrieve("q", bubbles=[]).facts
        with pytest.raises(ValueError):
            retriever.retrieve("q", bubbles=["news"], top_k=False)


@pytest.mark.asyncio
async def test_async_and_loop_guard():
    retriever = GraphitiRetriever(Searcher([edge()]))
    try:
        assert (await retriever.aretrieve("q", bubbles=["news"])).facts
        with pytest.raises(RuntimeError, match="aretrieve"):
            retriever.retrieve("q", bubbles=["news"])
    finally:
        await retriever.aclose()


def test_optional_import(monkeypatch):
    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "graphiti_core":
            raise ImportError("absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(ImportError, match="optional graphiti-core"):
        GraphitiCoreSearcher.from_settings(Settings(_env_file=None, llm_api_key="test"))


def test_exclusive_invalid_at():
    old = edge()
    old.invalid_at = datetime(2025, 2, 1)
    with GraphitiRetriever(Searcher([old])) as retriever:
        result = retriever.retrieve(
            "q", bubbles=["news"], time_scope=TimeScope(start=datetime(2025, 2, 1))
        )
        assert not result.facts


@pytest.mark.parametrize("grounded", [None, False, "true", 1])
def test_only_explicit_boolean_grounding_is_accepted(grounded):
    candidate = edge(grounded=grounded)
    if grounded is None:
        del candidate.attributes["grounded"]
    with GraphitiRetriever(Searcher([candidate])) as retriever:
        assert not retriever.retrieve("q", bubbles=["news"]).facts


@pytest.mark.parametrize("limit", [2, 20])
def test_overfetch_fills_limit_after_filters_preserving_original_ranks(limit):
    wrong = edge(3)
    wrong.group_id = "other"
    expired = edge(4)
    expired.invalid_at = datetime(2025, 2, 1)
    candidates = [edge(1, grounded=False), edge(2, item_id=None), wrong, expired]
    candidates += [edge(i) for i in range(5, 50)]

    class LimitedSearcher(Searcher):
        async def search(self, query, **kwargs):
            return (await super().search(query, **kwargs))[: kwargs["num_results"]]

    searcher = LimitedSearcher(candidates)
    with GraphitiRetriever(searcher) as retriever:
        retrieved = retriever.retrieve(
            "q",
            bubbles=["news"],
            top_k=limit,
            time_scope=TimeScope(start=datetime(2025, 2, 1)),
        )
        assert len(retrieved.facts) == limit
        assert [f.fact.id for f in retrieved.facts] == [
            str(i) for i in range(5, 5 + limit)
        ]
        assert [f.score for f in retrieved.facts] == [
            1 / i for i in range(5, 5 + limit)
        ]
        assert [f.ranks["graphiti"] for f in retrieved.facts] == list(
            range(5, 5 + limit)
        )
        assert searcher.calls[0][1]["num_results"] == limit * 3


def test_progressive_overfetch_fills_after_41_rejections_without_duplicates():
    class LimitedSearcher(Searcher):
        async def search(self, query, **kwargs):
            return (await super().search(query, **kwargs))[: kwargs["num_results"]]

    searcher = LimitedSearcher(
        [edge(i, item_id=None) for i in range(1, 42)] + [edge(i) for i in range(42, 62)]
    )
    with GraphitiRetriever(searcher) as retriever:
        result = retriever.retrieve("q", bubbles=["news"])
        assert [f.fact.id for f in result.facts] == [str(i) for i in range(42, 62)]
        assert [f.ranks["graphiti"] for f in result.facts] == list(range(42, 62))
        assert [f.score for f in result.facts] == [1 / i for i in range(42, 62)]
        assert [call[1]["num_results"] for call in searcher.calls] == [60, 120]
        assert retriever.skipped_missing_provenance == 41


def test_progressive_overfetch_stops_at_safety_cap():
    class LimitedSearcher(Searcher):
        async def search(self, query, **kwargs):
            return (await super().search(query, **kwargs))[: kwargs["num_results"]]

    searcher = LimitedSearcher([edge(i, grounded=False) for i in range(1000)])
    with GraphitiRetriever(searcher) as retriever:
        assert not retriever.retrieve("q", bubbles=["news"]).facts
        assert [call[1]["num_results"] for call in searcher.calls] == [
            60,
            120,
            240,
            480,
            500,
        ]


def _assert_no_graphiti_runner_threads() -> None:
    """Fail if any sync-loop daemon thread survived the tests above."""
    leaked = [t for t in threading.enumerate() if t.name == "omnistream-graphiti"]
    assert not leaked, f"leaked Graphiti sync loop threads: {leaked}"


def test_no_graphiti_runner_threads_are_leaked():
    """Every test above closes its retriever, so no runner threads remain."""
    _assert_no_graphiti_runner_threads()
