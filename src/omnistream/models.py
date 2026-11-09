from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class Bubble(BaseModel):
    id: str
    name: str
    description: str
    description_embedding: list[float] | None = None
    auto_summary: str | None = None
    updated_at: datetime


class ApiFeedConfig(BaseModel):
    items_path: str
    text_field: str
    url_field: str
    title_field: str | None = None
    published_field: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class Source(BaseModel):
    id: str
    type: Literal["rss", "api", "document"]
    url: str | None
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    poll_interval: int = Field(default=900, ge=60)
    bubble_ids: list[str] = Field(default_factory=list)
    auto_route: bool = True
    api_config: ApiFeedConfig | None = None
    last_polled_at: datetime | None = None
    last_error: str | None = None

    @model_validator(mode="after")
    def _api_requires_config(self) -> Self:
        if self.type == "api" and self.api_config is None:
            raise ValueError("api_config is required when type == 'api'")
        return self


class RawItem(BaseModel):
    source_id: str
    url: str
    title: str = ""
    text: str
    published_at: datetime | None = None
    bubble_ids_override: list[str] | None = None


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
    status: Literal["ingested", "duplicate", "unrouted", "empty", "failed"]
    item_hash: str
    bubble_ids: list[str] = Field(default_factory=list)
    facts_created: int = 0
    facts_merged: int = 0
    facts_superseded: int = 0
    dropped_ungrounded: int = 0
    error: str | None = None
