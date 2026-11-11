"""File-backed clean originals for spec sections 4.2, 6/C5 and 7."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from omnistream.retrieval.models import ItemPart

_ITEM_ID = re.compile(r"[A-Za-z0-9_.-]+")


class ItemUnavailableError(KeyError):
    """An original is missing; invalid IDs still raise ValueError."""


class FileItemStore:
    """Read clean UTF-8 originals, approximating tokens as whitespace words.

    Empty originals have one empty part. C5 defaults to about 2,000 tokens
    per part, with at most three parts returned by a single read_parts call.
    """

    def __init__(self, root: Path, *, tokens_per_part: int = 2000) -> None:
        if (
            isinstance(tokens_per_part, bool)
            or not isinstance(tokens_per_part, int)
            or tokens_per_part < 1
        ):
            raise ValueError("tokens_per_part must be a positive integer")
        self.root = Path(root).resolve()
        self.tokens_per_part = tokens_per_part

    def _words(self, item_id: str) -> list[str]:
        if not _ITEM_ID.fullmatch(item_id) or item_id in {".", ".."}:
            raise ValueError("invalid item id")
        path = (self.root / f"{item_id}.txt").resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("item path escapes root")
        try:
            return path.read_text(encoding="utf-8").split()
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise ItemUnavailableError(item_id) from exc

    def read_item(self, item_id: str, part: int = 1) -> ItemPart:
        """Read a 1-based part; unknown items raise KeyError (spec C5)."""
        words = self._words(item_id)
        return self._part(item_id, words, part)

    def _part(self, item_id: str, words: list[str], part: int) -> ItemPart:
        total = max(1, (len(words) + self.tokens_per_part - 1) // self.tokens_per_part)
        if (
            isinstance(part, bool)
            or not isinstance(part, int)
            or not 1 <= part <= total
        ):
            raise ValueError(f"part must be within 1..{total}")
        start = (part - 1) * self.tokens_per_part
        return ItemPart(
            item_id, part, total, " ".join(words[start : start + self.tokens_per_part])
        )

    def read_parts(self, item_id: str, parts: Sequence[int]) -> list[ItemPart]:
        """Read at most three requested parts in request order (spec C5)."""
        if len(parts) > 3:
            raise ValueError("at most 3 parts may be requested per call")
        words = self._words(item_id)
        return [self._part(item_id, words, part) for part in parts]

    def item_text(self, item_id: str, max_tokens: int = 4000) -> str:
        """Return at most max_tokens words for C5 simple-strategy context."""
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or max_tokens < 0
        ):
            raise ValueError("max_tokens must be a non-negative integer")
        return " ".join(self._words(item_id)[:max_tokens])
