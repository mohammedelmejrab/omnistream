"""Graphiti-core client adapters wired to OmniStream's local stack (spec 5, C4/C5).

Graphiti defaults its LLM, embedder and cross-encoder to OpenAI clients. This
project instead uses the configured OpenAI-compatible LLM endpoint (OpenRouter)
and the always-local ``EmbeddingService`` (spec 5: "Embeddings are always
local"). These adapters let ``GraphitiCoreSearcher.from_settings`` inject the
correct clients without pulling in any extra embedding or reranking models.

This module imports ``graphiti_core`` at module level on purpose: it is only
imported lazily from ``graphiti_mode.from_settings``, so the rest of the
package stays importable without the optional dependency.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

import numpy as np
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, ModelSize
from graphiti_core.llm_client.errors import EmptyResponseError
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message
from pydantic import BaseModel, ValidationError

from omnistream.embeddings import EmbeddingService
from omnistream.llm import completion_truncated, reasoning_kwargs


class _PolicyCompletions:
    """Keep Graphiti's upstream request generation and retry loop intact."""

    def __init__(self, completions, settings):
        self._completions = completions
        self._settings = settings

    async def create(self, **kwargs):
        policy = reasoning_kwargs(self._settings)
        if policy:
            kwargs["extra_body"] = {
                **kwargs.get("extra_body", {}),
                **policy["extra_body"],
            }
        response = await self._completions.create(**kwargs)
        if completion_truncated(response):
            raise EmptyResponseError(
                "Graphiti completion truncated (finish_reason=length); re-sample required"
            )
        return response


class _PolicyClient:
    def __init__(self, client, settings):
        from types import SimpleNamespace

        self._client = client
        self.chat = SimpleNamespace(
            completions=_PolicyCompletions(client.chat.completions, settings)
        )

    def __getattr__(self, name):
        return getattr(self._client, name)


class GraphitiLLMClient(OpenAIGenericClient):
    """``OpenAIGenericClient`` guarded against the JSON-schema echo failure.

    In ``json_object`` mode (the mode for providers without native schema
    enforcement, e.g. DeepSeek) graphiti appends the response schema to the
    prompt. Some models occasionally answer by echoing that schema back
    instead of filling it: a valid-JSON response that fails graphiti's
    response-model parsing downstream. This subclass detects the echo and
    raises ``EmptyResponseError``, which the base client's tenacity wrapper
    treats as transient (four total attempts). After an echo, replace the
    injected raw schema with a small instance example and a correction.
    Non-echo calls retain the original prompt and temperature; no extra
    transport attempts or shared configuration mutations are introduced.
    """

    def __init__(self, *args, settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        # No mutation of the injected SDK client; other users retain their policy.
        if settings is None:
            from omnistream.config import Settings

            settings = Settings(
                _env_file=None, llm_base_url=str(getattr(self.client, "base_url", ""))
            )
        self.client = _PolicyClient(self.client, settings)

    _SCHEMA_ECHO_KEYS = frozenset({"$defs", "properties", "items"})
    _CORRECTION = (
        "\n\nImportant: your response must be ONLY the JSON object containing the extracted "
        "data. Never repeat, echo or describe the schema definition itself."
    )

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        parsed = await super()._generate_response(
            messages, response_model, max_tokens, model_size, model=model
        )
        if response_model is not None and not self._is_schema_echo(
            parsed, response_model
        ):
            try:
                response_model.model_validate(parsed)
            except ValidationError as exc:
                raise EmptyResponseError(
                    "LLM returned an invalid extraction instance; re-sample required"
                ) from exc
        if self._is_schema_echo(parsed, response_model):
            if self._CORRECTION not in messages[-1].content:
                content = messages[-1].content
                if response_model is not None:
                    try:
                        schema = response_model.model_json_schema()
                        # Replace only the generic client's injected schema. Preserve
                        # the extraction prompt and field descriptions elsewhere.
                        injected = (
                            "\n\nRespond with a JSON object in the following format:\n\n"
                            + json.dumps(schema)
                        )
                        example = json.dumps(self._instance_example(schema, schema))
                    except Exception:  # noqa: BLE001, S110 - echo guard must never break the retry
                        # An illustrative example must never prevent an echo retry.
                        pass
                    else:
                        content = content.replace(injected, "")
                        content += (
                            "\n\nExample of the required instance shape (placeholders only; extract actual values from the input):\n"
                            + example
                        )
                messages[-1].content = content + self._CORRECTION
            raise EmptyResponseError(
                "LLM echoed the JSON schema instead of returning extracted data"
            )
        return parsed

    @classmethod
    def _instance_example(
        cls, node: dict[str, Any], root: dict[str, Any], depth: int = 0
    ) -> Any:
        """A tiny illustrative instance, bounded even for recursive schemas."""
        try:
            return cls._build_instance_example(node, root, depth)
        except Exception:  # noqa: BLE001
            # Malformed or unsupported schema shapes have a safe placeholder.
            return None

    @classmethod
    def _build_instance_example(
        cls, node: dict[str, Any], root: dict[str, Any], depth: int
    ) -> Any:
        if depth > 5:
            return None
        if not isinstance(node, dict):
            return None
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            resolved = dict(root.get("$defs", {}).get(name, {}))
            resolved.update(
                {key: value for key, value in node.items() if key != "$ref"}
            )
            return cls._instance_example(resolved, root, depth + 1)
        if "allOf" in node:
            merged = {key: value for key, value in node.items() if key != "allOf"}
            for part in node["allOf"]:
                if "$ref" in part:
                    part = {
                        **root.get("$defs", {}).get(
                            part["$ref"].rsplit("/", 1)[-1], {}
                        ),
                        **{key: value for key, value in part.items() if key != "$ref"},
                    }
                properties = {
                    **merged.get("properties", {}),
                    **part.get("properties", {}),
                }
                merged.update(part)
                if properties:
                    merged["properties"] = properties
            return cls._instance_example(merged, root, depth + 1)
        if "const" in node:
            return node["const"]
        for union in ("anyOf", "oneOf"):
            if union in node:
                branch = next(
                    (part for part in node[union] if part.get("type") != "null"), {}
                )
                return cls._instance_example(branch, root, depth + 1)
        if "enum" in node:
            return node["enum"][0] if node["enum"] else None
        kind = node.get("type")
        if isinstance(kind, list):
            kind = next((item for item in kind if item != "null"), None)
        if kind == "object" or "properties" in node:
            return {
                key: cls._instance_example(value, root, depth + 1)
                for key, value in node.get("properties", {}).items()
            }
        if kind == "array":
            if "prefixItems" in node:
                return [
                    cls._instance_example(item, root, depth + 1)
                    for item in node["prefixItems"]
                ]
            item = cls._instance_example(node.get("items", {}), root, depth + 1)
            # Show object shape, but never suggest real fact/episode indexes.
            return [item] if isinstance(item, dict) else []
        # In graphiti 0.31.2, negative duplicate_candidate_id means no match,
        # negative resolution id is skipped, and negative entity_type_id falls
        # back to Entity. Scalar lists (fact indexes / episode_indices) above
        # stay empty; no schema constraint requires a real index.
        # Unknown constructs fall back to null rather than invented values.
        return {
            "string": "<string>",
            "integer": -1,
            "number": 0.0,
            "boolean": False,
        }.get(kind)

    @classmethod
    def _is_schema_echo(
        cls, parsed: Any, response_model: type[BaseModel] | None = None
    ) -> bool:
        """Whether the parsed response is a JSON schema rather than instance data."""
        if not isinstance(parsed, dict):
            return False
        if cls._SCHEMA_ECHO_KEYS & parsed.keys():
            return True
        for field in cls._response_fields(response_model):
            value = parsed.get(field)
            if isinstance(value, dict) and cls._SCHEMA_ECHO_KEYS & value.keys():
                return True
        return False

    @staticmethod
    @lru_cache(maxsize=64)
    def _response_fields(response_model: type[BaseModel] | None) -> frozenset[str]:
        if response_model is None:
            return frozenset()
        schema = response_model.model_json_schema()
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return frozenset()
        return frozenset(properties)


# Set around the ``graphiti.search`` call by ``GraphitiCoreSearcher.search``
# (see graphiti_mode.py); ``LocalEmbedderClient.create`` reads it to embed the
# search query with the BGE query instruction instead of document encoding.
# Contextvars propagate through the awaits/tasks graphiti creates inside a
# search, and are reset automatically when the setter's task finishes, so
# ingestion-time embeddings are never affected.
_SEARCH_QUERY_MODE: ContextVar[bool] = ContextVar(
    "omnistream_search_query_mode", default=False
)


class LocalEmbedderClient(EmbedderClient):
    """``EmbedderClient`` backed by the project's local bge-small service.

    Graphiti's ``EmbedderClient`` interface has no query/document distinction,
    so by default everything is embedded in the document space
    (``embed_documents``): fact and name embeddings are persisted in the
    graph, and they must all live in one comparable space.

    The one exception is the search query itself: graphiti's search embeds the
    query through ``create`` (the only embedder call in the search path — MMR
    reads stored vectors back from the database and the reranker has its own
    client). BGE retrieval is asymmetric, so the query vector must be built
    with the query instruction (``embed_query``), exactly like the ``own``
    mode's ``EmbeddingService.embed_query``. ``GraphitiCoreSearcher.search``
    sets ``_SEARCH_QUERY_MODE`` around the ``graphiti.search`` call and
    ``create`` honours it; contextvars propagate through the awaits and
    tasks graphiti creates inside. ``create_batch`` and every ingestion call
    (``add_episode`` and friends, where the flag is never set) keep document
    encoding.
    """

    def __init__(self, embeddings: EmbeddingService) -> None:
        self.embeddings = embeddings

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        """Embed one text and return its vector (mirrors graphiti's OpenAIEmbedder)."""
        if isinstance(input_data, str):
            texts = [input_data]
        elif isinstance(input_data, list) and all(
            isinstance(item, str) for item in input_data
        ):
            texts = input_data
        else:
            raise TypeError(
                "input_data must be str or list[str] for the local embedder"
            )
        if _SEARCH_QUERY_MODE.get():
            # The search query is the only thing embedded while the flag is
            # set; use the BGE query instruction for asymmetric retrieval.
            vectors = await asyncio.to_thread(self.embeddings.embed_queries, texts)
            return [float(value) for value in vectors[0]]
        vectors = await self._embed(texts)
        return [float(value) for value in vectors[0]]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Embed a batch of texts, one vector per text."""
        if not all(isinstance(item, str) for item in input_data_list):
            raise TypeError("input_data_list must contain only str values")
        vectors = await self._embed(list(input_data_list))
        return [list(map(float, row)) for row in vectors]

    async def _embed(self, texts: list[str]) -> np.ndarray:
        # The encoder is synchronous (sentence-transformers); keep the event
        # loop free while it runs.
        return await asyncio.to_thread(self.embeddings.embed_documents, texts)


class LocalRerankerClient(CrossEncoderClient):
    """Cross-encoder substitute: rank passages by local embedding cosine.

    Graphiti only uses the cross-encoder in ``search_`` configurations that
    request cross-encoder reranking (its default ``search`` uses RRF), but the
    constructor still needs a client that does not require an OpenAI account.
    This ranks passages by the cosine similarity between the query embedding
    (with the BGE query instruction) and each passage's document embedding,
    which needs no extra model beyond the project's embedding service.
    """

    def __init__(self, embeddings: EmbeddingService) -> None:
        self.embeddings = embeddings

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        query_vector, passage_vectors = await asyncio.gather(
            asyncio.to_thread(self.embeddings.embed_query, query),
            asyncio.to_thread(self.embeddings.embed_documents, list(passages)),
        )
        scores = self.embeddings.cosine_similarity(query_vector, passage_vectors)
        ranked = sorted(
            (
                (passage, float(score))
                for passage, score in zip(passages, scores, strict=True)
            ),
            key=lambda row: row[1],
            reverse=True,
        )
        return ranked


__all__: list[str] = [
    "GraphitiLLMClient",
    "LocalEmbedderClient",
    "LocalRerankerClient",
]
