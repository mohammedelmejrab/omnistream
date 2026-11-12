"""Injected-driver Neo4j GraphStore (spec 4.3, C5 and 7).

Graphiti entities use uuid/group_id/name, fact relationships RELATES_TO use
uuid/fact and the provenance fields in section 7. Identity edges are SAME_AS.
Query values and limits are parameters; DDL index identifiers are backtick-escaped.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np

from omnistream.config import Settings
from omnistream.graph.memory_store import _bounds, _seed_bounds
from omnistream.retrieval.models import Entity, Fact, Subgraph, TimeScope, _utc

_VALID = """r.grounded = true
AND (r.valid_at IS NULL OR r.invalid_at IS NULL OR r.valid_at < r.invalid_at)
AND ($now IS NULL OR (r.expired_at IS NULL
     AND (r.valid_at IS NULL OR r.valid_at <= $now)
     AND (r.invalid_at IS NULL OR r.invalid_at > $now)))
AND ($start IS NULL OR r.invalid_at IS NULL OR r.invalid_at > $start)
AND ($end IS NULL OR r.valid_at IS NULL OR r.valid_at <= $end)"""

# Each query expands exactly one logical hop. The caller deduplicates the
# frontier before the next query, avoiding variable-length path enumeration.
_EXPAND_CYPHER = (
    """
MATCH (seed:Entity) WHERE seed.uuid IN $seed_ids
AND NOT coalesce(seed.group_id, '') IN $excluded_bubbles
CALL (seed) {
  RETURN seed AS target, null AS r, null AS link
  UNION
  MATCH (seed)-[r:RELATES_TO]-(target:Entity)
  WHERE """
    + _VALID
    + """
  AND NOT coalesce(r.group_id, '') IN $excluded_bubbles
  AND NOT coalesce(target.group_id, '') IN $excluded_bubbles
  RETURN target, r, null AS link
  UNION
  MATCH (seed)-[:SAME_AS]->(:GlobalEntity)<-[:SAME_AS]-(target:Entity)
  WHERE target <> seed AND NOT coalesce(target.group_id, '') IN $excluded_bubbles
  RETURN target, null AS r, [seed.uuid, target.uuid] AS link
}
WITH collect(DISTINCT seed) + collect(DISTINCT target) AS nodes,
     collect(DISTINCT r) AS edges, collect(DISTINCT link) AS links
CALL (edges) {
  UNWIND edges AS r
  WITH r WHERE NOT r.uuid IN $known_fact_ids
  ORDER BY r.uuid LIMIT $max_edges
  OPTIONAL MATCH (ep:Episodic) WHERE ep.uuid IN coalesce(r.episodes, [])
  WITH r, min(ep.valid_at) AS episode_valid_at ORDER BY r.uuid
  RETURN collect({fact: r{.*, episode_valid_at: episode_valid_at},
                  subject: startNode(r).uuid, object: endNode(r).uuid}) AS facts
}
RETURN facts, links AS same_as,
 [n IN nodes | n{.*, labels: labels(n),
 global_id: head([(n)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])}] AS entities
"""
)


def _scope_parameters(scope: TimeScope | None, now=None) -> dict[str, Any]:
    return {
        "now": (now() if now else datetime.now(UTC)) if scope is None else None,
        "start": _utc(scope.start) if scope else None,
        "end": _utc(scope.end) if scope else None,
    }


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
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
        type=next(
            (
                label
                for label in sorted(getattr(node, "labels", data.get("labels", ())))
                if label != "Entity"
            ),
            data.get("type") or data.get("entity_type") or "Concept",
        ),
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
        published_at=next(
            (
                _datetime(data.get(key))
                for key in (
                    "published_at",
                    "valid_at",
                    "episode_valid_at",
                    "created_at",
                )
                if data.get(key)
            ),
            datetime.min.replace(tzinfo=UTC),
        ),
        valid_at=_datetime(data.get("valid_at")),
        invalid_at=_datetime(data.get("invalid_at")),
        grounded=data.get("grounded", False),
        credibility=data.get("credibility", 0.5),
        confidence=data.get("confidence", 0.5),
        source_count=data.get("source_count", 1),
        expired_at=_datetime(data.get("expired_at")),
        item_ids=tuple(data.get("item_ids") or ()),
    )


class Neo4jGraphStore:
    """Synchronous read adapter; constructor never opens a network connection."""

    def __init__(
        self,
        driver: Any,
        database: str = "neo4j",
        entity_index_name: str = "entity_name_embedding",
        fact_index_name: str = "fact_embedding",
        *,
        now=None,
    ) -> None:
        if not all(
            isinstance(v, str) and v.strip()
            for v in (database, entity_index_name, fact_index_name)
        ):
            raise ValueError("database and index names must be non-empty strings")
        self.now = now or (lambda: datetime.now(UTC))
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
            ),
            entity_index_name=settings.entity_index_name,
        )

    def _run(self, query: str, **parameters: Any) -> list[Any]:
        with self.driver.session(database=self.database) as session:
            return list(session.run(query, **parameters))

    def ensure_schema(self, embed_dim: int) -> None:
        """Provision the reader's vector index and reject incompatible schemas."""
        self._run(
            f"CREATE VECTOR INDEX `{self.entity_index_name.replace(chr(96), chr(96) * 2)}` IF NOT EXISTS "
            "FOR (e:Entity) ON (e.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=embed_dim,
        )
        self.check_schema(embed_dim)
        self._run("CALL db.awaitIndex($name)", name=self.entity_index_name)

    def check_schema(self, embed_dim: int) -> None:
        """Read-only existence and dimension check; never create or await an index."""
        rows = self._run(
            "SHOW INDEXES YIELD name, options WHERE name = $name RETURN options",
            name=self.entity_index_name,
        )
        actual = (
            rows[0]["options"].get("indexConfig", {}).get("vector.dimensions")
            if rows
            else None
        )
        if actual != embed_dim:
            raise ValueError(
                f"Neo4j index {self.entity_index_name!r} dimension is {actual}; expected {embed_dim}"
            )

    def entities_in(self, bubbles: Sequence[str]) -> list[Entity]:
        records = self._run(
            "MATCH (e:Entity) WHERE e.group_id IN $bubbles RETURN e{.*, labels: labels(e), global_id: head([(e)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS e ORDER BY e.uuid",
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
RETURN node{.*, labels: labels(node), global_id: head([(node)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS e, score ORDER BY score DESC, node.uuid LIMIT $top_k
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
        excluded_bubbles: Sequence[str] = (),
    ) -> Subgraph:
        _bounds(max_hops, max_edges)
        entities, facts, links = {}, {}, set()
        frontier = sorted(set(seed_ids))
        visited = set()
        scope_parameters = _scope_parameters(time_scope, self.now)
        for _ in range(max_hops):
            if not frontier:
                break
            records = self._run(
                _EXPAND_CYPHER,
                seed_ids=frontier,
                max_edges=max_edges - len(facts),
                known_fact_ids=sorted(facts),
                excluded_bubbles=list(excluded_bubbles),
                **scope_parameters,
            )
            visited.update(frontier)
            reached = set()
            for record in records:
                for node in record.get("entities", []):
                    entity = _entity(node)
                    entities[entity.id] = entity
                    reached.add(entity.id)
                for row in record.get("facts", []):
                    fact = _fact(row["fact"], row["subject"], row["object"])
                    if len(facts) < max_edges:
                        facts.setdefault(fact.id, fact)
                links.update(tuple(sorted(pair)) for pair in record.get("same_as", []))
            frontier = sorted(reached - visited)
        return Subgraph(
            dict(sorted(entities.items())), tuple(facts.values()), tuple(sorted(links))
        )

    def neighbors(
        self, entity_id: str, depth: int = 1, *, excluded_bubbles: Sequence[str] = ()
    ) -> Subgraph:
        _bounds(depth, 500)
        return self.expand(
            [entity_id],
            bubbles=(),
            time_scope=None,
            max_hops=depth,
            excluded_bubbles=excluded_bubbles,
        )

    def facts_about(
        self,
        entity_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        excluded_bubbles: Sequence[str] = (),
    ) -> list[Fact]:
        scope = TimeScope(start, end) if start is not None or end is not None else None
        records = self._run(
            """MATCH (s)-[r:RELATES_TO]->(o)
WHERE (s.uuid = $entity_id OR o.uuid = $entity_id)
AND NOT coalesce(r.group_id, '') IN $excluded_bubbles AND """
            + _VALID
            + """
OPTIONAL MATCH (ep:Episodic) WHERE ep.uuid IN coalesce(r.episodes, [])
WITH r, s, o, min(ep.valid_at) AS episode_valid_at
RETURN r{.*, episode_valid_at: episode_valid_at} AS r, s.uuid AS subject, o.uuid AS object ORDER BY r.uuid""",
            entity_id=entity_id,
            excluded_bubbles=list(excluded_bubbles),
            **_scope_parameters(scope, self.now),
        )
        return [_fact(r["r"], r["subject"], r["object"]) for r in records]

    def fact_embeddings(self, fact_ids: Sequence[str]) -> dict[str, np.ndarray]:
        records = self._run(
            """MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $fact_ids
AND r.fact_embedding IS NOT NULL
RETURN r.uuid AS id, r.fact_embedding AS embedding""",
            fact_ids=list(fact_ids),
        )
        return {r["id"]: np.asarray(r["embedding"], dtype=float) for r in records}
