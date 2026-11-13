"""Structural store and retriever interfaces for spec section 6/C5."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

import numpy as np

from omnistream.retrieval.models import (
    Entity,
    Fact,
    ItemPart,
    RetrievalResult,
    Subgraph,
    TimeScope,
)


@runtime_checkable
class Retriever(Protocol):
    """Common query contract for all three C5 retrieval modes."""

    def retrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult: ...


@runtime_checkable
class GraphStore(Protocol):
    """C5 entity seeding, bounded expansion and graph tool access."""

    def seed_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 5,
        min_cosine: float = 0.5,
    ) -> list[tuple[Entity, float]]: ...

    def seed_by_fact_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 10,
        time_scope: TimeScope | None = None,
    ) -> list[tuple[Entity, float]]: ...

    def entities_in(self, bubbles: Sequence[str]) -> list[Entity]:
        """Return candidates for fuzzy entity-name matching."""
        ...

    def expand(
        self,
        seed_ids: Sequence[str],
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None,
        max_hops: int = 2,
        max_edges: int = 500,
        excluded_bubbles: Sequence[str] = (),
    ) -> Subgraph: ...

    def neighbors(
        self, entity_id: str, depth: int = 1, *, excluded_bubbles: Sequence[str] = ()
    ) -> Subgraph:
        """Return the neighborhood at depth 1..2 (spec C5 tools)."""
        ...

    def facts_about(
        self,
        entity_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        excluded_bubbles: Sequence[str] = (),
    ) -> list[Fact]: ...

    def fact_embeddings(self, fact_ids: Sequence[str]) -> dict[str, np.ndarray]: ...


@runtime_checkable
class ItemStore(Protocol):
    """Original clean-text access with item provenance (spec 4.2 and C5)."""

    def read_item(self, item_id: str, part: int = 1) -> ItemPart: ...

    def item_text(self, item_id: str, max_tokens: int = 4000) -> str: ...
