"""Shared fixtures and constants for the whole test suite (C1-C5)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from openai import OpenAI
from pydantic import BaseModel

from omnistream.config import Settings, get_settings
from omnistream.embeddings import BGE_QUERY_INSTRUCTION, EmbeddingService

DIM = 384  # embedding dimension used by the C5 test fixtures
FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------
# C5 environment isolation (autouse): no test reads the developer's .env
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Make every non-live test independent of the developer's configuration.

    Strips settings variables (prefixed and unprefixed) from the process
    environment and stops ``Settings()`` / ``get_settings()`` from reading the
    project ``.env``. Live tests keep the real configuration.
    """
    get_settings.cache_clear()
    if request.node.get_closest_marker("live") is None:
        for name in Settings.model_fields:
            monkeypatch.delenv(name.upper(), raising=False)
            monkeypatch.delenv("OMNI_" + name.upper(), raising=False)
        monkeypatch.setitem(Settings.model_config, "env_file", None)
        monkeypatch.setattr("omnistream.llm._sleep", lambda seconds: None)
    yield
    get_settings.cache_clear()


class HashingEncoder:
    """Deterministic bag-of-words encoder: shared words -> higher cosine.

    Each new token gets the next free dimension, so there are no collisions
    for vocabularies under ``dim`` tokens.
    """

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []
        self.vocab: dict[str, int] = {}

    def encode(self, sentences: list[str], **kwargs: Any) -> np.ndarray:
        self.calls.append(list(sentences))
        out = np.zeros((len(sentences), self.dim), dtype=np.float32)
        for row, text in enumerate(sentences):
            text = text.removeprefix(BGE_QUERY_INSTRUCTION)
            for tok in re.findall(r"[a-z0-9]+", text.lower()):
                idx = self.vocab.setdefault(tok, len(self.vocab) % self.dim)
                out[row, idx] += 1.0
        return out


@pytest.fixture
def settings() -> Settings:
    """Settings isolated from the developer's real .env and environment."""
    return Settings(
        _env_file=None,
        llm_base_url="https://openrouter.ai/api/v1",
        llm_api_key="test-key",
        llm_model="deepseek/deepseek-chat",
        judge_model="deepseek/deepseek-chat",
    )


@pytest.fixture
def encoder() -> HashingEncoder:
    return HashingEncoder()


@pytest.fixture
def embedder(settings: Settings, encoder: HashingEncoder) -> EmbeddingService:
    return EmbeddingService(settings, encoder=encoder)


class RecordingTransport:
    """httpx transport that answers chat completions with canned content."""

    def __init__(self, responder: Callable[[dict], httpx.Response | str]) -> None:
        self.responder = responder
        self.requests: list[httpx.Request] = []

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self.responder(json.loads(request.content))
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(
            200,
            json=chat_completion(result, model=json.loads(request.content)["model"]),
        )


def chat_completion(content: str | None, model: str = "deepseek/deepseek-chat") -> dict:
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def load_llm_fixture(name: str) -> dict:
    return json.loads((FIXTURES / "llm" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def mock_openai() -> Callable[..., tuple[OpenAI, RecordingTransport]]:
    def factory(
        responder: Callable[[dict], httpx.Response | str], **headers: str
    ) -> tuple[OpenAI, RecordingTransport]:
        transport = RecordingTransport(responder)
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
            max_retries=0,
            default_headers=headers or None,
            http_client=httpx.Client(transport=httpx.MockTransport(transport)),
        )
        return client, transport

    return factory


# --------------------------------------------------------------------------
# C1-C4 fixtures
# --------------------------------------------------------------------------
def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else list(v)


class FakeEmbedder:
    """Deterministic embedder. Table lookup is casefolded; unknown text gets a
    unit vector seeded from sha256(text). All vectors are L2-normalized."""

    def __init__(self, table: dict[str, list[float]] | None = None, dim: int = 8):
        self.dim = dim
        self.table = {k.casefold(): _unit(v) for k, v in (table or {}).items()}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        key = text.casefold()
        if key in self.table:
            return list(self.table[key])
        seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
        rng = random.Random(seed)
        return _unit([rng.gauss(0, 1) for _ in range(self.dim)])


class FakeLLM:
    """Stands in for LLMClient. responses maps schema type -> BaseModel instance
    or callable(user) -> BaseModel (which may raise, e.g. LLMError)."""

    def __init__(
        self,
        responses: dict[type, Callable[[str], BaseModel] | BaseModel],
        delay: float = 0.0,
    ):
        self.responses = responses
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def parse(self, model, system, user, schema, max_tokens=4096):
        self.calls.append((model, user))
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        resp = self.responses[schema]
        if isinstance(resp, BaseModel):
            return resp
        return resp(user)


class FakeLifecycleOps:
    """GraphOps stand-in for bubble counts/delete."""

    def __init__(self):
        self.counts = {"episodes": 2, "entities": 3, "facts": 4}
        self.deleted: list[str] = []

    async def group_counts(self, group_id):
        return dict(self.counts)

    async def delete_group(self, group_id):
        self.deleted.append(group_id)


class FakeChunks:
    def __init__(self):
        self.n = 5
        self.dropped: list[str] = []

    async def count(self, bubble_id):
        return self.n

    async def drop(self, bubble_id):
        self.dropped.append(bubble_id)
