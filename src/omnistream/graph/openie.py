"""Single-call OpenIE extraction: a fast alternative to Graphiti's episode pipeline.

Graphiti's ``add_episode`` makes many LLM calls per item (entity extraction,
node dedup, edge extraction, edge dedup, invalidation, summaries). For a static
benchmark corpus of tens of thousands of passages that is too slow and costly,
so this module does what HippoRAG does: ONE structured LLM call per passage that
returns typed entities and subject-predicate-object triples, then writes them as
ordinary Graphiti nodes and edges (``Episodic``, ``Entity``, ``MENTIONS``,
``RELATES_TO``) so every retriever reads the result unchanged.

Entities are deduplicated within a group by an exact normalised name key (as
HippoRAG does); cross-surface-form merging is left to the global linker and the
alias pairs it already applies. No temporal invalidation is attempted: the
corpus is static.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

from pydantic import BaseModel, Field

from omnistream.graph.graphiti_client import ENTITY_TYPES

TYPE_NAMES = tuple(ENTITY_TYPES)
DEFAULT_TYPE = "Concept"

OPENIE_SYSTEM = (
    "You build a knowledge graph from one encyclopedia-style passage.\n"
    "1. List the entities the passage mentions: people, organizations, places, "
    "works, events, products, dates and other specific things. Use the most "
    "complete name the passage gives (for example 'Barack Obama', not 'Obama' or "
    "'he'). Give each a type from: " + ", ".join(TYPE_NAMES) + ". Use Concept for "
    "anything that is not a named entity (dates, quantities, roles, generic "
    "things).\n"
    "2. List factual triples (subject, predicate, object) stated in the passage. "
    "Subject and object must be entity names from step 1, written exactly the same "
    "way. Resolve pronouns to the entity they refer to. Include every fact that "
    "links two entities, including dates, places and roles.\n"
    "3. For each triple, write 'fact': one short self-contained sentence that "
    "states it using the full entity names.\n"
    "Only use information stated in the passage. Do not add outside knowledge."
)


class OpenIEEntity(BaseModel):
    name: str
    type: str = DEFAULT_TYPE


class OpenIETriple(BaseModel):
    subject: str
    predicate: str
    object: str
    fact: str = ""


class OpenIEResult(BaseModel):
    entities: list[OpenIEEntity] = Field(default_factory=list)
    triples: list[OpenIETriple] = Field(default_factory=list)


def name_key(name: str) -> str:
    """Exact-match key: NFKC, casefolded, whitespace collapsed, edge punctuation off."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,;:!?\"'`()[]{}")


def canonical_type(value: str) -> str:
    lowered = re.sub(r"[^a-z]", "", (value or "").casefold())
    for type_name in TYPE_NAMES:
        if type_name.casefold() == lowered:
            return type_name
    aliases = {"organisation": "Organization", "place": "Location", "work": "Publication"}
    return aliases.get(lowered, DEFAULT_TYPE)


def relation_name(predicate: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", predicate)
    return "_".join(w.upper() for w in words)[:60] or "RELATED_TO"


@dataclass
class CleanExtraction:
    """Validated extraction: unique entities by key and triples between them."""

    entities: dict[str, tuple[str, str]] = field(default_factory=dict)  # key -> (name, type)
    triples: list[tuple[str, str, str, str]] = field(default_factory=list)  # (s_key, rel, o_key, fact)


def clean_extraction(result: OpenIEResult) -> CleanExtraction:
    out = CleanExtraction()
    for entity in result.entities:
        key = name_key(entity.name)
        if key and key not in out.entities:
            out.entities[key] = (entity.name.strip(), canonical_type(entity.type))
    seen: set[tuple[str, str, str]] = set()
    for triple in result.triples:
        s_key, o_key = name_key(triple.subject), name_key(triple.object)
        if not s_key or not o_key or s_key == o_key:
            continue
        # Endpoints the model forgot to list become untyped concepts.
        for key, raw in ((s_key, triple.subject), (o_key, triple.object)):
            out.entities.setdefault(key, (raw.strip(), DEFAULT_TYPE))
        rel = relation_name(triple.predicate)
        if (s_key, rel, o_key) in seen:
            continue
        seen.add((s_key, rel, o_key))
        fact = triple.fact.strip() or (
            f"{out.entities[s_key][0]} {triple.predicate.strip()} {out.entities[o_key][0]}"
        )
        out.triples.append((s_key, rel, o_key, fact))
    return out


# Fact-dense passages (e.g. long filmographies) need more than the default
# 4096 output tokens for their triples; the cap only matters for those.
OPENIE_MAX_TOKENS = 16384


async def extract_openie(llm, model: str, text: str) -> OpenIEResult:
    return await llm.parse(
        model, OPENIE_SYSTEM, f"Passage:\n{text}", OpenIEResult,
        max_tokens=OPENIE_MAX_TOKENS,
    )


_FIND_BY_KEY = (
    "UNWIND $keys AS key "
    "MATCH (n:Entity {group_id: $group, name_key: key}) "
    "RETURN key, n.uuid AS uuid ORDER BY n.created_at"
)


class OpenIEEpisodeBuilder:
    """Writes one passage's cached extraction as a Graphiti-shaped episode.

    Called by ``GraphWriter`` instead of ``Graphiti.add_episode``; returns an
    object with ``episode``, ``nodes`` and ``edges`` like ``AddEpisodeResults``.
    Reused entities keep their original ``created_at``, so the writer grounds
    and links only the nodes this episode created.
    """

    def __init__(self, driver, embedder, extractions: dict[str, OpenIEResult]):
        self._driver = driver
        self._embedder = embedder
        self._extractions = extractions
        self._indexed = False

    async def _ensure_index(self) -> None:
        if not self._indexed:
            await self._driver.execute_query(
                "CREATE INDEX entity_name_key IF NOT EXISTS FOR (n:Entity) ON (n.name_key)"
            )
            self._indexed = True

    async def __call__(
        self,
        *,
        item_id: str,
        name: str,
        text: str,
        group_id: str,
        reference_time: datetime,
        source_description: str,
    ):
        from graphiti_core.edges import EntityEdge, EpisodicEdge
        from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
        from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
        from graphiti_core.utils.datetime_utils import utc_now

        from omnistream.graph.graphiti_client import BgeEmbedderClient

        if item_id not in self._extractions:
            raise KeyError(f"no OpenIE extraction cached for item {item_id}")
        await self._ensure_index()
        clean = clean_extraction(self._extractions[item_id])
        now = utc_now()

        records, _, _ = await self._driver.execute_query(
            _FIND_BY_KEY, keys=list(clean.entities), group=group_id
        )
        existing: dict[str, str] = {}
        for record in records:
            existing.setdefault(record["key"], record["uuid"])
        reused = await EntityNode.get_by_uuids(self._driver, list(set(existing.values())))
        nodes_by_key: dict[str, EntityNode] = {}
        by_uuid = {n.uuid: n for n in reused}
        for key, uuid in existing.items():
            if uuid in by_uuid:
                nodes_by_key[key] = by_uuid[uuid]

        new_keys = [k for k in clean.entities if k not in nodes_by_key]
        triples = clean.triples
        vectors = await self._embedder.embed(
            [clean.entities[k][0] for k in new_keys] + [t[3] for t in triples]
        ) if (new_keys or triples) else []
        new_nodes = []
        for key, vector in zip(new_keys, vectors[: len(new_keys)]):
            entity_name, entity_type = clean.entities[key]
            node = EntityNode(
                name=entity_name,
                group_id=group_id,
                labels=["Entity", entity_type],
                created_at=now,
                name_embedding=vector,
                attributes={"name_key": key},
            )
            nodes_by_key[key] = node
            new_nodes.append(node)

        episode = EpisodicNode(
            name=name,
            group_id=group_id,
            source=EpisodeType.text,
            source_description=source_description,
            content=text,
            valid_at=reference_time,
            created_at=now,
        )
        edges = []
        for (s_key, rel, o_key, fact), vector in zip(triples, vectors[len(new_keys):]):
            edges.append(
                EntityEdge(
                    source_node_uuid=nodes_by_key[s_key].uuid,
                    target_node_uuid=nodes_by_key[o_key].uuid,
                    name=rel,
                    fact=fact,
                    fact_embedding=vector,
                    group_id=group_id,
                    episodes=[episode.uuid],
                    created_at=now,
                    valid_at=reference_time,
                    reference_time=reference_time,
                )
            )
        episode.entity_edges = [e.uuid for e in edges]
        mentions = [
            EpisodicEdge(
                source_node_uuid=episode.uuid,
                target_node_uuid=node.uuid,
                group_id=group_id,
                created_at=now,
            )
            for node in nodes_by_key.values()
        ]
        # One transaction: the episode, its new entities, MENTIONS and facts land
        # together, so the writer's recover_episode sees all or nothing.
        await add_nodes_and_edges_bulk(
            self._driver, [episode], mentions, new_nodes, edges,
            BgeEmbedderClient(self._embedder),
        )
        return SimpleNamespace(
            episode=episode, nodes=list(nodes_by_key.values()), edges=edges
        )


def load_extraction_cache(path) -> dict[str, dict]:
    """passage-keyed JSONL cache: {"key": ..., "result": {...}, "usage": {...}}."""
    cache: dict[str, dict] = {}
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn final line from an interrupted run
                cache[row["key"]] = row
    except FileNotFoundError:
        pass
    return cache
