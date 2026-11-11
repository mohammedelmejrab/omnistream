"""Regression coverage for C5 review fixes."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from omnistream.bubbles import RepositoryBubbleCatalog
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.graph.neo4j_store import _fact
from omnistream.models import Bubble
from omnistream.retrieval import runtime
from omnistream.retrieval.models import Entity
from tests.unit.test_neo4j_store import EDGE


@pytest.mark.parametrize(
    "name, expected", [("News", 3), ("Finance", 30), ("Research", 365), ("Other", 30)]
)
async def test_repository_default_half_life(name, expected):
    repo = Repository()
    try:
        await repo.create_bubble(Bubble(id="b", name=name, description="d"))
        assert (await repo.get_bubble("b")).half_life_days == expected
        assert RepositoryBubbleCatalog(repo).get("b").half_life_days == expected
    finally:
        await repo.close()


async def test_repository_configured_and_explicit_half_lives():
    repo = Repository(settings=Settings(_env_file=None, half_life_news_days=12))
    try:
        await repo.create_bubble(Bubble(id="default", name="News", description="d"))
        await repo.create_bubble(
            Bubble(id="explicit", name="News", description="d", half_life_days=30)
        )
        assert (await repo.get_bubble("default")).half_life_days == 12
        assert (await repo.get_bubble("explicit")).half_life_days == 30
    finally:
        await repo.close()


async def test_tools_and_own_retriever_respect_exclusions(embedder):
    from omnistream.agents.tools import ToolExecutor
    from omnistream.llm import ToolCall
    from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever

    entities = [
        Entity("a", "Acme", "Organization", "news"),
        Entity("b", "Acme", "Organization", "finance"),
        Entity("c", "Bank", "Organization", "finance"),
    ]
    store = InMemoryGraphStore(entities, [_fact(EDGE, "b", "c")], [("a", "b")])
    retriever = OwnRetriever(store, embedder)
    assert retriever.retrieve("Acme", bubbles=["news"]).facts
    assert not retriever.retrieve(
        "Acme", bubbles=["news"], excluded_bubbles=["finance"]
    ).facts
    executor = ToolExecutor(
        bubble="news",
        mode="own",
        retriever=retriever,
        graph_store=store,
        item_store=Mock(),
        excluded_bubbles=("finance",),
    )
    for name, args in [
        ("search", {"query": "Acme"}),
        ("neighbors", {"entity_id": "a", "depth": 2}),
        ("facts", {"entity_id": "b"}),
    ]:
        result = json.loads(await executor.execute(ToolCall("id", name, args)))
        assert result["facts"] == []
        assert all(e["bubble"] != "finance" for e in result.get("entities", []))


@pytest.mark.parametrize("fail_at", ["async_llm", "runtime"])
async def test_runtime_construction_cleans_every_created_resource(
    settings, embedder, monkeypatch, fail_at
):
    graph, chroma, graphiti, llm = Mock(), Mock(), Mock(), Mock()
    async_llm = SimpleNamespace(_client=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(
        runtime.Neo4jGraphStore, "from_settings", Mock(return_value=graph)
    )
    monkeypatch.setattr(runtime, "make_chroma_client", Mock(return_value=chroma))
    monkeypatch.setattr(
        runtime.GraphitiRetriever, "from_settings", Mock(return_value=graphiti)
    )
    monkeypatch.setattr(runtime, "LLMClient", Mock(return_value=llm))
    monkeypatch.setattr(runtime, "AsyncLLMClient", Mock(return_value=async_llm))
    if fail_at == "async_llm":
        monkeypatch.setattr(
            runtime, "AsyncLLMClient", Mock(side_effect=ValueError("failure"))
        )
    else:
        monkeypatch.setattr(
            runtime, "QueryRuntime", Mock(side_effect=ValueError("failure"))
        )
    with pytest.raises(ValueError, match="failure"):
        runtime.build_query_runtime(settings, Mock(), embeddings=embedder)
    graph.driver.close.assert_called_once()
    graphiti.close.assert_called_once()
    chroma.close.assert_called_once()
    llm._client.close.assert_called_once()
    if fail_at == "runtime":
        async_llm._client.close.assert_awaited_once()


@pytest.mark.parametrize("finish", [True, False])
async def test_runtime_close_waits_or_cancels_inflight(
    settings, embedder, monkeypatch, finish
):
    graph, chroma, graphiti, llm = Mock(), Mock(), Mock(), Mock()
    async_llm = SimpleNamespace(_client=SimpleNamespace(close=AsyncMock()))
    entered, release = asyncio.Event(), asyncio.Event()

    async def answer(*args, **kwargs):
        entered.set()
        await release.wait()
        assert not graph.driver.close.called
        return "done"

    monkeypatch.setattr(runtime, "answer_question", answer)
    rt = runtime.QueryRuntime(
        settings,
        SimpleNamespace(read_bubbles=list),
        embedder,
        graph,
        chroma,
        graphiti,
        llm,
        async_llm,
    )
    rt.close_timeout = 0.02
    answering = asyncio.create_task(rt.answer("q"))
    await entered.wait()
    closing = asyncio.create_task(rt.close())
    await asyncio.sleep(0)
    assert not graph.driver.close.called
    with pytest.raises(RuntimeError, match="closed"):
        await rt.answer("new")
    if finish:
        release.set()
        assert await answering == "done"
    else:
        with pytest.raises(asyncio.CancelledError):
            await answering
    await closing
    graph.driver.close.assert_called_once()
    await rt.close()


async def test_from_path_preserves_half_life_settings(tmp_path):
    repo = Repository.from_path(
        str(tmp_path / "state.db"),
        settings=Settings(_env_file=None, half_life_news_days=19),
    )
    try:
        await repo.create_bubble(Bubble(id="n", name="News", description="news"))
        assert (await repo.get_bubble("n")).half_life_days == 19
    finally:
        await repo.close()


async def test_runtime_schema_initialization_is_read_only_and_off_loop(settings):
    import threading

    graph = Mock()
    loop_thread = threading.get_ident()

    def check(dim):
        assert threading.get_ident() != loop_thread
        assert dim == settings.embed_dim

    graph.check_schema.side_effect = check
    graph.ensure_schema.side_effect = check
    repo = Mock()
    repo.read_bubbles.return_value = []
    rt = runtime.QueryRuntime(
        settings, repo, Mock(), graph, Mock(), Mock(), Mock(), Mock()
    )
    await asyncio.gather(rt.initialize(), rt.initialize())
    graph.check_schema.assert_called_once_with(settings.embed_dim)
    graph.ensure_schema.assert_not_called()
    await rt.initialize(create_schema=True)
    graph.ensure_schema.assert_called_once_with(settings.embed_dim)


async def test_query_graphiti_never_runs_constructor_schema_task(
    settings, embedder, monkeypatch
):
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    from omnistream.graph.graphiti_client import build_graphiti

    calls = []

    async def provision(self):
        calls.append("DDL")

    monkeypatch.setattr(Neo4jDriver, "build_indices_and_constraints", provision)
    graphiti = build_graphiti(settings, embedder, read_only=True)
    try:
        await asyncio.sleep(0)
        assert calls == []
        assert graphiti.driver._init_task.cancelled()
    finally:
        await graphiti.close()
