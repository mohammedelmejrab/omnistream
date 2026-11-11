import math

import numpy as np
import pytest

from omnistream.retrieval.fusion import (
    FusedResult,
    RankedItem,
    ranks_from_scores,
    reciprocal_rank_fusion,
)

R = RankedItem


def pairs(ranked):
    return [(r.id, r.rank) for r in ranked]


def ids(results):
    return [r.id for r in results]


# ------------------------------------------------------------ empty inputs
@pytest.mark.parametrize(
    "rankings", [[], {}, [[]], [[], []], {"dense": [], "sparse": []}]
)
def test_empty_inputs_return_empty(rankings):
    assert reciprocal_rank_fusion(rankings) == []


def test_one_empty_list_is_ignored():
    fused = reciprocal_rank_fusion({"dense": ["a", "b"], "sparse": []})
    assert ids(fused) == ["a", "b"]
    assert fused[0].ranks == {"dense": 1}


def test_single_list_preserves_order_and_scores():
    fused = reciprocal_rank_fusion([["x", "y", "z"]], k=60)
    assert ids(fused) == ["x", "y", "z"]
    assert [r.score for r in fused] == pytest.approx([1 / 61, 1 / 62, 1 / 63])


# ------------------------------------------------------- overlapping ranks
def test_overlap_sums_contributions():
    fused = reciprocal_rank_fusion(
        {"dense": ["a", "b", "c"], "sparse": ["c", "a", "d"]}, k=60
    )
    by_id = {r.id: r for r in fused}
    assert by_id["a"].score == pytest.approx(1 / 61 + 1 / 62)
    assert by_id["c"].score == pytest.approx(1 / 63 + 1 / 61)
    assert by_id["b"].score == pytest.approx(1 / 62)
    assert by_id["d"].score == pytest.approx(1 / 63)
    assert by_id["a"].ranks == {"dense": 1, "sparse": 2}
    assert ids(fused) == ["a", "c", "b", "d"]


def test_item_in_both_lists_beats_top_of_one():
    fused = reciprocal_rank_fusion([["solo", "both"], ["x", "both"]])
    assert fused[0].id == "both"


def test_identical_lists_keep_order():
    fused = reciprocal_rank_fusion([["a", "b", "c"]] * 3)
    assert ids(fused) == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(3 / 61)


def test_reversed_lists_produce_exact_ties_resolved_deterministically():
    # a = c = 1/61 + 1/63 (~0.032266) > b = 2/62 (~0.032258).
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "a"]])
    assert fused[0].score == fused[1].score
    assert fused[1].score > fused[2].score
    assert ids(fused) == ["a", "c", "b"]  # a/c tie -> first appearance


def test_duplicate_within_a_list_counts_once_at_best_rank():
    fused = reciprocal_rank_fusion([["a", "b", "a", "a"]])
    by_id = {r.id: r for r in fused}
    assert by_id["a"].score == pytest.approx(1 / 61)
    assert by_id["a"].ranks == {"0": 1}
    assert by_id["b"].ranks == {"0": 2}


# --------------------------------------------------------------- ties
def test_fused_score_tie_broken_by_best_individual_rank():
    # p: rank 1 + rank 3 ; q: rank 2 + rank 2 -> q scores higher (convexity),
    # so construct an exact tie with weights instead.
    fused = reciprocal_rank_fusion(
        {"A": ["p"], "B": ["x", "q"]}, k=0, weights={"A": 0.5, "B": 1.0}
    )
    # p = 0.5/1, q = 1/2 -> exact tie; p has best rank 1, q best rank 2.
    by_id = {r.id: r for r in fused}
    assert by_id["p"].score == by_id["q"].score
    assert ids(fused).index("p") < ids(fused).index("q")


def test_tie_broken_by_list_count_when_best_rank_equal():
    # m: rank 2 in A and rank 2 in B with weight 0.5 each = 1/2*... use k=0:
    # m = 0.5/2 + 0.5/2 = 0.5 ; n = 1.0/2 = 0.5 ; both best rank 2.
    fused = reciprocal_rank_fusion(
        {"A": ["x", "n"], "B": ["y", "m"], "C": ["z", "m"]},
        k=0,
        weights={"A": 1.0, "B": 0.5, "C": 0.5},
    )
    by_id = {r.id: r for r in fused}
    assert by_id["m"].score == pytest.approx(by_id["n"].score)
    assert ids(fused).index("m") < ids(fused).index("n")


def test_tied_input_scores_share_rank_and_fused_score():
    dense = ranks_from_scores({"a": 0.9, "b": 0.9, "c": 0.5})
    assert pairs(dense) == [("a", 1), ("b", 1), ("c", 3)]
    fused = reciprocal_rank_fusion({"dense": dense})
    assert fused[0].score == fused[1].score == pytest.approx(1 / 61)
    assert fused[2].score == pytest.approx(1 / 63)


def test_explicit_rank_pairs_and_unsorted_duplicates():
    fused = reciprocal_rank_fusion({"s": [R("a", 5), R("a", 2), R("b", 3)]})
    by_id = {r.id: r for r in fused}
    assert by_id["a"].ranks == {"s": 2}
    assert by_id["a"].score == pytest.approx(1 / 62)
    assert ids(fused) == ["a", "b"]


def test_output_is_deterministic_across_runs():
    rankings = {"d": ["e", "a", "c", "b"], "s": ["b", "e", "d"], "g": ["c", "d", "a"]}
    first = reciprocal_rank_fusion(rankings)
    for _ in range(5):
        assert reciprocal_rank_fusion(rankings) == first


# --------------------------------------------------- parameters & errors
def test_k_controls_top_rank_dominance():
    rankings = {"A": ["top", "mid"], "B": ["other", "mid"]}
    assert reciprocal_rank_fusion(rankings, k=60)[0].id == "mid"
    # With k=0, rank 1 (=1.0) beats two rank-2 hits (=0.5+0.5) only on tie-break.
    low_k = reciprocal_rank_fusion(rankings, k=0)
    assert low_k[0].id == "top"


def test_weights_mapping_and_sequence_are_equivalent():
    r = {"dense": ["a", "b"], "sparse": ["b", "a"]}
    by_map = reciprocal_rank_fusion(r, weights={"dense": 2.0})
    by_seq = reciprocal_rank_fusion(r, weights=[2.0, 1.0])
    assert by_map == by_seq
    assert by_map[0].id == "a"


def test_zero_weight_list_contributes_nothing_but_records_rank():
    fused = reciprocal_rank_fusion(
        {"dense": ["a"], "sparse": ["b"]}, weights={"sparse": 0.0}
    )
    by_id = {r.id: r for r in fused}
    assert by_id["b"].score == 0.0
    assert by_id["b"].ranks == {"sparse": 1}
    assert ids(fused) == ["a", "b"]


def test_top_n():
    r = [["a", "b", "c", "d"]]
    assert ids(reciprocal_rank_fusion(r, top_n=2)) == ["a", "b"]
    assert reciprocal_rank_fusion(r, top_n=0) == []
    assert len(reciprocal_rank_fusion(r, top_n=99)) == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": -1},
        {"top_n": -1},
        {"weights": {"nope": 1.0}},
        {"weights": [1.0]},
        {"weights": {"A": -1.0}},
    ],
)
def test_invalid_arguments(kwargs):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"A": ["a"], "B": ["b"]}, **kwargs)


def test_rank_below_one_rejected():
    with pytest.raises(ValueError):
        R("a", 0)


@pytest.mark.parametrize("bad", [1.0, "1", True, None])
def test_non_integer_rank_rejected(bad):
    with pytest.raises(TypeError):
        R("a", bad)


def test_numpy_integer_ranks_accepted():
    fused = reciprocal_rank_fusion([[R("x", np.int64(5)), R("y", np.int64(1))]])
    assert ids(fused) == ["y", "x"]
    assert type(fused[0].ranks["0"]) is int


def test_tuple_ids_are_never_read_as_rank_pairs():
    fused = reciprocal_rank_fusion([[("x", 5), ("y", 1)]])
    assert ids(fused) == [("x", 5), ("y", 1)]
    assert fused[0].ranks == {"0": 1}


@pytest.mark.parametrize("w", [math.nan, math.inf, -math.inf])
def test_non_finite_weights_rejected(w):
    with pytest.raises(ValueError, match="finite"):
        reciprocal_rank_fusion({"a": ["x"], "b": ["y"]}, weights={"a": w})


@pytest.mark.parametrize("k", [1.5, True, "60"])
def test_non_integer_k_rejected(k):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=k)


def test_duplicate_ranking_names_rejected():
    # names are stringified, so 1 and "1" collide
    with pytest.raises(ValueError, match="unique"):
        reciprocal_rank_fusion({1: ["a"], "1": ["b"]})


def test_rrf_reference_values():
    """Hand-computed example: 3 lists, k=60."""
    fused = reciprocal_rank_fusion(
        {"a": ["d1", "d2", "d3"], "b": ["d2", "d3"], "c": ["d3"]}
    )
    expected = {
        "d1": 1 / 61,
        "d2": 1 / 62 + 1 / 61,
        "d3": 1 / 63 + 1 / 62 + 1 / 61,
    }
    assert ids(fused) == ["d3", "d2", "d1"]
    for r in fused:
        assert r.score == pytest.approx(expected[r.id], abs=1e-15)


def test_non_string_ids_supported():
    fused = reciprocal_rank_fusion([[1, 2], [2, 3]])
    assert ids(fused) == [2, 1, 3]


def test_fused_result_best_rank():
    assert FusedResult(id="a", score=0.1, ranks={"x": 4, "y": 2}).best_rank == 2


# ------------------------------------------------------ ranks_from_scores
def test_ranks_from_scores_variants():
    assert ranks_from_scores({}) == []
    assert pairs(ranks_from_scores([("a", 1.0), ("b", 3.0), ("c", 2.0)])) == [
        ("b", 1),
        ("c", 2),
        ("a", 3),
    ]
    assert pairs(ranks_from_scores({"a": 0.1, "b": 0.5}, higher_is_better=False)) == [
        ("a", 1),
        ("b", 2),
    ]
    assert pairs(ranks_from_scores({"a": 1.0, "b": 1.0, "c": 1.0})) == [
        ("a", 1),
        ("b", 1),
        ("c", 1),
    ]
    assert pairs(ranks_from_scores({"a": math.nan, "b": 1.0})) == [("b", 1)]


def test_ranks_from_scores_duplicates_do_not_consume_positions():
    assert pairs(ranks_from_scores([("a", 3.0), ("a", 2.0), ("b", 1.0)])) == [
        ("a", 1),
        ("b", 2),
    ]
    # best score wins regardless of order, in both directions
    assert pairs(ranks_from_scores([("a", 2.0), ("b", 2.5), ("a", 3.0)])) == [
        ("a", 1),
        ("b", 2),
    ]
    assert pairs(
        ranks_from_scores([("a", 3.0), ("b", 2.5), ("a", 1.0)], higher_is_better=False)
    ) == [
        ("a", 1),
        ("b", 2),
    ]


def test_ranks_from_scores_infinities_are_ordered():
    scores = {"a": math.inf, "b": 1.0, "c": -math.inf}
    assert pairs(ranks_from_scores(scores)) == [("a", 1), ("b", 2), ("c", 3)]
    assert pairs(ranks_from_scores(scores, higher_is_better=False)) == [
        ("c", 1),
        ("b", 2),
        ("a", 3),
    ]
    assert pairs(ranks_from_scores({"a": math.inf, "b": math.inf})) == [
        ("a", 1),
        ("b", 1),
    ]
