"""Provider policy verified on serialized SDK requests, including Graphiti."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from omnistream.config import Settings
from omnistream.llm import (
    AsyncLLMClient,
    LLMClient,
    build_llm_client,
    judge_client,
    reasoning_kwargs,
)


class Result(BaseModel):
    ok: bool


@pytest.mark.parametrize(
    "host,policy,expected",
    [
        ("https://openrouter.ai/api/v1", "auto", True),
        ("https://openrouter.ai.evil.test/v1", "auto", False),
        ("https://api.deepseek.com/v1", "auto", False),
        ("https://api.deepseek.com/v1", "always", True),
        ("https://openrouter.ai/api/v1", "never", False),
    ],
)
@pytest.mark.parametrize("level", ["off", "low", "medium", "high", "provider_default"])
def test_policy(host, policy, expected, level):
    settings = Settings(
        _env_file=None,
        llm_base_url=host,
        llm_send_reasoning_param=policy,
        llm_reasoning=level,
    )
    result = reasoning_kwargs(settings)
    if expected and level != "provider_default":
        assert result == {
            "extra_body": {
                "reasoning": {"enabled": False} if level == "off" else {"effort": level}
            }
        }
    else:
        assert result == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,policy,level,send",
    [
        ("https://openrouter.ai/api/v1", "auto", "off", True),
        ("https://generic.test/v1", "auto", "off", False),
        ("https://generic.test/v1", "always", "off", True),
        ("https://openrouter.ai/api/v1", "never", "off", False),
        ("https://openrouter.ai/api/v1", "auto", "provider_default", False),
    ],
)
async def test_all_transports(settings, monkeypatch, endpoint, policy, level, send):
    settings.llm_base_url = endpoint
    settings.llm_send_reasoning_param = policy
    settings.llm_reasoning = level
    settings.judge_reasoning = level
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.prompts.models import Message

    from omnistream.eval import external
    from omnistream.eval.judge import Judge
    from omnistream.retrieval.graphiti_clients import GraphitiLLMClient

    bodies = []
    finishes = []

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finishes.pop(0) if finishes else "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"ok":true,"score":2,"rationale":"ok","supported":true}',
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    transport = httpx.MockTransport(respond)
    sync = OpenAI(
        api_key="test",
        base_url=settings.llm_base_url,
        http_client=httpx.Client(transport=transport),
    )
    async_ = AsyncOpenAI(
        api_key="test",
        base_url=settings.llm_base_url,
        http_client=httpx.AsyncClient(transport=transport),
    )
    monkeypatch.setattr("omnistream.llm.OpenAI", lambda **kwargs: sync)
    monkeypatch.setattr("omnistream.llm._build_async_openai", lambda settings: async_)
    monkeypatch.setattr("omnistream.llm._async_sleep", _no_sleep)
    structured = build_llm_client(settings)
    assert (await structured.parse("test", "JSON", "ok", Result)).ok
    chat = LLMClient(settings)
    chat.chat([{"role": "user", "content": "ok"}])
    chat.chat_json([{"role": "user", "content": "JSON"}])
    chat.answer("ok", ["ok"])
    await AsyncLLMClient(settings).chat_with_tools(
        [{"role": "user", "content": "ok"}], []
    )
    judge_client(settings).chat_json([{"role": "user", "content": "JSON"}])
    judge = Judge(settings)
    await judge.correctness({"question": "ok", "reference_answer": "ok"}, "ok")
    await judge._json([{"role": "user", "content": "entailment JSON"}], "supported")
    graph = GraphitiLLMClient(
        config=LLMConfig(model="test", api_key="test"),
        client=async_,
        settings=settings,
        structured_output_mode="json_object",
    )
    await graph.generate_response([Message(role="user", content="JSON")], Result)
    # Exercise the real LlamaIndex LLM created by the external builder.
    captured = {}
    index = Mock()

    def engine(**kwargs):
        captured.update(kwargs)
        return Mock()

    index.as_query_engine.side_effect = engine
    monkeypatch.setattr(
        external.VectorStoreIndex, "from_documents", lambda *a, **kw: index
    )
    external.ExternalBaseline(settings, [], SimpleNamespace(model_name="test"))
    llm = captured["llm"]
    llm._client = sync
    from llama_index.core.llms import ChatMessage

    llm.chat([ChatMessage(role="user", content="ok")])
    from datetime import UTC, datetime

    import numpy as np

    from omnistream.retrieval.citations import _entailed_span
    from omnistream.retrieval.models import Entity, Fact
    from omnistream.retrieval.router import BubbleInfo, QueryRouter

    embedder = SimpleNamespace(embed_query=lambda q: np.array([1.0]))
    QueryRouter(
        chat,
        embedder,
        [BubbleInfo("b", "b", "b", description_embedding=np.array([1.0]))],
    ).route("ok")
    fact = Fact(
        "f",
        "a",
        "b",
        "leads",
        "Alice leads Acme.",
        "news",
        "i",
        None,
        datetime.now(UTC),
    )
    _entailed_span(
        "Alice leads Acme.",
        fact,
        {
            "a": Entity("a", "Alice", "person", "news"),
            "b": Entity("b", "Acme", "organization", "news"),
        },
        chat,
    )
    assert len(bodies) == 12
    assert all(
        b.get("reasoning") == ({"enabled": False} if send else None) for b in bodies
    )
    # Reject even valid-looking JSON when the provider reports truncation.
    finishes.extend(["length", "stop"])
    assert (await structured.parse("test", "JSON", "ok", Result)).ok
    finishes.extend(["length", "stop"])
    assert chat.chat_json([{"role": "user", "content": "JSON"}])["ok"]
    finishes.extend(["length", "stop"])
    await graph.generate_response([Message(role="user", content="JSON")], Result)
    finishes.extend(["length", "stop"])
    await AsyncLLMClient(settings).chat_with_tools(
        [{"role": "user", "content": "ok"}], []
    )
    assert not finishes
    await async_.close()
    sync.close()


async def _no_sleep(seconds):
    pass


def test_reasoning_meter():
    from openai.types.chat import ChatCompletion

    from omnistream.eval.resources import UsageMeter

    response = ChatCompletion(
        id="x",
        created=0,
        model="x",
        object="chat.completion",
        choices=[],
        usage={
            "total_tokens": 9,
            "prompt_tokens": 2,
            "completion_tokens": 7,
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    )
    meter = UsageMeter()
    meter.record(response)
    assert meter.summary()["setup"]["reasoning_tokens"] == 5


def test_env_and_judge(monkeypatch, settings):
    monkeypatch.setenv("OMNI_LLM_REASONING", "high")
    assert Settings(_env_file=None).llm_reasoning == "high"
    settings.llm_reasoning = "high"
    assert judge_client(settings).settings.llm_reasoning == "off"


@pytest.mark.asyncio
async def test_truncation_exhaustion(settings, caplog):
    from unittest.mock import AsyncMock

    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.errors import EmptyResponseError
    from graphiti_core.prompts.models import Message

    from omnistream.llm import LLMError
    from omnistream.retrieval.graphiti_clients import GraphitiLLMClient

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length", message=SimpleNamespace(content='{"ok":true}')
            )
        ]
    )
    completions = SimpleNamespace(create=AsyncMock(return_value=response))
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    settings.llm_max_retries = 0
    structured = LLMClient(sdk, max_retries=0, settings=settings)
    with pytest.raises(LLMError, match="finish_reason=length"):
        await structured.parse("test", "JSON", "ok", Result)
    with pytest.raises(LLMError, match="finish_reason=length"):
        await AsyncLLMClient(settings, client=sdk).chat_with_tools([], [])
    graph = GraphitiLLMClient(
        config=LLMConfig(api_key="test", model="test"), client=sdk, settings=settings
    )
    with pytest.raises(EmptyResponseError, match="finish_reason=length"):
        await graph._generate_response([Message(role="user", content="JSON")], Result)
    assert completions.create.await_count == 3
    assert "re-sample required" in caplog.text


def test_missing_reasoning_details():
    from omnistream.eval.resources import UsageMeter

    meter = UsageMeter()
    meter.record(SimpleNamespace(usage=SimpleNamespace(total_tokens=2)))
    assert meter.summary()["setup"]["reasoning_tokens"] == 0
