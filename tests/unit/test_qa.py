from dataclasses import replace

import httpx
import pytest

from omnistream.agents.orchestrator import JoinedGroup
from omnistream.llm import LLMClient, ToolCall
from omnistream.qa import SPECIFIC_ITEM_INFERENCE_FACTS, answer_question
from omnistream.retrieval.models import Entity, RetrievalResult, ScoredFact, TimeScope
from omnistream.retrieval.modes import RetrievalDispatcher
from omnistream.retrieval.router import QueryRouter, RoutingDecision
from tests.conftest import load_llm_fixture
from tests.unit.test_agent_tools import CHUNK, FACT, Graph, Items
from tests.unit.test_query_router import CATALOG
from tests.unit.test_subagent import turn


class ModeRetriever:
    def __init__(self, mode):
        self.mode, self.requests = mode, []

    def retrieve(self, question, *, bubbles, time_scope=None, top_k=None):
        self.requests.append((question, tuple(bubbles), time_scope))
        return RetrievalResult(self.mode, (ScoredFact(FACT, 1),), (CHUNK,))


class BubbleItems:
    """Retriever answering with one fact per configured item, per bubble."""

    def __init__(self, items_by_bubble):
        self.items_by_bubble = items_by_bubble

    def retrieve(self, question, *, bubbles, time_scope=None, top_k=None):
        bubble = bubbles[0]
        return RetrievalResult(
            "own",
            tuple(
                ScoredFact(
                    replace(FACT, id=f"{bubble}-{rank}", item_id=item, bubble=bubble),
                    1.0,
                )
                for rank, item in enumerate(self.items_by_bubble[bubble])
            ),
        )


class Router:
    def __init__(self, strategy="simple", specific=False, bubbles=("news", "finance")):
        self.decision = RoutingDecision(tuple(bubbles), strategy, TimeScope(), specific)

    def route(self, question, **kwargs):
        self.kwargs = kwargs
        return self.decision


class ScriptedLLM:
    async def chat_with_tools(self, messages, tools, **kwargs):
        if len(messages) == 2:
            return turn(ToolCall("t", "search", {"query": "investigate"}))
        return turn(content="Evidence [item] and text [item2]")


@pytest.mark.parametrize("mode", ["classic", "graphiti", "own"])
@pytest.mark.parametrize("subagents", [False, True])
async def test_six_configurations(settings, mock_openai, mode, subagents):
    # Opposite strategy verifies explicit on/off always overrides routing.
    router = Router("simple" if subagents else "multi_hop")
    retriever = ModeRetriever(mode)
    client, transport = mock_openai(lambda _: "Supported [1] and [2].")
    result = await answer_question(
        "q",
        router=router,
        dispatcher=RetrievalDispatcher({mode: retriever}, mode),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=None if mode == "classic" else Graph(),
        item_store=Items(),
        settings=settings,
        subagents=subagents,
        pins=("news",),
        exclude=(),
    )
    assert result.mode == mode
    assert result.routing == router.decision
    assert router.kwargs == {"pins": ("news",), "exclude": ()}
    assert (result.multi_hop is not None) is subagents
    assert result.retrieval.mode == mode
    assert [c.item_id for c in result.answer.citations] == ["item", "item2"]
    assert result.answer.invalid_citations == ()
    assert [f.fact.id for f in result.retrieval.facts] == ["f"]
    assert [c.id for c in result.retrieval.chunks] == ["c"]
    if subagents:
        assert len(retriever.requests) == 2
        assert result.retrieval.facts[0].score == 0
        assert all(
            f.facts == (FACT,) and f.chunks == (CHUNK,)
            for f in result.multi_hop.findings
        )
        context = transport.bodies[0]["messages"][1]["content"]
        assert (
            "Bubble news findings:" in context and "Bubble finance findings:" in context
        )
    else:
        assert retriever.requests == [
            ("q", ("news", "finance"), router.decision.time_scope)
        ]


async def test_simple_recorded_router(settings, embedder, mock_openai):
    fixture = load_llm_fixture("router_json")

    def reply(body):
        if "Select bubbles" in body["messages"][0]["content"]:
            return httpx.Response(200, json=fixture["response"])
        return "Evidence [1]."

    client, transport = mock_openai(reply)
    llm = LLMClient(settings, client=client)
    retriever = ModeRetriever("own")
    result = await answer_question(
        "EU ruling",
        router=QueryRouter(llm, embedder, CATALOG),
        dispatcher=RetrievalDispatcher({"own": retriever}, "own"),
        llm=llm,
        async_llm=None,
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert result.routing.bubbles == ("news", "finance")
    assert result.multi_hop is None
    assert result.answer.citations[0].item_id == "item"
    assert len(transport.requests) == 2


@pytest.mark.parametrize("specific", [False, True])
async def test_specific_item(settings, mock_openai, specific):
    class Originals(Items):
        def __init__(self):
            self.read_ids = []

        def item_text(self, item_id, max_tokens=4000):
            self.read_ids.append(item_id)
            return f"UNIQUE ORIGINAL OF {item_id}"

    store = Originals()
    client, transport = mock_openai(lambda _: "Answer [1]")
    await answer_question(
        "q",
        router=Router(specific=specific),
        dispatcher=RetrievalDispatcher({"own": ModeRetriever("own")}, "own"),
        llm=LLMClient(settings, client=client),
        async_llm=None,
        graph_store=None,
        item_store=store,
        settings=settings,
        specific_item_id="item",
    )
    context = transport.bodies[0]["messages"][1]["content"]
    # Span lookups may read any cited item, but the original text is only
    # appended to the context for the specific item.
    assert sorted(store.read_ids) == ["item", "item2"]
    assert ("UNIQUE ORIGINAL OF item" in context) is specific
    assert "UNIQUE ORIGINAL OF item2" not in context


@pytest.mark.parametrize("strategy", ["simple", "multi_hop"])
async def test_strategy_and_mode_override(settings, mock_openai, strategy):
    client, _ = mock_openai(lambda _: "Answer [1]")
    result = await answer_question(
        "q",
        router=Router(strategy),
        dispatcher=RetrievalDispatcher(
            {m: ModeRetriever(m) for m in ["classic", "own"]}, "own"
        ),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=None,
        item_store=Items(),
        settings=settings,
        mode="classic",
    )
    assert result.mode == "classic"
    assert (result.multi_hop is not None) is (strategy == "multi_hop")


async def test_read_original_is_citable(settings, mock_openai):
    class ReadLLM:
        async def chat_with_tools(self, messages, tools):
            if len(messages) == 2:
                return turn(
                    ToolCall("t", "read_item", {"item_id": "original", "part": 1})
                )
            return turn(content="Original supports this.")

    client, _ = mock_openai(lambda _: "Answer [1]")
    result = await answer_question(
        "q",
        router=Router("multi_hop"),
        dispatcher=RetrievalDispatcher(
            {"classic": ModeRetriever("classic")}, "classic"
        ),
        llm=LLMClient(settings, client=client),
        async_llm=ReadLLM(),
        graph_store=None,
        item_store=Items(),
        settings=settings,
    )
    assert result.answer.citations[0].item_id == "original"
    assert len(result.retrieval.chunks) == 1


@pytest.mark.parametrize("has_graph", [True, False])
async def test_qa_canonicalizes_cross_bubble_conflicts(
    settings, mock_openai, has_graph
):
    import threading

    event_thread = threading.get_ident()

    class CanonicalGraph:
        def entities_in(self, bubbles):
            assert threading.get_ident() != event_thread
            assert tuple(bubbles) == ("news", "finance")
            return [
                Entity("apple-n", "Apple", "organization", "news", "g-apple"),
                Entity("apple-f", "Apple", "organization", "finance", "g-apple"),
            ]

    class CrossBubbleRetriever(ModeRetriever):
        def retrieve(self, *args, **kwargs):
            a = replace(FACT, subject_id="apple-n", credibility=0.7)
            b = replace(
                FACT,
                id="f2",
                subject_id="apple-f",
                object_id="different",
                bubble="finance",
                item_id="item2",
            )
            return RetrievalResult(self.mode, (ScoredFact(a, 1), ScoredFact(b, 0.5)))

    mode = "own" if has_graph else "classic"
    client, transport = mock_openai(lambda _: "Answer [1] [2]")
    await answer_question(
        "q",
        router=Router(),
        dispatcher=RetrievalDispatcher({mode: CrossBubbleRetriever(mode)}, mode),
        llm=LLMClient(settings, client=client),
        async_llm=None,
        graph_store=CanonicalGraph() if has_graph else None,
        item_store=Items(),
        settings=settings,
    )
    context = transport.bodies[0]["messages"][1]["content"]
    assert ("Subject g-apple; relation knows:" in context) is has_graph
    assert ("(preferred)" in context) is has_graph


async def _simple_ask(
    settings, mock_openai, *, items, item_store, specific_item_id=None, chunks=None
):
    class ChunkRetriever:
        def retrieve(self, question, *, bubbles, time_scope=None, top_k=None):
            return RetrievalResult("classic", (), tuple(chunks))

    retriever = BubbleItems({"news": items}) if chunks is None else ChunkRetriever()
    client, transport = mock_openai(lambda _: "Answer [1]")
    result = await answer_question(
        "q",
        router=Router(specific=True),
        dispatcher=RetrievalDispatcher(
            {"classic" if chunks else "own": retriever}, "classic" if chunks else "own"
        ),
        llm=LLMClient(settings, client=client),
        async_llm=None,
        graph_store=None,
        item_store=item_store,
        settings=settings,
        specific_item_id=specific_item_id,
    )
    return result, transport.bodies[0]["messages"][1]["content"]


async def test_inferred_specific_item_majority(settings, mock_openai):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return f"ORIGINAL OF {item_id}"

    result, context = await _simple_ask(
        settings, mock_openai, items=["a", "a", "a", "b", "b"], item_store=Originals()
    )
    assert "ORIGINAL OF a" in context
    assert "ORIGINAL OF b" not in context
    assert result.specific_item_id == "a"
    assert result.answer.citations[0].item_id == "a"


@pytest.mark.parametrize(
    "items",
    [
        ["a", "a", "b", "b"],  # tie
        ["a", "a", "b", "b", "c"],  # plurality but no strict majority
    ],
)
async def test_inference_without_majority_adds_no_item_text(
    settings, mock_openai, items
):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return "ORIGINAL TEXT"

    result, context = await _simple_ask(
        settings, mock_openai, items=items, item_store=Originals()
    )
    assert "ORIGINAL TEXT" not in context
    assert result.specific_item_id is None


async def test_inference_counts_only_top_five_facts(settings, mock_openai):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return f"ORIGINAL OF {item_id}"

    # The top five facts are b, b, b, a, a, so "b" wins despite "a" leading overall.
    items = ["b"] * 3 + ["a"] * SPECIFIC_ITEM_INFERENCE_FACTS
    result, context = await _simple_ask(
        settings, mock_openai, items=items, item_store=Originals()
    )
    assert result.specific_item_id == "b"
    assert "ORIGINAL OF b" in context
    assert "ORIGINAL OF a" not in context


async def test_inference_falls_back_to_chunks(settings, mock_openai):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return "ORIGINAL OF X"

    chunks = [
        replace(CHUNK, id=f"c{rank}", item_id=item)
        for rank, item in enumerate(["x", "x", "x", "y"])
    ]
    result, context = await _simple_ask(
        settings, mock_openai, items=None, item_store=Originals(), chunks=chunks
    )
    assert result.specific_item_id is None
    # build_context attaches original text only for items represented in facts.
    assert "ORIGINAL OF X" not in context


async def test_explicit_item_wins_over_inference(settings, mock_openai):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return f"ORIGINAL OF {item_id}"

    result, context = await _simple_ask(
        settings,
        mock_openai,
        items=["a", "a", "a", "b", "b"],
        item_store=Originals(),
        specific_item_id="b",
    )
    assert "ORIGINAL OF b" in context
    assert "ORIGINAL OF a" not in context
    assert result.specific_item_id == "b"


async def test_explicit_item_outside_top_facts_is_ignored(settings, mock_openai):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return f"ORIGINAL OF {item_id}"

    result, context = await _simple_ask(
        settings,
        mock_openai,
        items=["a", "a"],
        item_store=Originals(),
        specific_item_id="missing",
    )
    assert "ORIGINAL OF" not in context
    assert result.specific_item_id is None


@pytest.mark.parametrize("explicit", [None, "a"])
async def test_no_item_inference_for_multi_hop(settings, mock_openai, explicit):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            return "MUST NOT APPEAR"

    client, transport = mock_openai(lambda _: "Answer [1]")
    result = await answer_question(
        "q",
        router=Router("multi_hop", specific=True),
        dispatcher=RetrievalDispatcher(
            {"own": BubbleItems({"news": ["a", "a", "a"], "finance": ["b"]})}, "own"
        ),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=None,
        item_store=Originals(),
        settings=settings,
        specific_item_id=explicit,
    )
    context = transport.bodies[0]["messages"][1]["content"]
    assert "MUST NOT APPEAR" not in context
    assert result.specific_item_id is None


async def test_joined_groups_order_evidence_and_section(settings, mock_openai):
    class JoinGraph:
        def __init__(self, global_by_bubble):
            self.global_by_bubble = global_by_bubble

        def entities_in(self, bubbles):
            bubble = bubbles[0]
            gid = self.global_by_bubble.get(bubble)
            return (
                [] if gid is None else [Entity("e", "Example", "person", bubble, gid)]
            )

    client, transport = mock_openai(lambda _: "Answer [1] [2] [3] [4]")
    result = await answer_question(
        "q",
        router=Router("multi_hop", bubbles=("news", "finance", "sports")),
        dispatcher=RetrievalDispatcher(
            {
                "own": BubbleItems(
                    {"news": ["n1", "n2"], "finance": ["f1"], "sports": ["s1"]}
                )
            },
            "own",
        ),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=JoinGraph({"news": "g1", "sports": "g1", "finance": "g2"}),
        item_store=Items(),
        settings=settings,
    )
    assert result.multi_hop.joins == (
        JoinedGroup(frozenset({"news", "sports"}), frozenset({"g1"})),
    )
    # news and sports join via g1, so their facts become adjacent at news's routing position.
    assert [f.fact.item_id for f in result.retrieval.facts] == ["n1", "n2", "s1", "f1"]
    # Citations stay item-based and numbered by build_context, with no new numbers.
    assert [c.number for c in result.answer.citations] == [1, 2, 3, 4]
    assert [c.item_id for c in result.answer.citations] == ["n1", "n2", "s1", "f1"]
    assert result.answer.invalid_citations == ()
    context = transport.bodies[0]["messages"][1]["content"]
    assert "Joined findings (cite only numbered evidence above):" in context
    joined = context.split("Joined findings (cite only numbered evidence above):")[
        1
    ].split("Supplementary bubble notes")[0]
    assert "Bubbles news, sports share global entities: g1." in joined
    assert joined.index("Bubble news findings:") < joined.index(
        "Bubble sports findings:"
    )
    assert "Bubble finance findings:" not in joined
    assert "[" not in joined  # sanitized answers introduce no [n] citation numbers


@pytest.mark.parametrize("original", [None, ""])
async def test_unavailable_specific_item_not_reported(settings, mock_openai, original):
    class Originals(Items):
        def item_text(self, item_id, max_tokens=4000):
            if original is None:
                raise KeyError(item_id)
            return original

    result, _ = await _simple_ask(
        settings, mock_openai, items=["a"], item_store=Originals(), specific_item_id="a"
    )
    assert result.specific_item_id is None


async def test_join_identifiers_cannot_inject_citations(settings, mock_openai):
    from omnistream.retrieval.citations import AnswerContext, parse_citations

    class JoinGraph:
        def entities_in(self, bubbles):
            return [
                Entity("e", "Example", "person", bubble, "global[97]")
                for bubble in bubbles
            ]

    client, transport = mock_openai(lambda _: "Answer [1]")
    await answer_question(
        "q",
        router=Router("multi_hop", bubbles=("b[98]", "other")),
        dispatcher=RetrievalDispatcher(
            {"own": BubbleItems({"b[98]": ["a"], "other": ["b"]})}, "own"
        ),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=JoinGraph(),
        item_store=Items(),
        settings=settings,
    )
    context = transport.bodies[0]["messages"][1]["content"]
    notes = context.split("Joined findings")[1]
    parsed = parse_citations(notes, AnswerContext("", ()))
    assert not parsed and not parsed.invalid
    assert "b(98)" in notes and "global(97)" in notes


@pytest.mark.parametrize("subagents", [False, True])
async def test_exclusions_flow_from_routing_to_retrieval(
    settings, mock_openai, subagents
):
    from unittest.mock import Mock

    router = Router(bubbles=("news",))
    router.decision = replace(router.decision, excluded_bubbles=("finance",))
    retriever = Mock()
    retriever.retrieve.return_value = RetrievalResult("own", (ScoredFact(FACT, 1),))
    client, _ = mock_openai(lambda _: "Supported [1].")
    await answer_question(
        "q",
        router=router,
        dispatcher=RetrievalDispatcher({"own": retriever}, "own"),
        llm=LLMClient(settings, client=client),
        async_llm=ScriptedLLM(),
        graph_store=Graph(),
        item_store=Items(),
        settings=settings,
        subagents=subagents,
        exclude=("finance",),
    )
    assert retriever.retrieve.call_args.kwargs["excluded_bubbles"] == ("finance",)
