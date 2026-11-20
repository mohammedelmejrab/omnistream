"""Fakes for the UI trace and API tests: no network, no models, no Neo4j.

The fakes sit where the real objects sit, so the real ``answer_question`` and
the real subagent loop run against them.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from omnistream.config import Settings
from omnistream.llm import AssistantTurn, ToolCall
from omnistream.retrieval.models import Entity, Fact, RetrievalResult, ScoredFact
from omnistream.retrieval.router import RoutingDecision

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def fact(
    fact_id: str = "f1",
    *,
    bubble: str = "news",
    item_id: str = "i1",
    subject: str = "e-alice",
    obj: str = "e-acme",
) -> Fact:
    return Fact(
        id=fact_id,
        subject_id=subject,
        object_id=obj,
        relation="LEADS",
        text="Alice leads Acme.",
        bubble=bubble,
        item_id=item_id,
        source_url="https://example.test/i1",
        published_at=NOW,
    )


class FakeRetriever:
    """Own-retriever stand-in. ``gate`` blocks the call until released (for cancel tests)."""

    def __init__(
        self,
        *,
        gate: threading.Event | None = None,
        started: threading.Event | None = None,
        score: float = 0.9,
    ) -> None:
        self.score = score
        self.gate = gate
        self.started = started
        self.calls: list[list[str]] = []
        self.now = None

    def retrieve(self, question: str, *, bubbles, time_scope=None, top_k=None, excluded_bubbles=(), **_: Any) -> RetrievalResult:
        self.calls.append(list(bubbles))
        if self.started is not None:
            self.started.set()
        if self.gate is not None:
            self.gate.wait(10)
        bubble = bubbles[0] if bubbles else "news"
        return RetrievalResult(
            mode="own",
            facts=(ScoredFact(fact(f"f-{bubble}", bubble=bubble), self.score),),
            chunks=(),
            seeds=(Entity(id="e-alice", name="Alice", type="person", bubble=bubble),),
        )


class FakeDispatcher:
    default_mode = "own"

    def __init__(self, retriever: FakeRetriever) -> None:
        self.retrievers = {"own": retriever}
        self.calls = 0

    def retrieve(self, question: str, *, mode=None, bubbles, time_scope=None, top_k=None, excluded_bubbles=()) -> RetrievalResult:
        self.calls += 1
        return self.retrievers["own"].retrieve(question, bubbles=bubbles, time_scope=time_scope, excluded_bubbles=excluded_bubbles)


class FakeRouter:
    def __init__(self, strategy: str = "simple") -> None:
        self.strategy = strategy

    def route(self, question: str, *, pins=(), exclude=()) -> RoutingDecision:
        bubbles = tuple(pins) or ("news",)
        return RoutingDecision(bubbles=bubbles, strategy=self.strategy, rationale="fake route")


class FakeChat:
    """Sync LLM client (the answer generator). Counts calls."""

    def __init__(self, text: str = "Alice leads Acme [1].") -> None:
        self.text = text
        self.calls = 0

    def chat(self, messages, **kwargs: Any) -> str:
        self.calls += 1
        return self.text


class FakeAsyncLLM:
    """Async function-calling client for subagents.

    Default: one ``search`` call, then a final finding. ``fail`` raises on
    every call; ``silent`` answers without ever calling a tool.
    """

    def __init__(self, *, fail: bool = False, silent: bool = False) -> None:
        self.fail = fail
        self.silent = silent

    async def chat_with_tools(self, messages, tools, **kwargs: Any) -> AssistantTurn:
        if self.fail:
            raise RuntimeError("provider exploded")
        searched = any(m.get("role") == "tool" for m in messages)
        if not self.silent and not searched:
            call = ToolCall(id="c1", name="search", arguments={"query": "alice"})
            return AssistantTurn(None, (call,), {"role": "assistant", "content": None})
        return AssistantTurn("Finding: Alice leads Acme.", (), {"role": "assistant", "content": "Finding"})


class FakeGraph:
    def entities_in(self, bubbles, ids=None):
        return []


class FakeRuntime:
    """Shaped like ``QueryRuntime`` for the attributes the UI uses."""

    def __init__(
        self,
        *,
        router: Any = None,
        dispatcher: Any = None,
        llm: Any = None,
        async_llm: Any = None,
        settings: Settings | None = None,
    ) -> None:
        self.router = router or FakeRouter()
        self.dispatcher = dispatcher or FakeDispatcher(FakeRetriever())
        self.llm = llm or FakeChat()
        self.async_llm = async_llm or FakeAsyncLLM()
        self.graph = FakeGraph()
        self.items = object()
        self.settings = settings or Settings(_env_file=None)
        self.closed = False

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class GraphOps:
    """GraphOps stand-in: one entity pair per bubble, shaped like ops.bubble_graph."""

    async def bubble_graph(self, group_id: str, limit: int = 50, *, include_historical: bool = False) -> dict:
        return {
            "nodes": [
                {"id": f"{group_id}-alice", "label": "Alice", "value": 2},
                {"id": f"{group_id}-acme", "label": "Acme", "value": 1},
            ],
            "edges": [
                {"id": f"{group_id}-r1", "from": f"{group_id}-alice", "to": f"{group_id}-acme", "label": "LEADS"}
            ],
        }

    async def bubble_map(self) -> list:
        return []

    async def group_counts(self, group_id: str) -> dict:
        return {"episodes": 0, "entities": 2, "facts": 1}

    async def delete_group(self, group_id: str) -> None:
        return None

    async def recent_episodes(self, group: str) -> list:
        return []


def fake_scheduler() -> SimpleNamespace:
    from unittest.mock import AsyncMock

    return SimpleNamespace(
        schedule_source=lambda source: None,
        unschedule_source=lambda source_id: None,
        poll_source=AsyncMock(return_value=[]),
    )
