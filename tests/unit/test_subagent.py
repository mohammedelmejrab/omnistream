import asyncio
import copy
import json

import pytest

from omnistream.agents import Subagent
from omnistream.llm import AssistantTurn, ToolCall
from tests.unit.test_agent_tools import Graph, Items, Retriever


def turn(*calls, content=None):
    raw = {"role": "assistant", "content": content}
    if calls:
        raw["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in calls
        ]
    return AssistantTurn(content, tuple(calls), raw)


class Scripted:
    def __init__(self, *turns):
        self.turns = iter(turns)
        self.requests = []
        self.choices = []

    async def chat_with_tools(self, messages, tools, **kwargs):
        self.requests.append((copy.deepcopy(messages), tools))
        self.choices.append(kwargs.get("tool_choice"))
        value = next(self.turns)
        if isinstance(value, Exception):
            raise value
        return value


def agent(settings, llm, mode="classic", retriever=None):
    return Subagent(
        bubble="news",
        mode=mode,
        llm=llm,
        retriever=retriever or Retriever(),
        graph_store=None if mode == "classic" else Graph(),
        item_store=Items(),
        settings=settings,
    )


@pytest.mark.parametrize("mode", ["classic", "own", "graphiti"])
@pytest.mark.parametrize("batch", [False, True])
async def test_six_call_cap_and_forced_answer(settings, mode, batch):
    calls = [
        ToolCall(str(i), "search", {"query": "q"}) for i in range(8 if batch else 6)
    ]
    llm = Scripted(
        *([turn(*calls)] if batch else [turn(c) for c in calls]),
        turn(content="Final [item]"),
    )
    result = await agent(settings, llm, mode).run("q")
    assert result.tool_calls_used == 6
    assert result.stopped_reason == "tool_limit"
    assert result.answer == "Final [item]"
    assert llm.requests[-1][1] == llm.requests[0][1]
    assert llm.choices[-1] == "none"
    assert result.evidence_facts == ("f",)
    assert result.evidence_chunks == ("c",)
    assert result.item_ids == ("item", "item2")
    if mode != "classic":
        assert result.global_entity_ids == ("global",)
    if batch:
        results = [
            json.loads(m["content"]) for m in llm.requests[-1][0] if m["role"] == "tool"
        ]
        assert len(results) == 8
        assert sum("error" in r for r in results) == 2


async def test_errors_return_to_model_and_continue(settings):
    llm = Scripted(
        turn(
            ToolCall("1", "neighbors", {"entity_id": "e"}),
            ToolCall("2", "search", {}, "bad JSON"),
        ),
        turn(ToolCall("3", "read_item", {"item_id": "original", "part": [1, 2]})),
        turn(content="done"),
    )
    result = await agent(settings, llm).run("q")
    assert result.stopped_reason == "answered"
    assert result.tool_calls_used == 3
    assert result.item_ids == ("original",)
    messages, schemas = llm.requests[1]
    assert {s["function"]["name"] for s in schemas} == {"search", "read_item"}
    assert all(
        "error" in json.loads(m["content"]) for m in messages if m["role"] == "tool"
    )


@pytest.mark.parametrize("mode", ["classic", "own"])
async def test_timeout_keeps_partial_findings(settings, mode):
    started = asyncio.Event()

    class Slow(Scripted):
        async def chat_with_tools(self, messages, tools, **kwargs):
            if started.is_set():
                await asyncio.Event().wait()
            started.set()
            return turn(ToolCall("1", "search", {"query": "q"}), content="Partial")

    settings.subagent_timeout_seconds = 0.1
    result = await agent(settings, Slow(), mode).run("q")
    assert result.stopped_reason == "timeout"
    assert result.answer == "Partial"
    assert result.evidence_chunks == ("c",)


async def test_slow_tool_timeout(settings):
    class SlowRetriever:
        async def retrieve(self, *args, **kwargs):
            await asyncio.Event().wait()

    settings.subagent_timeout_seconds = 0.01
    result = await agent(
        settings,
        Scripted(turn(ToolCall("t", "search", {"query": "q"}))),
        retriever=SlowRetriever(),
    ).run("q")
    assert result.stopped_reason == "timeout"


async def test_provider_failure(settings):
    result = await agent(settings, Scripted(RuntimeError("provider failed"))).run("q")
    assert result.stopped_reason == "error"
    assert result.error == "RuntimeError: provider failed"


async def test_custom_limit_and_noncompliant_final_turn(settings):
    settings.subagent_max_tool_calls = 1
    call = ToolCall("t", "search", {"query": "q"})
    result = await agent(settings, Scripted(turn(call), turn(call))).run("q")
    assert result.tool_calls_used == 1
    assert result.stopped_reason == "tool_limit"


async def test_typed_evidence_first_seen_and_error_truncation(settings):
    from dataclasses import replace

    from omnistream.retrieval.models import RetrievalResult, ScoredFact
    from tests.unit.test_agent_tools import CHUNK, FACT

    class Changing:
        def __init__(self):
            self.n = 0

        def retrieve(self, *args, **kwargs):
            self.n += 1
            fact = FACT if self.n == 1 else replace(FACT, text="Later duplicate")
            return RetrievalResult("classic", (ScoredFact(fact, 1),), (CHUNK,))

    call = ToolCall("t", "search", {"query": "q"})
    result = await agent(
        settings,
        Scripted(turn(call), turn(call), RuntimeError("x" * 2000)),
        retriever=Changing(),
    ).run("q")
    assert result.facts == (FACT,)
    assert result.chunks == (CHUNK,)
    assert result.facts[0].published_at == FACT.published_at
    assert result.error.startswith("RuntimeError: ")
    assert len(result.error) == 1000
