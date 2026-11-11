"""Temporal contradiction and credibility checks (spec D8)."""

from dataclasses import replace
from datetime import datetime

from omnistream.retrieval.merge import detect_conflicts
from omnistream.retrieval.models import Fact, ScoredFact


def fact(i, **changes):
    base = Fact(
        str(i),
        "s",
        str(i),
        "leads",
        f"assertion {i}",
        "news",
        f"item{i}",
        None,
        datetime(2025, 1, i),
        credibility=0.6,
    )
    return ScoredFact(replace(base, **changes), 1.0)


def test_both_sides_and_credibility():
    a, b = fact(1), fact(2)
    (conflict,) = detect_conflicts([a, b])
    assert conflict.facts == (a, b)
    assert conflict.preferred_fact_id == "2"
    assert detect_conflicts([a, fact(2, credibility=0.59)])[0].preferred_fact_id == "1"
    assert (
        detect_conflicts([fact(1, credibility=0.5), fact(2, credibility=0.5)])[
            0
        ].preferred_fact_id
        is None
    )


def test_boundaries_and_distinct_assertions():
    boundary = datetime(2025, 2, 1)
    assert not detect_conflicts(
        [fact(1, invalid_at=boundary), fact(2, valid_at=boundary)]
    )
    assert not detect_conflicts([fact(1), fact(2, object_id="1")])
    assert not detect_conflicts([fact(1), fact(2, subject_id="other")])
    assert not detect_conflicts([fact(1), fact(2, relation="other")])
    assert not detect_conflicts(
        [fact(1, valid_at=boundary, invalid_at=boundary), fact(2)]
    )


def test_valid_at_breaks_published_tie():
    a = fact(1, valid_at=datetime(2024, 1, 1))
    b = fact(2, published_at=a.fact.published_at, valid_at=datetime(2024, 2, 1))
    assert detect_conflicts([a, b])[0].preferred_fact_id == "2"


def test_cluster_has_one_preference_and_keeps_corroboration_in_rank_order():
    ranked = [
        fact(2),
        fact(1),
        fact(3),
        fact(4, object_id="1"),
        fact(5, credibility=0.59),
    ]
    (conflict,) = detect_conflicts(ranked)
    assert conflict.facts == tuple(ranked)
    assert conflict.preferred_fact_id == "4"


def test_transitive_clusters_and_disconnected_components():
    a = fact(1, invalid_at=datetime(2025, 2, 1))
    b = fact(2, valid_at=datetime(2025, 1, 15), invalid_at=datetime(2025, 3, 1))
    c = fact(3, valid_at=datetime(2025, 2, 15), invalid_at=datetime(2025, 4, 1))
    d = fact(4, valid_at=datetime(2025, 5, 1), credibility=0.5)
    e = fact(5, valid_at=datetime(2025, 5, 1), credibility=0.5)
    other = fact(6, subject_id="other")
    conflicts = detect_conflicts([a, d, b, e, c, other])
    assert [x.facts for x in conflicts] == [(a, b, c), (d, e)]
    assert [x.preferred_fact_id for x in conflicts] == ["3", None]


def test_cluster_preference_id_breaks_timestamp_ties():
    ranked = [fact(i, published_at=datetime(2025, 1, 1)) for i in [3, 1, 2]]
    (conflict,) = detect_conflicts(ranked)
    assert conflict.preferred_fact_id == "3"


def test_conflicts_compare_canonical_subjects_and_objects():
    a = fact(1, subject_id="apple-n", object_id="ceo-n")
    b = fact(2, subject_id="apple-f", object_id="ceo-f")
    mapping = {"apple-n": "g-apple", "apple-f": "g-apple"}
    (conflict,) = detect_conflicts([a, b], canonical_ids=mapping)
    assert conflict.subject_id == "g-apple"
    assert conflict.facts == (a, b)
    assert conflict.preferred_fact_id == "2"
    assert not detect_conflicts(
        [a, b], canonical_ids={**mapping, "ceo-n": "g-ceo", "ceo-f": "g-ceo"}
    )
