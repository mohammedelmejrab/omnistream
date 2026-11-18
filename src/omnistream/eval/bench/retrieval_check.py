"""Retrieval-only check over the HippoRAG benchmark subsets.

No LLM is involved: dense (sentence-transformers) or BM25 retrievers rank
passages per question and we report Recall@2/@5/@10/@20, nDCG@10 and MRR with
bootstrap confidence intervals, so the numbers can be compared against the
published HippoRAG retrieval rows (different setting, reported separately).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from omnistream.config import DEFAULT_EMBEDDING_MODEL

from .datasets import DATASET_ALIASES, DATASET_FILES, Benchmark, load_benchmark
from .metrics import bootstrap_ci, ndcg_at_k, recall_at_k

TOP_K = 20
METRICS = ("recall_at_2", "recall_at_5", "recall_at_10", "recall_at_20", "ndcg_at_10", "mrr")

# HippoRAG 1 (NeurIPS 2024) Table 2, single-step passage retrieval R@2/R@5.
# Published numbers on the full benchmarks with their retrievers and corpus
# settings; shown only as an external reference, never mixed with our results.
HIPPORAG1_TABLE2_SINGLE_STEP = {
    "musique": {
        "BM25": (32.3, 41.2),
        "Contriever": (34.8, 46.6),
        "GTR": (37.4, 49.1),
        "ColBERTv2": (37.9, 49.2),
        "HippoRAG (ColBERTv2)": (40.9, 51.9),
    },
    "2wiki": {
        "BM25": (51.8, 61.9),
        "Contriever": (46.6, 57.5),
        "GTR": (60.2, 67.9),
        "ColBERTv2": (59.2, 68.2),
        "HippoRAG (ColBERTv2)": (70.7, 89.1),
    },
    "hotpotqa": {
        "BM25": (55.4, 72.2),
        "Contriever": (57.2, 75.5),
        "GTR": (59.4, 73.3),
        "ColBERTv2": (64.7, 79.3),
        "HippoRAG (ColBERTv2)": (60.5, 77.7),
    },
}

# Model-family query/passage prefixes; anything else encodes both unprefixed.
MODEL_PREFIXES = (
    (re.compile(r"^baai/bge-.*-en-v1\.5$"), ("Represent this sentence for searching relevant passages: ", "")),
    (re.compile(r"^intfloat/e5-.*$"), ("query: ", "passage: ")),
    # Instruction-tuned decoders: query instruction only. Same task wording
    # HippoRAG 2 uses for NV-Embed-v2 queries.
    (
        re.compile(r"^(qwen/qwen3-embedding-.*|alibaba-nlp/gte-qwen2-.*)$"),
        (
            ("Instruct: Given a question, retrieve relevant documents that best "
            "answer the question\nQuery: "),
            "",
        ),
    ),
)


def query_passage_prefixes(model_name: str) -> tuple[str, str]:
    name = str(model_name).strip().lower()
    for pattern, prefixes in MODEL_PREFIXES:
        if pattern.match(name):
            return prefixes
    return ("", "")


def sanitise_model_name(model_name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "-", str(model_name).strip()).strip("-").lower()


def default_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def load_encoder(model_name: str, device: str | None = None):
    from sentence_transformers import SentenceTransformer

    if device is None:
        device = default_device()
    kwargs = {}
    if device == "cuda":
        import torch

        # fp16 halves memory so 0.6B-1.5B embedders fit a 6 GB laptop GPU.
        kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
    return SentenceTransformer(
        model_name, device=device, trust_remote_code=True, **kwargs
    )


class DenseRetriever:
    """Cosine top-k over normalised sentence-transformer embeddings.

    ``encoder`` needs only ``.encode(list[str], **kw)`` per call, so tests can
    inject a deterministic fake. Passage embeddings are cached under
    ``cache_dir`` keyed by dataset, model and corpus-content hash.
    """

    def __init__(
        self,
        dataset: str,
        passages,
        encoder,
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
        batch_size: int = 32,
        cache_dir: str | Path | None = None,
        model_name: str = "encoder",
    ) -> None:
        import numpy as np

        self.passages = list(passages)
        self.encoder = encoder
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.batch_size = batch_size
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.model_name = model_name
        self.encode_seconds = 0.0
        texts = [passage_prefix + f"{p.title}\n{p.text}" for p in self.passages]
        corpus_digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:12]
        cache_path = None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self.cache_dir / (
                f"{dataset}__{sanitise_model_name(model_name)}__{corpus_digest}.npy"
            )
            if cache_path.exists():
                matrix = np.load(cache_path)
                if matrix.shape[0] == len(texts):
                    self.matrix = matrix
                    return
        started = time.perf_counter()
        rows = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            rows.extend(self.encoder.encode(batch, batch_size=self.batch_size))
        matrix = np.asarray(rows, dtype=np.float32)
        if matrix.shape[0] != len(texts):
            raise ValueError(
                f"encoder returned {matrix.shape[0]} embeddings for {len(texts)} passages"
            )
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        self.matrix = matrix / norms
        self.encode_seconds = time.perf_counter() - started
        if cache_path is not None:
            np.save(cache_path, self.matrix)

    def search(self, query: str, top_k: int = TOP_K) -> list[str]:
        import numpy as np

        vector = np.asarray(
            self.encoder.encode([self.query_prefix + query])[0], dtype=np.float32
        )
        norm = float(np.linalg.norm(vector))
        sims = self.matrix @ (vector / (norm or 1.0))
        order = np.argsort(-sims, kind="stable")[:top_k]
        return [self.passages[i].id for i in order]


class BM25Retriever:
    """Thin adapter over the harness BM25 index (documents: title + text)."""

    def __init__(self, passages) -> None:
        from omnistream.retrieval.sparse import BM25Index

        self.passages = list(passages)
        self.index = BM25Index({p.id: f"{p.title}\n{p.text}" for p in self.passages})
        self.encode_seconds = 0.0

    def search(self, query: str, top_k: int = TOP_K) -> list[str]:
        return [doc_id for doc_id, _ in self.index.search(query, top_k)]


def question_metrics(ranked_ids: list[str], gold_ids: list[str]) -> dict:
    gold = set(gold_ids)
    rank = next(
        (position for position, item in enumerate(dict.fromkeys(ranked_ids), 1) if item in gold),
        None,
    )
    return {
        "recall_at_2": recall_at_k(ranked_ids, gold_ids, 2),
        "recall_at_5": recall_at_k(ranked_ids, gold_ids, 5),
        "recall_at_10": recall_at_k(ranked_ids, gold_ids, 10),
        "recall_at_20": recall_at_k(ranked_ids, gold_ids, 20),
        "ndcg_at_10": ndcg_at_k(ranked_ids, gold_ids, 10),
        "mrr": 1.0 / rank if rank else 0.0,
    }


def run_retrieval_check(
    benchmark: Benchmark,
    *,
    retriever: str = "dense",
    model: str = DEFAULT_EMBEDDING_MODEL,
    encoder=None,
    device: str | None = None,
    batch_size: int = 32,
    top_k: int = TOP_K,
    cache_dir: str | Path = "data/bench/cache",
    use_cache: bool = True,
    n_resamples: int = 10000,
    seed: int = 0,
) -> dict:
    """Rank passages for every question and aggregate the retrieval metrics."""
    if retriever not in ("dense", "bm25"):
        raise ValueError("retriever must be 'dense' or 'bm25'")
    wall_started = time.perf_counter()
    if retriever == "dense":
        if encoder is None:
            encoder = load_encoder(model, device)
        query_prefix, passage_prefix = query_passage_prefixes(model)
        engine = DenseRetriever(
            benchmark.name,
            benchmark.passages,
            encoder,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
            batch_size=batch_size,
            cache_dir=cache_dir if use_cache else None,
            model_name=model,
        )
    else:
        engine = BM25Retriever(benchmark.passages)
    encode_seconds = engine.encode_seconds
    rows = []
    search_seconds = 0.0
    for question in benchmark.questions:
        started = time.perf_counter()
        ranked = engine.search(question.question, top_k)
        search_seconds += time.perf_counter() - started
        row = {
            "id": question.id,
            "question": question.question,
            "answers": question.answers,
            "qtype": question.qtype,
            "gold_passage_ids": question.gold_passage_ids,
            "ranked_ids": ranked,
        }
        row.update(question_metrics(ranked, question.gold_passage_ids))
        rows.append(row)

    aggregates = {}
    for metric in METRICS:
        mean, low, high = bootstrap_ci(
            [row[metric] for row in rows],
            n_resamples=n_resamples,
            seed=seed,
        )
        aggregates[metric] = {"mean": mean, "ci_low": low, "ci_high": high}
    by_qtype = {}
    for qtype in dict.fromkeys(row["qtype"] for row in rows):
        group = [row for row in rows if row["qtype"] == qtype]
        by_qtype[qtype] = {
            "questions": len(group),
            **{metric: sum(row[metric] for row in group) / len(group) for metric in METRICS},
        }
    return {
        "dataset": benchmark.name,
        "retriever": retriever,
        "model": model if retriever == "dense" else None,
        "question_count": len(rows),
        "passage_count": len(benchmark.passages),
        "unmatched_gold": benchmark.unmatched_gold,
        "aggregates": aggregates,
        "by_qtype": by_qtype,
        "timing": {
            "encode_seconds": encode_seconds,
            "search_seconds": search_seconds,
            "wall_seconds": time.perf_counter() - wall_started,
        },
        "questions": rows,
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_summary(result: dict) -> str:
    dataset = result["dataset"]
    timing = result["timing"]
    lines = [
        f"# Bench retrieval check: {dataset} / {result['retriever']}",
        "",
        (
            f"{result['question_count']} questions, "
            f"{result['passage_count']} corpus passages, "
            f"{result['unmatched_gold']} unmatched gold docs."
        ),
        (
            f"Retriever: {result['retriever']}"
            + (f" ({result['model']})" if result.get("model") else "")
            + f"; corpus: {result['settings']['corpus']}; seed: {result['settings']['seed']}."
        ),
        "",
        "## Our numbers",
        "",
        "| Metric | Value | 95% CI |",
        "|---|---|---|",
    ]
    for metric, values in result["aggregates"].items():
        lines.append(
            f"| {metric} | {values['mean']:.4f} | [{values['ci_low']:.4f}, {values['ci_high']:.4f}] |"
        )
    lines += [
        "",
        "## By question type",
        "",
        "| Type | Questions | " + " | ".join(METRICS) + " |",
        "|---|---|" + "---|" * (len(METRICS) + 1),
    ]
    for qtype, values in result["by_qtype"].items():
        lines.append(
            f"| {qtype} | {values['questions']} | "
            + " | ".join(f"{values[m]:.4f}" for m in METRICS)
            + " |"
        )
    lines += [
        "",
        (
            f"Timing: passage encoding {timing['encode_seconds']:.1f}s, "
            f"queries {timing['search_seconds']:.1f}s, wall {timing['wall_seconds']:.1f}s."
        ),
        "",
        "## Reference (published, different setting)",
        "",
        "HippoRAG 1 Table 2 single-step passage Recall@2 / Recall@5 for this dataset,",
        "with their retrievers and corpus settings; not directly comparable to our numbers above:",
        "",
        "| Retriever | R@2 | R@5 |",
        "|---|---|---|",
    ]
    for retriever, (r2, r5) in HIPPORAG1_TABLE2_SINGLE_STEP.get(dataset, {}).items():
        lines.append(f"| {retriever} | {r2:.1f} | {r5:.1f} |")
    lines.append("")
    return "\n".join(lines)


def run_bench_retrieval_cli(args) -> int:
    """``omni eval bench-retrieval`` entry: run the check, write JSON + Markdown."""
    dataset = DATASET_ALIASES.get(args.dataset, args.dataset)
    if dataset not in DATASET_FILES:
        raise SystemExit(f"unknown benchmark dataset {args.dataset!r}")
    root = Path(args.bench_root)
    # argparse leaves --corpus unset (None) so bench-ingest can default to the
    # slice; this retrieval-only check keeps its historic full-corpus default.
    corpus = args.corpus or "full"
    benchmark = load_benchmark(
        dataset,
        root=root,
        n=args.n,
        seed=args.seed,
        corpus=corpus,
    )
    if args.manifest:
        benchmark.write_manifest(args.manifest)
    result = run_retrieval_check(
        benchmark,
        retriever=args.retriever,
        model=args.model,
        device=args.device,
        batch_size=args.batch_size,
        cache_dir=Path(root).parent / "cache",
        use_cache=not args.no_cache,
    )
    stem = DATASET_FILES[dataset]
    result["settings"] = {
        "dataset": dataset,
        "retriever": args.retriever,
        "model": args.model if args.retriever == "dense" else None,
        "device": args.device or "auto",
        "n": args.n,
        "seed": args.seed,
        "corpus": corpus,
        "batch_size": args.batch_size,
        "root": str(root),
    }
    result["data_sha256"] = {
        f"{stem}.json": _file_sha256(root / f"{stem}.json"),
        f"{stem}_corpus.json": _file_sha256(root / f"{stem}_corpus.json"),
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = (
        Path(args.out)
        / f"{dataset}-{args.retriever}-{sanitise_model_name(args.model)}"
        f"-n{args.n if args.n is not None else 'all'}-s{args.seed}-{stamp}"
    )
    base.parent.mkdir(parents=True, exist_ok=True)
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(markdown_summary(result), encoding="utf-8")
    aggregates = result["aggregates"]
    print(
        f"{dataset}/{args.retriever}: "
        + ", ".join(
            f"{metric}={aggregates[metric]['mean']:.4f}"
            f" [{aggregates[metric]['ci_low']:.4f}, {aggregates[metric]['ci_high']:.4f}]"
            for metric in METRICS
        )
    )
    print(f"unmatched gold docs: {result['unmatched_gold']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0
