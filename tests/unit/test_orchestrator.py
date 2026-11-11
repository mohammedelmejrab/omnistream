import asyncio

from omnistream.agents import run_subagents
from omnistream.agents.orchestrator import JoinedGroup
from omnistream.llm import ToolCall
from omnistream.retrieval.models import Entity, Subgraph
from tests.unit.test_agent_tools import Items, Retriever
from tests.unit.test_subagent import turn


async def test_parallel_failure_isolation(settings):
    ready = asyncio.Event()
    entered = 0

    class ParallelLLM:
        async def chat_with_tools(self, messages, tools):
            nonlocal entered
            entered += 1
            if entered == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 1)
            if "'bad'" in messages[0]["content"]:
                raise RuntimeError("bad bubble")
            return turn(content="done")

    result = await run_subagents(
        "q",
        bubbles=["good", "bad"],
        mode="classic",
        llm=ParallelLLM(),
        retriever=Retriever(),
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert [f.stopped_reason for f in result.findings] == ["answered", "error"]
    assert result.findings[0].answer == "done"
    assert result.joined_groups == []
    assert result.joins == ()


async def test_transitive_global_join(settings):
    class Graph:
        def neighbors(self, entity_id, depth=1):
            globals = {"a": ["g1"], "b": ["g2"], "c": ["g1", "g2"], "d": ["g3"]}[
                entity_id
            ]
            return Subgraph(
                {g: Entity(g, g, "person", entity_id, g) for g in globals}, ()
            )

    class LLM:
        async def chat_with_tools(self, messages, tools):
            bubble = messages[0]["content"].split("'")[1]
            if len(messages) == 2:
                return turn(ToolCall("t", "neighbors", {"entity_id": bubble}))
            return turn(content="done")

    result = await run_subagents(
        "q",
        bubbles=["a", "b", "c", "d"],
        mode="own",
        llm=LLM(),
        retriever=Retriever(),
        graph_store=Graph(),
        item_store=Items(),
        settings=settings,
    )
    assert result.joined_groups == [{"a", "b", "c"}]
    assert result.joins == (
        JoinedGroup(frozenset({"a", "b", "c"}), frozenset({"g1", "g2"})),
    )
    assert all(f.stopped_reason == "answered" for f in result.findings)


async def test_joins_are_transitive_with_shared_global_entities(settings):
    class Graph:
        def neighbors(self, entity_id, depth=1):
            linked = {"a": ["g1"], "b": ["g1", "g2"], "c": ["g2"]}[entity_id]
            return Subgraph(
                {g: Entity(g, g, "person", entity_id, g) for g in linked}, ()
            )

    class LLM:
        async def chat_with_tools(self, messages, tools):
            bubble = messages[0]["content"].split("'")[1]
            if len(messages) == 2:
                return turn(ToolCall("t", "neighbors", {"entity_id": bubble}))
            return turn(content="done")

    result = await run_subagents(
        "q",
        bubbles=["a", "b", "c"],
        mode="own",
        llm=LLM(),
        retriever=Retriever(),
        graph_store=Graph(),
        item_store=Items(),
        settings=settings,
    )
    # A-B join via g1 and B-C join via g2 collapse into one group carrying both ids.
    assert result.joins == (
        JoinedGroup(frozenset({"a", "b", "c"}), frozenset({"g1", "g2"})),
    )
    assert result.joined_groups == [{"a", "b", "c"}]


async def test_empty_bubbles(settings):
    result = await run_subagents(
        "q",
        bubbles=[],
        mode="classic",
        llm=None,
        retriever=Retriever(),
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert result.findings == ()
    assert result.joins == ()


async def test_gather_exception_has_detail(settings, monkeypatch):
    async def broken(self, question):
        raise ValueError("unexpected failure")

    monkeypatch.setattr("omnistream.agents.orchestrator.Subagent.run", broken)
    result = await run_subagents(
        "q",
        bubbles=["news"],
        mode="classic",
        llm=None,
        retriever=Retriever(),
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert result.findings[0].stopped_reason == "error"
    assert result.findings[0].error == "ValueError: unexpected failure"
