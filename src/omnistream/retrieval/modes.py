"""Selectable retrieval modes (spec 1.3 and 6/C5)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from omnistream.retrieval.models import RetrievalMode, RetrievalResult, TimeScope
from omnistream.retrieval.protocols import Retriever


class RetrievalDispatcher:
    """Dispatch explicit overrides or a configured default through one contract."""

    def __init__(
        self, retrievers: Mapping[RetrievalMode, Retriever], default_mode: RetrievalMode
    ) -> None:
        self.retrievers = dict(retrievers)
        self.default_mode = default_mode
        if any(mode not in {"classic", "graphiti", "own"} for mode in retrievers):
            raise ValueError("unknown retrieval mode")
        self._retriever(default_mode)

    def _retriever(self, mode: RetrievalMode) -> Retriever:
        if mode not in {"classic", "graphiti", "own"} or mode not in self.retrievers:
            raise ValueError(f"unknown or unconfigured retrieval mode: {mode}")
        return self.retrievers[mode]

    def retrieve(
        self,
        question: str,
        *,
        mode: RetrievalMode | None = None,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
        excluded_bubbles: Sequence[str] = (),
    ) -> RetrievalResult:
        selected = self.default_mode if mode is None else mode
        result = self._retriever(selected).retrieve(
            question,
            bubbles=bubbles,
            time_scope=time_scope,
            top_k=top_k,
            **(
                {"excluded_bubbles": excluded_bubbles}
                if excluded_bubbles and selected == "own"
                else {}
            ),
        )
        if result.mode != selected:
            raise ValueError(f"retriever returned {result.mode}, expected {selected}")
        return result
