"""Offline billing-safety checks for the diagnostic resume command."""

import json
from types import SimpleNamespace

import pytest

from omnistream.eval.diagnostics import run
from omnistream.retrieval.models import Chunk, RetrievalResult
from omnistream.retrieval.router import RoutingDecision


class FakeRuntime:
    def __init__(self, blocked=False):
        self.calls = 0
        self.blocked = blocked
        self.router = SimpleNamespace(
            route=lambda *a, **kw: RoutingDecision(("eval-v2-news",))
        )

    async def answer(self, question, **kwargs):
        self.calls += 1
        if self.blocked:
            raise RuntimeError("Key limit exceeded (total limit)")
        routing = self.router.route(question)
        return SimpleNamespace(
            answer=SimpleNamespace(text="answer"),
            routing=routing,
            retrieval=RetrievalResult(
                kwargs["mode"],
                chunks=(
                    Chunk("c", "evidence", "runtime-g", "eval-v2-news", None, None),
                ),
            ),
            multi_hop=None,
        )


class FakeJudge:
    def __init__(self):
        self.calls = 0

    async def correctness(self, question, answer):
        self.calls += 1
        return {"score": 2}


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "OUT", tmp_path)
    monkeypatch.setattr(
        run,
        "DATA",
        {
            "questions": [
                {
                    "id": "q",
                    "type": "time_sensitive",
                    "question": "question",
                    "gold": ["g"],
                }
            ]
        },
    )
    monkeypatch.setattr(run, "IDS", {"g": "runtime-g"})
    return SimpleNamespace(summary=dict)


@pytest.mark.asyncio
async def test_resume_skips_every_finished_cell(sandbox):
    first, judge = FakeRuntime(), FakeJudge()
    await run.answers(first, judge, None, sandbox)
    assert first.calls == judge.calls == 10
    second, judge = FakeRuntime(), FakeJudge()
    await run.answers(second, judge, None, sandbox)
    assert second.calls == judge.calls == 0
    assert len(run.read("answers")) == 10


@pytest.mark.asyncio
async def test_capacity_failure_stops_and_remains_resumable(sandbox):
    blocked = FakeRuntime(blocked=True)
    with pytest.raises(run.ProviderCapacityError):
        await run.answers(blocked, FakeJudge(), None, sandbox)
    assert blocked.calls == 1
    assert run.read("answers")[0]["provider_blocked"]
    resumed = FakeRuntime()
    await run.answers(resumed, FakeJudge(), None, sandbox)
    assert resumed.calls == 10
    assert len(run.primary_answers()) == 10
    assert all(r["correctness"] == 2 for r in run.primary_answers())


@pytest.mark.asyncio
async def test_resume_rejudges_cached_answer_without_regenerating(sandbox):
    await run.answers(FakeRuntime(), FakeJudge(), None, sandbox)
    rows = run.read("answers")
    rows[0].pop("correctness")
    rows[0]["error"] = "judge temporarily unavailable"
    (run.OUT / "answers.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    resumed, judge = FakeRuntime(), FakeJudge()
    await run.answers(resumed, judge, None, sandbox)
    assert resumed.calls == 0
    assert judge.calls == 1
    assert run.primary_answers()[0]["resume_judge_only"]
