from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Bubble(BaseModel):
    id: str
    name: str
    description: str
    description_embedding: list[float] | None = None
    auto_summary: str | None = None
    half_life_days: int = Field(default=30, ge=1)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ApiMapping(BaseModel):
    """JSONPath expressions locating item fields in an API response (spec §5).

    `items` is evaluated against the response; the other paths against each item.
    """

    items: str
    title: str | None = None
    body: str
    date: str | None = None
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class Source(BaseModel):
    id: str
    type: Literal["rss", "api", "document", "log"]
    url: str | None = None
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    poll_interval: int = Field(default=900, ge=60)
    bubble_ids: list[str] = Field(default_factory=list)
    auto_route: bool = True
    api_mapping: ApiMapping | None = None
    max_items_per_hour: int = Field(default=30, ge=1)
    store_full_text: bool = True
    enabled: bool = True
    last_polled_at: datetime | None = None
    status: Literal["ok", "error", "pending"] = "pending"
    last_error: str | None = None

    @model_validator(mode="after")
    def _api_requires_mapping(self) -> Self:
        if self.type == "api" and self.api_mapping is None:
            raise ValueError("api_mapping is required when type == 'api'")
        return self


class RawItem(BaseModel):
    source_id: str
    url: str
    title: str = ""
    text: str
    published_at: datetime | None = None
    bubble_ids_override: list[str] | None = None
    # Original payload as fetched (RSS entry html, API entry json) for the
    # original store (spec §4.2); falls back to `text` when absent.
    raw_content: str | None = None
    raw_ext: str = "txt"


class ExtractedTriple(BaseModel):
    subject: str
    subject_type: str
    relation: str
    object: str
    object_type: str
    exclusive: bool = False
    valid_from: datetime | None = None


class Extraction(BaseModel):
    triples: list[ExtractedTriple]


class Entity(BaseModel):
    id: str
    canonical_name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    embedding: list[float]


class Fact(BaseModel):
    id: str
    subject_id: str
    relation: str
    object_id: str
    bubble_id: str
    source_id: str
    source_url: str
    credibility: float
    source_count: int = 1
    evidence_hashes: list[str]
    valid_from: datetime
    valid_to: datetime | None = None
    status: Literal["VERIFIED", "HISTORICAL"] = "VERIFIED"
    ingested_at: datetime


class IngestResult(BaseModel):
    status: Literal["queued", "ingested", "duplicate", "unrouted", "empty", "failed"]
    item_hash: str
    bubble_ids: list[str] = Field(default_factory=list)
    facts_created: int = 0
    facts_merged: int = 0
    facts_superseded: int = 0
    dropped_ungrounded: int = 0
    error: str | None = None
