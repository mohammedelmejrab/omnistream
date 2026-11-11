import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from omnistream.config import Settings
from omnistream.llm import AsyncLLMClient, LLMError
from tests.conftest import chat_completion


@pytest.mark.parametrize(
    "field,value", [("subagent_max_tool_calls", 0), ("subagent_timeout_seconds", 0)]
)
def test_subagent_settings(field, value):
    s = Settings(_env_file=None)
    assert s.subagent_max_tool_calls == 6
    assert s.subagent_timeout_seconds == 60.0
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    "arguments,error", [("{broken", True), ("[]", True), ('{"query":"q"}', False)]
)
async def test_tool_response(settings, arguments, error):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        payload = chat_completion(None)
        payload["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "t",
                "type": "function",
                "function": {"name": "search", "arguments": arguments},
            }
        ]
        return httpx.Response(200, json=payload)

    async with AsyncOpenAI(
        api_key="test",
        base_url="https://test.invalid",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        turn = await AsyncLLMClient(settings, client=client).chat_with_tools(
            [{"role": "user", "content": "q"}],
            [{"type": "function"}],
            model="override",
            temperature=0.3,
            max_tokens=7,
        )
    assert turn.content is None
    assert bool(turn.tool_calls[0].arguments_error) is error
    assert turn.raw_message["tool_calls"][0]["id"] == "t"
    assert requests[0]["model"] == "override"
    assert requests[0]["temperature"] == 0.3
    assert requests[0]["max_tokens"] == 7


async def test_async_empty_retry(settings, monkeypatch):
    sleeps = []

    async def sleep(value):
        sleeps.append(value)

    monkeypatch.setattr("omnistream.llm._async_sleep", sleep)
    empty = chat_completion(None)
    empty["choices"] = []
    replies = iter([empty, chat_completion(None), chat_completion("done")])

    def respond(request):
        assert "tool_choice" not in json.loads(request.content)
        return httpx.Response(200, json=next(replies))

    async with AsyncOpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        assert (
            await AsyncLLMClient(settings, client=client).chat_with_tools([], [])
        ).content == "done"
    assert sleeps == [0.5, 1.0]


async def test_async_empty_exhaustion(settings):
    settings.llm_max_retries = 0
    async with AsyncOpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=chat_completion(None))
            )
        ),
    ) as client:
        with pytest.raises(LLMError, match="empty message after 1"):
            await AsyncLLMClient(settings, client=client).chat_with_tools([], [])


def test_async_credentials_and_headers(settings):
    settings.llm_app_url = "https://example.test"
    client = AsyncLLMClient(settings).client
    assert client.api_key == "test-key"
    assert client.max_retries == settings.llm_max_retries
    assert client.timeout == settings.llm_timeout_seconds
    assert client.default_headers["HTTP-Referer"] == settings.llm_app_url
    assert client.default_headers["X-Title"] == settings.llm_app_title
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        _ = AsyncLLMClient(Settings(_env_file=None)).client


async def test_forced_final_request_retains_tools_and_history(settings):
    from omnistream.agents import Subagent
    from tests.unit.test_agent_tools import Items, Retriever

    settings.subagent_max_tool_calls = 1
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            payload = chat_completion(None)
            payload["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": "t",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"query":"q"}'},
                }
            ]
        else:
            payload = chat_completion("Final evidence")
        return httpx.Response(200, json=payload)

    async with AsyncOpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        result = await Subagent(
            bubble="news",
            mode="classic",
            llm=AsyncLLMClient(settings, client=client),
            retriever=Retriever(),
            graph_store=None,
            item_store=Items(),
            settings=settings,
        ).run("q")
    assert result.stopped_reason == "tool_limit"
    assert requests[1]["tools"] == requests[0]["tools"]
    assert requests[1]["tool_choice"] == "none"
    assert any(
        m["role"] == "tool" and m["tool_call_id"] == "t"
        for m in requests[1]["messages"]
    )
    assert any(m.get("tool_calls") for m in requests[1]["messages"])


async def test_tool_choice_requires_tools(settings):
    with pytest.raises(ValueError, match="requires tool"):
        await AsyncLLMClient(settings).chat_with_tools([], [], tool_choice="none")
