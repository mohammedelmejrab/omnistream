"""Application-state wiring for C5. Build once; await answer() and close().

Pass ingestion's EmbeddingService (or its async adapter) as embeddings to share
one lazy local model. Repository and supplied embeddings remain caller-owned.
Graphiti is constructed on its persistent sync runner and used in worker threads.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

from omnistream.bubbles import RepositoryBubbleCatalog
from omnistream.embeddings import EmbeddingService
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.items import RepositoryItemStore
from omnistream.llm import AsyncLLMClient, LLMClient
from omnistream.qa import answer_question
from omnistream.retrieval.classic import ClassicRetriever, make_chroma_client
from omnistream.retrieval.graphiti_mode import GraphitiRetriever
from omnistream.retrieval.modes import RetrievalDispatcher
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from omnistream.retrieval.router import QueryRouter


class CatalogHalfLives(Mapping):
    def __init__(self, catalog):
        self.catalog = catalog

    def __iter__(self):
        return iter({b.id: b.half_life_days for b in self.catalog.list()})

    def __len__(self):
        return len(self.catalog.list())

    def __getitem__(self, key):
        return self.catalog.get(key).half_life_days

    def items(self):
        return {b.id: b.half_life_days for b in self.catalog.list()}.items()


class QueryRuntime:
    def __init__(
        self,
        settings,
        repo,
        embeddings,
        graph,
        chroma,
        graphiti,
        llm,
        async_llm,
        *,
        now=None,
    ):
        self.settings, self.repo, self.embeddings = settings, repo, embeddings
        self.graph, self.chroma, self.graphiti = graph, chroma, graphiti
        self.llm, self.async_llm = llm, async_llm
        self.catalog = RepositoryBubbleCatalog(repo)
        self.router = QueryRouter(llm, embeddings, self.catalog, now=now)
        self.items = RepositoryItemStore(repo, Path(settings.data_dir))
        self.dispatcher = RetrievalDispatcher(
            {
                "classic": ClassicRetriever(chroma, embeddings),
                "graphiti": graphiti,
                "own": OwnRetriever(
                    graph,
                    embeddings,
                    now=now,
                    half_lives=CatalogHalfLives(self.catalog),
                ),
            },
            "own",
        )
        self._schema_lock = asyncio.Lock()
        self._schema_checked = False
        self._closed = False
        self._answers = set()
        self._close_task = None
        self.close_timeout = 30.0

    async def initialize(self, *, create_schema=False):
        """Check C4's index in a worker thread; provisioning is explicit opt-in."""
        async with self._schema_lock:
            if create_schema:
                await asyncio.to_thread(
                    self.graph.ensure_schema, self.settings.embed_dim
                )
            elif not self._schema_checked:
                await asyncio.to_thread(
                    self.graph.check_schema, self.settings.embed_dim
                )
            self._schema_checked = True

    async def answer(self, question, *, mode=None, subagents=None, pin=(), exclude=()):
        if self._closed:
            raise RuntimeError("query runtime is closed")

        async def run():
            await self.initialize()
            return await answer_question(
                question,
                router=self.router,
                dispatcher=self.dispatcher,
                llm=self.llm,
                async_llm=self.async_llm,
                graph_store=self.graph,
                item_store=self.items,
                settings=self.settings,
                mode=mode,
                subagents=subagents,
                pins=pin,
                exclude=exclude,
            )

        task = asyncio.create_task(run())
        self._answers.add(task)
        try:
            return await task
        finally:
            self._answers.discard(task)

    async def close(self):
        """Release owned clients; never dispose the app's Repository."""
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        if self._answers:
            _, pending = await asyncio.wait(self._answers, timeout=self.close_timeout)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        errors = []
        for closer in (self.graphiti.close, self.graph.driver.close):
            try:
                await asyncio.to_thread(closer)
            except Exception as exc:  # noqa: BLE001 - release remaining resources before reporting failures
                errors.append(exc)
        # Chroma close releases one client reference, preserving ingestion's
        # shared system until the final client closes.
        sync_closers = [self.chroma.close]
        client = getattr(self.llm, "_client", None)
        if client is not None:
            sync_closers.append(client.close)
        for closer in sync_closers:
            try:
                await asyncio.to_thread(closer)
            except Exception as exc:  # noqa: BLE001 - finish cleanup before reporting failures
                errors.append(exc)
        client = getattr(self.async_llm, "_client", None)
        if client is not None:
            try:
                await client.close()
            except Exception as exc:  # noqa: BLE001 - finish cleanup before reporting failures
                errors.append(exc)
        self.chroma = None
        if errors:
            raise ExceptionGroup("query runtime close failed", errors)


def build_query_runtime(settings, repo, *, embeddings=None, now=None):
    """Build lazy clients without Neo4j I/O, model loading, or LLM calls.

    Await runtime.initialize() for a read-only index check (also done on the
    first answer). C4 provisions indexes; explicit initialize(create_schema=True)
    is available for standalone setup. Blocking checks run in worker threads.
    """
    service = (
        getattr(embeddings, "service", embeddings)
        if embeddings is not None
        else EmbeddingService(settings)
    )
    graph = Neo4jGraphStore.from_settings(settings)
    if now is not None:
        graph.now = now
    chroma = graphiti = llm = async_llm = None
    try:
        chroma = make_chroma_client(Path(settings.data_dir) / "chroma")
        graphiti = GraphitiRetriever.from_settings(settings, embeddings=service)
        if now is not None:
            graphiti.now = now
        llm = LLMClient(settings)
        async_llm = AsyncLLMClient(settings)
        return QueryRuntime(
            settings,
            repo,
            service,
            graph,
            chroma,
            graphiti,
            llm,
            async_llm,
            now=now,
        )
    except BaseException:
        # Attempt every cleanup without masking the construction failure.
        import concurrent.futures

        for resource in (graphiti, chroma, getattr(llm, "_client", None), graph.driver):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "query runtime construction cleanup failed"
                    )
        client = getattr(async_llm, "_client", None)
        if client is not None:
            try:
                # Construction can also run inside an application's event loop.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(lambda: asyncio.run(client.close())).result()
            except Exception:
                logging.getLogger(__name__).exception(
                    "query runtime construction cleanup failed"
                )
        raise
