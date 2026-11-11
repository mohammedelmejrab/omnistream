"""Citation highlight spans into stored clean text (spec 6/C5)."""

from datetime import datetime

import pytest

from omnistream.items import FileItemStore
from omnistream.retrieval.citations import build_context, highlight
from omnistream.retrieval.models import Chunk, Fact, RetrievalResult, ScoredFact

TEXT = "the quick brown fox jumps over the lazy dog"


class Store:
    """Minimal ItemStore returning single-spaced text; missing items raise KeyError."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = dict(texts)

    def item_text(self, item_id: str, max_tokens: int = 4000) -> str:
        return " ".join(self.texts[item_id].split()[:max_tokens])


def _fact(text: str, item_id: str, fact_id: str = "f") -> ScoredFact:
    return ScoredFact(
        Fact(
            fact_id,
            "s",
            "o",
            "relates to",
            text,
            "news",
            item_id,
            f"https://source/{item_id}",
            datetime(2025, 1, 1),
        ),
        1.0,
    )


def _citations(evidence, texts):
    result = RetrievalResult(
        "own",
        tuple(e for e in evidence if isinstance(e, ScoredFact)),
        tuple(e for e in evidence if isinstance(e, Chunk)),
    )
    return build_context(result, item_store=Store(texts)).citations


def test_exact_match_span():
    (citation,) = _citations([_fact("quick brown fox", "item1")], {"item1": TEXT})
    assert citation.spans == ((4, 19),)


def test_case_insensitive_match_span():
    (citation,) = _citations(
        [_fact("quick brown fox", "item1")], {"item1": "The Quick Brown Fox"}
    )
    assert citation.spans == ((4, 19),)


def test_whitespace_normalised_match_span():
    stored = "alpha beta gamma delta epsilon"
    (citation,) = _citations([_fact("beta\ngamma", "item1")], {"item1": stored})
    assert citation.spans == ((6, 16),)
    assert (
        highlight(stored, citation.spans)
        == "alpha <mark>beta gamma</mark> delta epsilon"
    )


@pytest.mark.parametrize(
    "passage,expected",
    [
        (
            "quick brown fox leaps over the lazy dog",
            ((4, 43),),
        ),  # fuzzy score 92.3 >= 90
        ("quick brown fox jumps over a sleepy dog", ()),  # fuzzy score 87.2 < 90
    ],
)
def test_fuzzy_paraphrase_accepted_and_rejected(passage, expected):
    (citation,) = _citations([_fact(passage, "item1")], {"item1": TEXT})
    assert citation.spans == expected


def test_multiple_passages_sorted_and_merged():
    evidence = [
        _fact("lazy dog", "item1", "f1"),
        Chunk("c", "jumps over", "item1", "news", None, None),
        _fact("quick brown", "item1", "f2"),
        _fact(
            "brown fox", "item1", "f3"
        ),  # overlaps "quick brown": merged into one span
    ]
    (citation,) = _citations(evidence, {"item1": TEXT})
    assert citation.spans == ((4, 19), (20, 30), (35, 43))


def test_missing_item_tolerated():
    citations = _citations(
        [_fact("passage one", "item1"), _fact("passage two", "item2")],
        {"item1": "passage one"},
    )
    assert citations[0].spans == ((0, 11),)
    assert citations[1].spans == ()
    assert citations[1].snippet == "passage two"


def test_no_item_store_means_no_spans():
    result = RetrievalResult("own", (_fact("quick brown fox", "item1"),))
    (citation,) = build_context(result).citations
    assert citation.spans == ()


def test_unexpected_store_error_propagates():
    class Exploding:
        def item_text(self, item_id, max_tokens=4000):
            raise RuntimeError(f"store bug for {item_id}")

    result = RetrievalResult("own", (_fact("quick brown fox", "item1"),))
    with pytest.raises(RuntimeError, match="store bug"):
        build_context(result, item_store=Exploding())


def test_keyerror_for_one_item_leaves_only_that_item_without_spans():
    class Partial:
        def item_text(self, item_id, max_tokens=4000):
            if item_id == "missing":
                raise KeyError(item_id)
            return TEXT

    result = RetrievalResult(
        "own", (_fact("quick brown fox", "item1"), _fact("lazy dog", "missing"))
    )
    (first, second) = build_context(result, item_store=Partial()).citations
    assert first.spans == ((4, 19),)
    assert second.spans == ()


def test_store_without_item_text_gives_no_spans_and_no_error():
    class ReadOnly:
        def read_item(self, item_id, part=1):
            raise AssertionError("read_item must not be called for spans")

    result = RetrievalResult("own", (_fact("quick brown fox", "item1"),))
    context = build_context(result, item_store=ReadOnly())
    (citation,) = context.citations
    assert citation.spans == ()
    assert citation.snippet == "quick brown fox"
    assert "quick brown fox" in context.text


def test_span_loading_fetches_each_cited_item_once():
    calls = []

    class Recording:
        def item_text(self, item_id, max_tokens=4000):
            calls.append(item_id)
            return TEXT

    result = RetrievalResult(
        "own",
        (
            _fact("lazy dog", "item1", "f1"),
            _fact("brown fox", "item1", "f3"),
            _fact("quick brown", "item2", "f2"),
        ),
        (Chunk("c", "jumps over", "item1", "news", None, None),),
    )
    citations = build_context(result, item_store=Recording()).citations
    # Only the cited items are fetched, each exactly once, in rank order.
    assert calls == ["item1", "item2"]
    assert len(citations) == 2
    assert citations[0].spans == ((10, 19), (20, 30), (35, 43))
    assert citations[1].spans == ((4, 15),)


def test_fuzzy_alignment_skipped_above_cap_for_long_originals():
    long_text = "intro. " + "the quick brown fox jumps over the lazy dog. " * 5000
    assert len(long_text) > 200_000
    # The paraphrase matches TEXT fuzzily at score 92.3 >= 90 (see
    # test_fuzzy_paraphrase_accepted_and_rejected) but matches neither
    # exactly nor after normalisation, so the cap leaves it unlocated.
    (citation,) = _citations(
        [_fact("quick brown fox leaps over the lazy dog", "item1")],
        {"item1": long_text},
    )
    assert citation.spans == ()
    # Exact substring matching still applies to long originals.
    exact = "jumps over the lazy dog"
    (citation,) = _citations([_fact(exact, "item1")], {"item1": long_text})
    start = long_text.find(exact)
    assert citation.spans == ((start, start + len(exact)),)


def test_highlight_inserts_markers_from_the_end():
    assert (
        highlight("the quick brown fox", [(4, 15)])
        == "the <mark>quick brown</mark> fox"
    )
    assert (
        highlight("abcdefghij", [(0, 2), (5, 7)])
        == "<mark>ab</mark>cde<mark>fg</mark>hij"
    )
    assert highlight("hello", [(0, 3)], open="[", close="]") == "[hel]lo"


def test_highlight_clamps_rejects_and_merges_safely():
    assert highlight("hello", [(3, 99)]) == "hel<mark>lo</mark>"  # end clamped
    assert highlight("hello", [(10, 20), (5, 2), (3, 3), None, ("x", "y")]) == "hello"
    assert (
        highlight("abcdefgh", [(2, 6), (0, 4)]) == "<mark>abcdef</mark>gh"
    )  # overlap merged
    assert highlight("hello", []) == "hello"


def test_file_item_store_end_to_end(tmp_path):
    (tmp_path / "item1.txt").write_text(
        "alpha beta gamma\n\ndelta epsilon zeta", encoding="utf-8"
    )
    store = FileItemStore(tmp_path)
    stored = store.item_text("item1")  # single-spaced, the text the UI displays
    assert stored == "alpha beta gamma delta epsilon zeta"
    result = RetrievalResult(
        "own",
        (_fact("beta gamma\ndelta epsilon", "item1"),),
        (Chunk("c1", "epsilon zeta", "item1", "news", None, None),),
    )
    (citation,) = build_context(result, item_store=store).citations
    expected = (
        (
            stored.index("beta gamma"),
            stored.index("epsilon zeta") + len("epsilon zeta"),
        ),
    )
    assert citation.spans == expected
    assert (
        highlight(stored, citation.spans)
        == "alpha <mark>beta gamma delta epsilon zeta</mark>"
    )


@pytest.mark.parametrize(
    "error",
    [
        IndexError("list index out of range"),
        ValueError("invalid item id"),
        OSError("device failure"),
    ],
)
def test_store_programming_and_io_errors_propagate(error):
    class Broken:
        def item_text(self, item_id, max_tokens=4000):
            raise error

    with pytest.raises(type(error), match=str(error)):
        build_context(
            RetrievalResult("own", (_fact("passage", "item"),)), item_store=Broken()
        )


@pytest.mark.parametrize(
    "text,passage,expected",
    [
        ("\u0130 TARGET", "target", "\u0130 <mark>TARGET</mark>"),
        ("Stra\u00dfe", "STRASSE", "<mark>Stra\u00dfe</mark>"),
        (
            "prefix Stra\u00dfe  target end",
            "STRASSE\ntarget",
            "prefix <mark>Stra\u00dfe  target</mark> end",
        ),
    ],
)
def test_unicode_casefold_highlight_roundtrip(text, passage, expected):
    from omnistream.retrieval.citations import _locate

    span = _locate(text, passage)
    assert span is not None
    marked = highlight(text, [span])
    assert marked == expected
    assert marked.replace("<mark>", "").replace("</mark>", "") == text


@pytest.mark.parametrize("error", [KeyError("missing"), FileNotFoundError("missing")])
def test_unavailable_expansion_fetched_once_and_omitted(error):
    calls = []

    class Missing:
        def item_text(self, item_id, max_tokens=4000):
            calls.append(item_id)
            raise error

    context = build_context(
        RetrievalResult("own", (_fact("evidence", "missing"),)),
        item_store=Missing(),
        include_item_text_for="missing",
    )
    assert calls == ["missing"]
    assert context.text == "[1] evidence"
    assert context.citations[0].spans == ()
    assert context.expanded_item_id is None
