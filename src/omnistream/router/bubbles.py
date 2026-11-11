"""Bubble creation/update keeping `description_embedding` current (spec C3)."""

from omnistream.db import Repository
from omnistream.embed import Embedder
from omnistream.models import Bubble


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
