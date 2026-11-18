"""SQuAD-standard answer metrics and ranking metrics for the bench checks.

Ranking metrics deduplicate the ranked list in first-retrieval order before
cutting at ``k``, mirroring :func:`omnistream.eval.metrics.retrieval_metrics`.
"""

from __future__ import annotations

import random
import re
import string
from collections import Counter
from math import fsum, log2

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCTUATION = set(string.punctuation)


def normalize_answer(text: str) -> str:
    """SQuAD standard: lowercase, strip punctuation, drop articles, collapse."""
    lowered = text.lower()
    without_punctuation = "".join(ch for ch in lowered if ch not in _PUNCTUATION)
    without_articles = _ARTICLES.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def exact_match(prediction: str, answers: list[str]) -> float:
    if not answers:
        return 0.0
    normalized = normalize_answer(prediction)
    return float(any(normalize_answer(answer) == normalized for answer in answers))


def token_f1(prediction: str, answers: list[str]) -> float:
    """Maximum token-level F1 over the candidate answers."""
    if not answers:
        return 0.0
    prediction_tokens = normalize_answer(prediction).split()
    best = 0.0
    for answer in answers:
        answer_tokens = normalize_answer(answer).split()
        if not answer_tokens and not prediction_tokens:
            f1 = 1.0
        elif not answer_tokens or not prediction_tokens:
            f1 = 0.0
        else:
            overlap = sum((Counter(prediction_tokens) & Counter(answer_tokens)).values())
            f1 = (
                2 * overlap / (len(prediction_tokens) + len(answer_tokens))
                if overlap
                else 0.0
            )
        best = max(best, f1)
    return float(best)


def recall_at_k(ranked_ids: list[str], gold_ids: list[str], k: int) -> float:
    gold = set(gold_ids)
    if not gold:
        return 0.0
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    return len(set(ranked) & gold) / len(gold)


def ndcg_at_k(ranked_ids: list[str], gold_ids: list[str], k: int) -> float:
    """Binary-relevance nDCG with ``log2(i + 1)`` position discount."""
    gold = set(gold_ids)
    if not gold:
        return 0.0
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    dcg = fsum(
        1.0 / log2(position + 1)
        for position, item in enumerate(ranked, 1)
        if item in gold
    )
    ideal = fsum(
        1.0 / log2(position + 1)
        for position in range(1, min(len(gold), k) + 1)
    )
    return dcg / ideal


def bootstrap_ci(
    values: list[float],
    n_resamples: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Percentile bootstrap: ``(mean, low, high)`` of the sample mean."""
    values = [float(value) for value in values]
    if not values:
        raise ValueError("bootstrap_ci requires at least one value")
    size = len(values)
    mean = fsum(values) / size
    if n_resamples <= 0:
        return mean, mean, mean
    rng = random.Random(seed)
    means = sorted(
        fsum(rng.choices(values, k=size)) / size for _ in range(n_resamples)
    )
    low = means[int(alpha / 2 * n_resamples)]
    high = means[min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)]
    return mean, low, high
