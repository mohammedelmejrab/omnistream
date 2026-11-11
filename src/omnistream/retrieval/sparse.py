"""In-memory BM25 keyword index used for the sparse half of hybrid retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25Index:
    """Okapi BM25 (Lucene-style IDF) over a small document collection.

    ``idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))``
    ``score = sum_t idf(t) * f * (k1 + 1) / (f + k1 * (1 - b + b * len / avg_len))``
    """

    def __init__(
        self,
        documents: Mapping[str, str] | None = None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not (math.isfinite(k1) and k1 >= 0):
            raise ValueError("k1 must be finite and >= 0")
        if not (math.isfinite(b) and 0 <= b <= 1):
            raise ValueError("b must be within [0, 1]")
        self.k1 = k1
        self.b = b
        self._tf: dict[str, Counter[str]] = {}
        self._len: dict[str, int] = {}
        self._df: Counter[str] = Counter()
        if documents:
            self.add(documents)

    def __len__(self) -> int:
        return len(self._tf)

    def add(self, documents: Mapping[str, str]) -> None:
        for doc_id, text in documents.items():
            if not isinstance(text, str):
                raise TypeError(
                    f"document {doc_id!r} must be str, got {type(text).__name__}"
                )
        for doc_id, text in documents.items():
            if doc_id in self._tf:
                self._df.subtract(self._tf[doc_id].keys())
            tf = Counter(tokenize(text))
            self._tf[doc_id] = tf
            self._len[doc_id] = sum(tf.values())
            self._df.update(tf.keys())
        self._df = +self._df  # drop zero counts

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return ``(doc_id, score)`` best-first; documents scoring 0 are omitted."""
        # Sorted terms + fsum make scores bit-identical across processes
        # (set order depends on PYTHONHASHSEED).
        terms = sorted(set(tokenize(query)))
        if not terms or not self._tf or top_k <= 0:
            return []
        n = len(self._tf)
        avg_len = sum(self._len.values()) / n or 1.0
        idf = {
            t: math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
            for t in terms
            if self._df[t]
        }
        scores: dict[str, float] = {}
        for doc_id, tf in self._tf.items():
            norm = self.k1 * (1 - self.b + self.b * self._len[doc_id] / avg_len)
            parts = [
                idf[t] * f * (self.k1 + 1) / (f + norm)
                for t in terms
                if t in idf and (f := tf.get(t))
            ]
            if parts:
                s = math.fsum(parts)
                if s > 0:
                    scores[doc_id] = s
        return sorted(scores.items(), key=lambda p: (-p[1], p[0]))[:top_k]
