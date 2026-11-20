"""Offline tests for IRCoT-style multi-step retrieval over the own retriever."""

from omnistream.retrieval.models import Chunk, RetrievalResult
from omnistream.retrieval.own_algorithm.ircot import IRCoTRetriever


def _chunk(item):
    return Chunk(f"c-{item}", f"text {item}", item, "b", None, None, 1.0)


class Inner:
    def __init__(self):
        self.queries = []

    def retrieve(self, question, **_):
        self.queries.append(question)
        if question.startswith("Film"):
            return RetrievalResult("own", chunks=(_chunk("director"), _chunk("film")))
        return RetrievalResult("own", chunks=(_chunk("film"), _chunk("x"), _chunk("y")))


class LLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, **_):
        return self.replies.pop(0)


def test_ircot_retrieves_with_reasoning_sentence_and_interleaves():
    inner = Inner()
    out = IRCoTRetriever(inner, LLM(["Film F was directed by D.", "So the answer is: D."])).retrieve(
        "Who directed F?", bubbles=["b"]
    )
    assert inner.queries == ["Who directed F?", "Film F was directed by D."]
    assert [c.item_id for c in out.chunks] == ["film", "director", "x", "y"]
    assert out.chunks_first


def test_ircot_stops_when_answer_is_stated():
    inner = Inner()
    IRCoTRetriever(inner, LLM(["So the answer is: D."])).retrieve("q", bubbles=["b"])
    assert inner.queries == ["q"]
