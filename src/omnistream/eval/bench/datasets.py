"""HippoRAG 2 released benchmark subsets: loading, gold mapping, sampling.

Gold passages follow HippoRAG 2's ``get_gold_docs`` definition: each gold doc
is ``title + "\\n" + text`` built from the question's own supporting fields.
Corpus docs use the same string form, so gold docs are mapped to corpus
passage ids by exact match, then whitespace-normalised match, then title-only
match when the title is unique in the corpus. Gold docs that match nothing are
counted in ``Benchmark.unmatched_gold`` and never silently dropped.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

# Canonical name -> released HippoRAG 2 file stem inside ``root``.
DATASET_FILES = {
    "musique": "musique",
    "2wiki": "2wikimultihopqa",
    "hotpotqa": "hotpotqa",
}
DATASET_ALIASES = {"2wikimultihopqa": "2wiki"}


@dataclass
class Passage:
    id: str
    title: str
    text: str


@dataclass
class BenchQuestion:
    id: str
    question: str
    answers: list[str]
    gold_passage_ids: list[str]
    qtype: str


@dataclass
class Benchmark:
    name: str
    questions: list[BenchQuestion]
    passages: list[Passage]
    unmatched_gold: int

    def write_manifest(self, path) -> str:
        """Write the sampled question ids for reproducibility."""
        payload = {
            "dataset": self.name,
            "question_count": len(self.questions),
            "question_ids": [q.id for q in self.questions],
            "corpus_passages": len(self.passages),
            "unmatched_gold": self.unmatched_gold,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return str(path)


def _whitespace_normalised(text: str) -> str:
    return " ".join(text.split())


def _parse_musique(item: dict) -> tuple:
    gold_docs, context_docs = [], []
    for para in item.get("paragraphs", []):
        doc = str(para.get("title", "")) + "\n" + str(para.get("paragraph_text", ""))
        context_docs.append(doc)
        if para.get("is_supporting"):
            gold_docs.append(doc)
    answers = [str(item.get("answer", "")), *item.get("answer_aliases", [])]
    qtype = str(item.get("id", "")).split("__", 1)[0] or "unknown"
    return str(item["id"]), item["question"], answers, gold_docs, qtype, context_docs


def _parse_2wiki(item: dict) -> tuple:
    supporting = {title for title, _ in item.get("supporting_facts", [])}
    gold_docs, context_docs = [], []
    for title, sentences in item.get("context", []):
        doc = title + "\n" + " ".join(sentences)
        context_docs.append(doc)
        if title in supporting:
            gold_docs.append(doc)
    return str(item["_id"]), item["question"], [item.get("answer", "")], gold_docs, str(item.get("type", "")), context_docs


def _parse_hotpotqa(item: dict) -> tuple:
    supporting = {title for title, _ in item.get("supporting_facts", [])}
    gold_docs, context_docs = [], []
    for title, sentences in item.get("context", []):
        doc = title + "\n" + "".join(sentences)
        context_docs.append(doc)
        if title in supporting:
            gold_docs.append(doc)
    return str(item["_id"]), item["question"], [item.get("answer", "")], gold_docs, str(item.get("type", "")), context_docs


PARSERS = {
    "musique": _parse_musique,
    "2wiki": _parse_2wiki,
    "hotpotqa": _parse_hotpotqa,
}


def load_benchmark(
    name: str,
    *,
    root: str | Path = "data/bench/hipporag",
    n: int | None = None,
    seed: int = 0,
    corpus: str = "full",
    exclude_sample: tuple[int, int] | None = None,
) -> Benchmark:
    """Load a HippoRAG benchmark subset.

    ``n`` samples ``random.Random(seed).sample`` questions out of the full
    released set and keeps them in original file order. ``corpus`` selects the
    full released corpus (HippoRAG setting) or the slice of passages that the
    sampled questions actually reference (always including every matched gold
    passage).

    ``exclude_sample=(n0, seed0)`` first removes the questions that
    ``load_benchmark(name, n=n0, seed=seed0)`` would select (a development set),
    then samples ``n`` from the rest, so test questions never overlap it.
    """
    canonical = DATASET_ALIASES.get(name, name)
    if canonical not in DATASET_FILES:
        raise ValueError(
            f"unknown benchmark {name!r}; expected one of {sorted(set(DATASET_FILES) | set(DATASET_ALIASES))}"
        )
    if corpus not in ("full", "slice"):
        raise ValueError("corpus must be 'full' or 'slice'")
    root = Path(root)
    stem = DATASET_FILES[canonical]
    raw_questions = json.loads(
        (root / f"{stem}.json").read_text(encoding="utf-8")
    )
    raw_corpus = json.loads(
        (root / f"{stem}_corpus.json").read_text(encoding="utf-8")
    )

    passages = [
        Passage(id=f"{canonical}-{index}", title=entry["title"], text=entry["text"])
        for index, entry in enumerate(raw_corpus)
    ]
    exact_index, whitespace_index, title_index = {}, {}, {}
    for passage in passages:
        doc = passage.title + "\n" + passage.text
        exact_index[doc] = passage.id
        whitespace_index.setdefault(_whitespace_normalised(doc), passage.id)
        title_index.setdefault(passage.title, []).append(passage.id)

    def match(doc: str) -> str | None:
        passage_id = exact_index.get(doc)
        if passage_id is not None:
            return passage_id
        passage_id = whitespace_index.get(_whitespace_normalised(doc))
        if passage_id is not None:
            return passage_id
        candidates = title_index.get(doc.split("\n", 1)[0], [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    parsed = [PARSERS[canonical](item) for item in raw_questions]
    indices = list(range(len(parsed)))
    if exclude_sample is not None:
        dev_n, dev_seed = exclude_sample
        dev = (
            set(random.Random(dev_seed).sample(indices, dev_n))
            if dev_n < len(indices)
            else set(indices)
        )
        indices = [i for i in indices if i not in dev]
    if n is not None and n < len(indices):
        indices = sorted(random.Random(seed).sample(indices, n))

    questions: list[BenchQuestion] = []
    unmatched = 0
    slice_ids: set[str] = set()
    for index in indices:
        qid, question, answers, gold_docs, qtype, context_docs = parsed[index]
        gold_ids: list[str] = []
        for doc in gold_docs:
            passage_id = match(doc)
            if passage_id is None:
                unmatched += 1
            elif passage_id not in gold_ids:
                gold_ids.append(passage_id)
        if corpus == "slice":
            for doc in context_docs:
                passage_id = match(doc)
                if passage_id is not None:
                    slice_ids.add(passage_id)
            slice_ids.update(gold_ids)
        questions.append(
            BenchQuestion(
                id=qid,
                question=question,
                answers=list(dict.fromkeys(answers)),
                gold_passage_ids=gold_ids,
                qtype=qtype,
            )
        )
    selected = (
        passages
        if corpus == "full"
        else [p for p in passages if p.id in slice_ids]
    )
    return Benchmark(canonical, questions, selected, unmatched)
