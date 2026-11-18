"""Bench QA: scoring, mapping, closed book, external short style, resumability.

The harness test runs the real scoring/resume/report path with fake engines
(monkeypatched runtime/external/LLM), so no provider or Neo4j is touched.
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval.bench import qa as bench_qa
from omnistream.eval.bench.datasets import BenchQuestion, load_benchmark
from omnistream.eval.bench.ingest import save_bench_manifest
from omnistream.eval.bench.qa import (
    BENCH_QA_ROWS,
    HIPPORAG1_TABLE4_QA,
    aggregate_bench_rows,
    closed_book_answer,
    markdown_summary,
    parse_bench_rows,
    passage_ids,
    run_bench_qa,
    score_bench_question,
    unmeasured_row,
)

# --------------------------------------------------------------------------
# fixtures: a tiny musique subset (same shape as test_bench.py)
# --------------------------------------------------------------------------

MUSIQUE_CORPUS = [
    {"title": "Alpha", "text": "Alpha text one."},
    {"title": "Beta", "text": "Beta text with odd whitespace."},
    {"title": "Gamma", "text": "Different gamma text."},
]

MUSIQUE = [
    {
        "id": "2hop__1_2",
        "paragraphs": [
            {
                "idx": 0,
                "title": "Alpha",
                "paragraph_text": "Alpha text one.",
                "is_supporting": False,
            },
            {
                "idx": 1,
                "title": "Beta",
                "paragraph_text": "Beta text  with odd whitespace.",
                "is_supporting": True,
            },
            {
                "idx": 2,
                "title": "Gamma",
                "paragraph_text": "Gamma gold text.",
                "is_supporting": True,
            },
        ],
        "question": "What is the Beta value?",
        "question_decomposition": [],
        "answer": "yes",
        "answer_aliases": ["yeah"],
        "answerable": True,
    },
    {
        "id": "2hop__5_6",
        "paragraphs": [
            {
                "idx": 0,
                "title": "Gamma",
                "paragraph_text": "Gamma gold text.",
                "is_supporting": True,
            }
        ],
        "question": "What about Gamma?",
        "question_decomposition": [],
        "answer": "no",
        "answer_aliases": [],
        "answerable": True,
    },
]


def _write_bench(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "musique.json").write_text(json.dumps(MUSIQUE), encoding="utf-8")
    (root / "musique_corpus.json").write_text(
        json.dumps(MUSIQUE_CORPUS), encoding="utf-8"
    )
    return root


def _question():
    return BenchQuestion(
        id="2hop__1_2",
        question="What is the Beta value?",
        answers=["yes", "yeah"],
        gold_passage_ids=["musique-1", "musique-2"],
        qtype="2hop",
    )


# --------------------------------------------------------------------------
# pure pieces
# --------------------------------------------------------------------------


def test_parse_bench_rows():
    assert parse_bench_rows(None) == list(BENCH_QA_ROWS)
    assert parse_bench_rows("all") == list(BENCH_QA_ROWS)
    assert parse_bench_rows("own,classic") == ["own", "classic"]
    assert parse_bench_rows(["own", "own"]) == ["own"]
    assert parse_bench_rows("own, own+subagents") == ["own", "own+subagents"]
    with pytest.raises(ValueError):
        parse_bench_rows("own,unknown")
    with pytest.raises(ValueError):
        parse_bench_rows("")


def test_passage_ids_dedup_and_drop_unknown():
    mapping = {"i1": "p1", "i2": "p2", "i3": "p1"}
    # First-retrieval order kept; duplicates collapse; foreign ids drop.
    assert passage_ids(["i1", "i2", "i1", "junk", "i3"], mapping) == ["p1", "p2"]
    assert passage_ids(["junk"], mapping) == []


def test_score_bench_question_values():
    question = _question()
    row = score_bench_question(
        "own", question, "yeah", ["musique-1", "musique-0", "musique-2"], 1.5, None
    )
    assert row["exact_match"] == 1.0
    assert row["token_f1"] == 1.0
    # Gold {musique-1, musique-2}: rank 1 and rank 3 after dedup.
    assert row["recall_at_2"] == 0.5
    assert row["recall_at_5"] == 1.0
    assert row["recall_at_10"] == 1.0
    assert row["latency_seconds"] == 1.5

    wrong = score_bench_question("own", question, "Unknown", [], 0.1, {"tokens": 5})
    assert wrong["exact_match"] == 0.0 and wrong["token_f1"] == 0.0
    assert wrong["usage"] == {"tokens": 5}

    # Closed book has no retrieval: recall is not applicable, never 0.
    book = score_bench_question("closed_book", question, "yes", [], 0.2, None)
    assert book["exact_match"] == 1.0
    assert book["recall_at_2"] is None and book["recall_at_10"] is None


def test_unmeasured_row_never_zero():
    row = unmeasured_row("own", _question(), 0.3, RuntimeError("Error code: 402"))
    assert row["unmeasured"] is True
    assert row["exact_match"] is None
    assert row["recall_at_2"] is None
    assert "402" in row["error"]


def test_aggregate_bench_rows_cis_and_costs():
    question = _question()
    rows = []
    for index in range(10):
        rows.append(
            score_bench_question(
                "own",
                question,
                "yes" if index < 7 else "no",
                ["musique-1"],
                1.0 + index / 10,
                {"tokens": 10, "cost_usd": 0.001},
            )
        )
    aggregate = aggregate_bench_rows(rows, n_resamples=500, seed=0)
    entry = aggregate["own"]
    assert entry["questions"] == 10 and entry["measured"] == 10
    assert entry["status"] == "valid"
    assert entry["exact_match"]["mean"] == pytest.approx(0.7)
    assert entry["exact_match"]["ci_low"] <= 0.7 <= entry["exact_match"]["ci_high"]
    assert entry["mean_latency_seconds"] == pytest.approx(1.45)
    assert entry["total_tokens"] == 100
    assert entry["total_cost_usd"] == pytest.approx(0.01)


def test_aggregate_flags_invalid_over_ten_percent_unmeasured():
    question = _question()
    rows = [
        score_bench_question("own", question, "yes", ["musique-1"], 1.0, None)
        for _ in range(9)
    ]
    # Exactly 10% unmeasured stays valid; one more crosses the limit.
    rows.append(unmeasured_row("own", question, 0.1, RuntimeError("boom")))
    assert aggregate_bench_rows(rows)["own"]["status"] == "valid"
    rows.append(unmeasured_row("own", question, 0.1, RuntimeError("Error code: 500")))
    entry = aggregate_bench_rows(rows)["own"]
    assert entry["status"] == "INVALID"
    assert entry["unmeasured_share"] == pytest.approx(2 / 11)
    # Measured means never absorb unmeasured cells as zeros.
    assert entry["exact_match"]["mean"] == 1.0
    assert "RuntimeError" in entry["error_types"]
    # A configuration with no measured rows at all is INVALID.
    only_bad = [unmeasured_row("external", question, 0.1, RuntimeError("x"))]
    assert aggregate_bench_rows(only_bad)["external"]["status"] == "INVALID"


def test_hipporag1_table4_reference_values():
    assert HIPPORAG1_TABLE4_QA["musique"]["None"] == (12.5, 24.1)
    assert HIPPORAG1_TABLE4_QA["musique"]["IRCoT + HippoRAG"] == (21.9, 33.3)
    assert HIPPORAG1_TABLE4_QA["2wiki"]["HippoRAG (ColBERTv2)"] == (46.6, 59.5)
    assert HIPPORAG1_TABLE4_QA["hotpotqa"]["IRCoT (ColBERTv2)"] == (45.5, 58.4)
    assert set(HIPPORAG1_TABLE4_QA) == {"musique", "2wiki", "hotpotqa"}


def test_markdown_summary_tables():
    aggregate = aggregate_bench_rows(
        [score_bench_question("own", _question(), "yes", ["musique-1"], 2.0, None)]
    )
    result = {
        "dataset": "musique",
        "n": 100,
        "seed": 0,
        "snapshot": "bench-musique-n100-s0",
        "group_id": "bench-musique-n100-s0",
        "passage_count": 3,
        "question_count": 1,
        "settings": {
            "llm_model": "m",
            "own_seed_mode": "round3",
            "own_rerank": "off",
            "classic_rerank": "off",
        },
        "aggregates": aggregate,
        "reference": HIPPORAG1_TABLE4_QA["musique"],
    }
    text = markdown_summary(result)
    assert "| own | 1.0000" in text
    assert "fact -> item -> passage" in text
    assert "| IRCoT + HippoRAG | 21.9 | 33.3 |" in text
    assert "| None | 12.5 | 24.1 |" in text


# --------------------------------------------------------------------------
# closed book + external short style
# --------------------------------------------------------------------------


def test_closed_book_answer_uses_short_prompt_and_extraction():
    calls = []

    class FakeLLM:
        def chat(self, messages, **kwargs):
            calls.append(messages)
            return 'Answer: "Paris" [1]'

    answer = closed_book_answer(FakeLLM(), "Where?")
    assert answer == "Paris"
    system = calls[0][0]["content"]
    assert "without any context passages" in system
    assert "shortest possible answer span" in system
    assert calls[0][1]["content"] == "Question: Where?"


def test_external_baseline_short_style_and_default_unchanged(settings, monkeypatch):
    from omnistream.eval import external

    index = Mock()
    captured = {}

    def engine(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return index

    index.as_query_engine.side_effect = engine

    class FakeResult:
        def __init__(self, text, nodes):
            self._text = text
            self.source_nodes = nodes

        def __str__(self):
            return self._text

    node = NS(node=NS(metadata={"item_id": "rt-1"}, get_content=lambda: "text"))
    index.query.return_value = FakeResult('Answer: "Paris" [1]', [node])

    monkeypatch.setattr(
        external.VectorStoreIndex, "from_documents", lambda *a, **kw: index
    )
    service = NS(model_name="test")
    baseline = external.ExternalBaseline(settings, [], service, answer_style="short")
    assert (
        captured["text_qa_template"] is external.ExternalBaseline.SHORT_TEXT_QA_TEMPLATE
    )
    assert "shortest possible answer span" in str(
        external.ExternalBaseline.SHORT_TEXT_QA_TEMPLATE
    )
    answer, ids, sources = baseline.answer("Where?")
    assert answer == "Paris"  # extract_short_answer applied, provenance kept
    assert ids == ["rt-1"]
    assert sources == [("rt-1", "text")]

    # Default construction keeps the plain engine: no custom template.
    external.ExternalBaseline(settings, [], service)
    assert "text_qa_template" not in captured
    with pytest.raises(ValueError):
        external.ExternalBaseline(settings, [], service, answer_style="verbose")


# --------------------------------------------------------------------------
# harness run with fakes
# --------------------------------------------------------------------------


class _FakeAnswer:
    def __init__(self, text):
        self.text = text
        self.citations = ()
        self.invalid_citations = ()


def _qa_result(answer_text, item_ids):
    return NS(
        answer=_FakeAnswer(answer_text),
        retrieval=NS(facts=[], chunks=[NS(item_id=i) for i in item_ids]),
        multi_hop=None,
    )


async def test_run_bench_qa_with_fakes(tmp_path, monkeypatch):
    _write_bench(tmp_path)
    bench = load_benchmark("musique", root=tmp_path, corpus="slice")
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    question_by_text = {q.question: q for q in bench.questions}

    snapshot = tmp_path / "snapshots" / "bench-demo"
    save_bench_manifest(
        snapshot / "bench_manifest.json",
        {
            "kind": "bench-ingest",
            "dataset": "musique",
            "n": None,
            "seed": 0,
            "corpus": "slice",
            "group_id": "bench-demo",
            "question_ids": [q.id for q in bench.questions],
            "passages": {
                p.id: {"runtime_id": "rt-" + p.id, "status": "written"}
                for p in bench.passages
            },
        },
    )
    repo = Repository.from_path(str(snapshot / "state.db"), settings=settings)
    await repo.close()

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        async def answer(self, question, *, mode, subagents, answer_style, pin):
            self.calls.append((question, mode, subagents, answer_style))
            assert answer_style == "short" and pin == ("bench-demo",)
            q = question_by_text[question]
            ids = ["rt-" + q.gold_passage_ids[0]] if q.gold_passage_ids else []
            return _qa_result(q.answers[0], ids)

        async def close(self):
            pass

    class FakeExternal:
        def __init__(self, settings, items, service, *, answer_style="short"):
            assert answer_style == "short"
            self.items = items

        def answer(self, question):
            q = question_by_text[question]
            ids = ["rt-" + q.gold_passage_ids[0]] if q.gold_passage_ids else []
            return (q.answers[0], ids, [(i, "text") for i in ids])

    class FakeChatLLM:
        def __init__(self, settings):
            self.calls = []

        def chat(self, messages, **kwargs):
            self.calls.append(messages)
            return "Answer: no"

    fake_runtime = FakeRuntime()

    import omnistream.embed as embed_module
    import omnistream.eval.external as external_module
    import omnistream.retrieval.runtime as runtime_module

    monkeypatch.setattr(
        runtime_module, "build_query_runtime", lambda *a, **k: fake_runtime
    )
    monkeypatch.setattr(external_module, "ExternalBaseline", FakeExternal)
    monkeypatch.setattr(
        embed_module, "SentenceTransformerEmbedder", lambda name: NS(service=None)
    )
    monkeypatch.setattr(bench_qa, "LLMClient", FakeChatLLM)

    progress = []

    async def emit(message):
        progress.append(message)

    output = await run_bench_qa(
        settings,
        dataset_name="musique",
        n=None,
        seed=0,
        snapshot="bench-demo",
        rows="closed_book,external,own",
        bench_root=tmp_path,
        out=tmp_path / "out",
        progress=emit,
    )
    # 2 questions x 3 configurations
    assert len(output["questions"]) == 6
    assert set(output["aggregates"]) == {"closed_book", "external", "own"}
    own = output["aggregates"]["own"]
    assert own["exact_match"]["mean"] == 1.0
    # Q1 gold = {musique-1, musique-2}, only one retrieved -> 0.5;
    # Q2 gold = {musique-2} retrieved -> 1.0. Mean recall@2 = 0.75.
    assert own["recall_at_2"]["mean"] == pytest.approx(0.75)
    # Closed book answers "no": EM 1.0 on q2 ("no"), 0.0 on q1 ("yes").
    assert output["aggregates"]["closed_book"]["exact_match"]["mean"] == 0.5
    assert output["aggregates"]["closed_book"]["recall_at_2"]["mean"] is None
    assert output["validity"]["invalid_configurations"] == []
    # The external index was built from the manifest mapping.
    assert output["settings"]["own_seed_mode"] == settings.own_seed_mode

    files = list((tmp_path / "out").glob("qa-musique-nall-s0-*"))
    assert sorted(p.suffix for p in files) == [".json", ".md"]
    payload = json.loads(files[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert list(payload["reference"]["None"]) == [12.5, 24.1]
    assert len(payload["questions"]) == 6
    markdown = files[0].with_suffix(".md").read_text(encoding="utf-8")
    assert "| None | 12.5 | 24.1 |" in markdown


async def test_run_bench_qa_resume_retries_unmeasured_cells(tmp_path, monkeypatch):
    _write_bench(tmp_path)
    bench = load_benchmark("musique", root=tmp_path, corpus="slice")
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    question_by_text = {q.question: q for q in bench.questions}
    snapshot = tmp_path / "snapshots" / "bench-demo"

    save_bench_manifest(
        snapshot / "bench_manifest.json",
        {
            "kind": "bench-ingest",
            "dataset": "musique",
            "n": None,
            "seed": 0,
            "corpus": "slice",
            "group_id": "bench-demo",
            "question_ids": [q.id for q in bench.questions],
            "passages": {
                p.id: {"runtime_id": "rt-" + p.id, "status": "written"}
                for p in bench.passages
            },
        },
    )
    repo = Repository.from_path(str(snapshot / "state.db"), settings=settings)
    await repo.close()

    class FakeRuntime:
        def __init__(self, fail_on=frozenset()):
            self.calls = []
            self.fail_on = set(fail_on)

        async def answer(self, question, *, mode, subagents, answer_style, pin):
            self.calls.append(question)
            if question in self.fail_on:
                raise RuntimeError("Error code: 402")
            q = question_by_text[question]
            ids = ["rt-" + q.gold_passage_ids[0]] if q.gold_passage_ids else []
            return _qa_result(q.answers[0], ids)

        async def close(self):
            pass

    import omnistream.embed as embed_module
    import omnistream.retrieval.runtime as runtime_module

    failing = "What about Gamma?"
    fake = FakeRuntime(fail_on={failing})
    monkeypatch.setattr(runtime_module, "build_query_runtime", lambda *a, **k: fake)
    monkeypatch.setattr(
        embed_module, "SentenceTransformerEmbedder", lambda name: NS(service=None)
    )
    monkeypatch.setattr(
        bench_qa, "LLMClient", lambda settings: NS(_client=None)
    )

    output = await run_bench_qa(
        settings,
        dataset_name="musique",
        n=None,
        seed=0,
        snapshot="bench-demo",
        rows="own",
        bench_root=tmp_path,
        out=tmp_path / "out",
        progress=lambda m: None,
    )
    assert len(output["questions"]) == 2
    # The measured cell scored; the provider-402 cell is unmeasured, not zero.
    measured = [r for r in output["questions"] if not r.get("unmeasured")]
    assert len(measured) == 1 and measured[0]["exact_match"] == 1.0
    unmeasured = next(r for r in output["questions"] if r.get("unmeasured"))
    assert unmeasured["exact_match"] is None
    assert output["aggregates"]["own"]["status"] == "INVALID"
    assert output["validity"]["invalid_configurations"] == ["own"]
    # Provider credit failures stop further calls for this configuration.

    # Resume with the failure healed: only the unmeasured cell is retried.
    fake.fail_on = set()
    output = await run_bench_qa(
        settings,
        dataset_name="musique",
        n=None,
        seed=0,
        snapshot="bench-demo",
        rows="own",
        resume=True,
        bench_root=tmp_path,
        out=tmp_path / "out",
        progress=lambda m: None,
    )
    assert len(fake.calls) == 3  # 2 first run + exactly 1 retry
    assert len(output["questions"]) == 2
    assert all(not r.get("unmeasured") for r in output["questions"])
    retried = [r for r in output["questions"] if r.get("resume_retry")]
    assert len(retried) == 1
    assert output["aggregates"]["own"]["status"] == "valid"
    assert output["aggregates"]["own"]["recall_at_2"]["mean"] == pytest.approx(0.75)

    # A resume with different rows/questions is rejected.
    with pytest.raises(ValueError):
        await run_bench_qa(
            settings,
            dataset_name="musique",
            n=None,
            seed=0,
            snapshot="bench-demo",
            rows="own,classic",
            resume=True,
            bench_root=tmp_path,
            out=tmp_path / "out",
            progress=lambda m: None,
        )


async def test_run_bench_qa_resume_extends_limited_run(tmp_path, monkeypatch):
    _write_bench(tmp_path)
    bench = load_benchmark("musique", root=tmp_path, corpus="slice")
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    question_by_text = {q.question: q for q in bench.questions}
    snapshot = tmp_path / "snapshots" / "bench-demo"
    save_bench_manifest(
        snapshot / "bench_manifest.json",
        {
            "kind": "bench-ingest",
            "dataset": "musique",
            "n": None,
            "seed": 0,
            "corpus": "slice",
            "group_id": "bench-demo",
            "question_ids": [q.id for q in bench.questions],
            "passages": {
                p.id: {"runtime_id": "rt-" + p.id, "status": "written"}
                for p in bench.passages
            },
        },
    )
    repo = Repository.from_path(str(snapshot / "state.db"), settings=settings)
    await repo.close()

    calls = []

    class FakeRuntime:
        async def answer(self, question, *, mode, subagents, answer_style, pin):
            calls.append(question)
            q = question_by_text[question]
            ids = ["rt-" + q.gold_passage_ids[0]] if q.gold_passage_ids else []
            return _qa_result(q.answers[0], ids)

        async def close(self):
            pass

    import omnistream.embed as embed_module
    import omnistream.retrieval.runtime as runtime_module

    monkeypatch.setattr(
        runtime_module, "build_query_runtime", lambda *a, **k: FakeRuntime()
    )
    monkeypatch.setattr(
        embed_module, "SentenceTransformerEmbedder", lambda name: NS(service=None)
    )

    class SyncClose:  # e.g. an httpx-style client whose close() is synchronous
        def close(self):
            return None

    monkeypatch.setattr(bench_qa, "LLMClient", lambda settings: NS(_client=SyncClose()))
    common = {
        "dataset_name": "musique", "n": None, "seed": 0, "snapshot": "bench-demo",
        "rows": "own", "bench_root": tmp_path, "out": tmp_path / "out",
        "progress": lambda m: None,
    }
    first = await run_bench_qa(settings, limit_questions=1, **common)
    assert len(first["questions"]) == 1
    full = await run_bench_qa(settings, resume=True, **common)
    assert len(calls) == 2  # only the new question was answered
    assert len(full["questions"]) == 2
    assert full["aggregates"]["own"]["status"] == "valid"
    # Shrinking the question set on resume is still rejected.
    with pytest.raises(ValueError):
        await run_bench_qa(settings, resume=True, limit_questions=1, **common)


async def test_run_bench_qa_refuses_incomplete_snapshot(tmp_path):
    _write_bench(tmp_path)
    bench = load_benchmark("musique", root=tmp_path, corpus="slice")
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    snapshot = tmp_path / "snapshots" / "bench-demo"

    entries = {p.id: {"runtime_id": "rt-" + p.id} for p in bench.passages}
    entries[bench.passages[0].id]["status"] = "written"  # the rest unwritten
    save_bench_manifest(
        snapshot / "bench_manifest.json",
        {
            "kind": "bench-ingest",
            "dataset": "musique",
            "n": None,
            "seed": 0,
            "corpus": "slice",
            "group_id": "bench-demo",
            "question_ids": [q.id for q in bench.questions],
            "passages": entries,
        },
    )
    with pytest.raises(ValueError, match="incomplete"):
        await run_bench_qa(
            settings,
            dataset_name="musique",
            n=None,
            seed=0,
            snapshot="bench-demo",
            rows="own",
            bench_root=tmp_path,
            out=tmp_path / "out",
            progress=lambda m: None,
        )
    # No manifest at all points at bench-ingest.
    with pytest.raises(ValueError, match="bench-ingest"):
        await run_bench_qa(
            settings,
            dataset_name="musique",
            n=None,
            seed=0,
            snapshot="bench-empty",
            rows="own",
            bench_root=tmp_path,
            out=tmp_path / "out",
            progress=lambda m: None,
        )
