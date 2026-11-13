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
    source: Literal["vector", "fuzzy", "both", "fact"]


def is_named_entity(entity: Entity) -> bool:
    """Use ingestion's ontology, independent of spelling, case, or language.

    Concept and untyped Entity describe arbitrary phrases. The other shared
    ontology types represent named entities. SAME_AS alone is insufficient:
    ingestion can link generic concepts too.
    """
    return entity.type.casefold() in {
        "person",
        "organization",
        "location",
        "product",
        "event",
        "financialinstrument",
        "publication",
    }


def seed_entities(
    question: str,
    question_embedding: np.ndarray,
    store: GraphStore,
    *,
    bubbles: Sequence[str],
    top_k: int = 5,
    min_cosine: float = 0.5,
    fuzzy_threshold: float = 90,
    fact_top_k: int = 10,
    time_scope=None,
    max_seeds: int = 10,
) -> list[Seed]:
    """Combine bounded name/fact candidates, capped by distinct identity.

    Ten seeds is twice the five-name budget; fuzzy and fact endpoints share
    this total budget and the ontology eligibility rule.
    """
    if isinstance(max_seeds, bool) or not isinstance(max_seeds, int) or max_seeds < 0:
        raise ValueError("max_seeds must be a non-negative integer")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a non-negative integer")
    if not 0 <= fuzzy_threshold <= 100:
        raise ValueError("fuzzy_threshold must be within [0, 100]")
    # Bounded candidate pool; stores can match query tokens on the server.
    entities = store.name_candidates(question, bubbles=bubbles, limit=100)
    seeds = {
        e.id: Seed(e, score, "vector")
        for e, score in store.seed_by_embedding(
            question_embedding,
            bubbles=bubbles,
            top_k=max(50, top_k * 10),
            min_cosine=min_cosine,
        )
        if is_named_entity(e)
    }
    # Budget distinct identities after filtering; scan all candidates to refill.
    distinct = {}
    for seed in sorted(seeds.values(), key=lambda s: (-s.score, s.entity.id)):
        distinct.setdefault(seed.entity.global_id or seed.entity.id, seed)
    seeds = {s.entity.id: s for s in list(distinct.values())[:top_k]}
    question_tokens = re.findall(r"\w+", question.casefold())
    # Compare complete token windows, never substrings within another word.
    windows: dict[int, list[str]] = {}
    for entity in entities:
        if not is_named_entity(entity):
            continue
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
    for entity, score in store.seed_by_fact_embedding(
        question_embedding, bubbles=bubbles, top_k=fact_top_k, time_scope=time_scope
    ):
        if not is_named_entity(entity) or score <= 0:
            continue
        previous = seeds.get(entity.id)
        if previous is None or score > previous.score:
            seeds[entity.id] = Seed(entity, score, "fact")
    distinct = {}
    for seed in sorted(seeds.values(), key=lambda s: (-s.score, s.entity.id)):
        distinct.setdefault(seed.entity.global_id or seed.entity.id, seed)
    return list(distinct.values())[:max_seeds]
