"""Graphiti hybrid-search adapter (spec 1.3, 6/C5 and 7)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, Self

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Fact, RetrievalResult, ScoredFact, TimeScope

# Reserve candidates for grounding, provenance, group and time filtering.
SEARCH_OVERFETCH_FACTOR = 3
# Bound repeated prefix searches even when all candidates are rejected.
MAX_SEARCH_CANDIDATES = 500

# DeepSeek (and most OpenRouter models) cap output at 8192 tokens; graphiti's
# generic client default of 16384 would be rejected by the provider.
GRAPHITI_MAX_OUTPUT_TOKENS = 8192


class GraphitiSearcher(Protocol):
    """Injectable subset of Graphiti hybrid search; no dependency at import time."""

    async def search(
        self, query: str, *, group_ids: list[str], num_results: int
    ) -> list[Any]: ...


class GraphitiCoreSearcher:
    """Optional adapter; installation and connections remain caller controlled.

    Loop ownership: graphiti-core's ``Neo4jDriver`` schedules its
    ``_init_task`` (indices/constraints) on whatever event loop is running at
    construction time, and its pooled async connections stay bound to that
    loop. This adapter therefore records the loop it was constructed on as
    ``construction_loop`` (``None`` when no loop was running); the
    ``GraphitiRetriever`` refuses to run or close the searcher from any other
    loop. An explicit ``owner_loop`` can override the recorded loop.
    """

    def __init__(
        self, graphiti: Any, *, owner_loop: asyncio.AbstractEventLoop | None = None
    ) -> None:
        self.graphiti = graphiti
        if owner_loop is not None:
            self.construction_loop: asyncio.AbstractEventLoop | None = owner_loop
        else:
            try:
                self.construction_loop = asyncio.get_running_loop()
            except RuntimeError:
                self.construction_loop = None

    @classmethod
    def from_settings(
        cls, settings: Settings, *, embeddings: EmbeddingService | None = None
    ) -> GraphitiCoreSearcher:
        """Lazily construct Graphiti with the configured provider clients (spec 5, 7).

        Construction inside a running loop binds the driver to that loop; use
        aretrieve/aclose there. For sync use, prefer
        GraphitiRetriever.from_settings(), which constructs on its runner loop.

        The shared ``build_graphiti`` builder (spec C4/C5) wires the
        OpenAI-compatible endpoint from Settings (OpenRouter by default)
        through graphiti's ``OpenAIGenericClient`` (subclassed as
        ``GraphitiLLMClient``) in ``json_object`` mode (DeepSeek does not
        support ``json_schema`` structured output), with a guard against the
        schema-echo failure the provider occasionally exhibits.
        Embeddings are always local (spec 5): the project's ``EmbeddingService``
        wrapped as graphiti embedder and as the cross-encoder, so no OpenAI
        default client is ever created. An existing ``EmbeddingService`` can be
        injected to share one model instance.
        """
        try:
            from omnistream.graph.graphiti_client import build_graphiti
        except ImportError as exc:
            raise ImportError(
                "Graphiti mode requires optional graphiti-core; inject a GraphitiSearcher for offline use"
            ) from exc
        try:
            graphiti = build_graphiti(
                settings,
                embeddings,
                read_only=True,
                max_tokens=GRAPHITI_MAX_OUTPUT_TOKENS,
            )
        except ImportError as exc:
            raise ImportError(
                "Graphiti mode requires optional graphiti-core; inject a GraphitiSearcher for offline use"
            ) from exc
        return cls(graphiti)

    async def search(
        self, query: str, *, group_ids: list[str], num_results: int
    ) -> list[Any]:
        # The query vector is the only thing graphiti embeds during a search
        # (MMR reads stored vectors from the database; the reranker is a
        # separate client). Flag it so the local embedder uses the BGE query
        # encoding instead of document encoding, matching the asymmetric BGE
        # retrieval of the ``own`` mode. The import stays lazy so importing
        # this module never imports graphiti_core.
        from omnistream.retrieval.graphiti_clients import _SEARCH_QUERY_MODE

        token = _SEARCH_QUERY_MODE.set(True)
        try:
            edges = await self.graphiti.search(
                query, group_ids=group_ids, num_results=num_results
            )
            legacy = [
                e
                for e in edges
                if not e.attributes.get("published_at")
                and e.valid_at is None
                and e.episodes
            ]
            if legacy:
                rows, _, _ = await self.graphiti.driver.execute_query(
                    "MATCH (ep:Episodic) WHERE ep.uuid IN $ids "
                    "RETURN ep.uuid AS id, ep.valid_at AS valid_at",
                    ids=list({ep for e in legacy for ep in e.episodes}),
                )
                dates = {r["id"]: _date(r["valid_at"]) for r in rows}
                for edge in legacy:
                    stamps = [
                        dates[ep] for ep in edge.episodes if dates.get(ep) is not None
                    ]
                    if stamps:
                        edge.attributes["episode_valid_at"] = min(stamps)
            return edges
        finally:
            _SEARCH_QUERY_MODE.reset(token)

    async def close(self) -> None:
        """Close the underlying Graphiti driver (pooled connections included)."""
        closer = getattr(self.graphiti, "close", None)
        if closer is not None:
            await closer()


def _date(value: Any) -> datetime | None:
    if hasattr(value, "to_native"):
        return value.to_native()
    if value == "":
        return None
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


async def _cancel_and_drain(tasks: set[asyncio.Task[Any]], timeout: float) -> None:
    pending = set(tasks) - {asyncio.current_task()}
    for task in pending:
        # An interrupted bridge may already have requested cancellation. A
        # second cancel would interrupt its asynchronous rollback cleanup.
        if not task.cancelling():
            task.cancel()
    if pending:
        done, remaining = await asyncio.wait(pending, timeout=timeout)
        await asyncio.gather(*done, return_exceptions=True)
        if remaining:
            raise TimeoutError("Graphiti searches did not finish cancellation cleanup")


class _SyncLoopRunner:
    """One persistent background event loop for a retriever's sync calls.

    ``asyncio.run`` creates and closes a fresh loop per call, while Graphiti's
    pooled Neo4j async connections stay bound to the loop that created them;
    the next sync call would reuse those connections on a now-closed loop and
    fail. All sync work for one retriever instead runs on a single loop served
    by a daemon thread, so the pooled connections stay valid for the lifetime
    of the Graphiti instance.

    The runner is an explicit state machine (``NEW -> RUNNING -> CLOSING -> CLOSED``,
    with failed closes remaining retryable)
    guarded by one lock:

    * ``run`` holds the lock across the state check, loop creation and
      ``run_coroutine_threadsafe`` submission, so a concurrent ``stop`` can
      never interleave with a submission (which would either submit onto a
      closing loop or leave an orphaned coroutine). The coroutine is only
      created after the state check passes.
    * The runner thread is published as ``RUNNING`` only after the loop
      itself confirms ``run_forever`` has begun (a ``threading.Event`` set
      via ``loop.call_soon``), so concurrent first callers can never create
      a second loop/thread around the same driver.
    * ``stop`` atomically moves the state to ``CLOSING`` (new submissions are
      rejected with ``RuntimeError``), cancels and drains every outstanding
      asyncio task, optionally runs a close coroutine (e.g. ``graphiti.close``) on
      the loop, then stops and closes the loop and joins the thread.
    """

    _NEW = 0
    _RUNNING = 1
    _CLOSED = 2
    _CLOSING = 3
    _FAILED = 4

    _START_TIMEOUT = 30.0  # seconds; bounded so a startup regression fails, not hangs.
    _DRAIN_TIMEOUT = 10.0
    _CLOSE_TIMEOUT = 30.0
    _JOIN_TIMEOUT = 30.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = self._NEW
        self._close_done = threading.Event()
        self._close_outcome: concurrent.futures.Future[None] = (
            concurrent.futures.Future()
        )
        self._stop_issued = False
        self._close_factory: Callable[[], Any] | None = None
        self._searcher_closed = False
        self._shutdown_future: concurrent.futures.Future[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_cancelled: set[asyncio.Task[Any]] = set()

    def check_not_runner_thread(self) -> None:
        """Raise if called from the loop's own thread (close would deadlock)."""
        with self._lock:
            thread_id = self._thread_id
        if thread_id is not None and threading.get_ident() == thread_id:
            raise RuntimeError(
                "close() cannot be called from the sync loop's own thread (it "
                "would deadlock waiting on itself); call close() from another "
                "thread instead"
            )

    def run(self, coro_factory: Callable[[], Any]) -> Any:
        """Run ``coro_factory()`` on the persistent loop and return its result.

        Exceptions raised by the coroutine are re-raised in the calling
        thread; an interrupted wait cancels the submitted task instead of
        abandoning the search on the loop.
        """
        with self._lock:
            if self._state not in (self._NEW, self._RUNNING):
                raise RuntimeError("GraphitiRetriever is closed")
            self._ensure_loop_locked()
            if not self._thread.is_alive():
                raise RuntimeError("Graphiti sync loop thread died")
            # Only reachable when the runner is alive: the coroutine is
            # created after the state check, so a rejected call never leaves
            # an unawaited coroutine behind.
            future = asyncio.run_coroutine_threadsafe(
                self._tracked(coro_factory), self._loop
            )
        try:
            while True:
                try:
                    return future.result(timeout=0.1)
                except concurrent.futures.TimeoutError:
                    if future.done():
                        raise
                    if not self._thread.is_alive():
                        raise RuntimeError("Graphiti sync loop thread died")
        except BaseException:
            # KeyboardInterrupt (or any other interruption) while waiting
            # must not abandon the search on the loop; cancelling a future
            # that already resolved is a harmless no-op.
            future.cancel()
            raise

    async def _tracked(self, factory: Callable[[], Any]) -> Any:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            return await factory()
        except asyncio.CancelledError:
            if task in self._shutdown_cancelled:
                raise RuntimeError("GraphitiRetriever closed during retrieve") from None
            raise
        finally:
            self._tasks.discard(task)
            self._shutdown_cancelled.discard(task)

    async def _drain_and_close(self, close_factory: Callable[[], Any] | None) -> None:
        # Only cancellations issued by stop() get the shutdown diagnostic.
        self._shutdown_cancelled.update(
            task for task in self._tasks if not task.done() and not task.cancelling()
        )
        await _cancel_and_drain(self._tasks, self._DRAIN_TIMEOUT)
        if close_factory is not None and not self._searcher_closed:
            await close_factory()
            self._searcher_closed = True

    def stop(self, close_coro_factory: Callable[[], Any] | None = None) -> None:
        """Cancel in-flight work, run the close coroutine (if any), stop the loop.

        Idempotent. New submissions are rejected with ``RuntimeError`` from
        the moment ``stop`` begins. If the loop was never started, it is
        started briefly so the close runs on the loop the driver would have
        owned; the factory is only called when its coroutine will actually be
        awaited, so a second close never leaves one orphaned. A failed close
        leaves the driver and daemon thread alive until retry or process exit.
        """
        self.check_not_runner_thread()
        with self._lock:
            if self._state == self._CLOSED:
                return
            waiting = self._state == self._CLOSING
            if waiting:
                done = self._close_done
                outcome = self._close_outcome
            else:
                if self._state == self._NEW:
                    if close_coro_factory is None and self._close_factory is None:
                        self._state = self._CLOSED
                        return
                    self._ensure_loop_locked()
                self._state = self._CLOSING
                self._close_done = done = threading.Event()
                self._close_outcome = outcome = concurrent.futures.Future()
                if close_coro_factory is not None:
                    self._close_factory = close_coro_factory
            loop, thread = self._loop, self._thread
        if waiting:
            if not done.wait(
                self._DRAIN_TIMEOUT + self._CLOSE_TIMEOUT + self._JOIN_TIMEOUT
            ):
                raise TimeoutError("Graphiti close is still in progress")
            outcome.result()
            return
        try:
            if not self._stop_issued and (
                self._shutdown_future is None or self._shutdown_future.done()
            ):
                self._shutdown_future = asyncio.run_coroutine_threadsafe(
                    self._drain_and_close(self._close_factory), loop
                )
            if not self._stop_issued:
                self._shutdown_future.result(
                    timeout=self._DRAIN_TIMEOUT + self._CLOSE_TIMEOUT
                )
                loop.call_soon_threadsafe(loop.stop)
                self._stop_issued = True
            thread.join(self._JOIN_TIMEOUT)
            if thread.is_alive():
                raise RuntimeError("Graphiti sync loop thread did not stop in time")
            loop.close()
        except BaseException as exc:
            with self._lock:
                outcome.set_exception(exc)
                self._state = self._FAILED
            raise
        else:
            with self._lock:
                self._state = self._CLOSED
                outcome.set_result(None)
        finally:
            done.set()

    def _ensure_loop_locked(self) -> None:
        """Start the loop and thread if needed; the lock must be held.

        Does not return until ``run_forever`` is confirmed running, so no
        other caller can observe a half-started loop and create a second one.
        """
        if self._state == self._RUNNING:
            return
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        thread = threading.Thread(
            target=self._serve,
            args=(loop, ready),
            name="omnistream-graphiti",
            daemon=True,
        )
        try:
            thread.start()
        except BaseException:
            loop.close()
            raise
        if not ready.wait(self._START_TIMEOUT):
            self._abandon_start(loop, thread)
            raise RuntimeError("Graphiti sync loop failed to start")
        self._loop = loop
        self._thread = thread
        self._thread_id = thread.ident
        self._state = self._RUNNING

    @classmethod
    def _abandon_start(
        cls, loop: asyncio.AbstractEventLoop, thread: threading.Thread
    ) -> None:
        """Best-effort teardown when the loop thread never confirmed startup."""
        loop.call_soon_threadsafe(loop.stop)
        thread.join(cls._JOIN_TIMEOUT)
        if not thread.is_alive():
            loop.close()

    def _serve(self, loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
        asyncio.set_event_loop(loop)
        # Confirm the loop is serving before anyone is allowed to rely on it.
        loop.call_soon(ready.set)
        loop.run_forever()
        # Cancelled tasks that are never awaited raise their exceptions on
        # GC later; give whatever is left behind a chance to finish cleanup
        # while the loop is still usable.
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())


class GraphitiRetriever:
    """Top 20 facts, scored as 1 / original one-based search rank (spec C5).

    skipped_missing_provenance counts the latest completed query's skipped
    edges. Episode ids are never substituted for original item ids.

    A searcher constructed on a running loop pre-binds this retriever to
    that loop, requiring aretrieve/aclose and async with there. For sync
    applications use GraphitiRetriever.from_settings() to construct on the
    runner loop. Searchers constructed without a running loop bind on first use.

    Loop ownership: a retriever binds to exactly one owning event loop on its
    first use, and only that loop ever talks to the underlying Graphiti
    searcher (whose pooled Neo4j async connections stay bound to the loop
    that created them). The first call being sync ``retrieve`` binds the
    instance to its own persistent background loop (see
    ``_SyncLoopRunner``); the first call being ``await aretrieve`` binds it
    to the caller's running loop instead. Afterwards the other style raises
    ``RuntimeError``, and ``aretrieve`` is also rejected from any loop other
    than the bound one, so the cross-loop pooled-connection bug cannot
    reappear.

    Closing: for a sync-bound retriever use ``close`` (or the ``with``
    context manager); for an async-bound one use ``await aclose`` (or
    ``async with``) from the bound loop. ``close`` on an async-bound
    retriever raises and asks for ``aclose``; on a never-used retriever
    ``close`` just closes the searcher. Both styles refuse further work once
    closed.
    """

    mode = "graphiti"

    def __init__(self, searcher: GraphitiSearcher) -> None:
        self.searcher = searcher
        self.skipped_missing_provenance = 0
        self._loop = _SyncLoopRunner()
        self._lock = threading.Lock()
        self._owner: str | None = None  # None | "sync" | "async"
        self._owner_loop: asyncio.AbstractEventLoop | None = getattr(
            searcher, "construction_loop", None
        )
        if self._owner_loop is not None:
            self._owner = "async"
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False
        self._closing = False
        self._async_close_task: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(
        cls, settings: Settings, *, embeddings: EmbeddingService | None = None
    ) -> GraphitiRetriever:
        """Construct the searcher on a persistent runner loop for sync use."""
        runner = _SyncLoopRunner()

        async def construct() -> GraphitiCoreSearcher:
            searcher = GraphitiCoreSearcher.from_settings(
                settings, embeddings=embeddings
            )
            runner._close_factory = searcher.close
            return searcher

        try:
            retriever = cls(runner.run(construct))
        except BaseException:
            runner.stop()
            raise
        retriever._loop = runner
        retriever._owner = "sync"
        return retriever

    def _bind_sync(self) -> None:
        with self._lock:
            if self._closed or self._closing:
                raise RuntimeError("GraphitiRetriever is closed")
            if self._owner is None:
                self._owner = "sync"
            elif self._owner != "sync":
                raise RuntimeError(
                    "this GraphitiRetriever is bound to an event loop (first "
                    "used with await aretrieve()); retrieve() cannot be used "
                    "- keep using await aretrieve(...) on the same loop"
                )

    def _bind_async(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            if self._closed or self._closing:
                raise RuntimeError("GraphitiRetriever is closed")
            if self._owner is None:
                self._owner = "async"
                self._owner_loop = loop
            elif self._owner != "async":
                raise RuntimeError(
                    "this GraphitiRetriever is bound to its sync event loop "
                    "(first used with retrieve()); await aretrieve(...) "
                    "cannot be used - keep using retrieve()"
                )
            elif self._owner_loop is not loop:
                raise RuntimeError(
                    "this GraphitiRetriever is bound to a different event "
                    "loop; await aretrieve(...) from the loop it was first "
                    "used on"
                )

    async def aretrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Async entry point; the retriever binds to this loop on first use."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "aretrieve must be awaited from inside a running event loop"
            ) from None
        self._bind_async(loop)
        inner = asyncio.create_task(
            self._retrieve_impl(
                question, bubbles=bubbles, time_scope=time_scope, top_k=top_k
            )
        )
        self._tasks.add(inner)
        inner.add_done_callback(self._tasks.discard)
        try:
            return await asyncio.shield(inner)
        except asyncio.CancelledError:
            if not inner.cancelling():
                inner.cancel()
            # Keep ownership until cleanup completes, including repeated caller cancellation.
            while not inner.done():
                try:
                    await asyncio.shield(inner)
                except asyncio.CancelledError:
                    continue
                except BaseException:  # noqa: BLE001 - swallow non-cancel errors during drain
                    break
            if inner.done() and not inner.cancelled():
                inner.exception()
            if inner.cancelled() and asyncio.current_task().cancelling() == 0:
                raise RuntimeError("GraphitiRetriever closed during retrieve") from None
            raise

    async def _retrieve_impl(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None,
        top_k: int | None,
    ) -> RetrievalResult:
        limit = 20 if top_k is None else top_k
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(question, str):
            raise TypeError("question must be a string")
        self.skipped_missing_provenance = 0
        if not question.strip() or not bubbles:
            return RetrievalResult(mode="graphiti")
        groups = list(dict.fromkeys(bubbles))
        if any(not isinstance(b, str) or not b.strip() for b in groups):
            raise ValueError("bubbles must contain non-empty strings")
        facts = []
        missing = 0
        seen: set[str] = set()
        requested = min(limit * SEARCH_OVERFETCH_FACTOR, MAX_SEARCH_CANDIDATES)
        while True:
            edges = await self.searcher.search(
                question, group_ids=groups, num_results=requested
            )
            for rank, edge in enumerate(edges, 1):
                if edge.uuid in seen:
                    continue
                seen.add(edge.uuid)
                attrs = getattr(edge, "attributes", None) or {}
                if (
                    edge.group_id not in groups
                    or attrs.get("grounded", False) is not True
                ):
                    continue
                item_id = attrs.get("item_id")
                if not isinstance(item_id, str) or not item_id.strip():
                    missing += 1
                    continue
                valid, invalid = _date(edge.valid_at), _date(edge.invalid_at)
                if not (
                    time_scope or TimeScope(datetime.now(UTC), datetime.now(UTC))
                ).overlaps(valid, invalid) or (
                    time_scope is None
                    and _date(getattr(edge, "expired_at", None)) is not None
                ):
                    continue
                published = (
                    _date(attrs.get("published_at"))
                    or valid
                    or _date(attrs.get("episode_valid_at"))
                    or _date(edge.created_at)
                )
                if published is None:
                    published = datetime.min.replace(tzinfo=UTC)
                fact = Fact(
                    edge.uuid,
                    edge.source_node_uuid,
                    edge.target_node_uuid,
                    edge.name,
                    edge.fact,
                    edge.group_id,
                    item_id,
                    attrs.get("source_url"),
                    published,
                    valid,
                    invalid,
                    True,
                    attrs.get("credibility", 0.5),
                    attrs.get("confidence", 0.5),
                    attrs.get("source_count", 1),
                    _date(getattr(edge, "expired_at", None)),
                    tuple(attrs.get("item_ids") or ()),
                )
                facts.append(ScoredFact(fact, 1.0 / rank, ranks={"graphiti": rank}))
            if (
                len(facts) >= limit
                or len(edges) < requested
                or requested >= MAX_SEARCH_CANDIDATES
            ):
                break
            requested = min(requested * 2, MAX_SEARCH_CANDIDATES)
        self.skipped_missing_provenance = missing
        return RetrievalResult(mode="graphiti", facts=tuple(facts[:limit]))

    def retrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Sync entry point; async applications must await aretrieve.

        All sync calls run on this retriever's single persistent background
        loop, so Graphiti's pooled async Neo4j connections always stay on the
        loop that created them. Using ``retrieve`` first binds the retriever
        to that loop; mixing with ``aretrieve`` afterwards raises.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "retrieve cannot run inside an event loop; use await aretrieve(...) instead"
            )
        self._bind_sync()
        return self._loop.run(
            lambda: self._retrieve_impl(
                question, bubbles=bubbles, time_scope=time_scope, top_k=top_k
            )
        )

    def close(self) -> None:
        """Close the Graphiti driver (when the searcher exposes one) and stop the loop.

        Only valid for a retriever that was used synchronously (or never used
        at all). On an async-bound retriever this raises; use
        ``await aclose()`` from the bound loop instead. Raises instead of
        deadlocking when called from the sync loop's own thread.
        """
        self._loop.check_not_runner_thread()
        with self._lock:
            if self._closed:
                return
            if self._owner == "async":
                raise RuntimeError(
                    "this GraphitiRetriever is bound to an event loop; use "
                    "`await aclose()` from that loop instead of close()"
                )
            self._owner = "sync"
            self._closing = True
        closer = getattr(self.searcher, "close", None)
        self._loop.stop((lambda: closer()) if closer is not None else None)
        with self._lock:
            self._closed = True

    async def aclose(self) -> None:
        """Close the searcher on the loop this retriever is bound to.

        Must be awaited from the bound loop (the loop ``aretrieve`` was first
        awaited from). Refuses further work once closed.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "aclose() must be awaited from inside a running event loop"
            ) from None
        with self._lock:
            if self._closed:
                return
            if self._owner == "sync":
                raise RuntimeError(
                    "this GraphitiRetriever is bound to its sync event loop; "
                    "use close() instead of aclose()"
                )
            if self._owner == "async" and self._owner_loop is not loop:
                raise RuntimeError(
                    "aclose() must be awaited from the event loop this "
                    "GraphitiRetriever is bound to"
                )
            self._owner = "async"
            self._owner_loop = loop
            self._closing = True
            if self._async_close_task is None or self._async_close_task.done():
                self._async_close_task = asyncio.create_task(self._aclose_impl())
                # A shielded close can outlive its caller; consume late failures.
                self._async_close_task.add_done_callback(
                    lambda task: task.exception() if not task.cancelled() else None
                )
            task = self._async_close_task
        await asyncio.wait_for(
            asyncio.shield(task),
            _SyncLoopRunner._DRAIN_TIMEOUT + _SyncLoopRunner._CLOSE_TIMEOUT,
        )

    async def _aclose_impl(self) -> None:
        await _cancel_and_drain(self._tasks, _SyncLoopRunner._DRAIN_TIMEOUT)
        closer = getattr(self.searcher, "close", None)
        if closer is not None:
            await closer()
        with self._lock:
            self._closed = True

    def __enter__(self) -> Self:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "with cannot run inside an event loop; use async with instead"
            )
        self._bind_sync()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    async def __aenter__(self) -> Self:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "GraphitiRetriever must be entered from inside a running event loop"
            ) from None
        self._bind_async(loop)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
