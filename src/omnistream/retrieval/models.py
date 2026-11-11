"""Shared C5 evidence contracts (spec sections 4.2, 6/C5 and 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

RetrievalMode = Literal["classic", "graphiti", "own"]


def _utc(value: datetime | None) -> datetime | None:
    """Interpret naive timestamps as UTC for validity comparisons."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class TimeScope:
    """Closed query interval for C5 validity filtering; None bounds are open."""

    start: datetime | None = None
    end: datetime | None = None

    def __post_init__(self) -> None:
        start, end = _utc(self.start), _utc(self.end)
        if start is not None and end is not None and start > end:
            raise ValueError("start must not be after end")

    def overlaps(self, valid_at: datetime | None, invalid_at: datetime | None) -> bool:
        """Whether [valid_at, invalid_at) intersects [start, end].

        Missing bounds are unbounded, and naive datetimes mean UTC. Empty
        or reversed fact intervals do not intersect any query interval.
        """
        valid, invalid = _utc(valid_at), _utc(invalid_at)
        start, end = _utc(self.start), _utc(self.end)
        if valid is not None and invalid is not None and valid >= invalid:
            return False
        if invalid is not None and start is not None and invalid <= start:
            return False
        if valid is not None and end is not None and valid > end:  # noqa: SIM103
            return False
        return True


@dataclass(frozen=True)
class Entity:
    """Bubble-local entity with optional cross-bubble identity (spec 7)."""

    id: str
    name: str
    type: str
    bubble: str
    global_id: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fact:
    """Graph assertion with validity and original-item provenance (spec 4.2, 7)."""

    id: str
    subject_id: str
    object_id: str
    relation: str
    text: str
    bubble: str
    item_id: str
    source_url: str | None
    published_at: datetime
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    grounded: bool = True
    credibility: float = 0.5
    confidence: float = 0.5
    source_count: int = 1

    def __post_init__(self) -> None:
        for name in ("credibility", "confidence"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.source_count < 1:
            raise ValueError("source_count must be >= 1")


@dataclass(frozen=True)
class Subgraph:
    """C5 expansion result including cross-bubble SAME_AS links."""

    entities: dict[str, Entity]
    facts: tuple[Fact, ...]
    same_as: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScoredFact:
    """Ranked C5 fact; path contains entity ids from the nearest seed."""

    fact: Fact
    score: float
    path: tuple[str, ...] = ()
    ranks: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    """Ranked original-text evidence with provenance (spec 4.2, 7)."""

    id: str
    text: str
    item_id: str
    bubble: str
    source_url: str | None
    published_at: datetime | None
    score: float = 0.0


@dataclass(frozen=True)
class Citation:
    """Numbered passage pointing to an original item (spec C5 merge/answer).

    spans are [start, end) character offsets into the item's stored clean
    text (spec C5 original-text access); empty when no text was located.
    """

    number: int
    item_id: str
    source_url: str | None
    snippet: str
    spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class ItemPart:
    """One 1-based part of stored clean text (spec C5 original-text access)."""

    item_id: str
    part: int
    total_parts: int
    text: str


@dataclass(frozen=True)
class RetrievalResult:
    """Mode-tagged evidence in rank order (spec C5 retrieval modes)."""

    mode: RetrievalMode
    facts: tuple[ScoredFact, ...] = ()
    chunks: tuple[Chunk, ...] = ()

    @property
    def item_ids(self) -> tuple[str, ...]:
        """Distinct evidence item ids, preserving facts-first rank order."""
        return tuple(
            dict.fromkeys(
                [entry.fact.item_id for entry in self.facts]
                + [chunk.item_id for chunk in self.chunks]
            )
        )
