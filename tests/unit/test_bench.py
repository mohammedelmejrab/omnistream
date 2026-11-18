"""Bench (HippoRAG subsets) loading, metrics and retrieval-only checks.

Everything here runs offline: fixture JSONs are written to ``tmp_path`` and
the dense retriever gets the deterministic ``HashingEncoder`` from conftest.
"""

import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from omnistream.eval import score_question
from omnistream.eval.bench import metrics as bench_metrics
from omnistream.eval.bench.datasets import load_benchmark
from omnistream.eval.bench.retrieval_check import (
    HIPPORAG1_TABLE2_SINGLE_STEP,
    query_passage_prefixes,
    run_retrieval_check,
)
from omnistream.eval.metrics import aggregate, retrieval_metrics

# --------------------------------------------------------------------------
# Inline fixtures: one tiny released-format subset per dataset.
# --------------------------------------------------------------------------

MUSIQUE_CORPUS = [
    {"title": "Alpha", "text": "Alpha text one."},
    {"title": "Beta", "text": "Beta text with odd whitespace."},
    {"title": "Gamma", "text": "Different gamma text."},
    {"title": "Delta", "text": "Delta text A."},
    {"title": "Delta", "text": "Delta text B."},
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
        "answer_aliases": ["yeah", "yes"],
        "answerable": True,
    },
    {
        "id": "3hop1__3_4",
        "paragraphs": [
            {
                "idx": 0,
                "title": "Delta",
                "paragraph_text": "Delta unmatched text.",
                "is_supporting": True,
            },
            {
                "idx": 1,
                "title": "Omega",
                "paragraph_text": "Omega missing.",
                "is_supporting": True,
            },
        ],
        "question": "Where is it?",
        "question_decomposition": [],
        "answer": "no",
        "answer_aliases": [],
        "answerable": True,
    },
]

TWO_WIKI = [
    {
        "_id": "wiki-q1",
        "type": "compositional",
        "question": "Who died?",
        "context": [
            ["TitleA", ["Sentence one.", " Sentence two."]],
            ["TitleB", ["Unrelated."]],
        ],
        "supporting_facts": [["TitleA", 0], ["TitleB", 0]],
        "answer": "20 March 851",
        "evidences": [],
        "entity_ids": "",
        "evidences_id": [],
        "answer_id": None,
    }
]
TWO_WIKI_CORPUS = [
    {"title": "TitleA", "text": "Sentence one. Sentence two."},
    {"title": "TitleB", "text": "Unrelated."},
    {"title": "TitleC", "text": "Never referenced."},
]

HOTPOT = [
    {
        "_id": "hp-q1",
        "answer": "yes it is",
        "question": "Is it?",
        "supporting_facts": [["HotTitle", 0]],
        "context": [
            ["HotTitle", ["Part one.", " Part two."]],
            ["Other", ["irrelevant"]],
        ],
        "type": "bridge",
        "level": "hard",
    }
]
HOTPOT_CORPUS = [
    {"idx": 0, "title": "HotTitle", "text": "Part one. Part two."},
    {"idx": 1, "title": "Other", "text": "irrelevant"},
]


def _write(root, files):
    for name, payload in files.items():
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    return Path(root)


def _write_musique(root):
    return _write(
        root,
        {"musique.json": MUSIQUE, "musique_corpus.json": MUSIQUE_CORPUS},
    )


# --------------------------------------------------------------------------
# datasets.py
# --------------------------------------------------------------------------


def test_musique_gold_mapping_fallback_paths(tmp_path):
    _write_musique(tmp_path)
    bench = load_benchmark("musique", root=tmp_path)
    assert [p.id for p in bench.passages][:3] == ["musique-0", "musique-1", "musique-2"]
    first, second = bench.questions
    # Beta: whitespace-normalised match; Gamma: unique-title fallback.
    assert first.gold_passage_ids == ["musique-1", "musique-2"]
    assert first.answers == ["yes", "yeah"]  # aliases appended, deduplicated
    assert first.qtype == "2hop"
    # Delta: ambiguous duplicate title; Omega: title absent. Both unmatched.
    assert second.gold_passage_ids == []
    assert second.qtype == "3hop1"
    assert bench.unmatched_gold == 2
    with pytest.raises(ValueError):
        load_benchmark("triviaqa", root=tmp_path)


def test_2wiki_and_hotpotqa_formats_and_alias(tmp_path):
    _write(
        tmp_path,
        {
            "2wikimultihopqa.json": TWO_WIKI,
            "2wikimultihopqa_corpus.json": TWO_WIKI_CORPUS,
        },
    )
    bench = load_benchmark("2wiki", root=tmp_path)
    assert bench.name == "2wiki"
    # 2wiki gold text joins sentences with a single space -> needs the
    # whitespace-normalised match against the corpus entry.
    assert bench.questions[0].gold_passage_ids == ["2wiki-0", "2wiki-1"]
    assert bench.questions[0].answers == ["20 March 851"]
    assert bench.questions[0].qtype == "compositional"
    assert bench.unmatched_gold == 0
    alias = load_benchmark("2wikimultihopqa", root=tmp_path)
    assert [q.id for q in alias.questions] == [q.id for q in bench.questions]

    _write(
        tmp_path,
        {"hotpotqa.json": HOTPOT, "hotpotqa_corpus.json": HOTPOT_CORPUS},
    )
    hotpot = load_benchmark("hotpotqa", root=tmp_path)
    # hotpotqa joins sentences with no separator -> exact match.
    assert hotpot.questions[0].gold_passage_ids == ["hotpotqa-0"]
    assert hotpot.questions[0].qtype == "bridge"


def test_sampling_determinism_and_slice_corpus(tmp_path):
    # Five questions so random.Random(seed).sample has room to choose.
    many = [
        {
            "id": f"2hop__{i}_{i}",
            "paragraphs": [
                {
                    "idx": 0,
                    "title": "Alpha",
                    "paragraph_text": "Alpha text one.",
                    "is_supporting": True,
                }
            ],
            "question": f"question {i}",
            "question_decomposition": [],
            "answer": f"answer {i}",
            "answer_aliases": [],
            "answerable": True,
        }
        for i in range(5)
    ]
    _write(
        tmp_path,
        {"musique.json": many, "musique_corpus.json": MUSIQUE_CORPUS},
    )
    first = load_benchmark("musique", root=tmp_path, n=3, seed=0)
    again = load_benchmark("musique", root=tmp_path, n=3, seed=0)
    assert [q.id for q in first.questions] == [q.id for q in again.questions]
    all_ids = [f"2hop__{i}_{i}" for i in range(5)]
    assert [q.id for q in first.questions] == [
        qid for qid in all_ids if qid in {q.id for q in first.questions}
    ]  # sampled subset kept in original file order
    assert len(load_benchmark("musique", root=tmp_path, n=50).questions) == 5
    assert [
        q.id for q in load_benchmark("musique", root=tmp_path, n=None).questions
    ] == all_ids

    _write_musique(tmp_path)
    full = load_benchmark("musique", root=tmp_path)
    sliced = load_benchmark("musique", root=tmp_path, corpus="slice")
    slice_ids = {p.id for p in sliced.passages}
    # Slice keeps referenced passages plus every matched gold passage,
    # drops the never-referenced second Delta entry and Alpha stays: it is
    # a (non-gold) context paragraph of the first question.
    assert slice_ids == {"musique-0", "musique-1", "musique-2"}
    assert all(set(q.gold_passage_ids) <= slice_ids for q in sliced.questions)
    assert len(full.passages) == 5
    assert sliced.unmatched_gold == full.unmatched_gold == 2
    with pytest.raises(ValueError):
        load_benchmark("musique", root=tmp_path, corpus="half")


def test_write_manifest(tmp_path):
    _write_musique(tmp_path)
    bench = load_benchmark("musique", root=tmp_path, n=1, seed=0)
    path = bench.write_manifest(tmp_path / "sub" / "manifest.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["dataset"] == "musique"
    assert payload["question_ids"] == [q.id for q in bench.questions]
    assert payload["question_count"] == 1
    assert payload["unmatched_gold"] == 2


# --------------------------------------------------------------------------
# bench metrics
# --------------------------------------------------------------------------


def test_exact_match_and_token_f1_cases():
    assert bench_metrics.normalize_answer("The  Answer, Sir!") == "answer sir"
    assert bench_metrics.exact_match("The Answer.", ["ANSWER"]) == 1.0
    assert bench_metrics.exact_match("an apple", ["apple"]) == 1.0  # article dropped
    assert bench_metrics.exact_match("Paris.", ["London"]) == 0.0
    assert bench_metrics.exact_match("", ["nothing"]) == 0.0  # empty prediction
    assert bench_metrics.exact_match("x", []) == 0.0
    # max over aliases
    assert bench_metrics.exact_match("yeah", ["no", "Yeah"]) == 1.0
    assert bench_metrics.token_f1("yes", ["no", "Yes"]) == 1.0
    # prediction "the city Paris" -> tokens [city, paris] vs [paris]
    assert bench_metrics.token_f1("the city Paris", ["Paris"]) == pytest.approx(2 / 3)
    assert bench_metrics.token_f1("", ["answer"]) == 0.0
    assert bench_metrics.token_f1("x", []) == 0.0


def test_recall_ndcg_and_bootstrap():
    ranked = ["a", "a", "b", "c", "d"]  # dedup -> a, b, c, d
    gold = ["b", "e"]
    assert bench_metrics.recall_at_k(ranked, gold, 1) == 0.0
    # Duplicates collapse before the cutoff: "b" counts inside the first 2.
    assert bench_metrics.recall_at_k(["a", "a", "b"], gold, 2) == 0.5
    assert bench_metrics.recall_at_k(ranked, gold, 2) == 0.5
    assert bench_metrics.recall_at_k(ranked, gold, 3) == 0.5
    assert bench_metrics.recall_at_k(ranked, gold, 20) == 0.5
    assert bench_metrics.recall_at_k(ranked, [], 5) == 0.0
    # b at position 2 of the deduplicated ranking
    expected_dcg = 1 / math.log2(3)
    ideal = 1 + 1 / math.log2(3)
    assert bench_metrics.ndcg_at_k(ranked, gold, 10) == pytest.approx(expected_dcg / ideal)
    assert bench_metrics.ndcg_at_k(["b", "e", "a"], gold, 10) == 1.0
    assert bench_metrics.ndcg_at_k(ranked, [], 10) == 0.0

    values = [0.0, 1.0, 1.0, 1.0]
    mean, low, high = bench_metrics.bootstrap_ci(values, n_resamples=2000, seed=1)
    assert mean == pytest.approx(0.75)
    assert low <= 0.75 <= high and low < high
    repeat = bench_metrics.bootstrap_ci(values, n_resamples=2000, seed=1)
    assert (low, high) == (repeat[1], repeat[2])
    with pytest.raises(ValueError):
        bench_metrics.bootstrap_ci([])


# --------------------------------------------------------------------------
# retrieval_check.py
# --------------------------------------------------------------------------


def test_query_passage_prefixes_and_reference_table():
    bge = "Represent this sentence for searching relevant passages: "
    assert query_passage_prefixes("BAAI/bge-small-en-v1.5") == (bge, "")
    assert query_passage_prefixes("BAAI/bge-base-en-v1.5") == (bge, "")
    assert query_passage_prefixes("intfloat/e5-small-v2") == ("query: ", "passage: ")
    assert query_passage_prefixes("sentence-transformers/all-MiniLM-L6-v2") == ("", "")
    assert set(HIPPORAG1_TABLE2_SINGLE_STEP) == {"musique", "2wiki", "hotpotqa"}
    assert HIPPORAG1_TABLE2_SINGLE_STEP["musique"]["BM25"] == (32.3, 41.2)


def test_query_passage_prefixes_instruction_tuned_decoders():
    """Qwen3-Embedding / gte-Qwen2: query instruction, unprefixed passages."""
    instruction = (
        (
            "Instruct: Given a question, retrieve relevant documents that best "
            "answer the question\nQuery: "
        ),
        "",
    )
    for model in (
        "Qwen/Qwen3-Embedding-0.6B",
        "Qwen/Qwen3-Embedding-4B",
        "Qwen/Qwen3-Embedding-8B",
        "Alibaba-NLP/gte-Qwen2-1.5B-instruct",
        "Alibaba-NLP/gte-Qwen2-7B-instruct",
    ):
        assert query_passage_prefixes(model) == instruction, model
    # Case-insensitive family match; the bare base name still belongs to the
    # documented family regex, while siblings and rerankers stay unprefixed.
    assert query_passage_prefixes("qwen/qwen3-embedding-0.6b") == instruction
    assert query_passage_prefixes("Qwen/QwQ-32B") == ("", "")
    assert query_passage_prefixes("Qwen/Qwen3-Reranker-0.6B") == ("", "")
    assert query_passage_prefixes("BAAI/bge-m3") == ("", "")


def test_retrieval_check_dense_with_injected_encoder(tmp_path, encoder):
    _write_musique(tmp_path)
    bench = load_benchmark("musique", root=tmp_path)
    cache = tmp_path / "cache"
    result = run_retrieval_check(
        bench,
        retriever="dense",
        model="fake/dense-model",
        encoder=encoder,
        batch_size=2,
        cache_dir=cache,
    )
    assert result["dataset"] == "musique" and result["retriever"] == "dense"
    assert result["question_count"] == 2 and result["passage_count"] == 5
    assert result["unmatched_gold"] == 2
    row = next(r for r in result["questions"] if r["id"] == "2hop__1_2")
    # The query shares the rare token "beta" only with the Beta gold passage.
    assert row["ranked_ids"][0] == "musique-1"
    assert row["recall_at_5"] == 1.0 and row["mrr"] == 1.0
    # Gold at ranks 1 and 3 (ties keep corpus order), ideal = ranks 1 and 2.
    assert row["ndcg_at_10"] == pytest.approx(
        (1 / math.log2(2) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    )
    assert result["timing"]["encode_seconds"] >= 0.0
    aggregates = result["aggregates"]
    assert aggregates["recall_at_2"]["mean"] == pytest.approx(0.25)
    assert set(aggregates) == {
        "recall_at_2",
        "recall_at_5",
        "recall_at_10",
        "recall_at_20",
        "ndcg_at_10",
        "mrr",
    }
    for values in aggregates.values():
        assert values["ci_low"] <= values["mean"] <= values["ci_high"]
    assert result["by_qtype"]["2hop"]["recall_at_5"] == 1.0
    assert result["by_qtype"]["3hop1"]["questions"] == 1

    cache_files = list(cache.glob("*.npy"))
    assert len(cache_files) == 1
    assert cache_files[0].name.startswith("musique__fake-dense-model__")
    calls_before = len(encoder.calls)
    run_retrieval_check(
        bench,
        retriever="dense",
        model="fake/dense-model",
        encoder=encoder,
        batch_size=2,
        cache_dir=cache,
    )
    # Cached passages: only the two queries are re-encoded.
    assert len(encoder.calls) - calls_before == 2


def test_retrieval_check_bm25(tmp_path):
    _write_musique(tmp_path)
    bench = load_benchmark("musique", root=tmp_path)
    result = run_retrieval_check(bench, retriever="bm25")
    assert result["model"] is None
    assert result["timing"]["encode_seconds"] == 0.0
    row = next(r for r in result["questions"] if r["id"] == "2hop__1_2")
    assert row["ranked_ids"][0] == "musique-1"  # "beta" is the lone high-IDF hit
    assert set(row["ranked_ids"]) <= {p.id for p in bench.passages}
    assert result["aggregates"]["mrr"]["mean"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        run_retrieval_check(bench, retriever="hybrid")


# --------------------------------------------------------------------------
# harness additions
# --------------------------------------------------------------------------


def test_retrieval_metrics_new_keys_keep_existing_ones():
    retrieved = ["x", "x"] + [f"g{i}" for i in range(1, 10)] + ["g10", "junk"]
    metrics = retrieval_metrics(retrieved, ["g1", "g2"])
    # Existing keys unchanged.
    assert metrics["recall_at_10"] == 1.0
    assert metrics["mrr"] == 0.5
    assert metrics["hits_at_1"] == 0.0
    # New keys: gold only, deduplicated ranking.
    assert metrics["recall_at_2"] == 0.5
    assert metrics["recall_at_5"] == 1.0
    assert metrics["recall_at_20"] == 1.0
    expected = (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert metrics["ndcg_at_10"] == pytest.approx(expected)
    assert retrieval_metrics([], [])["ndcg_at_10"] == 0.0


def test_aggregate_averages_new_keys_and_tolerates_legacy_rows():
    row = {
        "configuration": "own",
        "type": "single",
        "recall_at_10": 1.0,
        "recall_at_2": 0.5,
        "recall_at_5": 1.0,
        "recall_at_20": 1.0,
        "ndcg_at_10": 0.5,
        "mrr": 1.0,
        "hits_at_1": 1.0,
        "routing_recall": 1.0,
        "routing_precision": 1.0,
        "latency_seconds": 0.1,
        "citation_count": None,
    }
    metrics = aggregate([row])["own"]
    assert metrics["recall_at_2"] == 0.5
    assert metrics["recall_at_5"] == 1.0
    assert metrics["recall_at_20"] == 1.0
    assert metrics["ndcg_at_10"] == 0.5
    assert metrics["by_type"]["single"]["ndcg_at_10"] == 0.5
    legacy = {
        key: value
        for key, value in row.items()
        if key not in {"recall_at_2", "recall_at_5", "recall_at_20", "ndcg_at_10"}
    }
    legacy["configuration"] = "classic"
    legacy_metrics = aggregate([legacy])["classic"]
    assert legacy_metrics["recall_at_2"] is None
    assert legacy_metrics["ndcg_at_10"] is None


async def test_score_question_short_answers_fields():
    question = {
        "id": "q",
        "question": "q",
        "type": "single",
        "expected_bubbles": ["News"],
        "reference_answer": "a",
        "short_answers": ["Paris", "Lutetia"],
    }
    judge = NS(
        correctness=AsyncMock(return_value={"score": 2}),
        citations=AsyncMock(return_value=(0, 0, [])),
    )
    row = await score_question(
        "own", question, "the city Paris", ["a"], ["News"], [], [], {}, judge, ["a"], 1
    )
    assert row["exact_match"] == 0.0
    assert row["token_f1"] == pytest.approx(2 / 3)
    row = await score_question(
        "own", question, "Paris.", ["a"], ["News"], [], [], {}, judge, ["a"], 1
    )
    assert row["exact_match"] == 1.0 and row["token_f1"] == 1.0


async def test_score_question_without_short_answers_unchanged():
    question = {
        "id": "q",
        "question": "q",
        "type": "single",
        "expected_bubbles": ["News"],
        "reference_answer": "a",
        "short_answers": [],
    }
    judge = NS(
        correctness=AsyncMock(return_value={"score": 2}),
        citations=AsyncMock(return_value=(0, 0, [])),
    )
    row = await score_question(
        "own", question, "Paris", ["a"], ["News"], [], [], {}, judge, ["a"], 1
    )
    assert "exact_match" not in row and "token_f1" not in row
