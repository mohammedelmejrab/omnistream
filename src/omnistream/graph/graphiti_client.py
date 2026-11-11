"""Graphiti wiring (spec C4/C5): one shared builder, hardened C5 clients.

``build_graphiti`` is the single construction path for both the C4 writer
(``GraphWriter``) and the C5 graphiti retrieval mode
(``GraphitiCoreSearcher.from_settings``). It always injects the hardened C5
clients from :mod:`omnistream.retrieval.graphiti_clients` - ``GraphitiLLMClient``
(DeepSeek schema-echo recovery), ``LocalEmbedderClient`` (BGE query-mode
contextvar) and ``LocalRerankerClient`` - so graphiti never falls back to its
OpenAI defaults.

The C4 ``BgeEmbedderClient``/``LocalCrossEncoder`` adapters remain: they wrap
the async ``Embedder`` protocol used by the ingestion modules, and
``build_graphiti`` accepts such an embedder in place of an ``EmbeddingService``.
"""

import math
from collections.abc import Iterable

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from pydantic import BaseModel

from omnistream.config import Settings
from omnistream.embed import Embedder
from omnistream.embeddings import EmbeddingService


class Person(BaseModel):
    """A named individual."""


class Organization(BaseModel):
    """A company, institution, agency, or other organized group."""


class Location(BaseModel):
    """A country, city, region, or other named place."""


class Product(BaseModel):
    """A named product, service, or technology."""


class Event(BaseModel):
    """A named occurrence such as a conference, merger, or election."""


class Concept(BaseModel):
    """A named idea, topic, theory, or technical concept."""


class FinancialInstrument(BaseModel):
    """A tradable security or instrument: stock, bond, currency pair, index, fund."""


class Publication(BaseModel):
    """A named paper, report, book, article, or other published work."""


# Spec C4: one shared set. Neo4j labels cannot contain spaces, so the spec's
# "Financial Instrument" is stored as the label `FinancialInstrument`.
ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Person": Person,
    "Organization": Organization,
    "Location": Location,
    "Product": Product,
    "Event": Event,
    "Concept": Concept,
    "FinancialInstrument": FinancialInstrument,
    "Publication": Publication,
}


class BgeEmbedderClient(EmbedderClient):
    """Adapts our local `Embedder` to Graphiti's EmbedderClient."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        if isinstance(input_data, str):
            text = input_data
        else:
            items = list(input_data)
            if not items or not isinstance(items[0], str):
                raise TypeError("BgeEmbedderClient only embeds text")
            text = items[0]
        return (await self._embedder.embed([text]))[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self._embedder.embed(input_data_list)


class LocalCrossEncoder(CrossEncoderClient):
    """Ranks passages by cosine similarity with our embedder; no network."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        query_vec, *vecs = await self._embedder.embed([query, *passages])
        scored = [(p, _cosine(query_vec, v)) for p, v in zip(passages, vecs)]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def build_graphiti(
    settings: Settings,
    embeddings: EmbeddingService | Embedder | None = None,
    *,
    read_only: bool = False,
    max_tokens: int = 8192,  # DeepSeek caps output at 8192; graphiti defaults to 16384
) -> Graphiti:
    """Build Graphiti with the hardened clients; never OpenAI defaults.

    ``embeddings`` may be an ``EmbeddingService`` (C5 query path; one shared
    model instance) or an async ``Embedder`` (C4 ingestion path); ``None``
    builds a fresh ``EmbeddingService`` from ``Settings``. The graphiti and
    client names are looked up at call time so tests can monkeypatch them.
    """
    from graphiti_core import Graphiti as GraphitiClass

    from omnistream.retrieval.graphiti_clients import (
        GraphitiLLMClient,
        LocalEmbedderClient,
        LocalRerankerClient,
    )

    if embeddings is None or isinstance(embeddings, EmbeddingService):
        service = embeddings if embeddings is not None else EmbeddingService(settings)
        embedder_client: EmbedderClient = LocalEmbedderClient(service)
        cross_encoder: CrossEncoderClient = LocalRerankerClient(service)
    else:
        embedder_client = BgeEmbedderClient(embeddings)
        cross_encoder = LocalCrossEncoder(embeddings)
    llm = GraphitiLLMClient(
        config=LLMConfig(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        ),
        max_tokens=max_tokens,
        # Spec: JSON mode (works on providers without json_schema, e.g. DeepSeek).
        structured_output_mode="json_object",
    )
    graphiti = GraphitiClass(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password.get_secret_value(),
        llm_client=llm,
        embedder=embedder_client,
        cross_encoder=cross_encoder,
    )

    if read_only:
        # graphiti-core 0.31 schedules schema writes in Neo4jDriver.__init__.
        # Cancel synchronously before the owning loop can run the task. C4
        # provisions schema explicitly; query-only users need no DDL privilege.
        task = getattr(graphiti.driver, "_init_task", None)
        if task is not None:
            task.cancel()
    return graphiti
