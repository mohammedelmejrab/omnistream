import asyncio
import json
import time
from typing import TypeVar

import openai
from pydantic import BaseModel, ValidationError

from omnistream.config import Settings

T = TypeVar("T", bound=BaseModel)

MAX_REASKS = 2


class LLMError(Exception):
    """The model returned no usable output after retries."""


class TokenBucket:
    """Refills continuously at `per_minute` tokens/min; capacity = per_minute."""

    def __init__(self, per_minute: int, clock=time.monotonic, sleep=asyncio.sleep):
        self._rate = per_minute / 60.0
        self._capacity = float(per_minute)
        self._tokens = float(per_minute)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._last) * self._rate
                )
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self._rate)


class LLMClient:
    """Structured output over any OpenAI-compatible endpoint: JSON mode plus
    Pydantic validation, re-ask on invalid output, token-bucket rate limit and
    backoff on 429/5xx (on top of the SDK's own max_retries)."""

    def __init__(
        self,
        client: openai.AsyncOpenAI,
        max_concurrency: int,
        tokens_per_minute: int = 60,
        max_retries: int = 5,
        sleep=asyncio.sleep,
    ) -> None:
        self._client = client
        self._sem = asyncio.Semaphore(max_concurrency)
        self._bucket = TokenBucket(tokens_per_minute, sleep=sleep)
        self._max_retries = max_retries
        self._sleep = sleep

    async def _complete(self, model: str, messages: list[dict], max_tokens: int) -> str:
        attempt = 0
        while True:
            await self._bucket.acquire()
            try:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except (openai.RateLimitError, openai.APIConnectionError) as e:
                err: Exception = e
            except openai.APIStatusError as e:
                if e.status_code < 500:
                    raise LLMError(f"LLM request failed: {e}") from e
                err = e
            else:
                if not resp.choices:
                    raise LLMError("model returned no choices")
                return resp.choices[0].message.content or ""
            attempt += 1
            if attempt > self._max_retries:
                raise LLMError(f"LLM request failed after retries: {err}") from err
            await self._sleep(min(2.0**attempt, 60.0))

    async def parse(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
    ) -> T:
        full_system = (
            f"{system}\n\nRespond with a single JSON object matching this JSON "
            f"schema:\n{json.dumps(schema.model_json_schema())}"
        )
        messages: list[dict] = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ]
        last_error = ""
        async with self._sem:
            for _ in range(MAX_REASKS + 1):
                content = await self._complete(model, messages, max_tokens)
                try:
                    return schema.model_validate_json(content)
                except ValidationError as e:
                    last_error = str(e)
                    messages = messages[:2] + [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": "Your reply was invalid: "
                            f"{last_error}\nReturn corrected JSON only.",
                        },
                    ]
        raise LLMError(f"invalid output after {MAX_REASKS} re-asks: {last_error}")

    async def connection_test(self, model: str) -> dict[str, bool]:
        json_mode = False
        function_calling = False
        try:
            r = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": 'Reply with {"ok": true} as JSON.'}
                ],
                max_tokens=32,
                response_format={"type": "json_object"},
            )
            json.loads(r.choices[0].message.content or "")
            json_mode = True
        except (openai.OpenAIError, ValueError):
            json_mode = False
        try:
            r = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Call the ping tool."}],
                max_tokens=64,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "ping",
                            "description": "Ping",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                tool_choice="required",
            )
            function_calling = bool(r.choices[0].message.tool_calls)
        except openai.OpenAIError:
            function_calling = False
        return {"json_mode": json_mode, "function_calling": function_calling}


def build_llm_client(settings: Settings) -> LLMClient:
    client = openai.AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "missing",
        max_retries=settings.llm_max_retries,
    )
    return LLMClient(
        client,
        max_concurrency=settings.llm_max_concurrency,
        tokens_per_minute=settings.llm_tokens_per_minute,
        max_retries=settings.llm_max_retries,
    )
