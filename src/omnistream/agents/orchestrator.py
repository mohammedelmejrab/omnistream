"""Parallel bubble research and transitive global-entity joining."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from omnistream.config import Settings
from omnistream.llm import AsyncLLMClient
from omnistream.retrieval.models import RetrievalMode, TimeScope
from omnistream.retrieval.protocols import GraphStore, ItemStore, Retriever

from .subagent import Subagent, SubagentFindings, format_error


@dataclass(frozen=True)
class JoinedGroup:
    """Bubbles merged through shared global entities, with those ids."""

    bubbles: frozenset[str]
    global_entity_ids: frozenset[str]


@dataclass(frozen=True)
class MultiHopResult:
    findings: tuple[SubagentFindings, ...]
    joined_groups: list[set[str]] = field(default_factory=list)
    joins: tuple[JoinedGroup, ...] = ()


async def run_subagents(
    question: str,
    *,
    bubbles: Sequence[str],
    mode: RetrievalMode,
    llm: AsyncLLMClient,
    retriever: Retriever,
    graph_store: GraphStore | None,
    item_store: ItemStore,
    settings: Settings,
    time_scope: TimeScope | None = None,
    excluded_bubbles: tuple[str, ...] = (),
) -> MultiHopResult:
    bubbles = list(dict.fromkeys(bubbles))

    async def run(bubble):
        return await Subagent(
            bubble=bubble,
            mode=mode,
            llm=llm,
            retriever=retriever,
            graph_store=graph_store,
            item_store=item_store,
            settings=settings,
            time_scope=time_scope,
            **({"excluded_bubbles": excluded_bubbles} if excluded_bubbles else {}),
        ).run(question)

    results = await asyncio.gather(
        *(run(bubble) for bubble in bubbles), return_exceptions=True
    )
    findings = tuple(
        SubagentFindings(bubble, stopped_reason="error", error=format_error(result))
        if isinstance(result, BaseException)
        else result
        for bubble, result in zip(bubbles, results)
    )
    groups: list[tuple[set[str], set[str]]] = []
    for finding in findings:
        linked = {finding.bubble}
        entities = set(finding.global_entity_ids)
        remaining = []
        for group, ids in groups:
            if entities & ids:
                linked |= group
                entities |= ids
            else:
                remaining.append((group, ids))
        groups = remaining + [(linked, entities)]
    return MultiHopResult(
        findings,
        [group for group, _ in groups if len(group) > 1],
        tuple(
            JoinedGroup(frozenset(group), frozenset(ids))
            for group, ids in groups
            if len(group) > 1
        ),
    )
