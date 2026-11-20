"""Run tracing for the chat UI (spec 10.1, 10.4).

Three pieces:

* ``RunRecorder`` records each step when it starts and when it finishes. Only
  finished steps are stored (``run_steps``); running steps live in memory and
  are published on the SSE bus.
* ``RunBus`` fans events out to SSE subscribers. Publishing is safe from any
  thread, because the own pipeline runs its synchronous parts in worker threads.
* ``PipelineTrace`` builds proxies around the existing pipeline objects (router,
  retrieval dispatcher, retriever, sync LLM client). ``answer_question`` (qa.py)
  is called unchanged: the proxies observe its calls and record steps. Each
  subagent step is tied to its own asyncio task, so it is recorded as it
  finishes, not when the orchestrator returns.

Normal records route -> retrieve -> answer. Agentic records route -> subagent
(one per bubble, with its retrieve calls nested) -> join -> answer. The join
and answer boundaries are observed at the first chat call of answer generation.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from omnistream.agents.subagent import SubagentFindings, format_error
from omnistream.db.tables import RunStepRow
from omnistream.retrieval.fusion import DEFAULT_RRF_K
from omnistream.retrieval.models import RetrievalResult, ScoredFact

FINISH_STATUSES = ("ok", "error", "cancelled")


def utc(value: datetime) -> datetime:
    """Normalise to aware UTC with microseconds, the form SQLite returns."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=value.microsecond)


def jsonable(value: Any) -> Any:
    """Plain JSON types only, so live payloads equal replayed ones."""
    return json.loads(json.dumps(value, default=str))


def step_payload(row: RunStepRow) -> dict[str, Any]:
    """The one serialisation of a step, used for SSE, storage and replay alike."""
    return {
        "id": row.id,
        "run_id": row.run_id,
        "seq": row.seq,
        "parent_step_id": row.parent_step_id,
        "kind": row.kind,
        "bubble": row.bubble,
        "started_at": utc(row.started_at).isoformat(),
        "duration_ms": None if row.status == "running" else row.duration_ms,
        "status": row.status,
        "summary": row.summary or {},
        "node_ids": list(row.node_ids or []),
        "edge_ids": list(row.edge_ids or []),
        "citations": list(row.citations or []),
        "error": row.error,
    }


def run_payload(row: Any) -> dict[str, Any]:
    """Run contract (spec 12), plus the question the trace view needs."""
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "mode": row.mode,
        "question": row.question,
        "status": row.status,
        "answer": row.answer,
        "error": row.error,
        "started_at": utc(row.started_at).isoformat(),
        "finished_at": utc(row.finished_at).isoformat() if row.finished_at else None,
    }


class RunBus:
    """Per-run fan-out of (event, data) pairs to SSE subscribers."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        """Thread-safe. Always hops through the loop, so events keep their order."""

        def deliver() -> None:
            for queue in list(self._subscribers.get(run_id, ())):
                queue.put_nowait((event, data))

        try:
            self._loop.call_soon_threadsafe(deliver)
        except RuntimeError:  # loop already closed during shutdown
            pass


@dataclass(eq=False)
class OpenStep:
    id: str
    seq: int
    kind: str
    run_id: str
    parent_id: str | None
    bubble: str | None
    started_at: datetime
    started_mono: float
    summary: dict[str, Any] = field(default_factory=dict)


class RunRecorder:
    """Writes steps as they finish and publishes start and finish events."""

    def __init__(
        self,
        save_step: Callable[[RunStepRow], None],
        bus: RunBus,
        run_id: str,
    ) -> None:
        self._save = save_step
        self._bus = bus
        self.run_id = run_id
        self._lock = threading.RLock()
        self._seq = 0
        self._open: dict[str, OpenStep] = {}
        self._closed = False

    def start(
        self,
        kind: str,
        *,
        parent: OpenStep | None = None,
        bubble: str | None = None,
        summary: dict[str, Any] | None = None,
        started_mono: float | None = None,
    ) -> OpenStep | None:
        """Open a step. ``started_mono`` backdates it (used for the join step)."""
        with self._lock:
            if self._closed:
                return None
            self._seq += 1
            now_mono = time.monotonic()
            mono = now_mono if started_mono is None else started_mono
            step = OpenStep(
                id=uuid.uuid4().hex,
                seq=self._seq,
                kind=kind,
                run_id=self.run_id,
                parent_id=parent.id if parent else None,
                bubble=bubble,
                started_at=datetime.now(UTC) - timedelta(seconds=now_mono - mono),
                started_mono=mono,
                summary=dict(summary or {}),
            )
            self._open[step.id] = step
            self._bus.publish(
                self.run_id, "step", step_payload(self._row(step, "running"))
            )
            return step

    def finish(
        self,
        step: OpenStep | None,
        status: str,
        *,
        summary: dict[str, Any] | None = None,
        node_ids: list[str] | tuple[str, ...] = (),
        edge_ids: list[str] | tuple[str, ...] = (),
        citations: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        error: str | None = None,
    ) -> None:
        """Persist and publish a finished step. Idempotent; no-op after close."""
        if status not in FINISH_STATUSES:
            raise ValueError(f"invalid finish status: {status!r}")
        if step is None:
            return
        with self._lock:
            if self._closed or self._open.pop(step.id, None) is None:
                return
            step.summary.update(summary or {})
            row = self._row(
                step,
                status,
                duration_ms=round((time.monotonic() - step.started_mono) * 1000, 3),
                node_ids=list(dict.fromkeys(node_ids)),
                edge_ids=list(dict.fromkeys(edge_ids)),
                citations=list(citations),
                error=error[:1000] if error else None,
            )
            self._save(row)
            self._bus.publish(self.run_id, "step", step_payload(row))

    def close(self, status: str, error: str | None = None) -> None:
        """Finish every open step with ``status`` and refuse new steps."""
        with self._lock:
            for step in sorted(self._open.values(), key=lambda s: s.seq):
                self.finish(step, status, error=error if status == "error" else None)
            self._closed = True

    def live_payloads(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                step_payload(self._row(step, "running"))
                for step in sorted(self._open.values(), key=lambda s: s.seq)
            ]

    def _row(
        self,
        step: OpenStep,
        status: str,
        *,
        duration_ms: float = 0.0,
        node_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        citations: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> RunStepRow:
        return RunStepRow(
            id=step.id,
            run_id=step.run_id,
            seq=step.seq,
            parent_step_id=step.parent_id,
            kind=step.kind,
            bubble=step.bubble,
            started_at=step.started_at,
            duration_ms=duration_ms,
            status=status,
            summary=jsonable(step.summary),
            node_ids=node_ids or [],
            edge_ids=edge_ids or [],
            citations=jsonable(citations or []),
            error=error,
        )


# ---------------------------------------------------------------- summaries


# The own pipeline fuses three rankings with RRF (retrieval/own_algorithm/fact_fusion.py).
# A fact ranked first by all three signals scores 3 / (k + 1); that is the ceiling used to
# turn a raw score into the 0..1 relevance that the trace UI shows as Low / Medium / High.
RRF_CEILING = 3 / (DEFAULT_RRF_K + 1)
SOURCE_TEXT_LIMIT = 600


def relevance_of(scored: Iterable[ScoredFact]) -> float | None:
    """0..1 relevance of the best fact, or None when there is no fact."""
    scores = [float(entry.score) for entry in scored]
    if not scores:
        return None
    return min(1.0, max(0.0, max(scores) / RRF_CEILING))


def source_text_of(texts: Iterable[str]) -> str:
    """The text a step read, whitespace-normalised and capped for storage and display."""
    joined = " ".join(" ".join(text.split()) for text in texts if text and text.strip())
    if len(joined) <= SOURCE_TEXT_LIMIT:
        return joined
    return joined[: SOURCE_TEXT_LIMIT - 1].rstrip() + "…"


def retrieval_digest(
    result: RetrievalResult,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Counts, scores and the graph ids a retrieval touched."""
    facts = list(result.facts)
    node_ids = [entity.id for entity in result.seeds]
    for entry in facts:
        node_ids += [entry.fact.subject_id, entry.fact.object_id]
    summary: dict[str, Any] = {
        "count": len(facts) + len(result.chunks),
        "seeds": len(result.seeds),
        "facts": len(facts),
        "chunks": len(result.chunks),
        "top_facts": [
            {"id": e.fact.id, "score": round(float(e.score), 4), "bubble": e.fact.bubble}
            for e in facts[:10]
        ],
        "no_relevant_sources": not facts and not result.chunks,
        "source_text": source_text_of(
            [e.fact.text for e in facts[:3]] + [c.text for c in result.chunks[:3]]
        ),
    }
    relevance = relevance_of(facts)
    if relevance is not None:
        summary["relevance"] = relevance
    return summary, node_ids, [e.fact.id for e in facts]


def findings_digest(
    findings: SubagentFindings,
) -> tuple[dict[str, Any], list[str], list[str]]:
    node_ids = [entity.id for entity in findings.seeds] + list(findings.global_entity_ids)
    for fact in findings.facts:
        node_ids += [fact.subject_id, fact.object_id]
    summary: dict[str, Any] = {
        "bubble": findings.bubble,
        "count": len(findings.facts) + len(findings.chunks),
        "tool_calls": findings.tool_calls_used,
        "stopped_reason": findings.stopped_reason,
        "facts": len(findings.facts),
        "chunks": len(findings.chunks),
        "source_text": source_text_of(
            [f.text for f in findings.facts[:3]] + [c.text for c in findings.chunks[:3]]
        ),
    }
    relevance = relevance_of(findings.scored_facts)
    if relevance is not None:
        summary["relevance"] = relevance
    return summary, node_ids, [fact.id for fact in findings.facts]


def record_retrieval_children(rec: RunRecorder, parent: OpenStep | None, result: RetrievalResult) -> None:
    """Seed and score steps under a finished retrieve step (spec 10.1).

    Both are measured inside the retrieval call, so they are recorded as zero-length
    children at the moment the retrieval returned. They carry the counts the trace reads.
    """
    if parent is None:
        return
    seed_count = len(result.seeds)
    seed = rec.start("seed", parent=parent, summary={"count": seed_count})
    rec.finish(seed, "ok", summary={"count": seed_count}, node_ids=[e.id for e in result.seeds])
    score_summary: dict[str, Any] = {"count": len(result.facts)}
    relevance = relevance_of(result.facts)
    if relevance is not None:
        score_summary["relevance"] = relevance
    score = rec.start("score", parent=parent)
    rec.finish(
        score,
        "ok",
        summary=score_summary,
        edge_ids=[e.fact.id for e in result.facts],
    )


def joined_groups(findings: list[SubagentFindings]) -> list[tuple[set[str], set[str]]]:
    """Mirror of the join rule in agents/orchestrator.py: bubbles that share a global entity.

    Duplicated here so the join step can be recorded when it happens. A test
    checks it against ``run_subagents`` output.
    """
    groups: list[tuple[set[str], set[str]]] = []
    for finding in findings:
        linked = {finding.bubble}
        entities = set(finding.global_entity_ids)
        remaining = []
        for group, ids in groups:
            if entities & ids:
                linked |= group
                entities |= ids
            else:
                remaining.append((group, ids))
        groups = remaining + [(linked, entities)]
    return [(group, ids) for group, ids in groups if len(group) > 1]


def _finish_exception(recorder: RunRecorder, step: OpenStep | None, exc: BaseException) -> None:
    if isinstance(exc, asyncio.CancelledError):
        recorder.finish(step, "cancelled")
    elif isinstance(exc, Exception):
        recorder.finish(step, "error", error=format_error(exc))
    else:
        recorder.finish(step, "cancelled")


# ------------------------------------------------------------------ proxies


class _Passthrough:
    """Forward every attribute a proxy does not override."""

    _inner: Any

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@dataclass(eq=False)
class PipelineTrace:
    """Per-run state shared by the proxies."""

    recorder: RunRecorder
    agentic: bool
    route_step: OpenStep | None = None
    _subagents: dict[Any, OpenStep] = field(default_factory=dict)
    _findings: list[SubagentFindings] = field(default_factory=list)
    _last_subagent_done: float | None = None
    _answer_opened: bool = False
    answer_step: OpenStep | None = None
    _lock: Any = field(default_factory=threading.RLock)

    # Factories used by the run executor.
    def router(self, inner: Any) -> _RouterProxy:
        return _RouterProxy(inner, self)

    def dispatcher(self, inner: Any) -> _DispatcherProxy:
        """Normal mode: one synchronous retrieval, observed as one step."""
        return _DispatcherProxy(inner, self)

    def agentic_dispatcher(self, inner: Any) -> _DispatcherProxy:
        """Agentic mode: the own retriever handed to subagents is wrapped asynchronously."""
        retrievers = dict(inner.retrievers)
        if "own" in retrievers:
            retrievers["own"] = _AsyncRetrieverProxy(retrievers["own"], self)
        return _DispatcherProxy(inner, self, retrievers=retrievers)

    def llm(self, inner: Any) -> _ChatProxy:
        return _ChatProxy(inner, self)

    # Internal hooks.
    def subagent_step(self, task: Any, bubble: str | None) -> OpenStep | None:
        with self._lock:
            step = self._subagents.get(task)
            if step is None:
                step = self.recorder.start("subagent", parent=self.route_step, bubble=bubble)
                if step is None:
                    return None
                self._subagents[task] = step
                task.add_done_callback(lambda done: self._subagent_done(done, step))
            return step

    def _subagent_done(self, task: Any, step: OpenStep) -> None:
        status, error, summary, node_ids, edge_ids = "ok", None, {}, [], []
        if task.cancelled():
            status = "cancelled"
        elif (exc := task.exception()) is not None:
            status, error = "error", format_error(exc)
        else:
            findings: SubagentFindings = task.result()
            summary, node_ids, edge_ids = findings_digest(findings)
            if findings.stopped_reason in {"error", "timeout"}:
                status = "error"
                error = findings.error or "The bubble did not finish in time"
            with self._lock:
                self._findings.append(findings)
        with self._lock:
            self._last_subagent_done = time.monotonic()
        self.recorder.finish(
            step, status, summary=summary, node_ids=node_ids, edge_ids=edge_ids, error=error
        )

    def open_answer(self) -> None:
        """Start answer generation. Called once, at the first chat call (agentic) or after retrieval (normal)."""
        with self._lock:
            if self._answer_opened:
                return
            self._answer_opened = True
            parent: OpenStep | None = self.route_step
            if self.agentic:
                join_started = self._last_subagent_done or (
                    self.route_step.started_mono if self.route_step else None
                )
                join = self.recorder.start(
                    "join", parent=self.route_step, started_mono=join_started
                )
                groups = joined_groups(self._findings)
                self.recorder.finish(
                    join,
                    "ok",
                    summary={
                        "bubbles": sorted({f.bubble for f in self._findings}),
                        "failed_bubbles": sorted(
                            f.bubble
                            for f in self._findings
                            if f.stopped_reason in {"error", "timeout"}
                        ),
                        "joined_groups": [sorted(group) for group, _ in groups],
                        "count": len({entity for _, ids in groups for entity in ids}),
                    },
                    node_ids=[entity for _, ids in groups for entity in sorted(ids)],
                )
                parent = join
            self.answer_step = self.recorder.start("answer", parent=parent)

    def record_untraced_subagents(self, findings: tuple[SubagentFindings, ...]) -> None:
        """A subagent that never retrieved has no task hook; record it after the orchestrator returns."""
        with self._lock:
            seen = {step.bubble for step in self._subagents.values()}
        for finding in findings:
            if finding.bubble in seen:
                continue
            failed = finding.stopped_reason in {"error", "timeout"}
            step = self.recorder.start("subagent", parent=self.route_step, bubble=finding.bubble)
            summary, node_ids, edge_ids = findings_digest(finding)
            self.recorder.finish(
                step,
                "error" if failed else "ok",
                summary=summary,
                node_ids=node_ids,
                edge_ids=edge_ids,
                error=(finding.error or "did not finish") if failed else None,
            )


class _RouterProxy(_Passthrough):
    def __init__(self, inner: Any, trace: PipelineTrace) -> None:
        self._inner, self._trace = inner, trace

    def route(self, question: str, **kwargs: Any) -> Any:
        rec = self._trace.recorder
        step = rec.start("route", summary={"question_chars": len(question)})
        self._trace.route_step = step
        try:
            decision = self._inner.route(question, **kwargs)
        except BaseException as exc:
            _finish_exception(rec, step, exc)
            raise
        scope = decision.time_scope
        rec.finish(
            step,
            "ok",
            summary={
                "strategy": decision.strategy,
                "bubbles": list(decision.bubbles),
                "rationale": decision.rationale,
                "time_scope": None
                if scope is None
                else {
                    "start": scope.start.isoformat() if scope.start else None,
                    "end": scope.end.isoformat() if scope.end else None,
                },
            },
        )
        return decision


class _DispatcherProxy(_Passthrough):
    def __init__(
        self, inner: Any, trace: PipelineTrace, retrievers: dict | None = None
    ) -> None:
        self._inner, self._trace = inner, trace
        self.retrievers = retrievers if retrievers is not None else inner.retrievers

    @property
    def default_mode(self) -> str:
        return self._inner.default_mode

    def retrieve(self, question: str, **kwargs: Any) -> RetrievalResult:
        rec = self._trace.recorder
        bubbles = list(kwargs.get("bubbles", ()))
        step = rec.start(
            "retrieve",
            parent=self._trace.route_step,
            bubble=bubbles[0] if len(bubbles) == 1 else None,
            summary={"bubbles": bubbles},
        )
        try:
            result = self._inner.retrieve(question, **kwargs)
        except BaseException as exc:
            _finish_exception(rec, step, exc)
            raise
        summary, node_ids, edge_ids = retrieval_digest(result)
        rec.finish(step, "ok", summary=summary, node_ids=node_ids, edge_ids=edge_ids)
        record_retrieval_children(rec, step, result)
        if not self._trace.agentic:
            # Normal: answer generation starts as soon as the single pass has finished.
            self._trace._answer_opened = True
            self._trace.answer_step = rec.start("answer", parent=step)
        return result


class _AsyncRetrieverProxy(_Passthrough):
    """Retriever seen by subagents. Its retrieve call runs inside the subagent's own task."""

    def __init__(self, inner: Any, trace: PipelineTrace) -> None:
        self._inner, self._trace = inner, trace

    async def retrieve(self, question: str, **kwargs: Any) -> RetrievalResult:
        rec = self._trace.recorder
        bubbles = list(kwargs.get("bubbles", ()))
        bubble = bubbles[0] if len(bubbles) == 1 else None
        task = asyncio.current_task()
        parent = self._trace.subagent_step(task, bubble) if task is not None else None
        step = rec.start("retrieve", parent=parent, bubble=bubble, summary={"bubbles": bubbles})
        try:
            result = await asyncio.to_thread(self._inner.retrieve, question, **kwargs)
        except BaseException as exc:
            _finish_exception(rec, step, exc)
            raise
        summary, node_ids, edge_ids = retrieval_digest(result)
        rec.finish(step, "ok", summary=summary, node_ids=node_ids, edge_ids=edge_ids)
        record_retrieval_children(rec, step, result)
        return result


class _ChatProxy(_Passthrough):
    """Sync LLM client seen by answer_question. The first ``chat`` call starts answer generation."""

    def __init__(self, inner: Any, trace: PipelineTrace) -> None:
        self._inner, self._trace = inner, trace

    def chat(self, messages: Any, **kwargs: Any) -> Any:
        self._trace.open_answer()
        return self._inner.chat(messages, **kwargs)
