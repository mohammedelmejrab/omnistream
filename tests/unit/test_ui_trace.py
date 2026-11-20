"""Step recording around the own pipeline and the orchestrator (spec 10.1, 10.4, 14 unit)."""

from __future__ import annotations

import asyncio
import threading

import pytest

from omnistream import qa
from omnistream.agents import orchestrator
from omnistream.agents.subagent import SubagentFindings
from omnistream.api.ui_trace import PipelineTrace, RunBus, RunRecorder, joined_groups
from omnistream.config import Settings
from tests.unit.ui_support import (
    FakeAsyncLLM,
    FakeChat,
    FakeDispatcher,
    FakeGraph,
    FakeRetriever,
    FakeRouter,
)


def _recorder(loop) -> tuple[RunRecorder, list, RunBus]:
    saved: list = []
    bus = RunBus(loop)
    return RunRecorder(saved.append, bus, "run-1"), saved, bus


async def _ask(trace: PipelineTrace, dispatcher, *, router, subagents: bool, pins=("news",), async_llm=None, llm=None):
    return await qa.answer_question(
        "Who leads Acme?",
        router=trace.router(router),
        dispatcher=trace.agentic_dispatcher(dispatcher) if subagents else trace.dispatcher(dispatcher),
        llm=trace.llm(llm or FakeChat()),
        async_llm=async_llm or FakeAsyncLLM(),
        graph_store=FakeGraph(),
        item_store=object(),
        settings=Settings(_env_file=None),
        mode="own",
        pins=pins,
        subagents=subagents,
    )


# ------------------------------------------------------------ the recorder


async def test_steps_are_stored_when_they_finish_and_keep_start_order_and_parents():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    route = rec.start("route")
    retrieve = rec.start("retrieve", parent=route)
    rec.finish(retrieve, "ok", node_ids=["e1", "e1", "e2"], edge_ids=["f1"])
    rec.finish(route, "ok")

    assert [row.kind for row in saved] == ["retrieve", "route"]  # finish order
    assert [row.seq for row in saved] == [2, 1]  # start order
    assert saved[0].parent_step_id == route.id
    assert saved[0].node_ids == ["e1", "e2"]  # de-duplicated, order kept
    assert saved[0].duration_ms >= 0


async def test_running_steps_are_published_but_never_stored():
    loop = asyncio.get_running_loop()
    rec, saved, bus = _recorder(loop)
    queue = bus.subscribe("run-1")
    step = rec.start("route")
    await asyncio.sleep(0)
    event, data = queue.get_nowait()
    assert (event, data["status"], data["duration_ms"]) == ("step", "running", None)
    assert saved == []
    assert [p["id"] for p in rec.live_payloads()] == [step.id]


async def test_events_are_delivered_in_order_start_then_finish():
    loop = asyncio.get_running_loop()
    rec, _, bus = _recorder(loop)
    queue = bus.subscribe("run-1")
    step = rec.start("retrieve")
    rec.finish(step, "error", error="index unavailable")
    await asyncio.sleep(0)
    statuses = [queue.get_nowait()[1]["status"] for _ in range(2)]
    assert statuses == ["running", "error"]
    bus.unsubscribe("run-1", queue)


async def test_errors_are_kept_with_text_and_double_finish_is_ignored():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    step = rec.start("retrieve")
    rec.finish(step, "error", error="ValueError: bad seed")
    rec.finish(step, "ok")  # ignored: already finished
    assert len(saved) == 1
    assert (saved[0].status, saved[0].error) == ("error", "ValueError: bad seed")


async def test_close_marks_open_steps_cancelled_and_refuses_later_steps():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    route = rec.start("route")
    rec.finish(route, "ok")
    rec.start("retrieve")
    rec.close("cancelled")
    assert [(r.kind, r.status) for r in saved] == [("route", "ok"), ("retrieve", "cancelled")]
    assert rec.start("answer") is None


async def test_invalid_finish_status_is_rejected():
    rec, _, _ = _recorder(asyncio.get_running_loop())
    with pytest.raises(ValueError):
        rec.finish(rec.start("route"), "running")


# -------------------------------------------------------- normal and agentic


async def test_normal_mode_calls_the_own_pipeline_once_and_records_route_retrieve_answer(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the orchestrator must not run in Normal mode")

    monkeypatch.setattr(qa, "run_subagents", forbidden)
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=False)
    dispatcher = FakeDispatcher(FakeRetriever())

    result = await _ask(trace, dispatcher, router=FakeRouter("multi_hop"), subagents=False)
    rec.finish(trace.answer_step, "ok", citations=[])
    rec.close("ok")

    assert dispatcher.calls == 1
    assert result.answer.text
    route, retrieve, answer = (r for r in saved if r.kind in ("route", "retrieve", "answer"))
    assert [r.kind for r in saved if r.kind in ("route", "retrieve", "answer")] == ["route", "retrieve", "answer"]
    assert route.summary["bubbles"] == ["news"]
    assert retrieve.parent_step_id == route.id
    assert answer.parent_step_id == retrieve.id
    assert retrieve.summary["facts"] == 1
    assert set(retrieve.node_ids) >= {"e-alice", "e-acme"}
    assert retrieve.edge_ids == ["f-news"]
    assert retrieve.summary["no_relevant_sources"] is False


async def test_agentic_mode_calls_the_orchestrator_and_records_nested_subagent_steps(monkeypatch):
    calls: list = []
    real = qa.run_subagents

    async def spy(*args, **kwargs):
        calls.append(list(kwargs["bubbles"]))
        return await real(*args, **kwargs)

    monkeypatch.setattr(qa, "run_subagents", spy)
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=True)

    result = await _ask(
        trace, FakeDispatcher(FakeRetriever()), router=FakeRouter("multi_hop"),
        subagents=True, pins=("news", "finance"),
    )
    trace.record_untraced_subagents(result.multi_hop.findings)
    rec.finish(trace.answer_step, "ok")
    rec.close("ok")

    assert calls == [["news", "finance"]]
    subagents = [r for r in saved if r.kind == "subagent"]
    assert sorted(r.bubble for r in subagents) == ["finance", "news"]
    assert all(r.status == "ok" for r in subagents)
    retrieves = [r for r in saved if r.kind == "retrieve"]
    assert {r.parent_step_id for r in retrieves} == {r.id for r in subagents}
    (route,) = [r for r in saved if r.kind == "route"]
    assert all(r.parent_step_id == route.id for r in subagents)
    (join,) = [r for r in saved if r.kind == "join"]
    assert join.parent_step_id == route.id
    assert sorted(join.summary["bubbles"]) == ["finance", "news"]
    (answer,) = [r for r in saved if r.kind == "answer"]
    assert answer.parent_step_id == join.id


async def test_a_failing_subagent_is_an_error_step_and_the_answer_still_forms():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=True)

    result = await _ask(
        trace, FakeDispatcher(FakeRetriever()), router=FakeRouter("multi_hop"),
        subagents=True, pins=("news",), async_llm=FakeAsyncLLM(fail=True),
    )
    trace.record_untraced_subagents(result.multi_hop.findings)
    rec.finish(trace.answer_step, "ok")
    rec.close("ok")

    (subagent,) = [r for r in saved if r.kind == "subagent"]
    assert subagent.status == "error"
    assert "provider exploded" in subagent.error
    assert result.answer.text  # the other evidence still produces an answer


async def test_a_subagent_that_never_searches_is_recorded_after_the_orchestrator_returns():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=True)
    result = await _ask(
        trace, FakeDispatcher(FakeRetriever()), router=FakeRouter("multi_hop"),
        subagents=True, pins=("news",), async_llm=FakeAsyncLLM(silent=True),
    )
    trace.record_untraced_subagents(result.multi_hop.findings)
    subagents = [r for r in saved if r.kind == "subagent"]
    assert [(r.bubble, r.status) for r in subagents] == [("news", "ok")]


async def test_cancel_keeps_finished_steps_and_late_thread_results_are_dropped():
    loop = asyncio.get_running_loop()
    rec, saved, _ = _recorder(loop)
    trace = PipelineTrace(rec, agentic=False)
    started, gate = threading.Event(), threading.Event()
    retriever = FakeRetriever(gate=gate, started=started)
    task = asyncio.create_task(
        _ask(trace, FakeDispatcher(retriever), router=FakeRouter(), subagents=False)
    )
    while not started.is_set():
        await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rec.close("cancelled")
    gate.set()  # the worker thread finishes after the run was closed
    await asyncio.sleep(0.05)

    assert [(r.kind, r.status) for r in saved] == [("route", "ok"), ("retrieve", "cancelled")]


def test_joined_groups_matches_the_orchestrator_join_rule(monkeypatch):
    findings = {
        "news": SubagentFindings("news", global_entity_ids=("g1",)),
        "finance": SubagentFindings("finance", global_entity_ids=("g1", "g2")),
        "research": SubagentFindings("research", global_entity_ids=("g3",)),
    }

    class FixedSubagent:
        def __init__(self, *, bubble, **_: object) -> None:
            self.bubble = bubble

        async def run(self, question: str) -> SubagentFindings:
            return findings[self.bubble]

    monkeypatch.setattr(orchestrator, "Subagent", FixedSubagent)
    result = asyncio.run(
        orchestrator.run_subagents(
            "q", bubbles=["news", "finance", "research"], mode="own", llm=None,
            retriever=None, graph_store=None, item_store=None, settings=Settings(_env_file=None),
        )
    )
    expected = [(set(j.bubbles), set(j.global_entity_ids)) for j in result.joins]
    ours = joined_groups(list(findings.values()))
    assert ours == expected == [({"news", "finance"}, {"g1", "g2"})]


# ------------------------------------------- summary keys read by web/src/trace


async def test_normal_mode_records_seed_and_score_children_under_retrieve(monkeypatch):
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=False)
    await _ask(trace, FakeDispatcher(FakeRetriever()), router=FakeRouter("multi_hop"), subagents=False)
    rec.finish(trace.answer_step, "ok", citations=[])
    rec.close("ok")

    by_kind = {r.kind: r for r in saved}
    retrieve = by_kind["retrieve"]
    seed, score = by_kind["seed"], by_kind["score"]
    assert seed.parent_step_id == retrieve.id and score.parent_step_id == retrieve.id
    assert seed.status == "ok" and score.status == "ok"
    assert seed.summary["count"] == 1
    assert seed.node_ids == ["e-alice"]
    assert 0.0 <= score.summary["relevance"] <= 1.0
    assert score.edge_ids == ["f-news"]


async def test_retrieve_summary_carries_count_relevance_and_source_text():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=False)
    retriever = FakeRetriever(score=0.0246)  # half of the best fused score the own pipeline can give
    await _ask(trace, FakeDispatcher(retriever), router=FakeRouter("multi_hop"), subagents=False)
    rec.finish(trace.answer_step, "ok", citations=[])
    rec.close("ok")

    (retrieve,) = [r for r in saved if r.kind == "retrieve"]
    assert retrieve.summary["count"] == 1  # one fact, no chunks
    assert retrieve.summary["source_text"].startswith("Alice leads Acme")
    (score,) = [r for r in saved if r.kind == "score"]
    assert score.summary["relevance"] == pytest.approx(0.5, abs=0.01)


async def test_subagent_summary_carries_count_relevance_and_source_text():
    rec, saved, _ = _recorder(asyncio.get_running_loop())
    trace = PipelineTrace(rec, agentic=True)
    await _ask(
        trace, FakeDispatcher(FakeRetriever()), router=FakeRouter("multi_hop"),
        subagents=True, pins=("news",),
    )
    trace.record_untraced_subagents(())
    rec.finish(trace.answer_step, "ok")
    rec.close("ok")

    (subagent,) = [r for r in saved if r.kind == "subagent"]
    assert subagent.summary["count"] >= 1
    assert 0.0 <= subagent.summary["relevance"] <= 1.0
    assert isinstance(subagent.summary["source_text"], str)
    assert subagent.summary["source_text"]
