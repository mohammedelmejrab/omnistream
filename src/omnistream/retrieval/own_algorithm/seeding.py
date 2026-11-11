"""Entity vector and fuzzy seeding (spec C5 step 1)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from rapidfuzz.fuzz import ratio

from omnistream.retrieval.models import Entity
from omnistream.retrieval.protocols import GraphStore


@dataclass(frozen=True)
class Seed:
    """Deduplicated entity seed; scores use a common [-1, 1] scale."""

    entity: Entity
    score: float
    source: Literal["vector", "fuzzy", "both"]


def seed_entities(
    question: str,
    question_embedding: np.ndarray,
    store: GraphStore,
    *,
    bubbles: Sequence[str],
    top_k: int = 5,
    min_cosine: float = 0.5,
    fuzzy_threshold: float = 90,
) -> list[Seed]:
    """Merge vector top-k with all matching names/aliases; ties use entity id."""
    if not 0 <= fuzzy_threshold <= 100:
        raise ValueError("fuzzy_threshold must be within [0, 100]")
    seeds = {
        e.id: Seed(e, score, "vector")
        for e, score in store.seed_by_embedding(
            question_embedding, bubbles=bubbles, top_k=top_k, min_cosine=min_cosine
        )
    }
    question_tokens = re.findall(r"\w+", question.casefold())
    # Compare complete token windows, never substrings within another word.
    windows: dict[int, list[str]] = {}
    for entity in store.entities_in(bubbles):
        score = -1.0
        for name in (entity.name, *entity.aliases):
            if len(name.strip()) < 3:
                continue
            tokens = re.findall(r"\w+", name.casefold())
            size = len(tokens)
            if not size:
                continue
            if size not in windows:
                windows[size] = [
                    " ".join(question_tokens[i : i + size])
                    for i in range(len(question_tokens) - size + 1)
                ]
            score = max(
                score,
                max(
                    (ratio(" ".join(tokens), window) for window in windows[size]),
                    default=-1,
                ),
            )
        if score >= fuzzy_threshold:
            previous = seeds.get(entity.id)
            seeds[entity.id] = Seed(
                entity,
                max(score / 100, previous.score if previous else -1),
                "both" if previous else "fuzzy",
            )
    return sorted(seeds.values(), key=lambda s: (-s.score, s.entity.id))
