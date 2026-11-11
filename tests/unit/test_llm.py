import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

from omnistream.llm import LLMClient, LLMError, TokenBucket


class Out(BaseModel):
    x: int


def completion(content):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class StubOpenAI:
    """Mirrors AsyncOpenAI().chat.completions.create; each script entry is a
    content string or an exception to raise."""

    def __init__(self, script, delay=0.0):
        self.script = list(script)
        self.delay = delay
        self.calls = []
        self.active = 0
        self.peak = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return completion(item)


async def nosleep(_):
    return None


def status_error(code):
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    resp = httpx.Response(code, request=req)
    cls = openai.RateLimitError if code == 429 else openai.InternalServerError
    return cls("err", response=resp, body=None)


def make(script, **kw):
    stub = StubOpenAI(script, delay=kw.pop("delay", 0.0))
    return stub, LLMClient(stub, max_concurrency=kw.pop("c", 2), sleep=nosleep, **kw)


async def test_parse_valid_json_uses_json_mode():
    stub, client = make(['{"x": 1}'])
    assert await client.parse("m", "sys", "usr", Out) == Out(x=1)
    call = stub.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == "m"
    assert call["messages"][0]["role"] == "system"
    assert "sys" in call["messages"][0]["content"]
    assert '"x"' in call["messages"][0]["content"]  # schema in system prompt
    assert call["messages"][1] == {"role": "user", "content": "usr"}


async def test_reask_on_validation_failure_then_succeeds():
    stub, client = make(["not json", '{"x": "bad"}', '{"x": 3}'])
    assert await client.parse("m", "s", "u", Out) == Out(x=3)
    assert len(stub.calls) == 3


async def test_llm_error_after_two_reasks():
    stub, client = make(["nope"])
    with pytest.raises(LLMError):
        await client.parse("m", "s", "u", Out)
    assert len(stub.calls) == 3


async def test_retries_on_429_and_5xx():
    stub, client = make([status_error(429), status_error(503), '{"x": 2}'])
    assert await client.parse("m", "s", "u", Out) == Out(x=2)
    assert len(stub.calls) == 3


async def test_gives_up_after_max_retries():
    stub, client = make([status_error(429)], max_retries=2)
    with pytest.raises(LLMError):
        await client.parse("m", "s", "u", Out)
    assert len(stub.calls) == 3


async def test_concurrency_is_capped():
    stub, client = make(['{"x": 1}'], delay=0.05, c=3, tokens_per_minute=600)
    await asyncio.gather(*(client.parse("m", "s", "u", Out) for _ in range(10)))
    assert stub.peak == 3


async def test_token_bucket_waits_when_empty():
    now = [0.0]
    slept = []

    async def sleep(d):
        slept.append(d)
        now[0] += d

    b = TokenBucket(60, clock=lambda: now[0], sleep=sleep)
    for _ in range(60):
        await b.acquire()
    assert slept == []
    await b.acquire()
    assert slept and slept[0] == pytest.approx(1.0)


async def test_connection_test_reports_capabilities():
    stub = StubOpenAI(['{"ok": true}'])
    client = LLMClient(stub, 1, sleep=nosleep)
    assert await client.connection_test("m") == {
        "json_mode": True,
        "function_calling": False,
    }


def test_build_llm_client_needs_no_api_key(monkeypatch):
    from omnistream.config import Settings
    from omnistream.llm import build_llm_client

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    client = build_llm_client(Settings(llm_max_concurrency=2, llm_max_retries=7))
    assert isinstance(client, LLMClient)
    assert client._client.max_retries == 7
