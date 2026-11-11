"""Offline tests for the graphiti-core client adapters and from_settings wiring.

No network access: embeddings come from the deterministic HashingEncoder and
the Graphiti constructor is faked, so these tests never touch Neo4j or an LLM.
graphiti_core itself is imported only where the wrapper classes need it
(importorskip keeps the file collectible without the optional dependency).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import BaseModel

pytest.importorskip("graphiti_core")

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.errors import EmptyResponseError
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.graphiti_clients import (
    _SEARCH_QUERY_MODE,
    GraphitiLLMClient,
    LocalEmbedderClient,
    LocalRerankerClient,
)
from omnistream.retrieval.graphiti_mode import (
    GRAPHITI_MAX_OUTPUT_TOKENS,
    GraphitiCoreSearcher,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_clients_subclass_graphiti_abstract_clients():
    assert issubclass(LocalEmbedderClient, EmbedderClient)
    assert issubclass(LocalRerankerClient, CrossEncoderClient)
    assert issubclass(GraphitiLLMClient, OpenAIGenericClient)


@pytest.mark.asyncio
async def test_local_embedder_create_and_create_batch(embedder):
    client = LocalEmbedderClient(embedder)
    expected = embedder.embed_documents(["Zephyr Labs", "Helios Grid"])
    assert expected.shape[1] == 384

    first = await client.create(["Zephyr Labs", "Helios Grid"])
    assert len(first) == 384
    np.testing.assert_allclose(first, expected[0], atol=1e-6)

    as_str = await client.create("Zephyr Labs")
    np.testing.assert_allclose(as_str, expected[0], atol=1e-6)

    batch = await client.create_batch(["Zephyr Labs", "Helios Grid"])
    assert len(batch) == 2
    np.testing.assert_allclose(batch, expected, atol=1e-6)

    assert await client.create_batch([]) == []


@pytest.mark.asyncio
async def test_local_embedder_rejects_token_inputs(embedder):
    client = LocalEmbedderClient(embedder)
    with pytest.raises(TypeError, match="str"):
        await client.create([1, 2, 3])
    with pytest.raises(TypeError, match="str"):
        await client.create_batch(["ok", 42])


class _TrackingEmbeddings:
    """Embeds nothing but records which space each call asked for."""

    def __init__(self):
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def embed_documents(self, texts):
        self.calls.append(("documents", tuple(texts)))
        return np.zeros((len(texts), 384), dtype=np.float32)

    def embed_queries(self, texts):
        self.calls.append(("queries", tuple(texts)))
        return np.zeros((len(texts), 384), dtype=np.float32)


@pytest.mark.asyncio
async def test_local_embedder_create_honours_search_query_mode_flag():
    embeddings = _TrackingEmbeddings()
    client = LocalEmbedderClient(embeddings)

    # Default: document encoding (ingestion and stored-vector space).
    await client.create(["Zephyr Labs"])
    await client.create_batch(["Helios Grid"])
    assert embeddings.calls == [
        ("documents", ("Zephyr Labs",)),
        ("documents", ("Helios Grid",)),
    ]

    # Query mode (what graphiti's search does): create embeds the query with
    # the BGE query instruction; create_batch is never used at search time and
    # stays in document space even while the flag is set.
    embeddings.calls.clear()
    token = _SEARCH_QUERY_MODE.set(True)
    try:
        await client.create(["Zephyr Labs"])
        await client.create_batch(["Helios Grid"])
    finally:
        _SEARCH_QUERY_MODE.reset(token)
    assert embeddings.calls == [
        ("queries", ("Zephyr Labs",)),
        ("documents", ("Helios Grid",)),
    ]

    # The flag is a contextvar: after reset, document encoding returns.
    embeddings.calls.clear()
    await client.create("Zephyr Labs")
    assert embeddings.calls == [("documents", ("Zephyr Labs",))]


@pytest.mark.asyncio
async def test_searcher_sets_query_mode_only_around_graphiti_search(embedder):
    client = LocalEmbedderClient(embedder)
    states: list[bool] = []
    embedded: list[tuple[str, tuple[str, ...]]] = []
    original_docs = embedder.embed_documents
    original_queries = embedder.embed_queries

    def tracking_docs(texts):
        embedded.append(("documents", tuple(texts)))
        return original_docs(texts)

    def tracking_queries(texts):
        embedded.append(("queries", tuple(texts)))
        return original_queries(texts)

    embedder.embed_documents = tracking_docs  # type: ignore[method-assign]
    embedder.embed_queries = tracking_queries  # type: ignore[method-assign]

    class FakeGraphiti:
        async def search(self, query, *, group_ids, num_results):
            states.append(_SEARCH_QUERY_MODE.get())
            # The only embedder call graphiti's search makes: the query vector.
            await client.create([query])
            return []

    searcher = GraphitiCoreSearcher(FakeGraphiti())
    assert not _SEARCH_QUERY_MODE.get()
    await searcher.search("Zephyr Labs", group_ids=["news"], num_results=10)
    assert states == [True]
    assert embedded == [("queries", ("Zephyr Labs",))]
    assert not _SEARCH_QUERY_MODE.get(), "query mode leaked past the search call"


@pytest.mark.asyncio
async def test_searcher_resets_query_mode_when_search_raises(embedder):
    class FailingGraphiti:
        async def search(self, query, *, group_ids, num_results):
            assert _SEARCH_QUERY_MODE.get()
            raise ValueError("boom")

    searcher = GraphitiCoreSearcher(FailingGraphiti())
    assert not _SEARCH_QUERY_MODE.get()
    with pytest.raises(ValueError, match="boom"):
        await searcher.search("q", group_ids=["news"], num_results=10)
    assert not _SEARCH_QUERY_MODE.get(), "query mode leaked past the failed search"


@pytest.mark.asyncio
async def test_local_reranker_ranks_passages_by_cosine(embedder):
    client = LocalRerankerClient(embedder)
    passages = [
        "banana smoothie recipe",
        "quantum flux generator",
        "quantum flux capacitor repair manual",
    ]
    ranked = await client.rank("quantum flux", passages)
    assert [passage for passage, _ in ranked] == sorted(
        passages,
        key=lambda p: (
            -float(
                embedder.cosine_similarity(
                    embedder.embed_query("quantum flux"),
                    embedder.embed_documents(passages),
                )[passages.index(p)]
            )
        ),
    )
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0][0] != "banana smoothie recipe"
    assert ranked[-1][0] == "banana smoothie recipe"
    assert await client.rank("anything", []) == []


class FakeCompletions:
    """Fake ``AsyncOpenAI`` chat.completions surface with canned JSON content."""

    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls: list[dict] = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def _echo_response() -> str:
    return json.dumps(
        {"$defs": {"Edge": {}}, "properties": {"edges": {}}, "type": "object"}
    )


def _echo_inside_field() -> str:
    return json.dumps(
        {"edges": {"$defs": {"Edge": {}}, "properties": {}, "type": "object"}}
    )


def _llm_client(contents: list[str]) -> GraphitiLLMClient:
    return GraphitiLLMClient(
        config=LLMConfig(api_key="test-key", model="deepseek/deepseek-chat"),
        client=FakeCompletions(contents),
        structured_output_mode="json_object",
    )


class Edges(BaseModel):
    edges: list[dict]


@pytest.mark.asyncio
async def test_llm_client_detects_and_retries_schema_echo():
    client = _llm_client([_echo_response(), json.dumps({"edges": []})])
    messages = [
        Message(role="system", content="extract"),
        Message(role="user", content="text"),
    ]
    assert GraphitiLLMClient._is_schema_echo({"$defs": {}, "type": "object"})
    assert not GraphitiLLMClient._is_schema_echo({"edges": []})
    assert GraphitiLLMClient._is_schema_echo(
        {"edges": {"$defs": {}, "type": "object"}}, response_model=Edges
    )

    # A schema echo raises EmptyResponseError (transient for graphiti's
    # tenacity wrapper) and appends the correction instruction once.
    with pytest.raises(EmptyResponseError):
        await client._generate_response(messages, response_model=Edges)
    assert GraphitiLLMClient._CORRECTION in messages[-1].content

    # The next sample is accepted and returned unchanged, with no extra
    # correction appended.
    parsed = await client._generate_response(messages, response_model=Edges)
    assert parsed == {"edges": []}
    assert messages[-1].content.count(GraphitiLLMClient._CORRECTION) == 1


@pytest.mark.asyncio
async def test_llm_client_rejects_echo_inside_a_field():
    client = _llm_client([_echo_inside_field()])
    messages = [
        Message(role="system", content="extract"),
        Message(role="user", content="text"),
    ]
    with pytest.raises(EmptyResponseError):
        await client._generate_response(messages, response_model=Edges)
    assert GraphitiLLMClient._CORRECTION in messages[-1].content


@pytest.fixture
def faked_graphiti_clients(monkeypatch):
    """Fake Graphiti + client constructors; returns the recorded calls."""
    graphiti_kwargs: dict = {}

    class FakeGraphiti:
        def __init__(self, uri, user, password, **kwargs):
            graphiti_kwargs.update(
                {"uri": uri, "user": user, "password": password, **kwargs}
            )

    class FakeLLMClient:
        def __init__(self, **kwargs):
            calls["llm"].append(kwargs)

    class FakeEmbedder:
        def __init__(self, service):
            calls["embedder"].append(service)

    class FakeReranker:
        def __init__(self, service):
            calls["reranker"].append(service)

    calls: dict = {"llm": [], "embedder": [], "reranker": []}
    monkeypatch.setattr("graphiti_core.Graphiti", FakeGraphiti)
    monkeypatch.setattr(
        "omnistream.retrieval.graphiti_clients.GraphitiLLMClient", FakeLLMClient
    )
    monkeypatch.setattr(
        "omnistream.retrieval.graphiti_clients.LocalEmbedderClient", FakeEmbedder
    )
    monkeypatch.setattr(
        "omnistream.retrieval.graphiti_clients.LocalRerankerClient", FakeReranker
    )
    return {"graphiti": graphiti_kwargs, "calls": calls, "graphiti_class": FakeGraphiti}


def test_from_settings_injects_custom_clients_never_openai_defaults(
    settings, faked_graphiti_clients
):
    searcher = GraphitiCoreSearcher.from_settings(settings)
    kwargs = faked_graphiti_clients["graphiti"]
    calls = faked_graphiti_clients["calls"]

    assert isinstance(searcher.graphiti, faked_graphiti_clients["graphiti_class"])
    assert kwargs["uri"] == settings.neo4j_uri
    assert kwargs["user"] == settings.neo4j_user
    assert kwargs["password"] == settings.neo4j_password.get_secret_value()
    # All three clients are explicitly injected; graphiti must never fall back
    # to its OpenAI defaults.
    assert kwargs["llm_client"] is not None
    assert kwargs["embedder"] is not None
    assert kwargs["cross_encoder"] is not None

    llm_kwargs = calls["llm"][0]
    assert llm_kwargs["structured_output_mode"] == "json_object"
    assert llm_kwargs["max_tokens"] == GRAPHITI_MAX_OUTPUT_TOKENS == 8192
    config = llm_kwargs["config"]
    assert config.base_url == settings.llm_base_url
    assert config.model == settings.llm_model
    assert config.api_key == settings.llm_api_key.get_secret_value()
    assert config.api_key == "test-key"

    # Embedder and cross-encoder share one EmbeddingService instance.
    assert len(calls["embedder"]) == 1
    assert calls["reranker"][0] is calls["embedder"][0]
    service = calls["embedder"][0]
    assert isinstance(service, EmbeddingService)
    assert service.model_name == settings.embedding_model
    assert service.dimension == settings.embedding_dim


def test_from_settings_accepts_injected_embedding_service(
    settings, embedder, faked_graphiti_clients
):
    GraphitiCoreSearcher.from_settings(settings, embeddings=embedder)
    calls = faked_graphiti_clients["calls"]
    assert calls["embedder"] == [embedder]
    assert calls["reranker"] == [embedder]


def test_from_settings_keeps_graphiti_import_lazy(settings):
    """Importing graphiti_mode must not import graphiti_core (spec 13.3)."""
    code = (
        "import sys\n"
        "import omnistream.retrieval.graphiti_mode\n"
        "assert 'graphiti_core' not in sys.modules, 'graphiti_core imported eagerly'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_from_settings_missing_dependency_raises_import_error(monkeypatch, settings):
    import builtins

    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "graphiti_core":
            raise ImportError("absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(ImportError, match="optional graphiti-core"):
        GraphitiCoreSearcher.from_settings(settings)


@pytest.mark.asyncio
@pytest.mark.parametrize("echoes", [0, 1, 3, 4])
async def test_schema_echo_recovery_is_bounded(echoes):
    from tenacity import wait_none

    client = _llm_client([_echo_response()] * echoes + [json.dumps({"edges": []})])
    # Keep the production four-attempt policy, removing only test backoff.
    client._generate_response_with_retry = (
        client._generate_response_with_retry.retry_with(wait=wait_none()).__get__(
            client, type(client)
        )
    )
    messages = [
        Message(role="system", content="extract"),
        Message(role="user", content="source text"),
    ]
    if echoes == 4:
        with pytest.raises(EmptyResponseError):
            await client.generate_response(messages, response_model=Edges)
    else:
        assert await client.generate_response(messages, response_model=Edges) == {
            "edges": []
        }
    calls = client.client.calls
    assert len(calls) == min(echoes + 1, 4)
    first = calls[0]["messages"][-1]["content"]
    assert '"properties"' in first
    if echoes:
        corrected = calls[1]["messages"][-1]["content"]
        assert '"properties"' not in corrected
        assert '"edges": [{}]' in corrected
        assert "source text" in corrected
        assert corrected.count(client._CORRECTION) == 1
    else:
        assert client._CORRECTION not in messages[-1].content


def test_all_graphiti_prompt_model_examples_are_valid_and_have_no_real_indexes():
    import importlib
    import inspect
    import pkgutil

    from graphiti_core import prompts
    from graphiti_core.prompts.dedupe_edges import EdgeDuplicate
    from graphiti_core.prompts.dedupe_nodes import NodeResolutions
    from pydantic import BaseModel

    from omnistream.retrieval.graphiti_clients import GraphitiLLMClient

    models = set()
    for info in pkgutil.iter_modules(prompts.__path__):
        if info.name == "models":  # Message / PromptSpec transport metadata.
            continue
        module = importlib.import_module(f"{prompts.__name__}.{info.name}")
        models.update(
            model
            for _, model in inspect.getmembers(module, inspect.isclass)
            if issubclass(model, BaseModel)
            and model is not BaseModel
            and model.__module__ == module.__name__
        )
    assert len(models) == 22

    def check_indexes(value):
        if type(value) is int:
            assert value < 0
        elif isinstance(value, dict):
            for item in value.values():
                check_indexes(item)
        elif isinstance(value, list):
            for item in value:
                check_indexes(item)

    examples = {}
    for model in models:
        schema = model.model_json_schema()
        example = GraphitiLLMClient._instance_example(schema, schema)
        model.model_validate(example)
        check_indexes(example)
        examples[model] = example
    assert examples[EdgeDuplicate] == {"duplicate_facts": [], "contradicted_facts": []}
    assert examples[NodeResolutions]["entity_resolutions"][0]["id"] == -1
    assert (
        examples[NodeResolutions]["entity_resolutions"][0]["duplicate_candidate_id"]
        == -1
    )


@pytest.mark.parametrize(
    "schema, expected",
    [
        (
            {
                "allOf": [
                    {"type": "object", "properties": {"a": {"type": "integer"}}},
                    {"properties": {"b": {"type": "string"}}},
                ]
            },
            {"a": -1, "b": "<string>"},
        ),
        (
            {
                "allOf": [
                    {"$ref": "#/$defs/A"},
                    {"properties": {"b": {"const": False}}},
                ],
                "$defs": {
                    "A": {"type": "object", "properties": {"a": {"type": "integer"}}}
                },
            },
            {"a": -1, "b": False},
        ),
        ({"const": "fixed", "type": "string"}, "fixed"),
        (
            {"type": "array", "prefixItems": [{"type": "integer"}, {"const": "fixed"}]},
            [-1, "fixed"],
        ),
        ({"type": "array", "items": {"type": "string"}}, []),
        ({"unrecognized": True}, None),
        ({"type": "array", "items": False}, []),
    ],
)
def test_instance_example_schema_constructs(schema, expected):
    from omnistream.retrieval.graphiti_clients import GraphitiLLMClient

    assert GraphitiLLMClient._instance_example(schema, schema) == expected


@pytest.mark.parametrize(
    "schema, expected",
    [
        ({"type": ["integer", "null"]}, -1),
        ({"type": ["null", "string"]}, "<string>"),
        ({"type": ["null"]}, None),
        ({"type": {}}, None),
        ({"properties": []}, None),
        ({"$ref": 42}, None),
    ],
)
def test_instance_example_handles_nullable_types_and_malformed_shapes(schema, expected):
    assert GraphitiLLMClient._instance_example(schema, schema) == expected


@pytest.mark.asyncio
async def test_malformed_schema_echo_remains_retryable(monkeypatch):
    monkeypatch.setattr(
        Edges,
        "model_json_schema",
        classmethod(
            lambda cls: {"type": "object", "properties": {"edges": {"type": {}}}}
        ),
    )
    client = _llm_client([_echo_response()])
    messages = [Message(role="user", content="source text")]
    with pytest.raises(EmptyResponseError):
        await client._generate_response(messages, response_model=Edges)
    assert client._CORRECTION in messages[-1].content
    assert '"edges": null' in messages[-1].content


@pytest.mark.asyncio
async def test_example_builder_failure_uses_generic_echo_correction(monkeypatch):
    def fail(*args):
        raise TypeError("unexpected schema shape")

    monkeypatch.setattr(GraphitiLLMClient, "_instance_example", fail)
    client = _llm_client([_echo_response()])
    messages = [Message(role="user", content="source text")]
    with pytest.raises(EmptyResponseError):
        await client._generate_response(messages, response_model=Edges)
    assert messages[-1].content == "source text" + client._CORRECTION
