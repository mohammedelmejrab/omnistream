"""Preserve contradictory assertions and mark preferred evidence (spec C5/D8)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations

from omnistream.retrieval.models import ScoredFact, _utc


@dataclass(frozen=True)
class Conflict:
    """A connected cluster of conflicting assertions; all sides remain visible (D8)."""

    subject_id: str
    relation: str
    facts: tuple[ScoredFact, ...]
    preferred_fact_id: str | None


def detect_conflicts(
    facts: Sequence[ScoredFact], *, canonical_ids: Mapping[str, str] | None = None
) -> list[Conflict]:
    """Cluster overlapping, different-object assertions per subject/relation.

    Components and their facts follow input rank order. Prefer highest
    published_at, then valid_at, then id among credible facts in each cluster.
    Validity is half-open, matching the shared TimeScope contract.
    """
    canonical = canonical_ids or {}
    low = datetime.min.replace(tzinfo=UTC)
    high = datetime.max.replace(tzinfo=UTC)
    groups: dict[tuple[str, str], list[int]] = {}
    for i, scored in enumerate(facts):
        groups.setdefault(
            (
                canonical.get(scored.fact.subject_id, scored.fact.subject_id),
                scored.fact.relation,
            ),
            [],
        ).append(i)
    adjacency: dict[int, set[int]] = {}
    for indices in groups.values():
        for i, j in combinations(indices, 2):
            a, b = facts[i].fact, facts[j].fact
            if canonical.get(a.object_id, a.object_id) == canonical.get(
                b.object_id, b.object_id
            ):
                continue
            if max(_utc(a.valid_at) or low, _utc(b.valid_at) or low) >= min(
                _utc(a.invalid_at) or high, _utc(b.invalid_at) or high
            ):
                continue
            adjacency.setdefault(i, set()).add(j)
            adjacency.setdefault(j, set()).add(i)
    conflicts = []
    seen: set[int] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        pending = [start]
        component = []
        seen.add(start)
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        ranked = tuple(facts[i] for i in sorted(component))
        eligible = [entry.fact for entry in ranked if entry.fact.credibility >= 0.6]
        preferred = (
            max(
                eligible,
                key=lambda f: (
                    _utc(f.published_at) or low,
                    _utc(f.valid_at) or low,
                    f.id,
                ),
            )
            if eligible
            else None
        )
        first = ranked[0].fact
        conflicts.append(
            Conflict(
                canonical.get(first.subject_id, first.subject_id),
                first.relation,
                ranked,
                preferred.id if preferred else None,
            )
        )
    return conflicts
