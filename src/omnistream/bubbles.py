"""Bubble rows and periodic auto-summary refresh.

Implements spec section 7 (the SQLite ``bubbles`` table), 6/C5 ("Bubble
auto-summaries refresh every 200 new episodes and never replace the
user-written description") and 9/D16 (user text is authoritative; the
auto-summary is supplementary, which prevents routing drift).
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import numpy as np

from omnistream.retrieval.router import BubbleInfo

#: Spec 6/C5: auto-summaries refresh every 200 new episodes.
REFRESH_EVERY_EPISODES = 200


@dataclass(frozen=True)
class Bubble:
    """One row of the ``bubbles`` table (spec 7).

    ``description`` is the user-written, authoritative text used for routing;
    ``auto_summary`` is the machine-generated supplement refreshed every
    ``every`` new episodes and never replaces it (spec 9/D16).
    ``episodes_since_summary`` counts episodes ingested since the last
    auto-summary refresh.
    """

    id: str
    name: str
    description: str
    description_embedding: np.ndarray | None = None
    auto_summary: str | None = None
    half_life_days: float = 30.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    episodes_since_summary: int = 0

    def __post_init__(self) -> None:
        for label, value in (
            ("id", self.id),
            ("name", self.name),
            ("description", self.description),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty string")
        if (
            isinstance(self.half_life_days, bool)
            or not isinstance(self.half_life_days, (int, float))
            or not math.isfinite(self.half_life_days)
            or self.half_life_days <= 0
        ):
            raise ValueError(
                f"half_life_days must be a finite number > 0, got {self.half_life_days!r}"
            )
        for label, value in (
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            if not isinstance(value, datetime):
                raise TypeError(
                    f"{label} must be a datetime, got {type(value).__name__}"
                )
        if self.description_embedding is not None and not isinstance(
            self.description_embedding, np.ndarray
        ):
            raise TypeError("description_embedding must be a numpy ndarray or None")
        if self.episodes_since_summary < 0:
            raise ValueError(
                f"episodes_since_summary must be >= 0, got {self.episodes_since_summary!r}"
            )

    def to_bubble_info(self) -> BubbleInfo:
        """Return the routing view used by the ingestion and query routers (spec 6/C3, 6/C5)."""
        return BubbleInfo(
            id=self.id,
            name=self.name,
            description=self.description,
            auto_summary=self.auto_summary,
            description_embedding=self.description_embedding,
        )


class BubbleCatalog(Protocol):
    """The storage operations the auto-summary refresher relies on (spec 7)."""

    def get(self, bubble_id: str) -> Bubble: ...
    def list(self) -> Sequence[Bubble]: ...
    def save(self, bubble: Bubble) -> None: ...
    def update(self, bubble_id: str, fn: Callable[[Bubble], Bubble]) -> Bubble: ...


class InMemoryBubbleCatalog:
    """Thread-safe in-memory ``BubbleCatalog`` (SQLite in production, spec 7)."""

    def __init__(self, bubbles: Sequence[Bubble] = ()) -> None:
        self._lock = threading.RLock()
        self._bubbles: dict[str, Bubble] = {}
        for bubble in bubbles:
            self.save(bubble)

    def get(self, bubble_id: str) -> Bubble:
        with self._lock:
            try:
                return self._bubbles[bubble_id]
            except KeyError:
                raise KeyError(f"unknown bubble id: {bubble_id!r}") from None

    def list(self) -> tuple[Bubble, ...]:
        with self._lock:
            return tuple(self._bubbles.values())

    def save(self, bubble: Bubble) -> None:
        if not isinstance(bubble, Bubble):
            raise TypeError(f"bubble must be a Bubble, got {type(bubble).__name__}")
        with self._lock:
            self._bubbles[bubble.id] = bubble

    def update(self, bubble_id: str, fn: Callable[[Bubble], Bubble]) -> Bubble:
        """Apply ``fn`` to the current row atomically, without changing its id."""
        with self._lock:
            bubble = fn(self.get(bubble_id))
            if not isinstance(bubble, Bubble):
                raise TypeError("update must return a Bubble")
            if bubble.id != bubble_id:
                raise ValueError("update must preserve the bubble id")
            self.save(bubble)
            return bubble


class AutoSummaryRefresher:
    """Compatibility entry point delegating to C4's single summary writer.

    Episode counting belongs to GraphWriter.write; query-time code must never
    increment counters or maintain a second episode buffer.
    """

    def __init__(self, writer):
        self.writer = writer

    async def maybe_refresh_summary(self, bubble_id: str) -> bool:
        return await self.writer.maybe_refresh_summary(bubble_id)


class RepositoryBubbleCatalog:
    """Live read-only query catalog. C4 GraphWriter owns summary refresh."""

    def __init__(self, repo):
        self.repo = repo

    def list(self) -> tuple[Bubble, ...]:
        return tuple(
            Bubble(
                id=row.id,
                name=row.name,
                description=row.description,
                description_embedding=np.asarray(row.description_embedding, dtype=float)
                if row.description_embedding is not None
                else None,
                auto_summary=row.auto_summary,
                half_life_days=row.half_life_days,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in self.repo.read_bubbles()
        )

    def get(self, bubble_id: str) -> Bubble:
        for bubble in self.list():
            if bubble.id == bubble_id:
                return bubble
        raise KeyError(bubble_id)
