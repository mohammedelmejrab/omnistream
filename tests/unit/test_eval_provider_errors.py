"""Offline regressions for provider failures and bounded completions."""

import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest

from omnistream.config import Settings
from omnistream.eval.metrics import (
    aggregate,
    fatal_provider_error,
    run_validity,
    success_criteria,
)
from omnistream.eval.report import reaggregate
from omnistream.llm import AsyncLLMClient, LLMClient


def good():
    return {
        "configuration": "own",
        "type": "time_sensitive",
        "correctness": 2,
        "recall_at_10": 1.0,
        "mrr": 1.0,
        "hits_at_1": 1.0,
        "routing_recall": 1.0,
        "routing_precision": 1.0,
        "citation_count": 1,
        "faithful_citations": 1,
    }


@pytest.mark.parametrize(
    "error",
    [
        "APIStatusError: Error code: 402 - Insufficient credits",
        "HTTP 503 unavailable",
        "APITimeoutError: timed out",
        "APIConnectionError: disconnected",
    ],
)
def test_failed_pairs_excluded_from_every_score(error):
    failed = dict(
        good(),
        correctness=0,
        recall_at_10=0.0,
        mrr=0.0,
        hits_at_1=0.0,
        routing_recall=0.0,
        routing_precision=0.0,
        faithful_citations=0,
        error=error,
    )
    m = aggregate([good(), failed])["own"]
    for key in (
        "recall_at_10",
        "mrr",
        "hits_at_1",
        "routing_recall",
        "routing_precision",
        "citation_faithfulness",
        "citation_faithfulness_micro",
        "changed_fact_accuracy",
    ):
        assert m[key] == 1
    assert m["correctness"] == 2
    assert (
        m["errors"] == m["unmeasured"] == m["by_type"]["time_sensitive"]["errors"] == 1
    )
    assert m["questions"] == 2 and m["measured"] == 1
    checks = success_criteria({"own": m}, {})
    assert all(
        c["status"] == "UNMEASURED"
        for label, c in checks.items()
        if label.startswith("own:")
    )


def test_validity_boundary_and_offline_export(tmp_path):
    rows = [good() for _ in range(9)] + [dict(good(), error="HTTP 500 unavailable")]
    assert run_validity(aggregate(rows))["status"] == "completed_with_errors"
    rows.append(dict(good(), error="HTTP 402 insufficient credits"))
    assert run_validity(aggregate(rows))["status"] == "invalid"
    source = tmp_path / "answers.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report, _, _ = reaggregate(source, tmp_path)
    assert "INVALID RUN" in Path(report).read_text(encoding="utf-8")


@pytest.mark.parametrize("status", [401, 402, 403])
def test_credit_auth_stop(status):
    assert fatal_provider_error(NS(status_code=status))
    assert fatal_provider_error(f"APIStatusError: Error code: {status} - denied")
    assert not fatal_provider_error("HTTP 429 rate limited")


async def test_answer_agent_caps(monkeypatch):
    monkeypatch.setenv("OMNI_LLM_MAX_OUTPUT_TOKENS", "2048")
    settings = Settings(_env_file=None)
    response = NS(
        choices=[
            NS(
                finish_reason="stop",
                message=NS(content="ok", tool_calls=[], model_dump=lambda **k: {}),
            )
        ]
    )
    sync = Mock()
    sync.chat.completions.create.return_value = response
    llm = LLMClient(settings, client=sync)
    llm.answer("q", [])
    assert sync.chat.completions.create.call_args.kwargs["max_tokens"] == 2048
    llm.chat([], max_tokens=131072)
    assert sync.chat.completions.create.call_args.kwargs["max_tokens"] == 2048
    client = NS(chat=NS(completions=NS(create=AsyncMock(return_value=response))))
    await AsyncLLMClient(settings, client=client).chat_with_tools([], [])
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 2048


async def test_judge_cap_from_environment(monkeypatch):
    from omnistream.eval.judge import Judge

    monkeypatch.setenv("OMNI_JUDGE_MAX_OUTPUT_TOKENS", "768")
    judge = Judge(Settings(_env_file=None))
    judge.client = NS(chat_json=Mock(return_value={"score": 2}))
    await judge.correctness({"question": "q", "reference_answer": "a"}, "a")
    assert judge.client.chat_json.call_args.kwargs["max_tokens"] == 768


async def test_credit_judge_does_not_start_citation_calls():
    from omnistream.eval import score_question

    judge = NS(
        correctness=AsyncMock(
            side_effect=RuntimeError("HTTP 402 Insufficient credits")
        ),
        citations=AsyncMock(),
    )
    q = {
        "id": "q",
        "type": "single",
        "question": "q",
        "reference_answer": "a",
        "expected_bubbles": [],
    }
    row = await score_question("own", q, "a", [], [], [], [], {}, judge, [], 0)
    assert row["correctness"] is None
    assert row["judgement_errors"]
    judge.citations.assert_not_called()
