"""SQLModel tables for application state (spec §7)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, TypeDecorator
from sqlmodel import Field, SQLModel


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns tz-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any):
        return value.replace(tzinfo=UTC) if value is not None else None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def dt_col(nullable: bool = True) -> Any:
    return Column(UTCDateTime, nullable=nullable)


def json_col(nullable: bool = False) -> Any:
    return Column(JSON, nullable=nullable)


class BubbleRow(SQLModel, table=True):
    __tablename__ = "bubbles"

    id: str = Field(primary_key=True)
    name: str
    description: str
    description_embedding: list[float] | None = Field(
        default=None, sa_column=json_col(nullable=True)
    )
    auto_summary: str | None = None
    half_life_days: int = 30
    episodes_since_summary: int = 0
    created_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))


class SourceRow(SQLModel, table=True):
    __tablename__ = "sources"

    id: str = Field(primary_key=True)
    type: str  # rss | api | document | log
    url: str | None = None
    credibility: float = 0.5
    poll_interval: int = 900
    bubble_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    auto_route: bool = True
    api_mapping: dict[str, Any] | None = Field(
        default=None, sa_column=json_col(nullable=True)
    )
    max_items_per_hour: int = 30
    store_full_text: bool = True
    enabled: bool = True
    last_polled_at: datetime | None = Field(default=None, sa_column=dt_col())
    status: str = "pending"
    last_error: str | None = None


class SeenItemRow(SQLModel, table=True):
    __tablename__ = "seen_items"

    hash: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    url: str = ""
    first_seen_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))


class ItemRow(SQLModel, table=True):
    __tablename__ = "items"

    id: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    bubble_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    url: str = ""
    title: str = ""
    published_at: datetime | None = Field(default=None, sa_column=dt_col())
    raw_path: str | None = None
    text_path: str | None = None
    text_truncated: bool = (
        False  # store_full_text off: only title + first 500 chars kept
    )
    # queued | routed | unsorted | extracted | written | failed | filtered
    status: str = Field(default="queued", index=True)
    route_confidence: float | None = None
    polled_at: datetime | None = Field(default=None, sa_column=dt_col())
    deduplicated_at: datetime | None = Field(default=None, sa_column=dt_col())
    routed_at: datetime | None = Field(default=None, sa_column=dt_col())
    extracted_at: datetime | None = Field(default=None, sa_column=dt_col())
    written_at: datetime | None = Field(default=None, sa_column=dt_col())
    error: str | None = None


class JobRow(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(index=True)
    state: str = Field(default="queued", index=True)  # queued | running | done | failed
    attempts: int = 0
    available_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))


class SettingRow(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class QueryLogRow(SQLModel, table=True):
    __tablename__ = "query_log"

    id: int | None = Field(default=None, primary_key=True)
    query: str
    bubbles: list[str] = Field(default_factory=list, sa_column=json_col())
    mode: str = ""
    latency_ms: float | None = None
    tokens: int | None = None
    rating: int | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))


class EvalRunRow(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: int | None = Field(default=None, primary_key=True)
    config: str
    scores: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    created_at: datetime = Field(default_factory=_utcnow, sa_column=dt_col(False))
