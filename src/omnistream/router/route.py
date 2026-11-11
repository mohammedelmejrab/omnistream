from typing import Protocol, TypeVar

from pydantic import BaseModel

from omnistream.llm import LLMError
from omnistream.models import Bubble, RawItem, Source

T = TypeVar("T", bound=BaseModel)

TEXT_LIMIT = 1500

ROUTING_SYSTEM = """\
You route an item to knowledge bubbles. Each bubble is listed as \
`id | name | description`.

Pick zero or more bubble ids from the list whose description fits the item. \
Return only ids that appear in the list. One item may belong to several bubbles. \
Return an empty list if none fit.
"""


class BubbleChoice(BaseModel):
    bubble_ids: list[str]


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
    """Keep known ids only, de-duplicated, order preserved."""
    return [i for i in dict.fromkeys(ids or []) if i in known]


class Router:
    """Decides which bubbles an item is written to.

    Precedence (first non-empty result, after filtering to known ids and
    de-duplicating, wins): item override; source bubbles when auto_route is
    off; LLM classifier; source bubbles as fallback; otherwise [] (unrouted).
    Only LLMError from the classifier is swallowed.
    """

    def __init__(self, llm: _Parser, model: str):
        self._llm = llm
        self._model = model

    async def route(
        self, item: RawItem, source: Source, bubbles: list[Bubble]
    ) -> list[str]:
        if not bubbles:
            return []
        known = {b.id for b in bubbles}

        if override := _clean(item.bubble_ids_override, known):
            return override

        configured = _clean(source.bubble_ids, known)
        if not source.auto_route and configured:
            return configured

        lines = "\n".join(f"{b.id} | {b.name} | {b.description}" for b in bubbles)
        user = f"{lines}\n\nTitle: {item.title}\nText: {item.text[:TEXT_LIMIT]}"
        try:
            choice = await self._llm.parse(
                self._model, ROUTING_SYSTEM, user, BubbleChoice
            )
        except LLMError:
            return configured
        return _clean(choice.bubble_ids, known) or configured
