"""Offline checks for the C5 contracts (spec sections 4.2, 6/C5 and 7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from omnistream.retrieval import (
    Chunk,
    Citation,
    Entity,
    Fact,
    GraphStore,
    ItemPart,
    ItemStore,
    RetrievalResult,
    Retriever,
    ScoredFact,
    Subgraph,
    TimeScope,
)

NOW = datetime(2025, 1, 2, tzinfo=UTC)
BEFORE = NOW - timedelta(days=1)
AFTER = NOW + timedelta(days=1)


def fact(item_id: str = "item") -> Fact:
    return Fact("f", "a", "b", "knows", "A knows B", "news", item_id, None, NOW)


@pytest.mark.parametrize(
    "scope,valid,invalid,expected",
    [
        (TimeScope(), None, None, True),
        (TimeScope(), BEFORE, AFTER, True),
        (TimeScope(NOW, NOW), None, None, True),
        (TimeScope(NOW, NOW), NOW, None, True),
        (TimeScope(NOW, NOW), None, NOW, False),
        (TimeScope(NOW, AFTER), BEFORE, NOW, False),
        (TimeScope(BEFORE, NOW), NOW, AFTER, True),
        (TimeScope(BEFORE, NOW), AFTER, None, False),
        (TimeScope(NOW, AFTER), None, BEFORE, False),
        (TimeScope(start=NOW), AFTER, None, True),
        (TimeScope(end=NOW), None, BEFORE, True),
        (TimeScope(end=NOW), AFTER, None, False),
        (TimeScope(), NOW, NOW, False),
        (TimeScope(), AFTER, BEFORE, False),
        (TimeScope(BEFORE, AFTER), BEFORE, AFTER, True),
    ],
)
def test_time_scope_overlap(scope, valid, invalid, expected):
    assert scope.overlaps(valid, invalid) is expected


def test_time_scope_naive_and_offset_datetimes():
    naive = NOW.replace(tzinfo=None)
    offset = NOW.astimezone(timezone(timedelta(hours=3)))
    assert TimeScope(naive, offset).overlaps(NOW, AFTER.replace(tzinfo=None))
    assert not TimeScope(offset, naive).overlaps(None, naive)
    assert TimeScope(end=naive).overlaps(offset, None)
    with pytest.raises(ValueError, match="start"):
        TimeScope(AFTER.replace(tzinfo=None), offset)


def test_time_scope_rejects_reversed_bounds():
    with pytest.raises(ValueError, match="start"):
        TimeScope(AFTER, BEFORE)


@pytest.mark.parametrize("name", ["credibility", "confidence"])
@pytest.mark.parametrize(
    "value", [-0.01, 1.01, float("nan"), float("inf"), -float("inf")]
)
def test_fact_rejects_invalid_probability(name, value):
    with pytest.raises(ValueError, match=name):
        replace(fact(), **{name: value})


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_fact_accepts_probability_boundaries(value):
    assert replace(fact(), credibility=value, confidence=value).credibility == value


@pytest.mark.parametrize("count", [0, -1])
def test_fact_rejects_invalid_source_count(count):
    with pytest.raises(ValueError, match="source_count"):
        replace(fact(), source_count=count)


def test_retrieval_item_ids_preserve_rank_and_deduplicate():
    result = RetrievalResult(
        "own",
        facts=tuple(
            ScoredFact(fact(item), score)
            for item, score in [("b", 3), ("a", 2), ("b", 1)]
        ),
        chunks=tuple(
            Chunk(item, "text", item, "news", None, None)
            for item in ["a", "c", "d", "c"]
        ),
    )
    assert result.item_ids == ("b", "a", "c", "d")
    assert RetrievalResult("classic").item_ids == ()
    assert RetrievalResult("classic", chunks=result.chunks).item_ids == ("a", "c", "d")


@pytest.mark.parametrize(
    "model,attribute",
    [
        (TimeScope(), "start"),
        (Entity("a", "A", "person", "news"), "id"),
        (fact(), "id"),
        (Subgraph({}, ()), "facts"),
        (ScoredFact(fact(), 1.0), "score"),
        (Chunk("c", "text", "item", "news", None, None), "text"),
        (Citation(1, "item", None, "snippet"), "number"),
        (ItemPart("item", 1, 1, "text"), "text"),
        (RetrievalResult("own"), "mode"),
    ],
)
def test_contracts_are_frozen(model, attribute):
    with pytest.raises(FrozenInstanceError):
        setattr(model, attribute, None)


def test_scored_fact_rank_defaults_are_independent():
    first, second = ScoredFact(fact(), 1), ScoredFact(fact(), 2)
    first.ranks["recency"] = 1
    assert second.ranks == {}
    assert first.path == ()


class OfflineRetriever:
    def retrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        return RetrievalResult("own")


class OfflineGraphStore:
    def seed_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 5,
        min_cosine: float = 0.5,
    ) -> list[tuple[Entity, float]]:
        return []

    def entities_in(self, bubbles: Sequence[str]) -> list[Entity]:
        return []

    def expand(
        self,
        seed_ids: Sequence[str],
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None,
        max_hops: int = 2,
        max_edges: int = 500,
    ) -> Subgraph:
        return Subgraph({}, ())

    def neighbors(self, entity_id: str, depth: int = 1) -> Subgraph:
        return Subgraph({}, ())

    def facts_about(
        self,
        entity_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Fact]:
        return []

    def fact_embeddings(self, fact_ids: Sequence[str]) -> dict[str, np.ndarray]:
        return {}


def test_runtime_protocols_are_structural():
    assert isinstance(OfflineRetriever(), Retriever)
    assert isinstance(OfflineGraphStore(), GraphStore)
    assert not isinstance(object(), Retriever)
    assert not isinstance(object(), GraphStore)
    assert not isinstance(object(), ItemStore)
    assert not isinstance(OfflineRetriever(), GraphStore)


def test_fact_scope_accepts_fixed_clock():
    from dataclasses import replace
    from datetime import UTC, datetime

    from omnistream.retrieval.models import fact_in_scope
    from tests.unit.test_agent_tools import FACT

    fact = replace(
        FACT,
        valid_at=datetime(2020, 1, 1, tzinfo=UTC),
        invalid_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert fact_in_scope(fact, None, now=lambda: datetime(2020, 6, 1, tzinfo=UTC))
    assert not fact_in_scope(fact, None, now=lambda: datetime(2022, 6, 1, tzinfo=UTC))
