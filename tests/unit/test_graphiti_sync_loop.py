"""Offline tests for GraphitiRetriever's persistent sync event loop.

``retrieve`` must never hand a second ``asyncio.run`` loop to the same Graphiti
instance: its pooled Neo4j async connections stay bound to the first loop,
which ``asyncio.run`` closes. These tests prove every consecutive sync call
runs on one long-lived loop, that loop-bound resources survive across calls,
and that ``close`` shuts the loop down and closes the searcher.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import threading
import warnings
from typing import Any

import pytest

from omnistream.retrieval.graphiti_mode import GraphitiCoreSearcher, GraphitiRetriever


class LoopRecordingSearcher:
    """Records the running loop of every call and keeps a per-loop lock."""

    def __init__(self) -> None:
        self.loops: list[asyncio.AbstractEventLoop] = []
        self.threads: list[int] = []
        self._lock: asyncio.Lock | None = None
        self.closed = False
        self.close_loop: asyncio.AbstractEventLoop | None = None
        self.calls = 0

    async def search(self, query: str, *, group_ids: list[str], num_results: int):
        loop = asyncio.get_running_loop()
        self.loops.append(loop)
        self.threads.append(threading.get_ident())
        # An asyncio.Lock is bound to the loop it is created on; creating it
        # on the first call and acquiring it on every call fails if a later
        # call runs on a different loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            self.calls += 1
        return []

    async def close(self) -> None:
        self.closed = True
        self.close_loop = asyncio.get_running_loop()


def _runner_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "omnistream-graphiti"]


def _record_retrieve_error(
    retriever: GraphitiRetriever, errors: list[BaseException]
) -> None:
    try:
        retriever.retrieve("q", bubbles=["news"])
    except BaseException as exc:  # noqa: BLE001 - deliberate catch-alls in loop-liveness tests
        errors.append(exc)


def test_consecutive_sync_retrieves_run_on_one_persistent_loop():
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    retriever.retrieve("first", bubbles=["news"])
    retriever.retrieve("second", bubbles=["news"])
    loop = searcher.loops[0]
    try:
        assert searcher.calls == 2
        assert len(searcher.loops) == 2
        assert searcher.loops[0] is searcher.loops[1], (
            "each sync call created its own loop"
        )
        # The loop is a live, dedicated background loop, not a one-shot
        # asyncio.run loop (which would be closed by the time the call
        # returned).
        assert loop.is_running()
        # The work happens on the loop's own thread, never the caller's.
        assert searcher.threads[0] == searcher.threads[1]
        assert searcher.threads[0] != threading.get_ident()
        # The loop-bound lock created on the first call was acquired on the
        # second without a cross-loop error.
        assert searcher._lock is not None
    finally:
        retriever.close()


def test_close_stops_the_loop_and_closes_the_searcher():
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    retriever.retrieve("q", bubbles=["news"])
    loop = searcher.loops[0]
    assert loop.is_running()

    retriever.close()
    assert searcher.closed
    assert loop.is_closed()
    # Idempotent.
    retriever.close()
    # A closed retriever refuses further sync work instead of silently
    # reopening a loop for a closed Graphiti driver.
    with pytest.raises(RuntimeError, match="closed"):
        retriever.retrieve("q", bubbles=["news"])


def test_close_before_first_use_still_closes_the_searcher():
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    # Never retrieved: close() starts the loop just long enough to run the
    # searcher's close coroutine on the loop the driver would have used.
    retriever.close()
    assert searcher.closed
    assert not searcher.loops


def test_context_manager_closes_loop_and_searcher():
    searcher = LoopRecordingSearcher()
    with GraphitiRetriever(searcher) as retriever:
        retriever.retrieve("q", bubbles=["news"])
        assert searcher.calls == 1
    assert searcher.closed
    assert searcher.loops[0].is_closed()


def test_sync_retrieve_propagates_searcher_errors():
    class FailingSearcher:
        async def search(self, query: str, *, group_ids: list[str], num_results: int):
            raise ValueError("searcher exploded")

    retriever = GraphitiRetriever(FailingSearcher())
    try:
        with pytest.raises(ValueError, match="searcher exploded"):
            retriever.retrieve("q", bubbles=["news"])
    finally:
        retriever.close()


def test_concurrent_first_retrieves_create_exactly_one_loop(monkeypatch):
    """Many threads racing the first retrieve() must share one loop/thread.

    The old code decided "no loop yet" from ``is_running()`` while the first
    thread had not begun ``run_forever``, so every racer built (and leaked) a
    second loop and thread around the same driver. The loop's startup is
    delayed here to make that race deterministic; the new runner waits for
    the loop to confirm it is serving before any other caller proceeds.
    """
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)

    entered = threading.Event()
    release = threading.Event()
    original_new_loop = asyncio.new_event_loop

    def slow_loop() -> asyncio.AbstractEventLoop:
        loop = original_new_loop()
        original_run_forever = loop.run_forever

        def delayed_run_forever() -> None:
            entered.set()
            assert release.wait(10), "test failed to release the runner loop"
            original_run_forever()

        loop.run_forever = delayed_run_forever  # type: ignore[method-assign]
        return loop

    monkeypatch.setattr(asyncio, "new_event_loop", slow_loop)

    workers = 8
    attempted = threading.Event()
    real_lock = retriever._loop._lock
    count_lock = threading.Lock()
    attempts = 0

    local = threading.local()

    def mark_attempt():
        nonlocal attempts
        with count_lock:
            attempts += 1
            if attempts == workers - 1:
                attempted.set()

    class ObservedLock:
        def __enter__(self):
            local.first = not entered.is_set()
            local.marked = False
            if not real_lock.acquire(blocking=False):
                if not local.first:
                    mark_attempt()
                    local.marked = True
                real_lock.acquire()

        def __exit__(self, *args):
            real_lock.release()
            if not local.first and not local.marked:
                mark_attempt()

    retriever._loop._lock = ObservedLock()
    errors: list[BaseException] = []

    def call_retrieve() -> None:
        _record_retrieve_error(retriever, errors)

    threads = [
        threading.Thread(target=call_retrieve, name=f"first-use-race-{i}")
        for i in range(workers)
    ]
    try:
        threads[0].start()
        assert entered.wait(10)
        for thread in threads[1:]:
            thread.start()
        assert attempted.wait(10), "racers never reached runner startup"
        assert entered.wait(10), "the sync loop never started running"
        release.set()
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive(), "a first-use racer deadlocked"
        assert not errors, errors
        assert len(set(searcher.loops)) == 1
        assert searcher.calls == workers
        assert len(_runner_threads()) == 1
    finally:
        release.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=15)
        retriever.close()
    assert not _runner_threads()


def test_stop_concurrent_with_running_retrieve_cancels_work_and_rejects_new():
    """stop() racing an in-flight retrieve must cancel it first, not after.

    The old stop() ran the close coroutine while searches were still in
    flight (tearing the driver down mid-query) and only cancelled whatever
    was left when the loop stopped. The new stop() cancels and drains
    outstanding work first, so the close coroutine runs last and every
    blocked caller is released. A searcher records the observable order:
    "search-cancelled" must come before "close".
    """

    class BlockingSearcher:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.events: list[str] = []

        async def search(self, query: str, *, group_ids: list[str], num_results: int):
            self.started.set()
            self.events.append("search-start")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.events.append("search-cancelled")
                raise
            return []

        async def close(self) -> None:
            self.events.append("close")

    searcher = BlockingSearcher()
    retriever = GraphitiRetriever(searcher)
    errors: list[BaseException] = []
    workers = [
        threading.Thread(
            target=lambda: _record_retrieve_error(retriever, errors),
            name=f"stop-race-{i}",
        )
        for i in range(3)
    ]
    closer = threading.Thread(target=retriever.close, name="stop-race-closer")
    try:
        for worker in workers:
            worker.start()
        assert searcher.started.wait(10), "the search never started"
        closer.start()
        closer.join(timeout=15)
        assert not closer.is_alive(), "close() hung while a retrieve was in flight"
    finally:
        retriever.close()
        if closer.ident is not None:
            closer.join(timeout=15)
        for worker in workers:
            if worker.ident is not None:
                worker.join(timeout=10)
                assert not worker.is_alive(), "a retrieve worker hung after close()"

    # Every in-flight search was cancelled before the close coroutine ran,
    # and every blocked caller was released (cancelled or rejected).
    assert "search-cancelled" in searcher.events, "no in-flight search was cancelled"
    assert searcher.events.index("search-cancelled") < searcher.events.index("close"), (
        f"close ran before in-flight work was cancelled: {searcher.events}"
    )
    assert all(
        isinstance(
            e, (asyncio.CancelledError, concurrent.futures.CancelledError, RuntimeError)
        )
        for e in errors
    ), errors

    # Rejected submissions raise RuntimeError and never leave an unawaited
    # coroutine behind (which would surface as a "coroutine was never
    # awaited" RuntimeWarning on GC).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(RuntimeError, match="closed"):
            retriever.retrieve("q", bubbles=["news"])
        gc.collect()
    assert not [w for w in caught if "coroutine was never awaited" in str(w.message)]
    assert not _runner_threads()


def test_aretrieve_then_retrieve_raises_instead_of_crossing_loops():
    """A sync retrieve() after aretrieve() must not hand the searcher a second loop."""
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(retriever.aretrieve("q", bubbles=["news"]))

        error: list[RuntimeError] = []

        def sync_call() -> None:
            try:
                retriever.retrieve("q", bubbles=["news"])
            except RuntimeError as exc:
                error.append(exc)

        thread = threading.Thread(target=sync_call, name="sync-after-async")
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert error and "aretrieve" in str(error[0]), "no ownership error was raised"

        loop.run_until_complete(retriever.aclose())
    finally:
        loop.close()
    assert len(set(searcher.loops)) == 1, "the searcher was used on more than one loop"
    assert searcher.closed
    assert searcher.close_loop is loop
    assert not _runner_threads()


def test_retrieve_then_aretrieve_raises_instead_of_crossing_loops():
    """An async aretrieve() after retrieve() must not cross onto another loop."""
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    try:
        retriever.retrieve("q", bubbles=["news"])

        async def misuse() -> None:
            with pytest.raises(RuntimeError, match="retrieve"):
                await retriever.aretrieve("q", bubbles=["news"])

        asyncio.run(misuse())
    finally:
        retriever.close()
    assert len(set(searcher.loops)) == 1, "the searcher was used on more than one loop"
    assert searcher.closed
    assert searcher.close_loop is searcher.loops[0], (
        "sync close() ran on a different loop"
    )
    assert not _runner_threads()


def test_aretrieve_from_a_second_loop_raises():
    """aretrieve() must always run on the loop the retriever first bound to."""
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    bound_loop = asyncio.new_event_loop()
    try:
        bound_loop.run_until_complete(retriever.aretrieve("q", bubbles=["news"]))
        other_loop = asyncio.new_event_loop()
        try:
            with pytest.raises(RuntimeError, match="loop"):
                other_loop.run_until_complete(
                    retriever.aretrieve("q", bubbles=["news"])
                )
        finally:
            other_loop.close()
        bound_loop.run_until_complete(retriever.aclose())
        assert searcher.closed
        assert searcher.close_loop is bound_loop
    finally:
        bound_loop.close()
    assert len(set(searcher.loops)) == 1, "the searcher was used on more than one loop"
    assert not _runner_threads()


def test_aclose_closes_the_searcher_on_the_bound_loop():
    """aclose() runs the searcher's close coroutine on the owner loop."""
    searcher = LoopRecordingSearcher()
    retriever = GraphitiRetriever(searcher)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(retriever.aretrieve("q", bubbles=["news"]))
        loop.run_until_complete(retriever.aclose())
    finally:
        loop.close()
    assert searcher.closed
    assert searcher.close_loop is loop
    assert not _runner_threads()
    # A closed async-bound retriever refuses further work.
    with pytest.raises(RuntimeError, match="closed"):
        retriever.retrieve("q", bubbles=["news"])


def test_async_context_manager_closes_on_exit():
    """``async with`` closes the searcher on the owner loop on exit."""
    searcher = LoopRecordingSearcher()
    loop = asyncio.new_event_loop()
    try:

        async def scenario() -> None:
            async with GraphitiRetriever(searcher) as retriever:
                await retriever.aretrieve("q", bubbles=["news"])

        loop.run_until_complete(scenario())
    finally:
        loop.close()
    assert searcher.closed
    assert not _runner_threads()


def test_close_from_the_runner_thread_raises_instead_of_deadlocking():
    """close() on the loop's own thread used to wait on itself forever."""

    class ClosingSearcher:
        def __init__(self) -> None:
            self.retriever: GraphitiRetriever | None = None
            self.error: RuntimeError | None = None
            self.closed = False

        async def search(self, query: str, *, group_ids: list[str], num_results: int):
            # Runs on the sync loop's own thread: close() here would wait on
            # this very thread if the guard were missing.
            try:
                assert self.retriever is not None
                self.retriever.close()
            except RuntimeError as exc:
                self.error = exc
            return []

        async def close(self) -> None:
            self.closed = True

    searcher = ClosingSearcher()
    retriever = GraphitiRetriever(searcher)
    searcher.retriever = retriever
    outcome: list[BaseException] = []

    caller = threading.Thread(target=lambda: _record_retrieve_error(retriever, outcome))
    caller.start()
    caller.join(timeout=15)
    assert not caller.is_alive(), "close() from the runner thread deadlocked"
    assert not outcome, outcome
    assert searcher.error is not None
    assert "another thread" in str(searcher.error)

    # The retriever is still healthy and can be closed from a normal thread.
    retriever.close()
    assert searcher.closed
    assert not _runner_threads()


def test_interrupted_wait_cancels_the_in_flight_future(monkeypatch):
    """A KeyboardInterrupt while waiting must cancel, not abandon, the search.

    The old run() let any BaseException escape and left the search running on
    the loop. The new run() cancels the future before re-raising, so the loop
    stays free and healthy for the next call.
    """

    class GatedSearcher:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.cancelled = threading.Event()
            self.first = True
            self.closed = False
            self.events = []

        async def search(self, query: str, *, group_ids: list[str], num_results: int):
            if self.first:
                self.first = False
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.cancelled.set()
                    await asyncio.sleep(0.05)
                    self.events.append("cleanup-done")
                    raise
            return []

        async def close(self) -> None:
            self.events.append("close")
            self.closed = True

    searcher = GatedSearcher()
    retriever = GraphitiRetriever(searcher)
    real_result = concurrent.futures.Future.result
    interrupt = {"armed": True}

    def interrupting_result(self, timeout: float | None = None) -> Any:
        # Interrupt the caller's wait as soon as the search is running, so
        # the abandoned future is deterministically mid-flight.
        if interrupt["armed"]:
            assert searcher.started.wait(15), "search never started"
            interrupt["armed"] = False
            raise KeyboardInterrupt
        return real_result(self, timeout)

    monkeypatch.setattr(concurrent.futures.Future, "result", interrupting_result)
    try:
        with pytest.raises(KeyboardInterrupt):
            retriever.retrieve("q", bubbles=["news"])
        # The abandoned wait must have cancelled the search...
        assert searcher.cancelled.wait(5), (
            "the interrupted search kept running on the loop"
        )
        # ...leaving the loop free and healthy for the next call.
        second = retriever.retrieve("q", bubbles=["news"])
        assert second.mode == "graphiti" and not second.facts
    finally:
        closer = threading.Thread(target=retriever.close, name="interrupt-test-closer")
        closer.start()
        closer.join(timeout=15)
        assert not closer.is_alive(), "close() hung after the interrupted retrieve"
    assert searcher.closed
    assert searcher.events == ["cleanup-done", "close"]
    assert not _runner_threads()


class CleanupSearcher(LoopRecordingSearcher):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.events = []

    async def search(self, *args, **kwargs):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            self.events.append("cleanup-done")
            raise

    async def close(self):
        self.events.append("close")


def test_sync_close_waits_for_async_cleanup():
    searcher = CleanupSearcher()
    retriever = GraphitiRetriever(searcher)
    errors = []
    worker = threading.Thread(target=_record_retrieve_error, args=(retriever, errors))
    try:
        worker.start()
        assert searcher.started.wait(10)
    finally:
        retriever.close()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert searcher.events == ["cleanup-done", "close"]
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert str(errors[0]) == "GraphitiRetriever closed during retrieve"


def test_async_close_waits_for_cleanup():
    async def scenario():
        searcher = CleanupSearcher()
        retriever = GraphitiRetriever(searcher)
        task = asyncio.create_task(retriever.aretrieve("q", bubbles=["news"]))
        try:
            while not searcher.started.is_set():
                await asyncio.sleep(0)
            await asyncio.wait_for(retriever.aclose(), 5)
            assert searcher.events == ["cleanup-done", "close"]
        finally:
            await retriever.aclose()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_construction_loop_and_context_ownership():
    owner = asyncio.new_event_loop()
    other = asyncio.new_event_loop()

    async def construct():
        return GraphitiRetriever(GraphitiCoreSearcher(LoopRecordingSearcher()))

    retriever = owner.run_until_complete(construct())
    try:
        with pytest.raises(RuntimeError, match="aretrieve"):
            retriever.retrieve("q", bubbles=["news"])
        with pytest.raises(RuntimeError):
            retriever.__enter__()
        with pytest.raises(RuntimeError, match="loop"):
            other.run_until_complete(retriever.aretrieve("q", bubbles=["news"]))
        with pytest.raises(RuntimeError, match="loop"):
            other.run_until_complete(retriever.__aenter__())
        with pytest.raises(RuntimeError, match="loop"):
            other.run_until_complete(retriever.aclose())
        owner.run_until_complete(retriever.aretrieve("q", bubbles=["news"]))
    finally:
        owner.run_until_complete(retriever.aclose())
        other.close()
        owner.close()


def test_sync_factory_constructs_on_runner_loop(monkeypatch):
    recorded = []

    def construct(cls, settings, **kwargs):
        recorded.append(asyncio.get_running_loop())
        return GraphitiCoreSearcher(LoopRecordingSearcher())

    monkeypatch.setattr(GraphitiCoreSearcher, "from_settings", classmethod(construct))
    retriever = GraphitiRetriever.from_settings(None)
    try:
        retriever.retrieve("q", bubbles=["news"])
        assert recorded == retriever.searcher.graphiti.loops
        with pytest.raises(RuntimeError, match="retrieve"):
            asyncio.run(retriever.__aenter__())
    finally:
        retriever.close()


@pytest.mark.parametrize("cancel_caller", [False, True])
def test_async_search_task_ownership(cancel_caller):
    async def scenario():
        started, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Searcher(LoopRecordingSearcher):
            async def search(self, *args, **kwargs):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        searcher = Searcher()
        retriever = GraphitiRetriever(searcher)
        continued = asyncio.Event()

        async def handler():
            try:
                await retriever.aretrieve("q", bubbles=["news"])
            except (asyncio.CancelledError, RuntimeError) as exc:
                assert isinstance(exc, asyncio.CancelledError) == cancel_caller
                continued.set()
                await release.wait()

        caller = asyncio.create_task(handler())
        try:
            await asyncio.wait_for(started.wait(), 10)
            if cancel_caller:
                caller.cancel()
                await asyncio.wait_for(cancelled.wait(), 10)
            await asyncio.wait_for(retriever.aclose(), 10)
            await asyncio.wait_for(continued.wait(), 10)
            assert not caller.done()
            assert searcher.closed
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), 10)
            await asyncio.wait_for(retriever.aclose(), 10)

    asyncio.run(scenario())


def test_async_drain_failure_can_retry(monkeypatch):
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    monkeypatch.setattr(_SyncLoopRunner, "_DRAIN_TIMEOUT", 0.01)

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class Searcher(LoopRecordingSearcher):
            closes = 0

            async def search(self, *args, **kwargs):
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await release.wait()
                return []

            async def close(self):
                self.closes += 1

        searcher = Searcher()
        r = GraphitiRetriever(searcher)
        task = asyncio.create_task(r.aretrieve("q", bubbles=["news"]))
        try:
            await asyncio.wait_for(started.wait(), 10)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(r.aclose(), 10)
            with pytest.raises(RuntimeError, match="closed"):
                await r.aretrieve("q", bubbles=["news"])
            assert searcher.closes == 0
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 10)
            await asyncio.wait_for(r.aclose(), 10)
        assert searcher.closes == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("sync", [False, True])
def test_close_failure_can_retry(sync):
    class Searcher(LoopRecordingSearcher):
        attempts = 0

        async def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise ValueError("close failed")
            await super().close()

    searcher = Searcher()
    r = GraphitiRetriever(searcher)
    if sync:
        try:
            with pytest.raises(ValueError, match="close failed"):
                r.close()
        finally:
            r.close()
    else:

        async def scenario():
            try:
                with pytest.raises(ValueError, match="close failed"):
                    await asyncio.wait_for(r.aclose(), 10)
            finally:
                await asyncio.wait_for(r.aclose(), 10)

        asyncio.run(scenario())
    assert searcher.closed and searcher.attempts == 2


def test_interrupted_factory_closes_registered_searcher(monkeypatch):
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    searcher = LoopRecordingSearcher()
    monkeypatch.setattr(
        GraphitiCoreSearcher,
        "from_settings",
        classmethod(lambda cls, *a, **kw: searcher),
    )
    original = _SyncLoopRunner.run

    def interrupted(self, factory):
        original(self, factory)
        raise KeyboardInterrupt

    monkeypatch.setattr(_SyncLoopRunner, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        GraphitiRetriever.from_settings(None)
    assert searcher.closed
    assert not _runner_threads()


def test_with_rejects_running_loop():
    async def scenario():
        r = GraphitiRetriever(LoopRecordingSearcher())
        try:
            with pytest.raises(RuntimeError, match="async with"), r:
                pass
        finally:
            await asyncio.wait_for(r.aclose(), 10)

    asyncio.run(scenario())


def test_concurrent_async_close_waits():
    async def scenario():
        started, release, second_entered = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        class Searcher(LoopRecordingSearcher):
            async def close(self):
                started.set()
                await release.wait()
                await super().close()

        searcher = Searcher()
        r = GraphitiRetriever(searcher)
        first = asyncio.create_task(r.aclose())

        async def second_close():
            second_entered.set()
            await r.aclose()

        second = None
        try:
            await asyncio.wait_for(started.wait(), 10)
            second = asyncio.create_task(second_close())
            await asyncio.wait_for(second_entered.wait(), 10)
            assert not second.done()
        finally:
            release.set()
            await asyncio.wait_for(
                asyncio.gather(first, *([second] if second else [])), 10
            )
        assert searcher.closed

    asyncio.run(scenario())


def test_dead_runner_rejects_run():
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    runner = _SyncLoopRunner()
    runner.run(lambda: asyncio.sleep(0))
    loop, thread = runner._loop, runner._thread
    try:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=10)
        assert not thread.is_alive()
        with pytest.raises(RuntimeError, match="thread died"):
            runner.run(lambda: asyncio.sleep(0))
    finally:
        if not loop.is_closed():
            loop.close()


def test_concurrent_sync_close_waits():
    started, release, entered = threading.Event(), threading.Event(), threading.Event()
    returned = threading.Event()

    class Searcher(LoopRecordingSearcher):
        async def close(self):
            started.set()
            assert await asyncio.to_thread(release.wait, 10)
            await super().close()

    searcher = Searcher()
    r = GraphitiRetriever(searcher)
    errors = []

    def close(second=False):
        if second:
            entered.set()
        try:
            r.close()
            if second:
                returned.set()
        except BaseException as exc:  # noqa: BLE001 - deliberate catch-alls in loop-liveness tests
            errors.append(exc)

    first = threading.Thread(target=close)
    second = threading.Thread(target=close, args=(True,))
    try:
        first.start()
        assert started.wait(10)
        second.start()
        assert entered.wait(10)
        assert not returned.wait(0.05)
    finally:
        release.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
        r.close()
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert returned.is_set()
    assert searcher.closed


@pytest.mark.parametrize("sync_first", [False, True])
def test_unused_mixed_close_claims_one_owner(sync_first):
    started, release = threading.Event(), threading.Event()

    class Searcher(LoopRecordingSearcher):
        closes = 0

        async def close(self):
            self.closes += 1
            started.set()
            assert await asyncio.to_thread(release.wait, 10)

    searcher = Searcher()
    r = GraphitiRetriever(searcher)
    errors = []

    def first_close():
        try:
            if sync_first:
                r.close()
            else:
                asyncio.run(r.aclose())
        except BaseException as exc:  # noqa: BLE001 - deliberate catch-alls in loop-liveness tests
            errors.append(exc)

    first = threading.Thread(target=first_close)
    try:
        first.start()
        assert started.wait(10)
        with pytest.raises(RuntimeError, match="close"):
            if sync_first:
                asyncio.run(r.aclose())
            else:
                r.close()
    finally:
        release.set()
        first.join(timeout=10)
    assert not first.is_alive()
    assert not errors
    assert searcher.closes == 1


def test_taskgroup_reports_search_lost_to_close():
    async def scenario():
        started = asyncio.Event()

        class Searcher(LoopRecordingSearcher):
            async def search(self, *args, **kwargs):
                started.set()
                await asyncio.Event().wait()

        r = GraphitiRetriever(Searcher())
        try:
            with pytest.raises(ExceptionGroup) as caught:
                async with asyncio.TaskGroup() as group:
                    group.create_task(r.aretrieve("q", bubbles=["news"]))
                    await asyncio.wait_for(started.wait(), 10)
                    await asyncio.wait_for(r.aclose(), 10)
            assert len(caught.value.exceptions) == 1
            assert (
                str(caught.value.exceptions[0])
                == "GraphitiRetriever closed during retrieve"
            )
        finally:
            await asyncio.wait_for(r.aclose(), 10)

    asyncio.run(scenario())


def test_empty_runner_stop_does_not_start_thread():
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    runner = _SyncLoopRunner()
    runner.stop()
    assert runner._thread is None


def test_stop_retry_after_join_timeout_does_not_resubmit(monkeypatch):
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    runner = _SyncLoopRunner()
    runner.run(lambda: asyncio.sleep(0))
    thread = runner._thread
    real_join, real_alive = thread.join, thread.is_alive
    try:
        with monkeypatch.context() as patch:
            patch.setattr(thread, "join", lambda timeout: None)
            patch.setattr(thread, "is_alive", lambda: True)
            with pytest.raises(RuntimeError, match="did not stop"):
                runner.stop()
        real_join(10)
        assert not real_alive()
        shutdown = runner._shutdown_future
        runner.stop()
        assert runner._shutdown_future is shutdown
    finally:
        runner.stop()


def test_sync_close_waiter_keeps_failed_attempt_outcome(monkeypatch):
    from omnistream.retrieval.graphiti_mode import _SyncLoopRunner

    runner = _SyncLoopRunner()
    started, release, waiting = threading.Event(), threading.Event(), threading.Event()
    errors = []
    attempts = 0

    async def closer():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            assert await asyncio.to_thread(release.wait, 10)
            raise ValueError("first attempt failed")

    def stop():
        try:
            runner.stop(closer)
        except BaseException as exc:  # noqa: BLE001 - deliberate catch-alls in loop-liveness tests
            errors.append(exc)

    first = threading.Thread(target=stop)
    second = threading.Thread(target=stop)
    try:
        first.start()
        assert started.wait(10)
        done = runner._close_done
        original_wait = done.wait

        def wait(timeout):
            waiting.set()
            result = original_wait(timeout)
            # Retry before this waiter examines the old attempt's outcome.
            runner.stop(closer)
            return result

        monkeypatch.setattr(done, "wait", wait)
        second.start()
        assert waiting.wait(10)
    finally:
        release.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
        runner.stop(closer)
    assert not first.is_alive() and not second.is_alive()
    assert len(errors) == 2
    assert all(
        isinstance(exc, ValueError) and str(exc) == "first attempt failed"
        for exc in errors
    )
    assert attempts == 2


def test_abandoned_async_close_consumes_late_failure():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        class Searcher(LoopRecordingSearcher):
            attempts = 0

            async def close(self):
                self.attempts += 1
                if self.attempts == 1:
                    started.set()
                    await release.wait()
                    raise ValueError("late close failure")
                await super().close()

        r = GraphitiRetriever(Searcher())
        caller = asyncio.create_task(r.aclose())
        try:
            await asyncio.wait_for(started.wait(), 10)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(caller, 10)
            task = r._async_close_task
            release.set()
            await asyncio.wait_for(asyncio.wait({task}), 10)
            # The callback has retrieved the failure without discarding it.
            await asyncio.sleep(0)
            assert not task._log_traceback
            assert isinstance(task.exception(), ValueError)
            await asyncio.wait_for(r.aclose(), 10)
            assert r.searcher.attempts == 2 and r.searcher.closed
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), 10)
            await asyncio.wait_for(r.aclose(), 10)

    asyncio.run(scenario())


def test_sync_coroutine_cancelled_error_is_not_shutdown():
    import concurrent.futures

    class Searcher(LoopRecordingSearcher):
        async def search(self, *args, **kwargs):
            raise asyncio.CancelledError("self cancellation")

    r = GraphitiRetriever(Searcher())
    try:
        with pytest.raises(concurrent.futures.CancelledError):
            r.retrieve("q", bubbles=["news"])
    finally:
        r.close()
