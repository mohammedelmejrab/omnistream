"""Conservative, bubble-local supersession before fusion.

Intervals (including two open bounds) retain every overlapping assertion.
Point queries collapse only near-identical assertions with the same endpoints
and relation. Different numeric/date tokens require explicit replacement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Fact, Subgraph, TimeScope, _utc, fact_in_scope


@dataclass(frozen=True)
class VersionGroup:
    representative: Fact
    versions: tuple[Fact, ...]


def fact_versions(
    graph: Subgraph, embeddings, *, scope: TimeScope | None, now: datetime
) -> list[VersionGroup]:
    facts = sorted(
        (f for f in graph.facts if fact_in_scope(f, scope, now=now)),
        key=lambda f: (
            -_utc(f.valid_at or f.published_at).timestamp(),
            -_utc(f.published_at).timestamp(),
            f.id,
        ),
    )
    if scope is not None and (
        scope.start is None or scope.end is None or scope.start != scope.end
    ):
        return [VersionGroup(f, (f,)) for f in facts]

    def key(f):
        return (
            f.bubble,
            f.subject_id,
            f.object_id,
            re.sub(r"[\W_]+", " ", f.relation.casefold()).strip(),
        )

    def equivalent(a, b):
        if key(a) != key(b):
            return False
        newer, older = sorted(
            (a, b),
            key=lambda f: (_utc(f.valid_at or f.published_at), f.id),
            reverse=True,
        )
        replaced = newer.valid_at is not None and any(
            t is not None and _utc(t) <= _utc(newer.valid_at)
            for t in (older.invalid_at, older.expired_at)
        )
        # Digits cover amounts, quarters and numeric dates; month names protect
        # spelled dates even when embeddings are insensitive to them.
        tokens = lambda f: re.findall(
            r"\d+(?:[.,:/-]\d+)*|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            f.text.casefold(),
        )
        if tokens(a) != tokens(b) and not replaced:
            return False
        text = lambda f: " ".join(re.findall(r"\w+", f.text.casefold()))
        return text(a) == text(b) or (
            a.id in embeddings
            and b.id in embeddings
            and float(
                EmbeddingService.cosine_similarity(embeddings[a.id], embeddings[b.id])[
                    0
                ]
            )
            >= 0.95
        )

    families = []
    for f in facts:
        # Complete-link comparison avoids transitive similarity bridges. Sorted
        # newest-first input and all-member comparison make replay deterministic.
        for family in families:
            if all(equivalent(f, other) for other in family):
                family.append(f)
                break
        else:
            families.append([f])
    return [VersionGroup(family[0], tuple(family)) for family in families]
