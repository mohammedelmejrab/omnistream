from typing import Protocol, TypeVar

from pydantic import BaseModel

from omnistream.ingest.normalize import normalize_relation
from omnistream.models import ExtractedTriple, Extraction, RawItem

T = TypeVar("T", bound=BaseModel)

ENTITY_TYPES = frozenset(
    {"PERSON", "ORG", "LOCATION", "PRODUCT", "EVENT", "CONCEPT", "MONEY", "OTHER"}
)

EXTRACTION_SYSTEM = """\
Extract factual (subject, relation, object) triples from the text.

Rules:
- Extract only statements actually made in the text. Do not add outside knowledge.
- subject and object must be copied verbatim as they appear in the text (surface \
form, not a canonicalized name). This is what makes grounding work.
- subject_type and object_type must be one of: PERSON | ORG | LOCATION | PRODUCT | \
EVENT | CONCEPT | MONEY | OTHER.
- relation is a short verb phrase, for example HAS_CEO or HEADQUARTERED_IN.
- Set exclusive=true only when the relation can have exactly one object at a time \
(for example HAS_CEO, HEADQUARTERED_IN, PRICE_IS). Otherwise exclusive=false.
- For such single-valued relations the constrained entity, the one that can have only \
one value at a time, is the SUBJECT, and the relation is phrased from its side: \
"Acme Corp HAS_CEO Dana Whitfield", "Acme Corp HEADQUARTERED_IN Berlin", \
"Widget X PRICE_IS $10". Never "Dana Whitfield CEO_OF Acme Corp".
- Set valid_from to the date the fact became true only if the text states it; \
otherwise null.
"""


class _Parser(Protocol):
    async def parse(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
    ) -> T: ...


class Extractor:
    def __init__(self, llm: _Parser, model: str):
        self._llm = llm
        self._model = model

    async def extract(self, item: RawItem) -> Extraction:
        published = item.published_at.isoformat() if item.published_at else "unknown"
        user = f"Title: {item.title}\nPublished: {published}\nText: {item.text}"
        raw = await self._llm.parse(self._model, EXTRACTION_SYSTEM, user, Extraction)
        kept: list[ExtractedTriple] = []
        for t in raw.triples:
            subject, obj = t.subject.strip(), t.object.strip()
            relation = normalize_relation(t.relation)
            stype, otype = t.subject_type.strip().upper(), t.object_type.strip().upper()
            if not (subject and obj and relation and stype and otype):
                continue
            if subject.casefold() == obj.casefold():
                continue
            kept.append(
                t.model_copy(
                    update={
                        "subject": subject,
                        "object": obj,
                        "relation": relation,
                        "subject_type": stype if stype in ENTITY_TYPES else "OTHER",
                        "object_type": otype if otype in ENTITY_TYPES else "OTHER",
                    }
                )
            )
        return Extraction(triples=kept)
