"""Ingestion router (spec C3).

Explicit bubble ids on the item (upload) or the source mean a fixed
assignment (confidence 1.0, no LLM). Otherwise: embed title + first 2,000
chars, cosine against bubble description embeddings, top-k candidates, one
LLM call picks the bubbles and a confidence. Low confidence or an empty pick
means `unsorted`.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

from omnistream.embed import Embedder
from omnistream.llm import LLMError
from omnistream.models import Bubble, RawItem, Source

T = TypeVar("T", bound=BaseModel)

TEXT_LIMIT = 2000

ROUTING_SYSTEM = """\
You route an item to knowledge bubbles. Each candidate is listed as \
`id | name | description | secondary hint`. The description is authoritative; \
the secondary hint is an auto-generated summary of current contents and may \
be stale.

Pick one or more candidate ids whose description fits the item. Return only \
ids that appear in the list. Reply as JSON: \
{"bubble_ids": [...], "confidence": <0..1>}. Use an empty list and low \
confidence if none fit.
"""


class BubbleChoice(BaseModel):
    bubble_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RouteDecision(BaseModel):
    bubble_ids: list[str]
    confidence: float
    unsorted: bool = False


class _Parser(Protocol):
    async def parse(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
    ) -> T: ...


def _clean(ids: list[str] | None, known: set[str]) -> list[str]:
    return [i for i in dict.fromkeys(ids or []) if i in known]


def _cosine(a: list[float], b: list[float]) -> float:
    # Embeddings are L2-normalized, so the dot product is the cosine.
    return sum(x * y for x, y in zip(a, b, strict=False))


class Router:
    def __init__(
        self,
        llm: _Parser,
        model: str,
        embedder: Embedder,
        threshold: float = 0.5,
        top_k: int = 3,
    ) -> None:
        self._llm = llm
        self._model = model
        self._embedder = embedder
        self._threshold = threshold
        self._top_k = top_k

    async def route(
        self, item: RawItem, source: Source, bubbles: list[Bubble]
    ) -> RouteDecision:
        known = {b.id for b in bubbles}
        fixed = _clean(item.bubble_ids_override, known) or _clean(
            source.bubble_ids, known
        )
        if fixed:
            return RouteDecision(bubble_ids=fixed, confidence=1.0)

        candidates = await self._candidates(item, bubbles)
        if not candidates:
            return RouteDecision(bubble_ids=[], confidence=0.0, unsorted=True)

        lines = "\n".join(
            f"{b.id} | {b.name} | {b.description} | {b.auto_summary or '-'}"
            for b in candidates
        )
        user = f"{lines}\n\nTitle: {item.title}\nText: {item.text[:TEXT_LIMIT]}"
        try:
            choice = await self._llm.parse(
                self._model, ROUTING_SYSTEM, user, BubbleChoice
            )
        except LLMError:
            return RouteDecision(bubble_ids=[], confidence=0.0, unsorted=True)
        ids = _clean(choice.bubble_ids, {b.id for b in candidates})
        if not ids or choice.confidence < self._threshold:
            return RouteDecision(
                bubble_ids=[], confidence=choice.confidence, unsorted=True
            )
        return RouteDecision(bubble_ids=ids, confidence=choice.confidence)

    async def _candidates(self, item: RawItem, bubbles: list[Bubble]) -> list[Bubble]:
        embedded = [b for b in bubbles if b.description_embedding]
        if not embedded:
            return []
        text = f"{item.title}\n{item.text[:TEXT_LIMIT]}"
        (vec,) = await self._embedder.embed([text])
        ranked = sorted(
            embedded,
            key=lambda b: _cosine(vec, b.description_embedding or []),
            reverse=True,
        )
        return ranked[: self._top_k]
