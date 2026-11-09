import asyncio
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from omnistream.config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The model refused, ran out of tokens, or returned no parsable output."""


class LLMClient:
    """Structured-output Claude calls behind a concurrency cap.

    Retry/backoff on 429/5xx is the SDK's job (max_retries on the client).
    """

    def __init__(self, client: anthropic.AsyncAnthropic, max_concurrency: int) -> None:
        self._client = client
        self._sem = asyncio.Semaphore(max_concurrency)

    async def parse(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
    ) -> T:
        async with self._sem:
            response = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        if response.stop_reason in {"refusal", "max_tokens"}:
            raise LLMError(f"model stopped with {response.stop_reason}")
        if response.parsed_output is None:
            raise LLMError("model returned no parsable output")
        return response.parsed_output


def build_llm_client(settings: Settings) -> LLMClient:
    # The SDK reads ANTHROPIC_API_KEY lazily at request time, not here.
    client = anthropic.AsyncAnthropic(max_retries=settings.llm_max_retries)
    return LLMClient(client, max_concurrency=settings.llm_max_concurrency)
