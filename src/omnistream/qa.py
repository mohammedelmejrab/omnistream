"""C5 end-to-end routed, cited question answering across all retrieval modes."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace

from omnistream.agents import MultiHopResult, SubagentFindings, run_subagents
from omnistream.config import Settings
from omnistream.llm import AsyncLLMClient, LLMClient
from omnistream.retrieval.citations import CitedAnswer, build_context, generate_answer
from omnistream.retrieval.merge import Conflict
from omnistream.retrieval.models import (
    RetrievalMode,
    RetrievalResult,
    ScoredFact,
    TimeScope,
)
from omnistream.retrieval.modes import RetrievalDispatcher
from omnistream.retrieval.protocols import GraphStore, ItemStore
from omnistream.retrieval.router import QueryRouter, RoutingDecision

SPECIFIC_ITEM_INFERENCE_FACTS = 5
"""Top facts (chunks when no facts exist) inspected to infer a specific item."""


def _retrieval_scope(routing: RoutingDecision) -> TimeScope | None:
    """Scope for retrieval: the routed interval, or any-time for event hints.

    A question relative to an event (temporal_relation) has no calendar date,
    so its routed scope is None and retrieval would default to "facts valid
    now" and hide the historical predecessor. An explicit unbounded scope
    keeps every fact-validity interval eligible (spec C5 own step 2; E8).
    """
    if routing.time_scope is not None or routing.temporal_relation is None:
        return routing.time_scope
    return TimeScope(None, None)


@dataclass(frozen=True)
class QAResult:
    answer: CitedAnswer
    routing: RoutingDecision
    mode: RetrievalMode
    retrieval: RetrievalResult | None = None
    multi_hop: MultiHopResult | None = None
    specific_item_id: str | None = None
    conflicts: tuple[Conflict, ...] = ()


def _infer_specific_item(result: RetrievalResult) -> str | None:
    """Item supplying a strict majority of the top evidence, if any (spec C5).

    Ranked facts come first; chunks are the fallback when none exist. Ties
    and the absence of a strict majority yield None, as does empty evidence.
    """
    if result.facts:
        items = [
            entry.fact.item_id for entry in result.facts[:SPECIFIC_ITEM_INFERENCE_FACTS]
        ]
    else:
        items = [
            chunk.item_id for chunk in result.chunks[:SPECIFIC_ITEM_INFERENCE_FACTS]
        ]
    if not items:
        return None
    item, count = Counter(items).most_common(1)[0]
    return item if count * 2 > len(items) else None


def _ordered_findings(
    multi_hop: MultiHopResult, bubbles: Sequence[str]
) -> tuple[SubagentFindings, ...]:
    """Findings with joined-group bubbles adjacent (spec C5 merge and answer).

    Each group is placed at its first bubble's position in the routing order;
    inside a group, bubbles and their evidence keep first-seen order.
    """
    position: dict[str, int] = {}
    for bubble in bubbles:
        position.setdefault(bubble, len(position))
    for finding in multi_hop.findings:
        position.setdefault(finding.bubble, len(position))
    group_of: dict[str, frozenset[str]] = {}
    for join in multi_hop.joins:
        for bubble in join.bubbles:
            group_of.setdefault(bubble, join.bubbles)
    ordered: list[str] = []
    for bubble in position:
        for member in sorted(group_of.get(bubble, {bubble}), key=position.__getitem__):
            if member not in ordered:
                ordered.append(member)
    by_bubble: dict[str, list[SubagentFindings]] = {}
    for finding in multi_hop.findings:
        by_bubble.setdefault(finding.bubble, []).append(finding)
    return tuple(finding for bubble in ordered for finding in by_bubble.get(bubble, ()))


def _plain(text: str) -> str:
    """Render agent identifiers so they cannot look like [n] citation numbers."""
    return text.replace("[", "(").replace("]", ")")


async def answer_question(
    question: str,
    *,
    router: QueryRouter,
    dispatcher: RetrievalDispatcher,
    llm: LLMClient,
    async_llm: AsyncLLMClient,
    graph_store: GraphStore | None,
    item_store: ItemStore,
    settings: Settings,
    mode: RetrievalMode | None = None,
    pins: Sequence[str] = (),
    exclude: Sequence[str] = (),
    subagents: bool | None = None,
    specific_item_id: str | None = None,
) -> QAResult:
    """Explicit subagents on/off overrides routing; dispatcher supplies default mode.

    The merged multi-hop evidence is exposed as retrieval as well, preserving
    joined-group adjacency, bubble order and each agent's first-seen evidence
    order. Subagent answers are supplementary notes; only stored evidence
    supplies citation numbers. When the question names a specific item, an
    explicit item wins; otherwise the simple strategy infers one from the top
    evidence (multi-hop subagents read item text themselves).
    """
    selected = dispatcher.default_mode if mode is None else mode
    if selected not in dispatcher.retrievers:
        raise ValueError(f"unknown or unconfigured retrieval mode: {selected}")
    routing = await asyncio.to_thread(
        router.route, question, pins=pins, exclude=exclude
    )
    retrieval_scope = _retrieval_scope(routing)
    use_agents = routing.strategy == "multi_hop" if subagents is None else subagents
    multi_hop = None
    ordered_findings: tuple[SubagentFindings, ...] = ()
    if use_agents:
        multi_hop = await run_subagents(
            question,
            bubbles=routing.bubbles,
            mode=selected,
            llm=async_llm,
            retriever=dispatcher.retrievers[selected],
            graph_store=graph_store,
            item_store=item_store,
            settings=settings,
            time_scope=retrieval_scope,
            **(
                {"excluded_bubbles": routing.excluded_bubbles}
                if routing.excluded_bubbles
                else {}
            ),
        )
        ordered_findings = _ordered_findings(multi_hop, routing.bubbles)
        facts, chunks = {}, {}
        for finding in ordered_findings:
            for fact in finding.facts:
                facts.setdefault(fact.id, fact)
            for chunk in finding.chunks:
                chunks.setdefault(chunk.id, chunk)
        scored = {
            entry.fact.id: entry
            for finding in ordered_findings
            for entry in finding.scored_facts
        }
        seeds = {
            entity.id: entity
            for finding in ordered_findings
            for entity in finding.seeds
        }
        result = RetrievalResult(
            selected,
            tuple(
                ScoredFact(
                    fact,
                    0.0,
                    path=scored[fact.id].path if fact.id in scored else (),
                    ranks={"subagent": rank},
                )
                for rank, fact in enumerate(facts.values(), 1)
            ),
            tuple(chunks.values()),
            tuple(seeds.values()),
        )
    else:
        result = await asyncio.to_thread(
            dispatcher.retrieve,
            question,
            mode=selected,
            bubbles=routing.bubbles,
            time_scope=retrieval_scope,
            **(
                {"excluded_bubbles": routing.excluded_bubbles}
                if routing.excluded_bubbles
                else {}
            ),
        )
    specific = None
    if routing.names_specific_item and not use_agents:
        if specific_item_id is not None:
            specific = specific_item_id
        elif not use_agents:
            specific = _infer_specific_item(result)
    if specific not in {entry.fact.item_id for entry in result.facts}:
        specific = None
    canonical_ids = None
    entities = []
    if graph_store is not None:
        entities = await asyncio.to_thread(
            graph_store.entities_in,
            tuple(
                dict.fromkeys(
                    [*routing.bubbles, *(f.fact.bubble for f in result.facts)]
                )
            ),
        )
        canonical_ids = {
            entity.id: entity.global_id or entity.id for entity in entities
        }
    context = await asyncio.to_thread(
        build_context,
        result,
        item_store=item_store,
        canonical_ids=canonical_ids,
        span_llm=llm,
        entities={entity.id: entity for entity in entities},
        include_item_text_for=specific,
    )
    specific = context.expanded_item_id
    if multi_hop:
        position = {
            finding.bubble: index for index, finding in enumerate(ordered_findings)
        }
        joins = sorted(
            multi_hop.joins,
            key=lambda join: min(position[bubble] for bubble in join.bubbles),
        )
        answers = {
            finding.bubble: finding.answer
            for finding in ordered_findings
            if finding.answer
        }
        notes = [
            f"Bubble {_plain(bubble)} findings: {_plain(answer)}"
            for bubble, answer in answers.items()
        ]
        sections = []
        if joins:
            lines = ["Joined findings (cite only numbered evidence above):"]
            for join in joins:
                members = sorted(join.bubbles, key=position.__getitem__)
                lines.append(
                    f"Bubbles {', '.join(map(_plain, members))} share global entities: "
                    f"{', '.join(_plain(gid) for gid in sorted(join.global_entity_ids))}."
                )
                lines.extend(
                    f"Bubble {_plain(bubble)} findings: {_plain(answers[bubble])}"
                    for bubble in members
                    if bubble in answers
                )
            sections.append("\n".join(lines))
        if notes:
            sections.append(
                "Supplementary bubble notes "
                "(cite only numbered evidence above):\n" + "\n".join(notes)
            )
        if sections:
            context = replace(
                context, text=context.text + "\n\n" + "\n\n".join(sections)
            )
    answer = await asyncio.to_thread(
        generate_answer,
        llm,
        question,
        context,
        time_scope=routing.time_scope,
        temporal_relation=routing.temporal_relation,
        anchor_event=routing.anchor_event,
    )
    return QAResult(
        answer, routing, selected, result, multi_hop, specific, context.conflicts
    )
