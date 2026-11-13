"""Current assertion representatives before global fusion.

Identity uses GlobalEntity when present; normalized relation names define an
assertion family. Within the same endpoint pair, cosine >= .95 also recognizes
near-identical paraphrases. This is a semantic duplicate threshold, not a
retrieval relevance threshold. Explicit interval queries retain all versions
intersecting the interval, so historical evidence is not silently collapsed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Fact, Subgraph, TimeScope, _utc, fact_in_scope


@dataclass(frozen=True)
class VersionGroup:
    representative: Fact
    versions: tuple[
        Fact, ...
    ]  # preserve full assertions and provenance for diagnostics


def fact_versions(
    graph: Subgraph, embeddings, *, scope: TimeScope | None, now: datetime
) -> list[VersionGroup]:
    buckets = defaultdict(list)
    for f in sorted(graph.facts, key=lambda f: f.id):
        if not fact_in_scope(f, scope, now=now):
            continue

        def identity(i):
            e = graph.entities[i]
            return e.global_id or e.id

        buckets[(identity(f.subject_id), identity(f.object_id))].append(f)
    groups = []
    for pair in sorted(buckets):
        families = []
        for f in buckets[pair]:
            relation = re.sub(r"[\W_]+", " ", f.relation.casefold()).strip()
            for family in families:
                other = family[0]
                same_relation = (
                    relation
                    == re.sub(r"[\W_]+", " ", other.relation.casefold()).strip()
                )
                similar = (
                    f.id in embeddings
                    and other.id in embeddings
                    and float(
                        EmbeddingService.cosine_similarity(
                            embeddings[f.id], embeddings[other.id]
                        )[0]
                    )
                    >= 0.95
                )
                if same_relation or similar:
                    family.append(f)
                    break
            else:
                families.append([f])
        for family in families:
            ordered = tuple(
                sorted(
                    family,
                    key=lambda f: (
                        -_utc(f.valid_at or f.published_at).timestamp(),
                        -_utc(f.published_at).timestamp(),
                        f.id,
                    ),
                )
            )
            # A past interval can legitimately ask for more than one change.
            # At a point in time, use the latest assertion valid at that point.
            if scope is not None and scope.start != scope.end:
                groups.extend(VersionGroup(f, (f,)) for f in ordered)
            else:
                groups.append(VersionGroup(ordered[0], ordered))
    return groups
