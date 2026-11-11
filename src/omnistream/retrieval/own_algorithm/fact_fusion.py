"""Step 5 of the ``own`` algorithm (spec C5): fuse fact signals with RRF.

Each candidate fact is ranked three ways and the rankings are fused with
Reciprocal Rank Fusion (k = 60):

1. fact score  - question similarity x endpoint PageRank (from step 4)
2. recency     - ``exp(-lambda * age_days)`` with ``lambda = ln 2 / half_life``
3. confidence  - corroboration ``1 - prod(1 - credibility_i)``
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from omnistream.retrieval.fusion import (
    DEFAULT_RRF_K,
    ranks_from_scores,
    reciprocal_rank_fusion,
)

# Per-bubble recency half-lives in days (spec C5 step 5 defaults).
DEFAULT_HALF_LIVES: Mapping[str, float] = {
    "news": 3.0,
    "finance": 30.0,
    "research": 365.0,
}
DEFAULT_TOP_N = 20
SIGNALS = ("fact_score", "recency", "confidence")


def recency_score(
    published_at: datetime, now: datetime, half_life_days: float
) -> float:
    """``exp(-ln2 * age_days / half_life_days)``: 1.0 when new, 0.5 after one half-life.

    Naive datetimes are treated as UTC. Future timestamps (clock skew) count
    as age 0 rather than scoring above 1.
    """
    if not (math.isfinite(half_life_days) and half_life_days > 0):
        raise ValueError("half_life_days must be finite and > 0")
    age_days = (_utc(now) - _utc(published_at)).total_seconds() / 86_400
    return math.exp(-math.log(2) * max(0.0, age_days) / half_life_days)


def corroboration_confidence(credibilities: Sequence[float]) -> float:
    """``1 - prod(1 - c_i)`` over the credibility of each asserting source (spec C4)."""
    for c in credibilities:
        if not (0.0 <= c <= 1.0):
            raise ValueError(f"credibility must be within [0, 1], got {c}")
    return 1.0 - math.prod(1.0 - c for c in credibilities)


@dataclass(frozen=True)
class FactCandidate:
    id: Hashable
    fact_score: float
    published_at: datetime
    bubble: str
    confidence: float
    path: tuple[Hashable, ...] = ()  # path from the nearest seed, passed through


@dataclass(frozen=True)
class FusedFact:
    fact: FactCandidate
    score: float
    recency: float
    ranks: dict[str, int] = field(default_factory=dict)


def fuse_facts(
    candidates: Sequence[FactCandidate],
    *,
    now: datetime,
    half_lives: Mapping[str, float] | None = None,
    default_half_life: float = 30.0,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = DEFAULT_TOP_N,
) -> list[FusedFact]:
    """Rank facts by RRF over fact score, recency and confidence.

    ``now`` is required (no hidden clock) so results are reproducible.
    ``half_lives`` overrides are merged over :data:`DEFAULT_HALF_LIVES`; lookup
    is by bubble name, case-insensitively, falling back to ``default_half_life``.
    ``fact_score`` must be finite and ``confidence`` within ``[0, 1]``.
    """
    lives = {name.lower(): float(v) for name, v in DEFAULT_HALF_LIVES.items()}
    lives.update({name.lower(): float(v) for name, v in (half_lives or {}).items()})
    by_id: dict[Hashable, FactCandidate] = {}
    for c in candidates:
        if c.id in by_id:
            raise ValueError(f"duplicate fact id {c.id!r}")
        if not math.isfinite(c.fact_score):
            raise ValueError(
                f"fact {c.id!r}: fact_score must be finite, got {c.fact_score}"
            )
        if not (0.0 <= c.confidence <= 1.0):
            raise ValueError(
                f"fact {c.id!r}: confidence must be within [0, 1], got {c.confidence}"
            )
        by_id[c.id] = c
    recency = {
        c.id: recency_score(
            c.published_at, now, lives.get(c.bubble.lower(), default_half_life)
        )
        for c in candidates
    }
    fused = reciprocal_rank_fusion(
        {
            "fact_score": ranks_from_scores([(c.id, c.fact_score) for c in candidates]),
            "recency": ranks_from_scores(recency),
            "confidence": ranks_from_scores([(c.id, c.confidence) for c in candidates]),
        },
        k=k,
        top_n=top_n,
    )
    return [
        FusedFact(fact=by_id[r.id], score=r.score, recency=recency[r.id], ranks=r.ranks)
        for r in fused
    ]


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
