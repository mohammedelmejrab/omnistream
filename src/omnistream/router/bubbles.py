"""Bubble creation/update keeping `description_embedding` current (spec C3)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from omnistream.db import Repository
from omnistream.embed import Embedder
from omnistream.models import Bubble, RawItem


class BubbleService:
    def __init__(self, repo: Repository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def _embed(self, name: str, description: str) -> list[float]:
        return (await self._embedder.embed([f"{name}: {description}"]))[0]

    async def create(self, bubble: Bubble) -> Bubble:
        vec = await self._embed(bubble.name, bubble.description)
        return await self._repo.create_bubble(
            bubble.model_copy(update={"description_embedding": vec})
        )

    async def update(self, id: str, **changes) -> Bubble:
        """Recomputes the embedding when name or description changes."""
        if "name" in changes or "description" in changes:
            current = await self._repo.get_bubble(id)
            if current is None:
                raise KeyError(id)
            changes["description_embedding"] = await self._embed(
                changes.get("name", current.name),
                changes.get("description", current.description),
            )
        return await self._repo.update_bubble(id, **changes)


class BubbleLifecycle:
    """Bubble create (with optional backfill), counts and cascading delete."""

    def __init__(self, repo: Repository, embedder: Embedder, router, ops, chunks):
        self._repo = repo
        self._service = BubbleService(repo, embedder)
        self._router = router
        self._ops = ops
        self._chunks = chunks

    async def create(self, bubble: Bubble, backfill_days: int | None = None) -> Bubble:
        created = await self._service.create(bubble)
        if backfill_days:
            await self.backfill(created.id, backfill_days)
        return created

    async def backfill(self, bubble_id: str, days: int) -> int:
        """Re-route stored items from the last `days` days; queue those routed to
        the new bubble. Returns the number queued."""
        since = datetime.now(UTC) - timedelta(days=days)
        bubbles = await self._repo.list_bubbles()
        queued = 0
        for item in await self._repo.list_items():
            if item.status not in ("written", "unsorted") or not item.text_path:
                continue
            when = item.published_at or item.polled_at
            if when is None or when < since:
                continue
            source = await self._repo.get_source(item.source_id)
            if source is None:
                continue
            raw = RawItem(
                source_id=source.id,
                url=item.url,
                title=item.title,
                text=Path(item.text_path).read_text(encoding="utf-8"),
                published_at=item.published_at,
            )
            # Fixed-assignment sources keep their bubbles; only auto-routed ones move.
            if source.bubble_ids:
                continue
            decision = await self._router.route(raw, source, bubbles)
            if bubble_id not in decision.bubble_ids:
                continue
            await self._repo.update_item(
                item.id, bubble_ids=[bubble_id], status="queued"
            )
            await self._repo.enqueue_job(item.id)
            queued += 1
        return queued

    async def counts(self, bubble_id: str) -> dict[str, int]:
        graph = await self._ops.group_counts(bubble_id)
        sources = [
            s for s in await self._repo.list_sources() if bubble_id in s.bubble_ids
        ]
        return {
            **graph,
            "chunks": await self._chunks.count(bubble_id),
            "sources": len(sources),
        }

    async def delete(self, bubble_id: str) -> None:
        await self._ops.delete_group(bubble_id)
        await self._chunks.drop(bubble_id)
        for s in await self._repo.list_sources():
            if bubble_id not in s.bubble_ids:
                continue
            rest = [b for b in s.bubble_ids if b != bubble_id]
            # Sole-bubble sources are disabled; seen_items and originals stay.
            await self._repo.upsert_source(
                s.model_copy(
                    update={"bubble_ids": rest, "enabled": s.enabled and bool(rest)}
                )
            )
        await self._repo.delete_bubble(bubble_id)
