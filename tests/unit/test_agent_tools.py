import json
from datetime import UTC, datetime

import pytest

from omnistream.agents.tools import MAX_RESULT_CHARS, ToolExecutor, tools_for_mode
from omnistream.llm import ToolCall
from omnistream.retrieval.models import (
    Chunk,
    Entity,
    Fact,
    ItemPart,
    RetrievalResult,
    ScoredFact,
    Subgraph,
    TimeScope,
)


class Retriever:
    def __init__(self):
        self.requests = []

    def retrieve(self, query, *, bubbles, time_scope):
        self.requests.append((query, bubbles, time_scope))
        return RetrievalResult("own", facts=(ScoredFact(FACT, 1),), chunks=(CHUNK,))


FACT = Fact(
    "f",
    "e",
    "other",
    "knows",
    "Evidence",
    "news",
    "item",
    None,
    datetime(2025, 1, 1, tzinfo=UTC),
)
CHUNK = Chunk("c", "Text", "item2", "news", None, None)
ENTITY = Entity("e", "Example", "person", "news", "global")


class Graph:
    def entities_in(self, bubbles):
        return [ENTITY]

    def neighbors(self, entity_id, depth=1):
        return Subgraph({"e": ENTITY}, (FACT,))

    def facts_about(self, entity_id, start=None, end=None):
        self.bounds = start, end
        return [FACT]


class Items:
    def read_item(self, item_id, part=1):
        return ItemPart(item_id, part, 10, "word " * 2500)

    def item_text(self, item_id, max_tokens=4000):
        return " ".join(("word " * 2500).split()[:max_tokens])


def executor(mode="own", **kwargs):
    return ToolExecutor(
        bubble="news",
        mode=mode,
        retriever=kwargs.pop("retriever", Retriever()),
        graph_store=kwargs.pop("graph_store", Graph()),
        item_store=Items(),
        **kwargs,
    )


@pytest.mark.parametrize(
    "mode,names",
    [
        ("classic", {"search", "read_item"}),
        ("own", {"search", "read_item", "facts", "neighbors"}),
        ("graphiti", {"search", "read_item", "facts", "neighbors"}),
    ],
)
def test_mode_schemas(mode, names):
    assert {t["function"]["name"] for t in tools_for_mode(mode)} == names


@pytest.mark.parametrize(
    "name,args",
    [
        ("neighbors", {"entity_id": "e", "depth": 3}),
        ("neighbors", {"entity_id": "e", "depth": 0}),
        ("read_item", {"item_id": "i", "part": [1, 2, 3, 4]}),
        ("read_item", {"item_id": "i", "part": True}),
        ("facts", {"entity_id": "e", "from": "bad"}),
    ],
)
async def test_bad_arguments(name, args):
    assert "error" in json.loads(await executor().execute(ToolCall("t", name, args)))


async def test_unavailable_and_malformed():
    assert "unavailable" in await executor("classic", graph_store=None).execute(
        ToolCall("t", "neighbors", {})
    )
    assert "invalid arguments" in await executor().execute(
        ToolCall("t", "search", {}, "bad json")
    )


async def test_search_scope_and_evidence():
    retriever = Retriever()
    scope = TimeScope()
    data = json.loads(
        await executor(retriever=retriever, time_scope=scope).execute(
            ToolCall("t", "search", {"query": "question"})
        )
    )
    assert retriever.requests == [("question", ["news"], scope)]
    assert data["facts"][0]["id"] == "f"
    assert data["chunks"][0]["item_id"] == "item2"
    assert data["entities"][0]["global_id"] == "global"


async def test_graph_dates_and_neighbors():
    graph = Graph()
    tool = executor(graph_store=graph)
    assert "facts" in json.loads(
        await tool.execute(
            ToolCall(
                "t",
                "facts",
                {"entity_id": "e", "from": "2025-01-01", "to": "2025-02-01"},
            )
        )
    )
    assert graph.bounds == (datetime(2025, 1, 1), datetime(2025, 2, 1))
    assert json.loads(
        await tool.execute(ToolCall("t", "neighbors", {"entity_id": "e", "depth": 2}))
    )["entities"]


@pytest.mark.parametrize("part", [1, [1, 2, 3]])
async def test_read_parts(part):
    data = json.loads(
        await executor().execute(
            ToolCall("t", "read_item", {"item_id": "i", "part": part})
        )
    )
    assert len(data["parts"]) == (1 if isinstance(part, int) else 3)
    assert all(len(p["text"].split()) == 2000 for p in data["parts"])


async def test_json_truncation():
    class Huge:
        def retrieve(self, *args, **kwargs):
            return RetrievalResult(
                "classic",
                chunks=(
                    Chunk("c", "x" * MAX_RESULT_CHARS * 2, "i", "news", None, None),
                ),
            )

    result = await executor("classic", retriever=Huge(), graph_store=None).execute(
        ToolCall("t", "search", {"query": "q"})
    )
    assert len(result) <= MAX_RESULT_CHARS
    assert json.loads(result)["truncated"] is True


@pytest.mark.parametrize("name", ["facts", "neighbors"])
async def test_graph_tools_enforce_routed_time_scope(name):
    from dataclasses import replace

    class TemporalGraph(Graph):
        future = replace(
            FACT, id="future", object_id="future-o", valid_at=datetime(2030, 1, 1)
        )
        ungrounded = replace(FACT, id="ungrounded", grounded=False)

        def neighbors(self, entity_id, depth=1):
            entities = {
                id: Entity(id, id, "person", "news")
                for id in ["e", "other", "future-o", "future-global"]
            }
            return Subgraph(
                entities,
                (FACT, self.future, self.ungrounded),
                (("future-o", "future-global"),),
            )

        def facts_about(self, entity_id, start=None, end=None):
            self.bounds = start, end
            return [FACT, self.future, self.ungrounded]

    graph = TemporalGraph()
    scope = TimeScope(
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 31, tzinfo=UTC),
    )
    data = json.loads(
        await executor(graph_store=graph, time_scope=scope).execute(
            ToolCall("t", name, {"entity_id": "e"})
        )
    )
    assert [f["id"] for f in data["facts"]] == ["f"]
    if name == "neighbors":
        assert {e["id"] for e in data["entities"]} == {"e", "other"}
        assert data["same_as"] == []
    else:
        assert graph.bounds == (scope.start, scope.end)


@pytest.mark.parametrize(
    "bounds,expected",
    [
        (
            {"from": "2025-01-15", "to": "2025-02-10"},
            (datetime(2025, 1, 15), datetime(2025, 1, 31, tzinfo=UTC)),
        ),
        ({"from": "2030-01-01"}, None),
        ({"to": "2024-12-01"}, None),
    ],
)
async def test_facts_intersects_explicit_and_routed_bounds(bounds, expected):
    graph = Graph()
    scope = TimeScope(
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 31, tzinfo=UTC),
    )
    data = json.loads(
        await executor(graph_store=graph, time_scope=scope).execute(
            ToolCall("t", "facts", {"entity_id": "e", **bounds})
        )
    )
    assert "error" not in data
    if expected is None:
        assert data == {"facts": [], "entities": []}
        assert not hasattr(graph, "bounds")
    else:
        assert graph.bounds == expected
        assert len(data["facts"]) == 1


async def test_neighbors_preserves_standalone_identity_entities():
    class IdentityGraph(Graph):
        def neighbors(self, entity_id, depth=1):
            return Subgraph(
                {"global": Entity("global", "Global", "person", "news", "global")}, ()
            )

    data = json.loads(
        await executor(graph_store=IdentityGraph()).execute(
            ToolCall("t", "neighbors", {"entity_id": "e"})
        )
    )
    assert [e["id"] for e in data["entities"]] == ["global"]
