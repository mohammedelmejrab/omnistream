"""Reciprocal Rank Fusion (Cormack et al., 2009).

``score(d) = sum_i  w_i / (k + rank_i(d))`` over every ranking ``i`` that
contains ``d``, with 1-based ranks and ``k = 60`` by default (spec C5 step 5).
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class RankedItem[T: Hashable]:
    """An item with an explicit 1-based rank.

    Ranked lists may mix plain ids (ranked by position) and ``RankedItem``
    entries. A dedicated type is used rather than ``(id, rank)`` tuples so a
    tuple-valued id is never misread as a rank pair.
    """

    id: T
    rank: int

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, numbers.Integral):
            raise TypeError(f"rank must be an integer, got {type(self.rank).__name__}")
        if self.rank < 1:
            raise ValueError(f"rank must be >= 1, got {self.rank}")
        object.__setattr__(self, "rank", int(self.rank))


@dataclass(frozen=True)
class FusedResult[T: Hashable]:
    """One fused item, its RRF score and the rank it held in each input list."""

    id: T
    score: float
    ranks: dict[str, int] = field(default_factory=dict)

    @property
    def best_rank(self) -> int:
        return min(self.ranks.values())


def ranks_from_scores[T: Hashable](
    scores: Mapping[T, float] | Iterable[tuple[T, float]],
    *,
    higher_is_better: bool = True,
) -> list[RankedItem[T]]:
    """Convert raw scores into ranked items; tied scores share the same rank.

    * Standard competition ranking ("1224"): equal scores share a rank and the
      next distinct score skips ahead. Order among ties follows input order.
    * An id given more than once keeps only its best score, *before* ranks
      are assigned, so duplicates never push other items down.
    * NaN scores are dropped; ``+inf``/``-inf`` are ordered normally.
    """
    pairs = scores.items() if isinstance(scores, Mapping) else scores
    better = (lambda a, b: a > b) if higher_is_better else (lambda a, b: a < b)
    best: dict[T, float] = {}
    for item, raw in pairs:
        s = float(raw)
        if math.isnan(s):
            continue
        if item not in best or better(s, best[item]):
            best[item] = s

    ordered = sorted(best.items(), key=lambda p: -p[1] if higher_is_better else p[1])
    ranked: list[RankedItem[T]] = []
    prev: float | None = None
    rank = 0
    for position, (item, s) in enumerate(ordered, start=1):
        if s != prev:
            rank, prev = position, s
        ranked.append(RankedItem(item, rank))
    return ranked


def reciprocal_rank_fusion[T: Hashable](
    rankings: Mapping[str, Sequence[T | RankedItem[T]]]
    | Sequence[Sequence[T | RankedItem[T]]],
    *,
    k: int = DEFAULT_RRF_K,
    weights: Mapping[str, float] | Sequence[float] | None = None,
    top_n: int | None = None,
) -> list[FusedResult[T]]:
    """Fuse several ranked lists into one.

    ``rankings`` is either a mapping ``name -> ranked list`` or a plain sequence
    of ranked lists (named ``"0"``, ``"1"``, ...). A ranked list holds ids
    best-first, or :class:`RankedItem` entries with explicit ranks (e.g. from
    :func:`ranks_from_scores`, which lets tied inputs share a rank).

    Edge cases:

    * empty input, or only empty lists -> ``[]``
    * an id repeated within one list keeps only its best rank
    * ties in fused score are broken by best individual rank, then by the
      number of lists containing the item, then by first appearance, so the
      output is fully deterministic.
    """
    if isinstance(k, bool) or not isinstance(k, numbers.Integral) or k < 0:
        raise ValueError("k must be a non-negative integer")
    if top_n is not None and top_n < 0:
        raise ValueError("top_n must be non-negative")

    named: list[tuple[str, Sequence]] = (
        [(str(name), lst) for name, lst in rankings.items()]
        if isinstance(rankings, Mapping)
        else [(str(i), lst) for i, lst in enumerate(rankings)]
    )
    if len({n for n, _ in named}) != len(named):
        raise ValueError("ranking names must be unique")
    weight_of = _resolve_weights(named, weights)

    # Pass 1: best rank of each item per list.
    ranks: dict[T, dict[str, int]] = {}
    first_seen: dict[T, int] = {}
    for name, ranked in named:
        for position, entry in enumerate(ranked, start=1):
            if isinstance(entry, RankedItem):
                item, rank = entry.id, entry.rank
            else:
                item, rank = entry, position
            first_seen.setdefault(item, len(first_seen))
            item_ranks = ranks.setdefault(item, {})
            if rank < item_ranks.get(name, rank + 1):
                item_ranks[name] = rank

    # Pass 2: score from final ranks (no incremental corrections).
    results = [
        FusedResult(
            id=item,
            score=math.fsum(weight_of[n] / (k + r) for n, r in item_ranks.items()),
            ranks=item_ranks,
        )
        for item, item_ranks in ranks.items()
    ]
    results.sort(key=lambda r: (-r.score, r.best_rank, -len(r.ranks), first_seen[r.id]))
    return results[:top_n] if top_n is not None else results


def _resolve_weights(
    named: list[tuple[str, Sequence]],
    weights: Mapping[str, float] | Sequence[float] | None,
) -> dict[str, float]:
    names = [n for n, _ in named]
    if weights is None:
        return dict.fromkeys(names, 1.0)
    if isinstance(weights, Mapping):
        unknown = set(map(str, weights)) - set(names)
        if unknown:
            raise ValueError(f"weights given for unknown rankings: {sorted(unknown)}")
        resolved = {n: float(weights.get(n, 1.0)) for n in names}
    else:
        if len(weights) != len(names):
            raise ValueError("weights must have one entry per ranking")
        resolved = {n: float(w) for n, w in zip(names, weights, strict=True)}
    if not all(math.isfinite(w) and w >= 0 for w in resolved.values()):
        raise ValueError("weights must be finite and non-negative")
    return resolved
