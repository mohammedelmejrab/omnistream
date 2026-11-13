"""LLM clients for any OpenAI-compatible endpoint, shared by C3-C5.

Two call styles live on one ``LLMClient`` class so the router/writer path and
the C5 query path stay on a single client construction from ``Settings``:

* **structured (C4)** - ``LLMClient(async_client, max_concurrency, ...)`` with
  ``await parse(model, system, user, schema)``: JSON mode plus Pydantic
  validation, re-asks on invalid output, a token-bucket rate limit and backoff
  on HTTP 429/5xx. Used by the ingestion router and graph writer.
* **chat (C5)** - ``LLMClient(settings, *, client=..., model=...)`` with
  ``chat``/``chat_json``/``answer``: synchronous completions with empty-200
  response retry and OpenRouter attribution headers. Used by query routing,
  merge-and-answer and auto-summaries.

``AsyncLLMClient`` adds the C5 function-calling loop (``chat_with_tools``) used
by multi-hop subagents. All clients share the same ``Settings``-driven
``AsyncOpenAI`` construction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from urllib.parse import urlparse

import openai
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, ValidationError

from omnistream.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)

MAX_REASKS = 2

ANSWER_SYSTEM_PROMPT = (
    "You answer questions using only the numbered context passages provided. "
    "Cite passages inline as [n]. If the context does not contain the answer, say so."
)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

# Backoff for empty 200 responses (HTTP 429/5xx are retried by the SDK itself).
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 8.0
_sleep = time.sleep  # module-level so tests can replace it
_async_sleep = asyncio.sleep  # module-level so tests can replace it


class LLMError(RuntimeError):
    """Raised when the provider returns an unusable response."""


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


logger = logging.getLogger(__name__)


def reasoning_kwargs(settings: Settings) -> dict[str, Any]:
    """Provider-safe OpenAI request kwargs; never send extensions implicitly."""
    policy = settings.llm_send_reasoning_param
    if policy == "never" or (
        policy == "auto" and urlparse(settings.llm_base_url).hostname != "openrouter.ai"
    ):
        return {}
    value = settings.llm_reasoning
    if value == "provider_default":
        return {}
    reasoning = {"enabled": False} if value == "off" else {"effort": value}
    return {"extra_body": {"reasoning": reasoning}}


def completion_truncated(response: Any) -> bool:
    truncated = (
        bool(response.choices)
        and getattr(response.choices[0], "finish_reason", None) == "length"
    )
    if truncated:
        logger.warning(
            "LLM completion truncated (finish_reason=length); re-sample required"
        )
    return truncated


def _build_async_openai(settings: Settings) -> AsyncOpenAI:
    """AsyncOpenAI construction shared by every client style."""
    headers: dict[str, str] = {}
    if settings.llm_app_url:
        headers["HTTP-Referer"] = settings.llm_app_url
    if settings.llm_app_title:
        headers["X-Title"] = settings.llm_app_title
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value() or "missing",
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        default_headers=headers or None,
    )


def _provider_error(response: Any) -> str:
    """OpenRouter puts upstream failures in an ``error`` field of a 200 body."""
    extra = getattr(response, "model_extra", None) or {}
    error = extra.get("error")
    if isinstance(error, dict):
        return f": {error.get('code', '')} {error.get('message', '')}".rstrip()
    return f": {error}" if error else ""


class LLMClient:
    """One client class with two construction styles (see module docstring)."""

    def __init__(
        self,
        client_or_settings: AsyncOpenAI | Settings | None = None,
        max_concurrency: int = 2,
        tokens_per_minute: int = 60,
        max_retries: int = 5,
        sleep=asyncio.sleep,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._request_settings = settings
        if isinstance(client_or_settings, Settings):
            self._init_chat(client_or_settings, client=client, model=model)
        else:
            self._init_structured(
                client_or_settings,
                max_concurrency,
                tokens_per_minute,
                max_retries,
                sleep,
            )

    # ------------------------------------------------------------- C4 style
    def _init_structured(
        self,
        client,
        max_concurrency: int,
        tokens_per_minute: int,
        max_retries: int,
        sleep,
    ) -> None:
        self._style = "structured"
        self._client = client
        if self._request_settings is None:
            self._request_settings = Settings(
                _env_file=None, llm_base_url=str(getattr(client, "base_url", ""))
            )
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
                    **(
                        reasoning_kwargs(self._request_settings)
                        if self._request_settings
                        else {}
                    ),
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
                if not completion_truncated(resp):
                    return resp.choices[0].message.content or ""
                err = LLMError("completion truncated (finish_reason=length)")
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
                **(
                    reasoning_kwargs(self._request_settings)
                    if self._request_settings
                    else {}
                ),
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
                **(
                    reasoning_kwargs(self._request_settings)
                    if self._request_settings
                    else {}
                ),
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

    # ------------------------------------------------------------- C5 style
    def _init_chat(
        self, settings: Settings, *, client: OpenAI | None, model: str | None
    ) -> None:
        self._style = "chat"
        self.settings = settings
        self.model = model or self.settings.llm_model
        self._client = client

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self.settings.has_llm_credentials:
                raise LLMError("LLM_API_KEY is not set")
            headers = {}
            if self.settings.llm_app_url:
                headers["HTTP-Referer"] = self.settings.llm_app_url
            if self.settings.llm_app_title:
                headers["X-Title"] = self.settings.llm_app_title
            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key.get_secret_value(),
                timeout=self.settings.llm_timeout_seconds,
                max_retries=self.settings.llm_max_retries,
                default_headers=headers or None,
            )
        return self._client

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Return the assistant message text.

        HTTP 429/5xx and connection errors are retried by the OpenAI SDK with
        exponential backoff (``llm_max_retries``). OpenRouter can also answer
        HTTP 200 with no choices (an upstream error in the body); those are
        retried here with the same budget, then raised as ``LLMError``.
        """
        params: dict[str, Any] = {
            **reasoning_kwargs(self.settings),
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
            **kwargs,
        }
        cap = getattr(
            self.settings,
            "llm_max_output_tokens",
            int(os.environ.get("OMNI_LLM_MAX_OUTPUT_TOKENS", "4096")),
        )
        params["max_tokens"] = min(max_tokens or cap, cap)
        attempts = 1 + max(0, self.settings.llm_max_retries)
        for attempt in range(attempts):
            response = self.client.chat.completions.create(**params)
            truncated = completion_truncated(response)
            if (
                not truncated
                and response.choices
                and response.choices[0].message.content is not None
            ):
                return response.choices[0].message.content
            problem = (
                "truncated completion (finish_reason=length)"
                if truncated
                else ("no choices" if not response.choices else "an empty message")
            )
            detail = _provider_error(response)
            if attempt + 1 < attempts:
                _sleep(min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * 2**attempt))
        raise LLMError(
            f"provider returned {problem} after {attempts} attempt(s){detail}"
        )

    def chat_json(self, messages: Sequence[dict[str, str]], **kwargs: Any) -> Any:
        """Chat and parse the reply as JSON (tolerates a ```json fence)."""
        text = self.chat(messages, **kwargs).strip()
        fenced = _JSON_FENCE.match(text)
        if fenced:
            text = fenced.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"response is not valid JSON: {text[:200]!r}") from exc

    def answer(self, question: str, passages: Sequence[str], **kwargs: Any) -> str:
        """Generate a cited answer grounded in retrieved passages."""
        context = (
            "\n\n".join(f"[{i}] {p}" for i, p in enumerate(passages, start=1))
            or "(no context)"
        )
        return self.chat(
            [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
            **kwargs,
        )


def build_llm_client(settings: Settings) -> LLMClient:
    """Structured-style client for the C3/C4 pipeline (no API key required)."""
    return LLMClient(
        _build_async_openai(settings),
        max_concurrency=settings.llm_max_concurrency,
        tokens_per_minute=settings.llm_tokens_per_minute,
        max_retries=settings.llm_max_retries,
        settings=settings,
    )


def judge_client(settings: Settings | None = None, **kwargs: Any) -> LLMClient:
    settings = settings or get_settings()
    settings = settings.model_copy(update={"llm_reasoning": settings.judge_reasoning})
    return LLMClient(settings, model=settings.judge_model, **kwargs)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict
    arguments_error: str | None = None


@dataclass(frozen=True)
class AssistantTurn:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    raw_message: dict


class AsyncLLMClient:
    """Async function-calling client with the synchronous client's policy."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.llm_model
        self._client = client

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self.settings.has_llm_credentials:
                raise LLMError("LLM_API_KEY is not set")
            self._client = _build_async_openai(self.settings)
        return self._client

    async def chat_with_tools(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tool_choice: Literal["auto", "none", "required"] | None = None,
    ) -> AssistantTurn:
        params: dict[str, Any] = {
            **reasoning_kwargs(self.settings),
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if tools:
            params["tools"] = list(tools)
        elif tool_choice is not None:
            raise ValueError("tool_choice requires tool definitions")
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        cap = getattr(
            self.settings,
            "llm_max_output_tokens",
            int(os.environ.get("OMNI_LLM_MAX_OUTPUT_TOKENS", "4096")),
        )
        params["max_tokens"] = min(max_tokens or cap, cap)
        attempts = 1 + max(0, self.settings.llm_max_retries)
        for attempt in range(attempts):
            response = await self.client.chat.completions.create(**params)
            truncated = completion_truncated(response)
            if not truncated and response.choices:
                message = response.choices[0].message
                if message.content is not None or message.tool_calls:
                    calls = []
                    for call in message.tool_calls or ():
                        error = None
                        try:
                            arguments = json.loads(call.function.arguments)
                            if not isinstance(arguments, dict):
                                raise ValueError("arguments must be a JSON object")  # noqa: TRY004
                        except (ValueError, TypeError) as exc:
                            arguments, error = {}, str(exc)
                        calls.append(
                            ToolCall(call.id, call.function.name, arguments, error)
                        )
                    return AssistantTurn(
                        message.content,
                        tuple(calls),
                        message.model_dump(exclude_none=True),
                    )
            problem = (
                "truncated completion (finish_reason=length)"
                if truncated
                else ("no choices" if not response.choices else "an empty message")
            )
            detail = _provider_error(response)
            if attempt + 1 < attempts:
                await _async_sleep(
                    min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * 2**attempt)
                )
        raise LLMError(
            f"provider returned {problem} after {attempts} attempt(s){detail}"
        )
