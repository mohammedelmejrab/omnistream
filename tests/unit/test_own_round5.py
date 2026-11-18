"""CPU-free integration checks for the final candidate rerank."""

from unittest.mock import Mock

from omnistream.retrieval.classic import ClassicRetriever, add_chunks
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from omnistream.retrieval.own_algorithm.rerank import rerank
from tests.unit.test_classic_mode import chunks
from tests.unit.test_classic_mode import store as chroma_store  # noqa: F401 - pytest fixture
from tests.unit.test_own_pipeline import NOW, embedder, store  # noqa: F401 - pytest fixture


def test_classic_reranks_before_output_cap(chroma_store):  # noqa: F811
    client, service = chroma_store
    add_chunks(client, service, "a", chunks("a", 0, 35))
    encoder = Mock()
    encoder.predict.side_effect = lambda pairs, **_: [int(text) for _, text in pairs]
    result = ClassicRetriever(client, service, reranker=lambda: encoder).retrieve(
        "0", bubbles=["a"], top_k=1
    )
    assert len(encoder.predict.call_args.args[0]) == 30
    assert [chunk.text for chunk in result.chunks] == ["29"]


def test_own_reranks_before_output_cap(store):  # noqa: F811
    service, _ = embedder()
    encoder = Mock()
    encoder.predict.side_effect = lambda pairs, **_: [
        text == "Fact cross" for _, text in pairs
    ]
    result = OwnRetriever(
        store, service, now=lambda: NOW, reranker=lambda: encoder
    ).retrieve("Acme", bubbles=["news"], top_k=1)
    assert [scored.fact.id for scored in result.facts] == ["cross"]


def test_equal_scores_and_tail_preserve_order():
    encoder = Mock()
    encoder.predict.return_value = [0] * 30
    candidates = list(range(34))
    assert rerank("q", candidates, str, lambda: encoder) == candidates
