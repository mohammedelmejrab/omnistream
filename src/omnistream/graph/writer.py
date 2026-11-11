"""Graph writer (spec C4): Graphiti episode + provenance, grounding flags, global
links, temporal status, corroboration, chunks, and bubble summary refresh."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.datetime_utils import utc_now
from pydantic import BaseModel

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.graph.chunks import ChunkStore
from omnistream.graph.graphiti_client import ENTITY_TYPES
from omnistream.graph.grounding import is_grounded
from omnistream.graph.linker import GlobalEntityLinker
from omnistream.graph.ops import EdgeState, GraphOps
from omnistream.models import Source
from omnistream.retrieval.models import _utc

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = (
    "You maintain a short overview of a topic area in a knowledge base. Given the "
    "topic's name, description and recent facts, write 2-4 sentences describing what "
    "the area currently covers. Do not invent facts."
)


class BubbleSummary(BaseModel):
    summary: str


@dataclass
class WriteResult:
    episode_uuids: list[str] = field(default_factory=list)
    entities_new: int = 0
    entities_ungrounded: int = 0
    edges: int = 0
    chunks: int = 0


def corroborate(
    state: EdgeState, source_id: str, credibility: float
) -> tuple[list[str], list[float], float]:
    """Record one source's assertion; returns (source_ids, credibilities,
    confidence) with confidence = 1 - prod(1 - c_i) over distinct sources."""
    ids, creds = list(state.source_ids), list(state.credibilities)
    if source_id in ids:
        creds[ids.index(source_id)] = credibility
    else:
        ids.append(source_id)
        creds.append(credibility)
    miss = 1.0
    for c in creds:
        miss *= 1.0 - c
    return ids, creds, 1.0 - miss


def _entity_type(labels: list[str]) -> str:
    return next((label for label in labels if label != "Entity"), "Entity")


class GraphWriter:
    def __init__(
        self,
        graphiti: Graphiti,
        ops: GraphOps,
        linker: GlobalEntityLinker,
        chunks: ChunkStore,
        repo: Repository,
        settings: Settings,
        llm=None,
    ) -> None:
        self._graphiti = graphiti
        self._ops = ops
        self._linker = linker
        self._chunks = chunks
        self._repo = repo
        self._settings = settings
        self._llm = llm
        # Graphiti's dedup/invalidation is not safe under concurrent episodes.
        self._lock = asyncio.Lock()

    @property
    def ops(self) -> GraphOps:
        return self._ops

    @property
    def chunks(self) -> ChunkStore:
        return self._chunks

    async def write(
        self, item: ItemRow, text: str, bubble_ids: list[str], source: Source
    ) -> WriteResult:
        result = WriteResult()
        for bubble_id in bubble_ids:
            async with self._lock:
                await self._write_bubble(item, text, bubble_id, source, result)
            await self._repo.bump_episode_counter(bubble_id)
            try:
                await self.maybe_refresh_summary(bubble_id)
            except Exception:
                logger.exception("summary refresh failed for bubble %s", bubble_id)
        return result

    async def _write_bubble(
        self,
        item: ItemRow,
        text: str,
        bubble_id: str,
        source: Source,
        result: WriteResult,
    ) -> None:
        ref_time = item.published_at or datetime.now(UTC)
        started = utc_now()
        # 1. Graphiti episode, tagged with item provenance.
        res = await self._graphiti.add_episode(
            name=item.title or item.url or item.id,
            episode_body=text,
            source=EpisodeType.text,
            source_description=json.dumps(
                {
                    "item_id": item.id,
                    "url": item.url,
                    "credibility": source.credibility,
                    "source_id": source.id,
                }
            ),
            reference_time=ref_time,
            group_id=bubble_id,
            entity_types=ENTITY_TYPES,
        )
        episode_uuid = res.episode.uuid
        result.episode_uuids.append(episode_uuid)
        await self._ops.tag_episode(
            episode_uuid, item.id, item.url, source.credibility, source.id
        )

        # 2. Grounding of newly created entities (flag, never delete).
        grounding_text = f"{item.title}\n{text}"
        ungrounded: set[str] = set()
        new_nodes = [n for n in res.nodes if n.created_at >= started]
        for node in new_nodes:
            aliases = node.attributes.get("aliases") or []
            ok = any(
                is_grounded(name, grounding_text, self._settings.grounding_threshold)
                for name in (node.name, *aliases)
            )
            await self._ops.set_node_grounded(node.uuid, ok)
            if not ok:
                ungrounded.add(node.uuid)
        result.entities_new += len(new_nodes)
        result.entities_ungrounded += len(ungrounded)

        # 3. Global linking.
        for node in new_nodes:
            await self._linker.link(
                node.uuid,
                node.name,
                _entity_type(node.labels),
                node.name_embedding,
                add_alias=node.uuid not in ungrounded,
            )

        # Edges asserted by this episode vs. old edges Graphiti merely invalidated.
        asserted = [e for e in res.edges if episode_uuid in e.episodes]
        states = await self._ops.get_edge_states([e.uuid for e in res.edges])
        for edge in asserted:
            state = states.get(edge.uuid, EdgeState())
            # 5. Corroboration.
            ids, creds, conf = corroborate(state, source.id, source.credibility)
            bad = {edge.source_node_uuid, edge.target_node_uuid} & ungrounded
            props = {
                "item_ids": state.item_ids
                if item.id in state.item_ids
                else [*state.item_ids, item.id],
                "credibility": source.credibility,
                "source_ids": ids,
                "credibilities": creds,
                "source_count": len(ids),
                "confidence": conf,
                # A previously-flagged edge is never silently promoted.
                "grounded": not bad and state.grounded is not False,
            }
            previous = state.published_at
            if previous is None or _utc(ref_time) > _utc(previous):
                props.update(
                    item_id=item.id, published_at=_utc(ref_time), source_url=item.url
                )
            await self._ops.set_edge_props(edge.uuid, props)
        result.edges += len(asserted)

        # 4. Temporal status, including edges Graphiti invalidated just now.
        if res.edges:
            await self._ops.set_edge_statuses([e.uuid for e in res.edges])

        # 6. Chunks.
        result.chunks += await self._chunks.add(
            bubble_id, item.id, text, item.url, item.published_at
        )

    async def maybe_refresh_summary(self, bubble_id: str) -> bool:
        """Regenerate `auto_summary` every N episodes; `description` is never touched."""
        if self._llm is None:
            return False
        if (
            await self._repo.episodes_since_summary(bubble_id)
            < self._settings.summary_refresh_episodes
        ):
            return False
        bubble = await self._repo.get_bubble(bubble_id)
        if bubble is None:
            return False
        facts = await self._ops.recent_facts(bubble_id, 40)
        user = (
            f"Topic: {bubble.name}\nDescription: {bubble.description}\n"
            f"Previous overview: {bubble.auto_summary or '(none)'}\n"
            "Recent facts:\n" + "\n".join(f"- {f}" for f in facts)
        )
        out = await self._llm.parse(
            self._settings.llm_model, SUMMARY_SYSTEM, user, BubbleSummary
        )
        await self._repo.set_auto_summary(bubble_id, out.summary)
        return True


async def build_graph_writer(
    settings: Settings, repo: Repository, embedder, llm=None
) -> GraphWriter:
    """Real wiring: Graphiti on Neo4j, indices built once at startup."""
    from omnistream.graph.graphiti_client import build_graphiti
    from omnistream.graph.ops import Neo4jGraphOps

    graphiti = build_graphiti(settings, embedder)
    await graphiti.build_indices_and_constraints()
    ops = Neo4jGraphOps(graphiti.driver, settings.embed_dim)
    await ops.ensure_schema()
    return GraphWriter(
        graphiti,
        ops,
        GlobalEntityLinker(
            ops,
            embedder,
            settings.embed_match_threshold,
            settings.fuzzy_match_threshold,
        ),
        ChunkStore(settings.data_dir, embedder, settings.chunk_tokens),
        repo,
        settings,
        llm,
    )
