"""Event-relative time intent (Finding 4 cause 5 / E8).

"Who led X immediately before the September recall?" got time_scope None,
"now"-only retrieval and a "prefer the most recent statement" answer prompt,
the opposite of what the question asks. These tests pin the general mechanism:
a temporal_relation hint from the router (LLM field plus deterministic cues),
any-time retrieval threading, and a matching answer-prompt instruction. No
dataset-specific tuning and no paid LLM calls.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from omnistream.agents.tools import ToolExecutor
from omnistream.llm import LLMClient, ToolCall
from omnistream.qa import answer_question
from omnistream.retrieval.citations import AnswerContext, generate_answer
from omnistream.retrieval.models import (
    Entity,
    RetrievalResult,
    ScoredFact,
    TimeScope,
    fact_in_scope,
)
from omnistream.retrieval.modes import RetrievalDispatcher
from omnistream.retrieval.router import QueryRouter, RoutingDecision, _event_relation
from tests.unit.test_agent_tools import FACT, Graph, Items
from tests.unit.test_qa import ScriptedLLM
from tests.unit.test_query_router import CATALOG

# ---------------------------------------------------------------- router cues


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Who led X immediately before the September recall?", ("before", "the September recall")),
        ("Who led X just before the September recall?", ("before", "the September recall")),
        ("Who led X right before the September recall?", ("before", "the September recall")),
        ("Who led X shortly before the September recall?", ("before", "the September recall")),
        ("Who led X before the September recall?", ("before", "the September recall")),
        ("Who led X prior to the September recall?", ("before", "the September recall")),
        ("Who led X until the September recall?", ("before", "the September recall")),
        ("Who led X immediately after the September recall?", ("after", "the September recall")),
        ("Who led X just after the September recall?", ("after", "the September recall")),
        ("Who led X after the September recall?", ("after", "the September recall")),
        ("Who led X since the September recall?", ("after", "the September recall")),
        ("Who led X following the September recall?", ("after", "the September recall")),
        ("Who led X in the wake of the September recall?", ("after", "the September recall")),
        ("Who led X at the time of the September recall?", ("at", "the September recall")),
        ("Who led X when the September recall happened?", ("at", "the September recall")),
        ("Who led X before the Halvex brake-seal recall?", ("before", "the Halvex brake-seal recall")),
        ("Who led X before the iPhone 15 launch?", ("before", "the iPhone 15 launch")),
        ("Who led X before the Q3 product recall?", ("before", "the Q3 product recall")),
        ("Who led X before the merger with Acme?", ("before", "the merger with Acme")),
        # Role-succession cues imply "before" without naming an event.
        ("Who was the previous CEO?", ("before", "")),
        ("Who was X's predecessor?", ("before", "")),
        ("Who preceded Ada as chief?", ("before", "")),
        ("Who led X previously?", ("before", "")),
        ("Who is the former chief of X?", ("before", "")),
        ("Who led X formerly?", ("before", "")),
    ],
)
def test_event_relation_cues(question, expected):
    assert _event_relation(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        # Generic common-noun anchors are not specific events; no hint.
        "What happened before markets opened?",
        "What happened before trading began?",
        "What happened after the bell rang?",
        "What happened before the meeting?",
        "What happened before the crash?",
        "What happened before the crash in 2008?",
        "Who led X before the recall?",
        "Which companies led the market after the close?",
        # Pure calendar anchors stay on the explicit-date scope path.
        "Who led X before September 18?",
        "Who led X before September 18, 2025?",
        "Who led X after 2025?",
        "Who led X since Q3 2025?",
        "Who led X before yesterday?",
        "Who led X before last week?",
        "Who led X before two years ago?",
        # Interrogative phrasings, not event anchors.
        "Since when did Halvex appoint a new chief?",
        "Until when did Ada lead the laboratory?",
        # Naming question, not a state relative to an event.
        "What was X formerly known as?",
        "Which of the following items is current?",
        # No anchor text after the cue.
        "Who led X after?",
    ],
)
def test_event_relation_rejects_generic_or_date_anchors(question):
    assert _event_relation(question) is None


def router_for(reply, settings, embedder, mock_openai):
    client, transport = mock_openai(lambda body: reply)
    return QueryRouter(LLMClient(settings, client=client), embedder, CATALOG), transport


@pytest.mark.parametrize(
    "reply,question,expected",
    [
        (
            {"bubbles": ["news"], "temporal_relation": "before", "anchor_event": "the merger"},
            "Who led X before the merger?",
            ("before", "the merger"),
        ),
        (
            {"bubbles": ["news"], "temporal_relation": "after", "anchor_event": "the merger"},
            "Who led X after the merger?",
            ("after", "the merger"),
        ),
        (
            # Missing anchor_event is filled by the deterministic detector.
            {"bubbles": ["news"], "temporal_relation": "at"},
            "Who led X at the time of the Halvex recall?",
            ("at", "the Halvex recall"),
        ),
        (
            # Invalid LLM value falls back to the deterministic net.
            {"bubbles": ["news"], "temporal_relation": "sometimes", "anchor_event": "x"},
            "Who led X immediately before the September recall?",
            ("before", "the September recall"),
        ),
        (
            # Non-string anchor_event is ignored; deterministic net supplies it.
            {"bubbles": ["news"], "temporal_relation": "before", "anchor_event": 7},
            "Who led X immediately before the September recall?",
            ("before", "the September recall"),
        ),
        (
            # Field absent entirely; deterministic net supplies it.
            {"bubbles": ["news"]},
            "Who led X immediately before the September recall?",
            ("before", "the September recall"),
        ),
    ],
)
def test_llm_json_temporal_relation(
    reply, question, expected, settings, embedder, mock_openai
):
    router, _ = router_for(json.dumps(reply), settings, embedder, mock_openai)
    result = router.route(question)
    assert result.time_scope is None
    assert result.temporal_relation == expected[0]
    assert result.anchor_event == expected[1]


def test_explicit_date_scope_suppresses_event_hint(settings, embedder, mock_openai):
    router, _ = router_for(
        json.dumps(
            {
                "bubbles": ["news"],
                "time_scope": {"start": None, "end": "2026-02-07"},
                "temporal_relation": "before",
                "anchor_event": "the recall",
            }
        ),
        settings,
        embedder,
        mock_openai,
    )
    result = router.route("Who led X before the recall on February 7?")
    assert result.time_scope is not None
    assert result.temporal_relation is None
    assert result.anchor_event == ""


def test_router_prompt_describes_temporal_fields(settings, embedder, mock_openai):
    router, transport = router_for("{}", settings, embedder, mock_openai)
    router.route("research papers")
    system = transport.bodies[0]["messages"][0]["content"]
    assert '"temporal_relation"' in system
    assert '"anchor_event"' in system
    assert "relative to an event" in system


def test_no_event_hint_on_plain_question(settings, embedder, mock_openai):
    router, _ = router_for(
        json.dumps({"bubbles": ["news"]}), settings, embedder, mock_openai
    )
    result = router.route("Who leads X now?")
    assert result.temporal_relation is None
    assert result.anchor_event == ""
    assert result.time_scope is None


# ------------------------------------------------------- retrieval threading


class DecisionRouter:
    def __init__(self, decision):
        self.decision = decision

    def route(self, question, **kwargs):
        return self.decision


class RecordingRetriever:
    def __init__(self):
        self.requests = []

    def retrieve(self, question, *, bubbles, time_scope=None, top_k=None):
        self.requests.append((question, tuple(bubbles), time_scope))
        return RetrievalResult("own", (ScoredFact(FACT, 1),))


def event_decision():
    return RoutingDecision(
        ("news", "finance"),
        "simple",
        None,
        temporal_relation="before",
        anchor_event="the September recall",
    )


@pytest.mark.parametrize("subagents", [False, True])
async def test_event_hint_threads_unbounded_scope(settings, mock_openai, subagents):
    router = DecisionRouter(event_decision())
    retriever = RecordingRetriever()
    client, transport = mock_openai(lambda _: "Answer [1].")
    await answer_question(
        "Who led X immediately before the September recall?",
        router=router,
        dispatcher=RetrievalDispatcher({"own": retriever}, "own"),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=Graph() if subagents else None,
        item_store=Items(),
        settings=settings,
        subagents=subagents,
    )
    assert retriever.requests
    for _, _, scope in retriever.requests:
        assert scope is not None
        assert scope == TimeScope(None, None)
    system = transport.bodies[-1]["messages"][0]["content"]
    assert "not as of now" in system
    assert "immediately before it" in system
    assert "the September recall" in system
    assert "Answer for now" not in system


async def test_no_event_hint_keeps_none_scope(settings, mock_openai):
    router = DecisionRouter(RoutingDecision(("news",), "simple", None))
    retriever = RecordingRetriever()
    client, _ = mock_openai(lambda _: "Answer [1].")
    await answer_question(
        "Who leads X now?",
        router=router,
        dispatcher=RetrievalDispatcher({"own": retriever}, "own"),
        llm=LLMClient(settings, client=client),
        async_llm=None,
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert retriever.requests == [("Who leads X now?", ("news",), None)]


def test_unbounded_scope_includes_historical_facts():
    now = datetime(2025, 2, 7, tzinfo=UTC)
    historical = replace(
        FACT,
        valid_at=datetime(2024, 6, 1, tzinfo=UTC),
        invalid_at=datetime(2024, 9, 1, tzinfo=UTC),
    )
    assert not fact_in_scope(historical, None, now=now)
    assert fact_in_scope(historical, TimeScope(None, None), now=now)


def test_own_expansion_unbounded_includes_historical_facts():
    from omnistream.graph.memory_store import InMemoryGraphStore

    now = datetime(2025, 2, 7, tzinfo=UTC)
    current = replace(
        FACT, id="current", valid_at=datetime(2024, 9, 1, tzinfo=UTC)
    )
    historical = replace(
        FACT,
        id="historical",
        valid_at=datetime(2024, 6, 1, tzinfo=UTC),
        invalid_at=datetime(2024, 9, 1, tzinfo=UTC),
    )
    store = InMemoryGraphStore(
        [
            Entity("e", "Example", "person", "news"),
            Entity("other", "Other", "person", "news"),
        ],
        [current, historical],
        now=now,
    )
    scoped = store.expand(["e"], bubbles=["news"], time_scope=None)
    assert [f.id for f in scoped.facts] == ["current"]
    any_time = store.expand(["e"], bubbles=["news"], time_scope=TimeScope(None, None))
    assert sorted(f.id for f in any_time.facts) == ["current", "historical"]


def test_graphiti_unbounded_scope_includes_historical_facts():
    from types import SimpleNamespace

    from omnistream.retrieval.graphiti_mode import GraphitiRetriever

    historical = SimpleNamespace(
        uuid="h",
        fact="old lead",
        name="led",
        source_node_uuid="s",
        target_node_uuid="t",
        group_id="news",
        valid_at=datetime(2024, 6, 1, tzinfo=UTC),
        invalid_at=datetime(2024, 9, 1, tzinfo=UTC),
        created_at=datetime(2024, 6, 2, tzinfo=UTC),
        episodes=[],
        attributes={"grounded": True, "item_id": "item-h"},
    )

    class Searcher:
        async def search(self, query, **kwargs):
            return [historical]

    with GraphitiRetriever(Searcher()) as retriever:
        assert not retriever.retrieve("q", bubbles=["news"], time_scope=None).facts
        result = retriever.retrieve(
            "q", bubbles=["news"], time_scope=TimeScope(None, None)
        )
        assert [f.fact.id for f in result.facts] == ["h"]


# ----------------------------------------------------------- facts tool


class RecordingGraph(Graph):
    def facts_about(self, entity_id, start=None, end=None, **kwargs):
        self.bounds = start, end
        return [FACT]


def facts_tool(graph, time_scope):
    return ToolExecutor(
        bubble="news",
        mode="own",
        retriever=type("Retriever", (), {"requests": []})(),
        graph_store=graph,
        item_store=Items(),
        time_scope=time_scope,
    )


async def test_facts_tool_unbounded_scope_reads_history():
    graph = RecordingGraph()
    data = json.loads(
        await facts_tool(graph, TimeScope(None, None)).execute(
            ToolCall("t", "facts", {"entity_id": "e"})
        )
    )
    assert [f["id"] for f in data["facts"]] == ["f"]
    assert graph.bounds == (
        datetime.min.replace(tzinfo=UTC),
        datetime.max.replace(tzinfo=UTC),
    )


async def test_facts_tool_unbounded_scope_keeps_explicit_bounds():
    graph = RecordingGraph()
    data = json.loads(
        await facts_tool(graph, TimeScope(None, None)).execute(
            ToolCall("t", "facts", {"entity_id": "e", "from": "2025-01-01", "to": "2025-02-01"})
        )
    )
    assert [f["id"] for f in data["facts"]] == ["f"]
    assert graph.bounds == (datetime(2025, 1, 1), datetime(2025, 2, 1))


async def test_facts_tool_no_scope_keeps_valid_now_default():
    graph = RecordingGraph()
    data = json.loads(
        await facts_tool(graph, None).execute(
            ToolCall("t", "facts", {"entity_id": "e"})
        )
    )
    assert [f["id"] for f in data["facts"]] == ["f"]
    assert graph.bounds == (None, None)


# -------------------------------------------------------- answer prompt


@pytest.mark.parametrize(
    "relation,anchor,needle",
    [
        ("before", "the September recall", "immediately before it"),
        ("after", "the September recall", "immediately after it"),
        ("at", "the September recall", "at the time of the event"),
    ],
)
def test_generate_answer_event_relative(settings, mock_openai, relation, anchor, needle):
    client, transport = mock_openai(lambda _: "Answer.")
    llm = LLMClient(settings, client=client)
    generate_answer(
        llm,
        "Who led X?",
        AnswerContext("[1] Evidence", ()),
        time_scope=None,
        temporal_relation=relation,
        anchor_event=anchor,
    )
    system = transport.bodies[0]["messages"][0]["content"]
    assert "Answer for now" not in system
    assert "not as of now" in system
    assert needle in system
    assert "the September recall" in system


def test_generate_answer_default_now_unchanged(settings, mock_openai):
    client, transport = mock_openai(lambda _: "Answer.")
    llm = LLMClient(settings, client=client)
    generate_answer(
        llm,
        "Who leads X now?",
        AnswerContext("[1] Evidence", ()),
        time_scope=None,
        temporal_relation=None,
    )
    system = transport.bodies[0]["messages"][0]["content"]
    assert "Answer for now" in system
    assert "not as of now" not in system


def test_generate_answer_explicit_date_unchanged(settings, mock_openai):
    client, transport = mock_openai(lambda _: "Answer.")
    llm = LLMClient(settings, client=client)
    cutoff = datetime(2020, 6, 1, 23, 59, 59, 999999, tzinfo=UTC)
    generate_answer(
        llm,
        "Who led X?",
        AnswerContext("[1] Evidence", ()),
        time_scope=TimeScope(cutoff, cutoff),
        temporal_relation="before",
        anchor_event="the recall",
    )
    system = transport.bodies[0]["messages"][0]["content"]
    assert "Answer as of" in system
    assert "not as of now" not in system
