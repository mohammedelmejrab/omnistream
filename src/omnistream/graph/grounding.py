"""Grounding check: drop extracted triples whose entities are absent from the source."""

import re

from rapidfuzz import fuzz

from omnistream.ingest.normalize import normalize_text
from omnistream.models import Extraction

_SHORT_MENTION_MAX_LEN = 3


def is_grounded(mention: str, text: str, threshold: int) -> bool:
    """True if the mention appears in the text (fuzzy; word-bounded when short)."""
    norm_mention = normalize_text(mention)
    if not norm_mention:
        return False
    norm_text = normalize_text(text)
    if len(norm_mention) <= _SHORT_MENTION_MAX_LEN:
        return re.search(rf"\b{re.escape(norm_mention)}\b", norm_text) is not None
    return fuzz.partial_ratio(norm_mention, norm_text) >= threshold


def ground_extraction(
    extraction: Extraction, text: str, threshold: int
) -> tuple[Extraction, int]:
    """Return a new Extraction without ungrounded triples, and the dropped count."""
    kept = [
        t
        for t in extraction.triples
        if is_grounded(t.subject, text, threshold)
        and is_grounded(t.object, text, threshold)
    ]
    return Extraction(triples=kept), len(extraction.triples) - len(kept)
