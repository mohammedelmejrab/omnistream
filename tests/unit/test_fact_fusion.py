"""Spec C5 step 5: RRF over fact score, recency and corroboration confidence."""

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from omnistream.retrieval.own_algorithm import (
    DEFAULT_HALF_LIVES,
    FactCandidate,
    corroboration_confidence,
    fuse_facts,
    recency_score,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def fact(fid, score=0.5, age_days=0.0, bubble="news", confidence=0.5, path=()):
    return FactCandidate(
        id=fid,
        fact_score=score,
        published_at=NOW - timedelta(days=age_days),
        bubble=bubble,
        confidence=confidence,
        path=path,
    )


# ---------------------------------------------------------------- recency
def test_default_half_lives_match_spec():
    assert DEFAULT_HALF_LIVES == {"news": 3.0, "finance": 30.0, "research": 365.0}


@pytest.mark.parametrize("half_life", [3.0, 30.0, 365.0])
def test_recency_halves_every_half_life(half_life):
    assert recency_score(NOW, NOW, half_life) == 1.0
    assert recency_score(
        NOW - timedelta(days=half_life), NOW, half_life
    ) == pytest.approx(0.5)
    assert recency_score(
        NOW - timedelta(days=2 * half_life), NOW, half_life
    ) == pytest.approx(0.25)


def test_recency_formula_is_exp_minus_lambda_age():
    age, hl = 7.3, 30.0
    expected = math.exp(-(math.log(2) / hl) * age)
    assert recency_score(NOW - timedelta(days=age), NOW, hl) == pytest.approx(
        expected, rel=1e-12
    )


def test_recency_future_timestamp_clamped_to_one():
    assert recency_score(NOW + timedelta(days=2), NOW, 3.0) == 1.0


def test_recency_naive_datetimes_treated_as_utc_and_timezones_respected():
    naive = datetime(2026, 11, 10, 12, 0)
    assert recency_score(naive, NOW, 3.0) == 1.0
    plus2 = datetime(
        2026, 11, 10, 14, 0, tzinfo=timezone(timedelta(hours=2))
    )  # same instant
    assert recency_score(plus2, NOW, 3.0) == 1.0


@pytest.mark.parametrize("hl", [0.0, -1.0, math.inf, math.nan])
def test_recency_invalid_half_life(hl):
    with pytest.raises(ValueError):
        recency_score(NOW, NOW, hl)


# ----------------------------------------------------------- corroboration
def test_corroboration_formula():
    assert corroboration_confidence([]) == 0.0
    assert corroboration_confidence([0.5]) == pytest.approx(0.5)
    assert corroboration_confidence([0.5, 0.5]) == pytest.approx(0.75)
    assert corroboration_confidence([0.6, 0.7, 1.0]) == pytest.approx(1.0)
    assert corroboration_confidence([0.2, 0.4]) == pytest.approx(1 - 0.8 * 0.6)


@pytest.mark.parametrize("bad", [[-0.1], [1.1], [math.nan]])
def test_corroboration_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        corroboration_confidence(bad)


# ---------------------------------------------------------------- fusion
def test_empty_candidates():
    assert fuse_facts([], now=NOW) == []


def test_rrf_over_three_signals_exact_scores():
    a = fact(
        "a", score=0.9, age_days=10, confidence=0.1
    )  # best fact score, oldest, least confident
    b = fact("b", score=0.5, age_days=0, confidence=0.5)
    c = fact("c", score=0.1, age_days=5, confidence=0.9)
    fused = {f.fact.id: f for f in fuse_facts([a, b, c], now=NOW, relevance_weight=1)}
    assert fused["a"].ranks == {"fact_score": 1, "recency": 3, "confidence": 3}
    assert fused["b"].ranks == {"fact_score": 2, "recency": 1, "confidence": 2}
    assert fused["c"].ranks == {"fact_score": 3, "recency": 2, "confidence": 1}
    assert fused["b"].score == pytest.approx(1 / 62 + 1 / 61 + 1 / 62)
    assert fused["a"].score == pytest.approx(1 / 61 + 1 / 63 + 1 / 63)


def test_per_bubble_half_life_changes_recency_ranking():
    # Both 6 days old: news (3-day half-life) decays to 0.25, research barely moves.
    news = fact("news", age_days=6, bubble="News")
    research = fact("research", age_days=6, bubble="research")
    out = {f.fact.id: f for f in fuse_facts([news, research], now=NOW)}
    assert out["news"].recency == pytest.approx(0.25)
    assert out["research"].recency == pytest.approx(2 ** (-6 / 365))
    assert out["research"].ranks["recency"] == 1


def test_unknown_bubble_uses_default_half_life():
    out = fuse_facts(
        [fact("x", age_days=30, bubble="sports")], now=NOW, default_half_life=30.0
    )
    assert out[0].recency == pytest.approx(0.5)


def test_custom_half_lives():
    out = fuse_facts(
        [fact("x", age_days=1, bubble="news")], now=NOW, half_lives={"news": 1.0}
    )
    assert out[0].recency == pytest.approx(0.5)


def test_partial_half_life_override_keeps_other_defaults():
    facts = [
        fact("n", age_days=3, bubble="news"),
        fact("f", age_days=10, bubble="finance"),
    ]
    out = {f.fact.id: f for f in fuse_facts(facts, now=NOW, half_lives={"Finance": 10})}
    assert out["n"].recency == pytest.approx(0.5)  # News still 3 days
    assert out["f"].recency == pytest.approx(0.5)  # Finance overridden to 10


@pytest.mark.parametrize("conf", [math.inf, -0.01, 1.01, math.nan])
def test_invalid_confidence_rejected(conf):
    with pytest.raises(ValueError, match="confidence"):
        fuse_facts([fact("a", confidence=conf)], now=NOW)


@pytest.mark.parametrize("score", [math.inf, -math.inf, math.nan])
def test_non_finite_fact_score_rejected(score):
    with pytest.raises(ValueError, match="fact_score"):
        fuse_facts([fact("a", score=score)], now=NOW)


def test_tied_signals_share_ranks():
    out = fuse_facts([fact("a"), fact("b")], now=NOW)
    assert (
        out[0].ranks == out[1].ranks == {"fact_score": 1}
    )
    assert out[0].score == out[1].score
    assert [f.fact.id for f in out] == ["a", "b"]


def test_top_n_defaults_to_spec_20():
    out = fuse_facts([fact(i, score=i) for i in range(30)], now=NOW)
    assert len(out) == 20
    assert out[0].fact.id == 29


def test_path_is_passed_through():
    out = fuse_facts([fact("f", path=("seed", "e1", "e2"))], now=NOW)
    assert out[0].fact.path == ("seed", "e1", "e2")


def test_duplicate_fact_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        fuse_facts([fact("a"), fact("a")], now=NOW)


def test_deterministic_given_now():
    facts = [
        fact(i, score=(i * 7) % 5, age_days=i % 4, confidence=(i % 3) / 3)
        for i in range(12)
    ]
    assert fuse_facts(facts, now=NOW) == fuse_facts(list(facts), now=NOW)
