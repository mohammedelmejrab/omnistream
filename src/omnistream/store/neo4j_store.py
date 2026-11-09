"""Neo4j-backed GraphStore. One database; bubbles are namespaces on FACT edges."""

from datetime import UTC, datetime
from importlib import resources
from typing import Any

from neo4j import AsyncGraphDatabase

from omnistream.models import ApiFeedConfig, Bubble, Entity, Fact, Source

_FACT_PROPS = (
    "id", "relation", "bubble_id", "source_id", "source_url", "credibility",
    "source_count", "evidence_hashes", "valid_from", "valid_to", "status",
    "ingested_at",
)


def _dt(value: Any) -> datetime | None:
    """Neo4j DateTime -> tz-aware UTC datetime."""
    if value is None:
        return None
    native = value.to_native() if hasattr(value, "to_native") else value
    if native.tzinfo is None:
        native = native.replace(tzinfo=UTC)
    return native.astimezone(UTC)


def _bubble(n: Any) -> Bubble:
    return Bubble(
        id=n["id"], name=n["name"], description=n["description"],
        description_embedding=n.get("description_embedding"),
        auto_summary=n.get("auto_summary"), updated_at=_dt(n["updated_at"]),
    )


def _source(n: Any) -> Source:
    cfg = n.get("api_config")
    return Source(
        id=n["id"], type=n["type"], url=n.get("url"),
        credibility=n["credibility"], poll_interval=n["poll_interval"],
        bubble_ids=list(n["bubble_ids"]), auto_route=n["auto_route"],
        api_config=ApiFeedConfig.model_validate_json(cfg) if cfg else None,
        last_polled_at=_dt(n.get("last_polled_at")), last_error=n.get("last_error"),
    )


def _entity(n: Any) -> Entity:
    return Entity(
        id=n["id"], canonical_name=n["canonical_name"], type=n["type"],
        aliases=list(n["aliases"]), embedding=list(n["embedding"]),
    )


def _fact(rel: Any, subject_id: str, object_id: str) -> Fact:
    return Fact(
        subject_id=subject_id, object_id=object_id,
        **{
            **{k: rel[k] for k in _FACT_PROPS},
            "valid_from": _dt(rel["valid_from"]),
            "valid_to": _dt(rel.get("valid_to")),
            "ingested_at": _dt(rel["ingested_at"]),
            "evidence_hashes": list(rel["evidence_hashes"]),
        },
    )


def _fact_params(f: Fact) -> dict[str, Any]:
    return f.model_dump(exclude={"subject_id", "object_id"})


class Neo4jStore:
    """GraphStore on Neo4j 5.x.

    Entities referenced by a fact before being created exist as property-less
    stub nodes (no canonical_name); they are invisible to get/search until
    create_entity fills them in.
    """

    def __init__(self, uri: str, user: str, password: str, embed_dim: int) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self._dim = embed_dim

    async def init_schema(self) -> None:
        """Apply schema.cypher idempotently, then wait for the vector index."""
        text = resources.files("omnistream.store").joinpath("schema.cypher").read_text()
        text = text.replace("__DIM__", str(int(self._dim)))
        for stmt in (s.strip() for s in text.split(";")):
            if stmt:
                await self._driver.execute_query(stmt)
        # A new vector index populates asynchronously; once ONLINE it is
        # maintained transactionally, so waiting here keeps search consistent.
        await self._driver.execute_query("CALL db.awaitIndexes(300)")

    async def close(self) -> None:
        await self._driver.close()

    async def _run(self, query: str, **params: Any) -> list[Any]:
        records, _, _ = await self._driver.execute_query(query, params)
        return records

    # --- seen items ---
    async def has_seen(self, item_hash: str) -> bool:
        recs = await self._run(
            "MATCH (s:SeenItem {hash: $h}) RETURN count(s) AS c", h=item_hash
        )
        return recs[0]["c"] > 0

    async def mark_seen(self, item_hash: str, source_id: str) -> None:
        await self._run(
            "MERGE (s:SeenItem {hash: $h}) "
            "ON CREATE SET s.source_id = $sid, s.seen_at = datetime()",
            h=item_hash, sid=source_id,
        )

    # --- bubbles ---
    async def create_bubble(self, b: Bubble) -> Bubble:
        await self._run(
            "MERGE (n:Bubble {id: $id}) SET n.name = $name, n.description = $description, "
            "n.description_embedding = $description_embedding, "
            "n.auto_summary = $auto_summary, n.updated_at = $updated_at",
            **b.model_dump(),
        )
        return b.model_copy(deep=True)

    async def get_bubble(self, id: str) -> Bubble | None:
        recs = await self._run("MATCH (n:Bubble {id: $id}) RETURN n", id=id)
        return _bubble(recs[0]["n"]) if recs else None

    async def list_bubbles(self) -> list[Bubble]:
        recs = await self._run("MATCH (n:Bubble) RETURN n ORDER BY n.id")
        return [_bubble(r["n"]) for r in recs]

    # --- sources ---
    async def upsert_source(self, s: Source) -> Source:
        await self._run(
            "MERGE (n:Source {id: $id}) SET n.type = $type, n.url = $url, "
            "n.credibility = $credibility, n.poll_interval = $poll_interval, "
            "n.bubble_ids = $bubble_ids, n.auto_route = $auto_route, "
            "n.api_config = $api_config, n.last_polled_at = $last_polled_at, "
            "n.last_error = $last_error",
            id=s.id, type=s.type, url=s.url, credibility=s.credibility,
            poll_interval=s.poll_interval, bubble_ids=s.bubble_ids,
            auto_route=s.auto_route,
            api_config=s.api_config.model_dump_json() if s.api_config else None,
            last_polled_at=s.last_polled_at, last_error=s.last_error,
        )
        return s.model_copy(deep=True)

    async def get_source(self, id: str) -> Source | None:
        recs = await self._run("MATCH (n:Source {id: $id}) RETURN n", id=id)
        return _source(recs[0]["n"]) if recs else None

    async def list_sources(self) -> list[Source]:
        recs = await self._run("MATCH (n:Source) RETURN n ORDER BY n.id")
        return [_source(r["n"]) for r in recs]

    # --- entities ---
    async def create_entity(self, e: Entity) -> Entity:
        await self._run(
            "MERGE (n:Entity {id: $id}) SET n.canonical_name = $canonical_name, "
            "n.type = $type, n.aliases = $aliases, n.embedding = $embedding",
            **e.model_dump(),
        )
        return e.model_copy(deep=True)

    async def add_alias(self, entity_id: str, alias: str) -> None:
        async def work(tx: Any) -> None:
            res = await tx.run(
                "MATCH (n:Entity {id: $id}) WHERE n.canonical_name IS NOT NULL "
                "RETURN n.canonical_name AS name, n.aliases AS aliases",
                id=entity_id,
            )
            rec = await res.single()
            if rec is None:
                raise KeyError(entity_id)
            known = {rec["name"].casefold()} | {a.casefold() for a in rec["aliases"]}
            if alias.casefold() not in known:
                await tx.run(
                    "MATCH (n:Entity {id: $id}) SET n.aliases = n.aliases + $alias",
                    id=entity_id, alias=alias,
                )

        async with self._driver.session() as session:
            await session.execute_write(work)

    async def get_entity(self, id: str) -> Entity | None:
        recs = await self._run(
            "MATCH (n:Entity {id: $id}) WHERE n.canonical_name IS NOT NULL RETURN n",
            id=id,
        )
        return _entity(recs[0]["n"]) if recs else None

    async def search_entities(
        self, embedding: list[float], type: str, k: int
    ) -> list[tuple[Entity, float]]:
        recs = await self._run(
            "CALL db.index.vector.queryNodes('entity_embedding', $k_oversample, $emb) "
            "YIELD node, score WHERE node.type = $type "
            "RETURN node, score ORDER BY score DESC LIMIT $k",
            k_oversample=k * 5, emb=embedding, type=type, k=k,
        )
        # Neo4j scores are (1 + cos) / 2; convert back to raw cosine.
        return [
            (_entity(r["node"]), max(-1.0, min(1.0, 2 * r["score"] - 1)))
            for r in recs
        ]

    # --- facts ---
    async def create_fact(self, f: Fact) -> Fact:
        await self._run(
            "MERGE (s:Entity {id: $subject_id}) MERGE (o:Entity {id: $object_id}) "
            "CREATE (s)-[r:FACT]->(o) SET r = $props",
            subject_id=f.subject_id, object_id=f.object_id, props=_fact_params(f),
        )
        return f.model_copy(deep=True)

    async def update_fact(self, f: Fact) -> Fact:
        recs = await self._run(
            "MATCH ()-[r:FACT {id: $id}]->() SET r = $props RETURN count(r) AS c",
            id=f.id, props=_fact_params(f),
        )
        if recs[0]["c"] == 0:
            raise KeyError(f.id)
        return f.model_copy(deep=True)

    async def find_active_facts(
        self, bubble_id: str, subject_id: str, relation: str
    ) -> list[Fact]:
        recs = await self._run(
            "MATCH (s:Entity {id: $sid})-[r:FACT {bubble_id: $b, relation: $rel}]->(o) "
            "WHERE r.status = 'VERIFIED' RETURN r, s.id AS sid, o.id AS oid ORDER BY r.id",
            sid=subject_id, b=bubble_id, rel=relation,
        )
        return [_fact(r["r"], r["sid"], r["oid"]) for r in recs]

    async def list_facts(self, bubble_id: str) -> list[Fact]:
        recs = await self._run(
            "MATCH (s)-[r:FACT {bubble_id: $b}]->(o) "
            "RETURN r, s.id AS sid, o.id AS oid ORDER BY r.id",
            b=bubble_id,
        )
        return [_fact(r["r"], r["sid"], r["oid"]) for r in recs]
