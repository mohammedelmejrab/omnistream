import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from omnistream.llm import LLMClient, LLMError


class Out(BaseModel):
    x: int


class StubAnthropic:
    """Mirrors AsyncAnthropic().messages.parse: kwargs in, object with
    stop_reason and parsed_output out."""

    def __init__(self, stop_reason="end_turn", parsed=None, delay=0.0):
        self.stop_reason = stop_reason
        self.parsed = parsed
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.kwargs = None
        self.messages = SimpleNamespace(parse=self._parse)

    async def _parse(self, **kwargs):
        self.kwargs = kwargs
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=self.parsed)


async def test_parse_returns_parsed_output():
    stub = StubAnthropic(parsed=Out(x=1))
    client = LLMClient(stub, max_concurrency=2)
    assert await client.parse("m", "sys", "usr", Out) == Out(x=1)
    assert stub.kwargs == {
        "model": "m",
        "max_tokens": 4096,
        "system": "sys",
        "messages": [{"role": "user", "content": "usr"}],
        "output_format": Out,
    }


async def test_refusal_raises_llm_error():
    client = LLMClient(StubAnthropic(stop_reason="refusal", parsed=Out(x=1)), 2)
    with pytest.raises(LLMError):
        await client.parse("m", "s", "u", Out)


async def test_max_tokens_raises_llm_error():
    client = LLMClient(StubAnthropic(stop_reason="max_tokens", parsed=Out(x=1)), 2)
    with pytest.raises(LLMError):
        await client.parse("m", "s", "u", Out)


async def test_missing_parsed_output_raises_llm_error():
    client = LLMClient(StubAnthropic(parsed=None), 2)
    with pytest.raises(LLMError):
        await client.parse("m", "s", "u", Out)


async def test_concurrency_is_capped():
    stub = StubAnthropic(parsed=Out(x=1), delay=0.05)
    client = LLMClient(stub, max_concurrency=3)
    await asyncio.gather(*(client.parse("m", "s", "u", Out) for _ in range(10)))
    assert stub.peak == 3


def test_build_llm_client_needs_no_api_key(monkeypatch):
    from omnistream.config import Settings
    from omnistream.llm import build_llm_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = build_llm_client(Settings(llm_max_concurrency=2, llm_max_retries=7))
    assert isinstance(client, LLMClient)
    assert client._client.max_retries == 7
