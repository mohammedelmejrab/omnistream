"""Neo4j operations on top of Graphiti's driver: provenance props, flags, links."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from omnistream.graph.linker import GlobalCandidate

GLOBAL_INDEX = "global_entity_embedding"


@dataclass
class EdgeState:
    item_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    credibilities: list[float] = field(default_factory=list)
    grounded: bool | None = None


class GraphOps(Protocol):
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


class Neo4jGraphOps:
    """Implements GraphOps and the linker's GlobalEntityStore over Graphiti's driver."""

    def __init__(self, driver: Any, embed_dim: int) -> None:
        self._driver = driver
        self._dim = embed_dim

    async def _q(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = await self._driver.execute_query(query, **params)
        return [dict(r) for r in records]

    async def ensure_schema(self) -> None:
        await self._q(
            f"CREATE VECTOR INDEX {GLOBAL_INDEX} IF NOT EXISTS "
            "FOR (g:GlobalEntity) ON (g.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=self._dim,
        )
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

    async def get_edge_states(self, uuids: list[str]) -> dict[str, EdgeState]:
        rows = await self._q(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $uuids "
            "RETURN r.uuid AS uuid, r.item_ids AS item_ids, r.source_ids AS source_ids, "
            "r.credibilities AS credibilities, r.grounded AS grounded",
            uuids=uuids,
        )
        return {
            r["uuid"]: EdgeState(
                list(r["item_ids"] or []),
                list(r["source_ids"] or []),
                list(r["credibilities"] or []),
                r["grounded"],
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

    # --- GlobalEntityStore ---
    async def nearest_global_entities(
        self, embedding: list[float], type: str, k: int
    ) -> list[GlobalCandidate]:
        # Over-fetch: the type filter is applied after the ANN search.
        rows = await self._q(
            f"CALL db.index.vector.queryNodes('{GLOBAL_INDEX}', $k, $emb) "
            "YIELD node, score WHERE node.type = $type "
            "RETURN node.uuid AS uuid, node.name AS name, node.type AS type, "
            "node.aliases AS aliases, score ORDER BY score DESC",
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
