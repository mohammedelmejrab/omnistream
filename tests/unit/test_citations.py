"""Stored-item citation numbering, parsing and generation (spec C5)."""

from datetime import datetime

import pytest

from omnistream.items import FileItemStore
from omnistream.retrieval.citations import (
    build_context,
    generate_answer,
    parse_citations,
)
from omnistream.retrieval.models import Chunk, Fact, RetrievalResult, ScoredFact


def result():
    facts = tuple(
        ScoredFact(
            Fact(
                str(i),
                "s",
                str(i),
                "leads",
                f"assertion {i}",
                "news",
                f"item{i}",
                f"https://source/{i}",
                datetime(2025, 1, i),
                credibility=0.7,
            ),
            1 / i,
        )
        for i in [1, 2]
    )
    return RetrievalResult(
        "own", facts, (Chunk("c", "chunk", "item1", "news", None, None),)
    )


def test_numbering_and_conflicts():
    context = build_context(result())
    assert [(c.number, c.item_id) for c in context.citations] == [
        (1, "item1"),
        (2, "item2"),
    ]
    assert context.citations[0].snippet == "assertion 1\nchunk"
    assert "assertion 2 (preferred)" in context.text
    assert "Conflicts" in context.text
    assert len(context.conflicts) == 1


def test_original_text_limit_and_eligibility(tmp_path):
    (tmp_path / "item1.txt").write_text("one two three four", encoding="utf-8")
    store = FileItemStore(tmp_path)
    context = build_context(
        result(), item_store=store, include_item_text_for="item1", max_item_tokens=2
    )
    assert "one two" in context.text and "three" not in context.text
    build_context(result(), item_store=store, include_item_text_for="missing")
    only_chunks = RetrievalResult("classic", chunks=result().chunks)
    assert (
        "one two"
        not in build_context(
            only_chunks, item_store=store, include_item_text_for="item1"
        ).text
    )
    with pytest.raises(ValueError, match="item_store"):
        build_context(result(), include_item_text_for="item1")
    with pytest.raises(ValueError):
        build_context(result(), max_item_tokens=-1)


def test_parse_groups_ranges_invalid_and_deduplication():
    context = build_context(result())
    parsed = parse_citations("A [2] B [1, 2] C [1-4] D [0] E [9, 9]", context)
    assert [c.number for c in parsed] == [2, 1]
    assert parsed.invalid == [3, 4, 0, 9]
    assert parse_citations("No refs [abc] [3-1]", context) == []


def test_answer_stub_and_empty_context():
    class LLM:
        def chat(self, messages):
            assert "only the numbered context" in messages[0]["content"]
            assert "Question: Who?" in messages[1]["content"]
            return "Claim [1, 2]. Bad [55]."

    answer = generate_answer(LLM(), "Who?", build_context(result()))
    assert len(answer.citations) == 2
    assert answer.invalid_citations == (55,)
    context = build_context(RetrievalResult("classic"))
    assert context.text == "(no context)"
    assert parse_citations("Claim [1]", context).invalid == [1]


@pytest.mark.parametrize(
    "reference,bounds", [("[1-1000000]", [1, 1000000]), ("[5-2]", [5, 2])]
)
def test_oversized_and_reversed_ranges_are_invalid_without_expansion(reference, bounds):
    parsed = parse_citations(reference, build_context(result()))
    assert list(parsed) == []
    assert parsed.invalid == bounds


def test_invalid_range_bounds_do_not_hide_later_valid_references():
    parsed = parse_citations("[1] [1-1000000] [5-2] [2]", build_context(result()))
    assert [c.number for c in parsed] == [1, 2]
    assert parsed.invalid == [1, 1000000, 5, 2]


def test_cluster_context_renders_all_sides_with_one_preference():
    from dataclasses import replace

    original = result()
    third = ScoredFact(
        replace(
            original.facts[1].fact,
            id="3",
            object_id="3",
            item_id="item3",
            text="assertion 3",
            published_at=datetime(2025, 1, 3),
        ),
        0.1,
    )
    context = build_context(replace(original, facts=(*original.facts, third)))
    assert len(context.conflicts) == 1
    assert context.text.count("Subject s; relation leads:") == 1
    assert context.text.count("(preferred)") == 1
    assert "[3] assertion 3 (preferred)" in context.text
    assert "all assertions retained" in context.text


def test_context_threads_canonical_ids_for_cross_bubble_conflicts():
    from dataclasses import replace

    original = result()
    a, b = original.facts
    b = replace(b, fact=replace(b.fact, subject_id="finance-s", bubble="finance"))
    context = build_context(
        replace(original, facts=(a, b)),
        canonical_ids={"s": "global-s", "finance-s": "global-s"},
    )
    assert len(context.conflicts) == 1
    assert "Subject global-s; relation leads:" in context.text
    assert "assertion 2 (preferred)" in context.text


def test_parse_citations_rejects_5000_digit_numbers_without_conversion():
    huge = "9" * 5000
    parsed = parse_citations(
        f"[{huge}] [1, {huge}] [1-{huge}] [{huge}-2] [2]", build_context(result())
    )
    assert [c.number for c in parsed] == [1, 2]
    assert parsed.invalid == [-1]
