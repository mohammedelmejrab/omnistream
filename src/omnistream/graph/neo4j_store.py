"""Injected-driver Neo4j GraphStore (spec 4.3, C5 and 7).

Graphiti entities use uuid/group_id/name, fact relationships RELATES_TO use
uuid/fact and the provenance fields in section 7. Identity edges are SAME_AS.
Query values and limits are parameters; DDL index identifiers are backtick-escaped.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import numpy as np

from omnistream.config import Settings
from omnistream.graph.memory_store import _bounds, _seed_bounds
from omnistream.retrieval.models import Entity, Fact, Subgraph, TimeScope, _utc

logger = logging.getLogger(__name__)

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
            data.get("type") or data.get("entity_type") or "Entity",
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
        exact_search: bool = False,
    ) -> None:
        if not all(
            isinstance(v, str) and v.strip()
            for v in (database, entity_index_name, fact_index_name)
        ):
            raise ValueError("database and index names must be non-empty strings")
        self.exact_search = exact_search
        self.search_paths = []
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
            fact_index_name=getattr(settings, "fact_index_name", "fact_embedding"),
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

    def name_candidates(
        self, question: str, *, bubbles: Sequence[str], limit: int = 100
    ) -> list[Entity]:
        from omnistream.graph.name_search import lucene_query, rank_names

        started = perf_counter()
        query = lucene_query(question)
        if not query or limit <= 0:
            return []
        indexes = self._run(
            "SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties "
            "WHERE type = 'FULLTEXT' AND state = 'ONLINE' AND 'Entity' IN labelsOrTypes "
            "AND 'name' IN properties RETURN name ORDER BY name"
        )
        if indexes:
            rows = self._run(
                "CALL db.index.fulltext.queryNodes($index_name, $lexical_query) YIELD node AS e, score "
                "WHERE e.group_id IN $bubbles "
                "RETURN e{.*, labels: labels(e), global_id: head([(e)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS e "
                "ORDER BY score DESC, e.name, e.uuid LIMIT $limit",
                index_name=indexes[0]["name"],
                lexical_query=query,
                bubbles=list(bubbles),
                limit=limit,
            )
            found = [_entity(r["e"]) for r in rows]
            path = "name_fulltext"
        else:
            found = rank_names(question, self.entities_in(bubbles))[:limit]
            path = "name_exact"
        self._record_path(path, started)
        return found

    def _cosine_index(self, name: str, kind: str) -> bool:
        rows = self._run(
            "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state, options "
            "WHERE name = $name AND type = 'VECTOR' AND entityType = $kind "
            "RETURN name, state, labelsOrTypes, properties, options",
            name=name,
            kind=kind,
        )
        if not rows:
            return False
        row = rows[0]
        config = row["options"].get("indexConfig", {})
        label, prop = (
            ("RELATES_TO", "fact_embedding")
            if kind == "RELATIONSHIP"
            else ("Entity", "name_embedding")
        )
        if (
            row["labelsOrTypes"] != [label]
            or row["properties"] != [prop]
            or str(config.get("vector.similarity_function", "")).lower() != "cosine"
        ):
            logger.warning("Index %r is incompatible; using exact cosine search", name)
            return False
        return row["state"] == "ONLINE"

    def _record_path(self, path, started, **details):
        entry = dict(path=path, seconds=perf_counter() - started, **details)
        self.search_paths.append(entry)
        logger.debug("retrieval search %s", entry)

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
        started = perf_counter()
        projection = "node{.*, labels: labels(node), global_id: head([(node)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS e"
        if self.exact_search or not self._cosine_index(self.entity_index_name, "NODE"):
            rows = self._run(
                "MATCH (node:Entity) WHERE node.group_id IN $bubbles AND node.name_embedding IS NOT NULL "
                "WITH node, vector.similarity.cosine(node.name_embedding, $embedding) AS normalized "
                "WITH node, 2.0 * normalized - 1.0 AS score WHERE score >= $min_cosine "
                "RETURN "
                + projection
                + ", score ORDER BY round(score, 6) DESC, node.uuid LIMIT $top_k",
                bubbles=list(bubbles),
                embedding=vector.tolist(),
                min_cosine=min_cosine,
                top_k=top_k,
            )
            path = "entity_exact"
        else:
            # Finite refill: never request the graph's entire population.
            for fetch in (top_k * 5, top_k * 15, top_k * 25):
                rows = self._run(
                    "CALL db.index.vector.queryNodes($index_name, $fetch, $embedding) YIELD node, score AS normalized "
                    "WITH node, 2.0 * normalized - 1.0 AS score WHERE node.group_id IN $bubbles AND score >= $min_cosine "
                    "RETURN "
                    + projection
                    + ", score ORDER BY round(score, 6) DESC, node.uuid LIMIT $top_k",
                    index_name=self.entity_index_name,
                    fetch=fetch,
                    embedding=vector.tolist(),
                    bubbles=list(bubbles),
                    min_cosine=min_cosine,
                    top_k=top_k,
                )
                if len(rows) >= top_k:
                    break
            path = "entity_ann"
            if len(rows) < top_k:
                logger.warning(
                    "Entity ANN shortfall: %s/%s; falling back to exact",
                    len(rows),
                    top_k,
                )
                from copy import copy

                exact = copy(self)
                exact.exact_search = True
                return exact.seed_by_embedding(
                    embedding, bubbles=bubbles, top_k=top_k, min_cosine=min_cosine
                )
        self._record_path(path, started)
        return [(_entity(r["e"]), float(r["score"])) for r in rows]

    def seed_by_fact_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 10,
        time_scope: TimeScope | None = None,
    ) -> list[tuple[Entity, float]]:
        """Bounded ANN with group/validity filtering and finite refill.

        Exact replay is scored inside Neo4j; only top-k vectors' endpoints cross
        Bolt. Missing-index fallback remains read-only and explicitly logged.
        """
        _seed_bounds(top_k, -1)
        vector = np.asarray(embedding, dtype=float)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError("embedding must be a finite vector")
        if not top_k or not bubbles:
            return []
        started = perf_counter()
        params = dict(
            embedding=vector.tolist(),
            bubbles=list(bubbles),
            top_k=top_k,
            **_scope_parameters(time_scope, self.now),
        )
        suffix = " RETURN r.uuid AS id, startNode(r).uuid AS subject, endNode(r).uuid AS object, score ORDER BY round(score, 6) DESC, id LIMIT $top_k"
        indexed = (
            self._cosine_index(self.fact_index_name, "RELATIONSHIP")
            if not self.exact_search
            else False
        )
        if indexed:
            for fetch in (top_k * 5, top_k * 15, top_k * 25):
                rows = self._run(
                    "CALL db.index.vector.queryRelationships($index_name, $fetch, $embedding) YIELD relationship AS r, score AS normalized "
                    "WITH r, 2.0 * normalized - 1.0 AS score WHERE r.group_id IN $bubbles AND "
                    + _VALID
                    + suffix,
                    index_name=self.fact_index_name,
                    fetch=fetch,
                    **params,
                )
                if len(rows) >= top_k:
                    break
            path = "fact_ann"
        if not indexed or len(rows) < top_k:
            if indexed:
                logger.warning(
                    "Fact ANN shortfall: %s/%s; falling back to exact", len(rows), top_k
                )
            rows = self._run(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id IN $bubbles AND r.fact_embedding IS NOT NULL AND "
                + _VALID
                + " WITH r, 2.0 * vector.similarity.cosine(r.fact_embedding, $embedding) - 1.0 AS score"
                + suffix,
                **params,
            )
            path = (
                "fact_exact"
                if self.exact_search
                else (
                    "fact_exact_ann_shortfall"
                    if indexed
                    else "fact_exact_missing_index"
                )
            )
        ids = sorted({r[key] for r in rows for key in ("subject", "object")})
        nodes = (
            self._run(
                "MATCH (e:Entity) WHERE e.uuid IN $ids AND e.group_id IN $bubbles "
                "RETURN e{.*, labels: labels(e), global_id: head([(e)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS e ORDER BY e.uuid",
                ids=ids,
                bubbles=list(bubbles),
            )
            if ids
            else []
        )
        entities = {e.id: e for e in (_entity(r["e"]) for r in nodes)}
        self._record_path(path, started, facts=len(rows))
        return [
            (entities[r[key]], float(r["score"]))
            for r in rows
            for key in ("subject", "object")
            if r[key] in entities
        ]

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
