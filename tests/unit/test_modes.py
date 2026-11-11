"""Mode selection and contract enforcement (spec C5)."""

import pytest

from omnistream.retrieval.models import RetrievalResult, TimeScope
from omnistream.retrieval.modes import RetrievalDispatcher


class Stub:
    def __init__(self, mode):
        self.mode = mode
        self.calls = []

    def retrieve(self, question, **kwargs):
        self.calls.append((question, kwargs))
        return RetrievalResult(self.mode)


def test_dispatch_and_forward():
    a, b = Stub("classic"), Stub("graphiti")
    dispatcher = RetrievalDispatcher({"classic": a, "graphiti": b}, "classic")
    assert dispatcher.retrieve("q", bubbles=["a"]).mode == "classic"
    scope = TimeScope()
    assert (
        dispatcher.retrieve(
            "q", bubbles=["b"], mode="graphiti", time_scope=scope, top_k=2
        ).mode
        == "graphiti"
    )
    assert b.calls == [("q", {"bubbles": ["b"], "time_scope": scope, "top_k": 2})]


@pytest.mark.parametrize("mode", ["own", "unknown", ""])
def test_invalid_mode(mode):
    dispatcher = RetrievalDispatcher({"classic": Stub("classic")}, "classic")
    with pytest.raises(ValueError):
        dispatcher.retrieve("q", bubbles=[], mode=mode)


def test_invalid_default_and_mismatch():
    with pytest.raises(ValueError):
        RetrievalDispatcher({}, "classic")
    dispatcher = RetrievalDispatcher({"classic": Stub("own")}, "classic")
    with pytest.raises(ValueError, match="expected classic"):
        dispatcher.retrieve("q", bubbles=[])
