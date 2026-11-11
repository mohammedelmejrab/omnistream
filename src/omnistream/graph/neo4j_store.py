"""Injected-driver Neo4j GraphStore (spec 4.3, C5 and 7).

Graphiti entities use uuid/group_id/name, fact relationships RELATES_TO use
uuid/fact and the provenance fields in section 7. Identity edges are SAME_AS.
All query values, including index names and limits, are parameters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np

from omnistream.config import Settings
from omnistream.graph.memory_store import _bounds, _seed_bounds
from omnistream.retrieval.models import Entity, Fact, Subgraph, TimeScope, _utc

_VALID = """r.grounded = true
AND (r.valid_at IS NULL OR r.invalid_at IS NULL OR r.valid_at < r.invalid_at)
AND ($start IS NULL OR r.invalid_at IS NULL OR r.invalid_at > $start)
AND ($end IS NULL OR r.valid_at IS NULL OR r.valid_at <= $end)"""

# Neo4j 5.23+ scoped subquery: the outer variable is imported by listing it in
# parentheses, without the deprecated importing WITH. Inside the clause all
# other variables are new (p is re-bound by UNWIND), and the outer scope
# continues using its own `paths` after the clause returns `facts`.
_EXPAND_CYPHER = (
    """
MATCH (seed) WHERE seed.uuid IN $seed_ids
OPTIONAL MATCH p=(seed)-[:RELATES_TO|SAME_AS*0..2]-(endpoint)
WHERE length(p) <= $max_hops AND all(r IN relationships(p) WHERE type(r) = 'SAME_AS' OR ("""
    + _VALID
    + """))
WITH collect(p) AS paths
CALL (paths) {
  UNWIND paths AS p
  WITH p, last(relationships(p)) AS r
  WHERE type(r) = 'RELATES_TO'
  WITH r, min(length(p)) AS distance
  ORDER BY distance, r.uuid LIMIT $max_edges
  RETURN collect({fact: properties(r), subject: startNode(r).uuid,
                  object: endNode(r).uuid}) AS facts
}
RETURN facts,
 reduce(ns = [], p IN paths | ns + nodes(p)) AS entities,
 reduce(links = [], p IN paths | links + [r IN relationships(p) WHERE type(r) = 'SAME_AS' |
     [startNode(r).uuid, endNode(r).uuid]]) AS same_as
"""
)


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_native"):
        return value.to_native()
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
        if isinstance(value, str)
        else value
    )


def _entity(node: Any) -> Entity:
    data = dict(node)
    return Entity(
        id=data.get("id", data.get("uuid")),
        name=data["name"],
        type=data.get("type", "Concept"),
        bubble=data.get("bubble", data.get("group_id", "")),
        global_id=data.get("global_id"),
        aliases=tuple(data.get("aliases") or ()),
    )


def _fact(edge: Any, subject_id: str, object_id: str) -> Fact:
    data = dict(edge)
    return Fact(
        id=data.get("id", data.get("uuid")),
        subject_id=subject_id,
        object_id=object_id,
        relation=data.get("relation", data.get("name", "RELATES_TO")),
        text=data.get("text", data.get("fact", "")),
        bubble=data.get("bubble", data.get("group_id", "")),
        item_id=data["item_id"],
        source_url=data.get("source_url"),
        published_at=_datetime(data["published_at"]),
        valid_at=_datetime(data.get("valid_at")),
        invalid_at=_datetime(data.get("invalid_at")),
        grounded=data.get("grounded", False),
        credibility=data.get("credibility", 0.5),
        confidence=data.get("confidence", 0.5),
        source_count=data.get("source_count", 1),
    )


class Neo4jGraphStore:
    """Synchronous read adapter; constructor never opens a network connection."""

    def __init__(
        self,
        driver: Any,
        database: str = "neo4j",
        entity_index_name: str = "entity_name_embedding",
        fact_index_name: str = "fact_embedding",
    ) -> None:
        if not all(
            isinstance(v, str) and v.strip()
            for v in (database, entity_index_name, fact_index_name)
        ):
            raise ValueError("database and index names must be non-empty strings")
        self.driver, self.database = driver, database
        self.entity_index_name, self.fact_index_name = (
            entity_index_name,
            fact_index_name,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> Neo4jGraphStore:
        """Build a lazy driver using NEO4J_URI/USER/PASSWORD; caller owns its lifetime."""
        from neo4j import GraphDatabase

        return cls(
            GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            )
        )

    def _run(self, query: str, **parameters: Any) -> list[Any]:
        with self.driver.session(database=self.database) as session:
            return list(session.run(query, **parameters))

    def entities_in(self, bubbles: Sequence[str]) -> list[Entity]:
        records = self._run(
            "MATCH (e:Entity) WHERE e.group_id IN $bubbles RETURN e ORDER BY e.uuid",
            bubbles=list(bubbles),
        )
        return [_entity(r["e"]) for r in records]

    def seed_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 5,
        min_cosine: float = 0.5,
    ) -> list[tuple[Entity, float]]:
        _seed_bounds(top_k, min_cosine)
        vector = np.asarray(embedding, dtype=float)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError("embedding must be a finite vector")
        if not top_k or not bubbles:
            return []
        # Query all indexed entity candidates before filtering, so unrelated
        # bubbles cannot consume the selected bubbles' top-k budget. Neo4j's
        # cosine index score is (1 + cosine) / 2; expose the actual cosine.
        records = self._run(
            """
MATCH (candidate:Entity) WITH count(candidate) AS candidate_count
CALL db.index.vector.queryNodes($index_name, CASE WHEN candidate_count > 0 THEN candidate_count ELSE 1 END,
                                $embedding) YIELD node, score AS index_score
WITH node, 2.0 * index_score - 1.0 AS score
WHERE node.group_id IN $bubbles AND score >= $min_cosine
RETURN node AS e, score ORDER BY score DESC, node.uuid LIMIT $top_k
""",
            index_name=self.entity_index_name,
            embedding=vector.tolist(),
            bubbles=list(bubbles),
            min_cosine=min_cosine,
            top_k=top_k,
        )
        return [(_entity(r["e"]), float(r["score"])) for r in records]

    def expand(
        self,
        seed_ids: Sequence[str],
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None,
        max_hops: int = 2,
        max_edges: int = 500,
    ) -> Subgraph:
        _bounds(max_hops, max_edges)
        scope = time_scope or TimeScope()
        # The literal maximum is always two: runtime depth only narrows it.
        # Collect identity links separately so the fact cap never consumes them.
        records = self._run(
            _EXPAND_CYPHER,
            seed_ids=list(seed_ids),
            max_hops=max_hops,
            max_edges=max_edges,
            start=_utc(scope.start),
            end=_utc(scope.end),
        )
        entities, facts, links = {}, {}, set()
        for record in records:
            for node in record.get("entities", []):
                entity = _entity(node)
                entities[entity.id] = entity
            for row in record.get("facts", []):
                fact = _fact(row["fact"], row["subject"], row["object"])
                facts[fact.id] = fact
            links.update(tuple(sorted(pair)) for pair in record.get("same_as", []))
        return Subgraph(
            dict(sorted(entities.items())), tuple(facts.values()), tuple(sorted(links))
        )

    def neighbors(self, entity_id: str, depth: int = 1) -> Subgraph:
        _bounds(depth, 500)
        return self.expand([entity_id], bubbles=(), time_scope=None, max_hops=depth)

    def facts_about(
        self, entity_id: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[Fact]:
        scope = TimeScope(start, end)
        records = self._run(
            """MATCH (s)-[r:RELATES_TO]->(o)
WHERE (s.uuid = $entity_id OR o.uuid = $entity_id) AND """
            + _VALID
            + """
RETURN DISTINCT r, s.uuid AS subject, o.uuid AS object ORDER BY r.uuid""",
            entity_id=entity_id,
            start=_utc(scope.start),
            end=_utc(scope.end),
        )
        return [_fact(r["r"], r["subject"], r["object"]) for r in records]

    def fact_embeddings(self, fact_ids: Sequence[str]) -> dict[str, np.ndarray]:
        records = self._run(
            """MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $fact_ids
AND coalesce(r.fact_embedding, r.embedding) IS NOT NULL
RETURN r.uuid AS id, coalesce(r.fact_embedding, r.embedding) AS embedding""",
            fact_ids=list(fact_ids),
        )
        return {r["id"]: np.asarray(r["embedding"], dtype=float) for r in records}
