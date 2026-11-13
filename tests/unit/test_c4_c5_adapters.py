"""C4 record-shape and live application-state regression tests."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from omnistream.bubbles import RepositoryBubbleCatalog
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.graph.neo4j_store import _entity, _fact
from omnistream.items import RepositoryItemStore
from omnistream.models import Bubble
from omnistream.retrieval.classic import collection_name
from omnistream.retrieval.models import TimeScope, fact_in_scope
from omnistream.retrieval.router import QueryRouter
from tests.unit.test_neo4j_store import EDGE

PAST = datetime(2020, 1, 1, tzinfo=UTC)
CHANGE = datetime(2021, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "key", ["published_at", "valid_at", "episode_valid_at", "created_at", None]
)
def test_c4_fact_date_fallback(key):
    data = {k: v for k, v in EDGE.items() if k not in {"published_at", "valid_at"}}
    if key:
        data[key] = PAST
    fact = _fact(data, "a", "b")
    assert fact.published_at == (PAST if key else datetime.min.replace(tzinfo=UTC))
    assert fact.item_id == "item"


def test_c4_date_precedence_and_entity_labels():
    fact = _fact(
        {
            **EDGE,
            "published_at": "",
            "valid_at": PAST,
            "created_at": CHANGE,
            "item_ids": ["i1", "i2"],
        },
        "a",
        "b",
    )
    assert fact.published_at == PAST and fact.item_ids == ("i1", "i2")
    data = {
        "uuid": "p",
        "name": "Alice",
        "group_id": "news",
        "labels": ["Entity", "Person"],
        "type": "Concept",
        "global_id": "g",
    }
    assert _entity(data).type == "Person"
    assert _entity(data).global_id == "g"
    assert (
        _entity(
            {**data, "labels": [], "entity_type": "Organization", "type": None}
        ).type
        == "Organization"
    )


def test_changed_ceo_time_semantics():
    old = replace(_fact(EDGE, "a", "old"), valid_at=PAST, invalid_at=CHANGE)
    new = replace(old, id="new", object_id="new", valid_at=CHANGE, invalid_at=None)
    assert not fact_in_scope(old, None) and fact_in_scope(new, None)
    assert fact_in_scope(old, TimeScope(PAST, PAST))
    assert not fact_in_scope(new, TimeScope(PAST, PAST))
    assert not fact_in_scope(replace(new, expired_at=CHANGE), None)
    assert fact_in_scope(replace(new, expired_at=CHANGE), TimeScope(CHANGE, CHANGE))


@pytest.mark.parametrize(
    "slug", ["news", "a", "abc-123", "a_b", "..", "a/b", "a b", "???", "x" * 600]
)
def test_shared_legal_chroma_names(slug):
    import re

    from omnistream.graph.chunks import collection_name as writer_name

    name = collection_name(slug)
    assert name == writer_name(slug)
    assert 3 <= len(name) <= 512
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*[A-Za-z0-9]", name)
    if slug == "news":
        assert name == "bubble_news"
    assert collection_name("a b") != collection_name("a/b")


async def test_sqlite_catalog_router_and_half_lives(settings, embedder):
    from omnistream.retrieval.runtime import CatalogHalfLives

    repo = Repository()
    try:
        vec = embedder.embed_documents(["news"])[0].tolist()
        await repo.create_bubble(
            Bubble(
                id="custom",
                name="News",
                description="authoritative",
                description_embedding=vec,
                auto_summary="supplement",
                half_life_days=7,
            )
        )
        catalog = RepositoryBubbleCatalog(repo)
        llm = Mock()
        llm.chat_json.return_value = {"bubbles": ["custom"], "rationale": "news match"}
        router = QueryRouter(llm, embedder, catalog)
        assert router.route("news").hints[0][1] == pytest.approx(1)
        assert router.route("news").rationale == "news match"
        lives = CatalogHalfLives(catalog)
        assert dict(lives.items()) == {"custom": 7}
        await repo.update_bubble("custom", half_life_days=19, description="edited")
        assert dict(lives.items()) == {"custom": 19}
        await repo.create_bubble(
            Bubble(id="second", name="Research", description="papers")
        )
        assert router.route("papers", pins=["second"]).bubbles == ("custom", "second")
        assert catalog.get("custom").description == "edited"
        await repo.delete_bubble("custom")
        assert router.route("papers").bubbles == ("second",)
    finally:
        await repo.close()


async def test_repository_originals_and_highlight_offsets(tmp_path):
    from omnistream.retrieval.citations import build_context
    from omnistream.retrieval.models import Chunk, RetrievalResult

    repo = Repository()
    root = tmp_path / "data"
    root.mkdir()
    clean = root / "hash.txt"
    original = "Title\n\nAlice   leads Acme.\nMore text."
    clean.write_text(original, encoding="utf-8")
    try:
        await repo.create_item(
            ItemRow(
                id="i",
                source_id="s",
                text_path=str(clean),
                raw_path=str(root / "hash.pdf"),
            )
        )
        store = RepositoryItemStore(repo, root, tokens_per_part=2)
        assert store.read_item("i").text == "Title Alice"
        assert len(store.read_parts("i", [1, 2, 3])) == 3
        assert store.item_text("i") == original
        result = RetrievalResult(
            "classic",
            chunks=(Chunk("c", "Alice leads Acme.", "i", "news", None, None),),
        )
        citation = build_context(result, item_store=store).citations[0]
        start, end = citation.spans[0]
        assert original[start:end] == "Alice   leads Acme."
        with pytest.raises(KeyError):
            store.read_item("missing")
        with pytest.raises(ValueError):
            store.read_item("../i")
        await repo.update_item("i", text_path=str(tmp_path / "outside.txt"))
        with pytest.raises(ValueError, match="escapes"):
            store.read_item("i")
    finally:
        await repo.close()


async def test_runtime_factory_uses_shared_dependencies_and_closes(
    settings, embedder, tmp_path, monkeypatch
):
    from omnistream.retrieval import runtime

    repo = Repository()
    settings.data_dir = str(tmp_path)
    graph = Mock()
    chroma = Mock()
    graphiti = Mock()
    llm, async_llm = Mock(), Mock()
    llm._client = Mock()
    async_llm._client = SimpleNamespace(close=AsyncMock())
    build_graph = Mock(return_value=graph)
    build_chroma = Mock(return_value=chroma)
    build_graphiti = Mock(return_value=graphiti)
    monkeypatch.setattr(runtime.Neo4jGraphStore, "from_settings", build_graph)
    monkeypatch.setattr(runtime, "make_chroma_client", build_chroma)
    monkeypatch.setattr(runtime.GraphitiRetriever, "from_settings", build_graphiti)
    monkeypatch.setattr(runtime, "LLMClient", Mock(return_value=llm))
    monkeypatch.setattr(runtime, "AsyncLLMClient", Mock(return_value=async_llm))
    answer = AsyncMock(return_value="qa-result")
    monkeypatch.setattr(runtime, "answer_question", answer)
    from datetime import UTC, datetime

    clock = lambda: datetime(2020, 6, 1, tzinfo=UTC)
    rt = runtime.build_query_runtime(
        settings, repo, embeddings=SimpleNamespace(service=embedder), now=clock
    )
    assert rt.router.now is clock
    assert rt.dispatcher.retrievers["own"].now is clock
    assert graph.now is clock
    assert graphiti.now is clock
    graph.ensure_schema.assert_not_called()
    graph.check_schema.assert_not_called()
    assert rt.embeddings is embedder
    assert rt.dispatcher.retrievers["classic"].embedder is embedder
    build_graphiti.assert_called_once_with(settings, embeddings=embedder)
    build_chroma.assert_called_once_with(tmp_path / "chroma")
    assert (
        await rt.answer(
            "q", mode="classic", pin=["news"], exclude=["finance"], subagents=False
        )
        == "qa-result"
    )
    graph.check_schema.assert_called_once_with(settings.embed_dim)
    assert answer.call_args.kwargs["pins"] == ["news"]
    await rt.close()
    await rt.close()
    graph.driver.close.assert_called_once()
    graphiti.close.assert_called_once()
    chroma.close.assert_called_once()
    async_llm._client.close.assert_awaited_once()
    with pytest.raises(RuntimeError):
        await rt.answer("q")
    await repo.close()


async def test_graphiti_changed_fact_temporal_filter_and_dates():
    from omnistream.retrieval.graphiti_mode import GraphitiRetriever
    from tests.unit.test_graphiti_mode import Searcher, edge

    old, new = edge(1), edge(2)
    old.valid_at, old.invalid_at = PAST, CHANGE
    old.expired_at = CHANGE
    new.valid_at = CHANGE
    old.attributes["published_at"] = PAST.isoformat()
    new.attributes["published_at"] = ""
    retriever = GraphitiRetriever(Searcher([old, new]))
    try:
        current = await retriever.aretrieve("CEO", bubbles=["news"])
        assert [f.fact.id for f in current.facts] == ["2"]
        assert current.facts[0].fact.published_at == CHANGE
        past = await retriever.aretrieve(
            "CEO", bubbles=["news"], time_scope=TimeScope(PAST, PAST)
        )
        assert [f.fact.id for f in past.facts] == ["1"]
    finally:
        await retriever.aclose()


async def test_graph_tools_past_scope_reaches_historical_facts(settings):
    import json

    from omnistream.agents.tools import ToolExecutor
    from omnistream.graph.memory_store import InMemoryGraphStore
    from omnistream.llm import ToolCall
    from omnistream.retrieval.models import Entity

    old = replace(_fact(EDGE, "a", "b"), valid_at=PAST, invalid_at=CHANGE)
    store = InMemoryGraphStore(
        [
            Entity("a", "Acme", "Organization", "news"),
            Entity("b", "Alice", "Person", "news"),
        ],
        [old],
    )
    for scope, expected in [(None, []), (TimeScope(PAST, PAST), ["f"])]:
        executor = ToolExecutor(
            bubble="news",
            mode="own",
            retriever=Mock(),
            graph_store=store,
            item_store=Mock(),
            time_scope=scope,
        )
        for name in ["neighbors", "facts"]:
            payload = json.loads(
                await executor.execute(ToolCall("id", name, {"entity_id": "a"}))
            )
            assert [f["id"] for f in payload["facts"]] == expected


async def test_c4_chunk_store_classic_shared_space(tmp_path, embedder):
    from omnistream.embed import SentenceTransformerEmbedder
    from omnistream.graph.chunks import ChunkStore
    from omnistream.retrieval.classic import ClassicRetriever, make_chroma_client

    writer = ChunkStore(
        str(tmp_path), SentenceTransformerEmbedder("unused", service=embedder), 300
    )
    reader = make_chroma_client(tmp_path / "chroma")
    try:
        await writer.add("news", "i", "Acme has CEO Bob", "https://source", None)
        result = ClassicRetriever(reader, embedder).retrieve(
            "Acme CEO", bubbles=["news"]
        )
        assert len(result.chunks) == 1
        assert result.chunks[0].published_at is None
        assert result.chunks[0].source_url == "https://source"
        assert result.chunks[0].item_id == "i"
        assert reader._system is writer._client._system
    finally:
        reader.close()
        writer._client.close()


async def test_c4_ensure_schema_creates_entity_index_with_settings_dimension():
    from omnistream.graph.ops import Neo4jGraphOps

    driver = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                ([], None, None),
                (
                    [{"options": {"indexConfig": {"vector.dimensions": 384}}}],
                    None,
                    None,
                ),
                ([], None, None),
                (
                    [
                        {
                            "entityType": "RELATIONSHIP",
                            "labelsOrTypes": ["RELATES_TO"],
                            "properties": ["fact_embedding"],
                            "options": {
                                "indexConfig": {
                                    "vector.dimensions": 384,
                                    "vector.similarity_function": "cosine",
                                }
                            },
                        }
                    ],
                    None,
                    None,
                ),
                ([], None, None),
                (
                    [
                        {
                            "name": "existing_global",
                            "options": {"indexConfig": {"vector.dimensions": 384}},
                        }
                    ],
                    None,
                    None,
                ),
                ([], None, None),
                ([], None, None),
            ]
        )
    )
    await Neo4jGraphOps(driver, 384, "custom`entities").ensure_schema()
    (query,) = driver.execute_query.call_args_list[0].args
    assert "`custom``entities` IF NOT EXISTS" in query
    assert driver.execute_query.call_args_list[1].kwargs["name"] == "custom`entities"
    assert "(e:Entity) ON (e.name_embedding)" in query
    assert driver.execute_query.call_args_list[0].kwargs["dim"] == 384


async def test_global_linker_uses_existing_equivalent_index():
    from omnistream.graph.ops import Neo4jGraphOps

    driver = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                ([], None, None),
                (
                    [{"options": {"indexConfig": {"vector.dimensions": 384}}}],
                    None,
                    None,
                ),
                ([], None, None),
                (
                    [
                        {
                            "entityType": "RELATIONSHIP",
                            "labelsOrTypes": ["RELATES_TO"],
                            "properties": ["fact_embedding"],
                            "options": {
                                "indexConfig": {
                                    "vector.dimensions": 384,
                                    "vector.similarity_function": "cosine",
                                }
                            },
                        }
                    ],
                    None,
                    None,
                ),
                ([], None, None),
                (
                    [
                        {
                            "name": "existing`global",
                            "options": {"indexConfig": {"vector.dimensions": 384}},
                        }
                    ],
                    None,
                    None,
                ),
                ([], None, None),
                ([], None, None),
                ([], None, None),
            ]
        )
    )
    ops = Neo4jGraphOps(driver, 384)
    await ops.ensure_schema()
    await ops.nearest_global_entities([1.0] * 384, "Organization", 5)
    query = driver.execute_query.call_args.args[0]
    assert "queryNodes($index," in query
    assert driver.execute_query.call_args.kwargs["index"] == "existing`global"
    assert "existing`global" not in query


async def test_recovery_only_collects_edges_from_the_requested_episode():
    from omnistream.graph.ops import Neo4jGraphOps

    driver = SimpleNamespace(execute_query=AsyncMock(return_value=([], None, None)))
    assert await Neo4jGraphOps(driver, 384).recover_episode("item", "group") is None
    query = driver.execute_query.call_args.args[0]
    assert "ep.uuid IN coalesce(r.episodes, [])" in query
    assert "r.expired_at >=" not in query
