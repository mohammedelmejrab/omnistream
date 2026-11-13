"""Neo4j operations on top of Graphiti's driver: provenance props, flags, links."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from omnistream.graph.linker import GlobalCandidate

GLOBAL_INDEX = "global_entity_embedding"


@dataclass
class EdgeState:
    item_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    credibilities: list[float] = field(default_factory=list)
    grounded: bool | None = None
    published_at: datetime | None = None


class GraphOps(Protocol):
    async def recover_episode(self, item_id: str, group_id: str): ...

    async def tag_episode(
        self, episode_uuid: str, item_id: str, source_url: str, credibility: float,
        source_id: str,
    ) -> None: ...  # fmt: skip

    async def get_edge_states(self, uuids: list[str]) -> dict[str, EdgeState]: ...

    async def set_edge_props(self, uuid: str, props: dict[str, Any]) -> None: ...

    async def set_edge_statuses(self, uuids: list[str]) -> None:
        """HISTORICAL when invalid_at/expired_at is set, else VERIFIED."""
        ...

    async def set_node_grounded(self, uuid: str, grounded: bool) -> None: ...

    async def recent_facts(self, group_id: str, limit: int) -> list[str]: ...

    async def group_counts(self, group_id: str) -> dict[str, int]:
        """{"episodes", "entities", "facts"} stored for a Graphiti group."""
        ...

    async def delete_group(self, group_id: str) -> None:
        """Delete the group's nodes and edges (incl. SAME_AS), then any
        GlobalEntity left without incoming SAME_AS."""
        ...


class Neo4jGraphOps:
    """Implements GraphOps and the linker's GlobalEntityStore over Graphiti's driver."""

    def __init__(
        self,
        driver: Any,
        embed_dim: int,
        entity_index_name: str = "entity_name_embedding",
        fact_index_name: str = "fact_embedding",
    ) -> None:
        self._driver = driver
        self._dim = embed_dim
        self._entity_index = entity_index_name
        self._fact_index = fact_index_name
        self._global_index = GLOBAL_INDEX

    async def _q(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = await self._driver.execute_query(query, **params)
        return [dict(r) for r in records]

    async def ensure_schema(self) -> None:
        await self._q(
            f"CREATE VECTOR INDEX `{self._entity_index.replace(chr(96), chr(96) * 2)}` IF NOT EXISTS "
            "FOR (e:Entity) ON (e.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=self._dim,
        )
        rows = await self._q(
            "SHOW INDEXES YIELD name, options WHERE name = $name RETURN options",
            name=self._entity_index,
        )
        actual = (
            rows[0]["options"].get("indexConfig", {}).get("vector.dimensions")
            if rows
            else None
        )
        if actual != self._dim:
            raise ValueError(
                f"Neo4j index {self._entity_index!r} dimension is {actual}; expected {self._dim}"
            )
        await self._q(
            f"CREATE VECTOR INDEX `{self._fact_index.replace(chr(96), chr(96) * 2)}` IF NOT EXISTS "
            "FOR ()-[r:RELATES_TO]-() ON (r.fact_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=self._dim,
        )
        fact_rows = await self._q(
            "SHOW INDEXES YIELD name, entityType, labelsOrTypes, properties, options "
            "WHERE name = $name RETURN entityType, labelsOrTypes, properties, options",
            name=self._fact_index,
        )
        if (
            not fact_rows
            or fact_rows[0]["entityType"] != "RELATIONSHIP"
            or fact_rows[0]["labelsOrTypes"] != ["RELATES_TO"]
            or fact_rows[0]["properties"] != ["fact_embedding"]
            or fact_rows[0]["options"].get("indexConfig", {}).get("vector.dimensions")
            != self._dim
            or str(
                fact_rows[0]["options"]
                .get("indexConfig", {})
                .get("vector.similarity_function", "")
            ).lower()
            != "cosine"
        ):
            raise ValueError("Fact vector index missing or incompatible")
        await self._q(
            f"CREATE VECTOR INDEX {GLOBAL_INDEX} IF NOT EXISTS "
            "FOR (g:GlobalEntity) ON (g.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=self._dim,
        )
        rows = await self._q(
            "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options "
            "WHERE type = 'VECTOR' AND labelsOrTypes = ['GlobalEntity'] "
            "AND properties = ['name_embedding'] RETURN name, options"
        )
        if (
            not rows
            or rows[0]["options"].get("indexConfig", {}).get("vector.dimensions")
            != self._dim
        ):
            raise ValueError(
                "GlobalEntity vector index missing or incompatible dimensions"
            )
        self._global_index = rows[0]["name"]
        await self._q("CALL db.awaitIndex($name)", name=self._global_index)
        await self._q(
            "CREATE CONSTRAINT global_entity_uuid IF NOT EXISTS "
            "FOR (g:GlobalEntity) REQUIRE g.uuid IS UNIQUE"
        )

    # --- GraphOps ---
    async def tag_episode(
        self, episode_uuid: str, item_id: str, source_url: str, credibility: float,
        source_id: str,
    ) -> None:  # fmt: skip
        await self._q(
            "MATCH (e:Episodic {uuid: $uuid}) SET e.item_id = $item_id, "
            "e.source_url = $url, e.credibility = $cred, e.source_id = $sid",
            uuid=episode_uuid,
            item_id=item_id,
            url=source_url,
            cred=credibility,
            sid=source_id,
        )

    async def recover_episode(self, item_id: str, group_id: str):
        """Resume C4 postprocessing after Graphiti committed but a later step failed."""
        from types import SimpleNamespace

        from graphiti_core.edges import EntityEdge
        from graphiti_core.nodes import EntityNode, EpisodicNode

        rows = await self._q(
            "MATCH (ep:Episodic {group_id: $group}) "
            "WHERE ep.item_id = $item OR ep.source_description CONTAINS $item "
            "OPTIONAL MATCH (ep)-[:MENTIONS]->(n:Entity) "
            "WITH ep, collect(DISTINCT n.uuid) AS nodes "
            "OPTIONAL MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $group "
            "AND ep.uuid IN coalesce(r.episodes, []) "
            "RETURN ep.uuid AS episode, ep.created_at AS created_at, nodes, collect(DISTINCT r.uuid) AS edges "
            "ORDER BY created_at DESC LIMIT 1",
            item=item_id,
            group=group_id,
        )
        if not rows:
            return None
        row = rows[0]
        if not getattr(self, "_recovery_indexes", False):
            for prop in ("invalid_at", "expired_at"):
                await self._q(
                    f"CREATE RANGE INDEX relates_{prop} IF NOT EXISTS "
                    f"FOR ()-[r:RELATES_TO]-() ON (r.{prop})"
                )
            self._recovery_indexes = True
        # Only recovery performs this time-window repair. Use relationship range
        # indexes so a crashed write does not require scanning its entire group.
        await self._q(
            "MATCH (next:Episodic {group_id: $group}) "
            "WHERE next.created_at > $created "
            "WITH min(next.created_at) AS until "
            "CALL { WITH until MATCH ()-[r:RELATES_TO]->() "
            "WHERE r.invalid_at >= $created AND (until IS NULL OR r.invalid_at < until) "
            "AND r.group_id = $group RETURN r "
            "UNION WITH until MATCH ()-[r:RELATES_TO]->() "
            "WHERE r.expired_at >= $created AND (until IS NULL OR r.expired_at < until) "
            "AND r.group_id = $group RETURN r } "
            "SET r.status = 'HISTORICAL'",
            group=group_id,
            created=row["created_at"],
        )
        return SimpleNamespace(
            episode=await EpisodicNode.get_by_uuid(self._driver, row["episode"]),
            nodes=await EntityNode.get_by_uuids(self._driver, row["nodes"]),
            edges=await EntityEdge.get_by_uuids(self._driver, row["edges"]),
        )

    async def get_edge_states(self, uuids: list[str]) -> dict[str, EdgeState]:
        rows = await self._q(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $uuids "
            "RETURN r.uuid AS uuid, r.item_ids AS item_ids, r.source_ids AS source_ids, "
            "r.credibilities AS credibilities, r.grounded AS grounded, r.published_at AS published_at",
            uuids=uuids,
        )
        return {
            r["uuid"]: EdgeState(
                list(r["item_ids"] or []),
                list(r["source_ids"] or []),
                list(r["credibilities"] or []),
                r["grounded"],
                r.get("published_at").to_native()
                if hasattr(r.get("published_at"), "to_native")
                else r.get("published_at"),
            )
            for r in rows
        }

    async def set_edge_props(self, uuid: str, props: dict[str, Any]) -> None:
        await self._q(
            "MATCH ()-[r:RELATES_TO {uuid: $uuid}]->() SET r += $props",
            uuid=uuid,
            props=props,
        )

    async def set_edge_statuses(self, uuids: list[str]) -> None:
        await self._q(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $uuids "
            "SET r.status = CASE WHEN r.invalid_at IS NOT NULL "
            "OR r.expired_at IS NOT NULL THEN 'HISTORICAL' ELSE 'VERIFIED' END",
            uuids=uuids,
        )

    async def set_node_grounded(self, uuid: str, grounded: bool) -> None:
        await self._q(
            "MATCH (n:Entity {uuid: $uuid}) SET n.grounded = $g", uuid=uuid, g=grounded
        )

    async def recent_facts(self, group_id: str, limit: int) -> list[str]:
        rows = await self._q(
            "MATCH ()-[r:RELATES_TO {group_id: $g}]->() "
            "WHERE r.status = 'VERIFIED' AND coalesce(r.grounded, true) "
            "RETURN r.fact AS fact ORDER BY r.created_at DESC LIMIT $limit",
            g=group_id,
            limit=limit,
        )
        return [r["fact"] for r in rows]

    async def group_counts(self, group_id: str) -> dict[str, int]:
        rows = await self._q(
            "CALL { MATCH (e:Episodic {group_id: $g}) RETURN count(e) AS episodes } "
            "CALL { MATCH (n:Entity {group_id: $g}) RETURN count(n) AS entities } "
            "CALL { MATCH ()-[r:RELATES_TO {group_id: $g}]->() "
            "RETURN count(r) AS facts } "
            "RETURN episodes, entities, facts",
            g=group_id,
        )
        r = rows[0]
        return {k: int(r[k]) for k in ("episodes", "entities", "facts")}

    async def delete_group(self, group_id: str) -> None:
        # DETACH removes MENTIONS/RELATES_TO/HAS_MEMBER and SAME_AS relationships.
        await self._q("MATCH (n {group_id: $g}) DETACH DELETE n", g=group_id)
        await self._q(
            "MATCH (g:GlobalEntity) WHERE NOT ()-[:SAME_AS]->(g) DETACH DELETE g"
        )

    # --- GlobalEntityStore ---
    async def existing_global_entity(self, entity_uuid: str) -> str | None:
        rows = await self._q(
            "MATCH (:Entity {uuid: $uuid})-[:SAME_AS]->(g:GlobalEntity) "
            "RETURN g.uuid AS uuid ORDER BY uuid LIMIT 1",
            uuid=entity_uuid,
        )
        return rows[0]["uuid"] if rows else None

    async def nearest_global_entities(
        self, embedding: list[float], type: str, k: int
    ) -> list[GlobalCandidate]:
        # Over-fetch: the type filter is applied after the ANN search.
        rows = await self._q(
            "CALL db.index.vector.queryNodes($index, $k, $emb) "
            "YIELD node, score WHERE node.type = $type "
            "RETURN node.uuid AS uuid, node.name AS name, node.type AS type, "
            "node.aliases AS aliases, score ORDER BY score DESC",
            index=self._global_index,
            k=k * 5,
            emb=embedding,
            type=type,
        )
        # Neo4j reports cosine as (1 + cos) / 2.
        return [
            GlobalCandidate(
                r["uuid"],
                r["name"],
                r["type"],
                list(r["aliases"] or []),
                2 * r["score"] - 1,
            )
            for r in rows[:k]
        ]

    async def create_global_entity(
        self, uuid: str, name: str, type: str, embedding: list[float]
    ) -> None:
        await self._q(
            "CREATE (g:GlobalEntity {uuid: $uuid, name: $name, type: $type, "
            "name_embedding: $emb, aliases: []})",
            uuid=uuid,
            name=name,
            type=type,
            emb=embedding,
        )

    async def add_global_alias(self, uuid: str, alias: str) -> None:
        await self._q(
            "MATCH (g:GlobalEntity {uuid: $uuid}) "
            "SET g.aliases = coalesce(g.aliases, []) + $alias",
            uuid=uuid,
            alias=alias,
        )

    async def link_same_as(self, entity_uuid: str, global_uuid: str) -> None:
        await self._q(
            "MATCH (n:Entity {uuid: $e}), (g:GlobalEntity {uuid: $g}) "
            "MERGE (n)-[:SAME_AS]->(g)",
            e=entity_uuid,
            g=global_uuid,
        )

    async def bubble_graph(
        self, group_id: str, limit: int = 50, *, include_historical: bool = False
    ) -> dict:
        nodes = await self._q(
            "MATCH (n:Entity {group_id: $g}) OPTIONAL MATCH (n)-[r:RELATES_TO]-() "
            "WHERE $historical OR (r.invalid_at IS NULL AND r.expired_at IS NULL AND coalesce(r.status, 'CURRENT') <> 'HISTORICAL') "
            "RETURN n.uuid AS id, n.name AS label, count(r) AS value "
            "ORDER BY value DESC, id LIMIT $limit",
            g=group_id,
            limit=limit,
            historical=include_historical,
        )
        edges = await self._q(
            "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) "
            "WHERE a.uuid IN $ids AND b.uuid IN $ids "
            "AND ($historical OR (r.invalid_at IS NULL AND r.expired_at IS NULL AND coalesce(r.status, 'CURRENT') <> 'HISTORICAL')) "
            "RETURN r.uuid AS id, a.uuid AS `from`, b.uuid AS `to`, r.name AS label",
            ids=[n["id"] for n in nodes],
            historical=include_historical,
        )
        return {"nodes": nodes, "edges": edges}

    async def bubble_map(self) -> list[dict]:
        return await self._q(
            "MATCH (a:Entity)-[:SAME_AS]->(g:GlobalEntity)<-[:SAME_AS]-(b:Entity) "
            "WHERE a.group_id < b.group_id "
            "WITH a.group_id AS a, b.group_id AS b, collect(DISTINCT {id:g.uuid, name:g.name}) AS entities "
            "RETURN a AS `from`, b AS `to`, size(entities) AS value, entities"
        )

    async def recent_episodes(self, group_id: str, limit: int = 20) -> list[dict]:
        return await self._q(
            "MATCH (e:Episodic {group_id: $g}) RETURN e.uuid AS id, e.name AS name, "
            "e.item_id AS item_id, toString(e.created_at) AS created_at "
            "ORDER BY e.created_at DESC LIMIT $limit",
            g=group_id,
            limit=limit,
        )
