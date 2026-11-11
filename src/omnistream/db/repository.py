"""Async facade over SQLite application state.

Sync SQLModel sessions run in worker threads via ``asyncio.to_thread``.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import Engine, event, func, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from omnistream.db.tables import (
    BubbleRow,
    EvalRunRow,
    ItemRow,
    JobRow,
    QueryLogRow,
    SeenItemRow,
    SettingRow,
    SourceRow,
)
from omnistream.models import ApiMapping, Bubble, Source

T = TypeVar("T")

_BUBBLE_FIELDS = tuple(Bubble.model_fields)


def _bubble(r: BubbleRow) -> Bubble:
    return Bubble(**{f: getattr(r, f) for f in _BUBBLE_FIELDS})


def _source(r: SourceRow) -> Source:
    data = {f: getattr(r, f) for f in Source.model_fields if f != "api_mapping"}
    data["api_mapping"] = (
        ApiMapping.model_validate(r.api_mapping) if r.api_mapping else None
    )
    return Source(**data)


def _source_row(s: Source) -> SourceRow:
    data = s.model_dump(exclude={"api_mapping"})
    data["api_mapping"] = s.api_mapping.model_dump() if s.api_mapping else None
    return SourceRow(**data)


class Repository:
    def __init__(self, url: str = "sqlite://") -> None:
        kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared in-memory connection
        self._engine: Engine = create_engine(url, **kwargs)
        event.listen(self._engine, "connect", _sqlite_pragmas)
        SQLModel.metadata.create_all(self._engine)

    @classmethod
    def from_path(cls, path: str) -> "Repository":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path}")

    async def close(self) -> None:
        await asyncio.to_thread(self._engine.dispose)

    async def _run(self, fn: Callable[[Session], T]) -> T:
        def work() -> T:
            with Session(self._engine, expire_on_commit=False) as session:
                result = fn(session)
                session.commit()
                return result

        return await asyncio.to_thread(work)

    # --- bubbles ---
    async def create_bubble(self, b: Bubble) -> Bubble:
        def fn(s: Session) -> Bubble:
            existing = s.get(BubbleRow, b.id)
            data = b.model_dump()
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                s.add(existing)
                return _bubble(existing)
            row = BubbleRow(**data)
            s.add(row)
            return _bubble(row)

        return await self._run(fn)

    async def get_bubble(self, id: str) -> Bubble | None:
        return await self._run(lambda s: (r := s.get(BubbleRow, id)) and _bubble(r))

    async def list_bubbles(self) -> list[Bubble]:
        return await self._run(
            lambda s: [
                _bubble(r) for r in s.exec(select(BubbleRow).order_by(BubbleRow.id))
            ]
        )

    async def update_bubble(self, id: str, **changes: Any) -> Bubble:
        def fn(s: Session) -> Bubble:
            row = s.get(BubbleRow, id)
            if row is None:
                raise KeyError(id)
            for k, v in changes.items():
                setattr(row, k, v)
            row.updated_at = datetime.now(UTC)
            s.add(row)
            return _bubble(row)

        return await self._run(fn)

    async def delete_bubble(self, id: str) -> None:
        def fn(s: Session) -> None:
            if row := s.get(BubbleRow, id):
                s.delete(row)

        await self._run(fn)

    async def bump_episode_counter(self, bubble_id: str, by: int = 1) -> int:
        """Add to the bubble's episodes_since_summary counter; returns the new value."""

        def fn(s: Session) -> int:
            row = s.get(BubbleRow, bubble_id)
            if row is None:
                raise KeyError(bubble_id)
            row.episodes_since_summary += by
            s.add(row)
            return row.episodes_since_summary

        return await self._run(fn)

    async def set_auto_summary(self, bubble_id: str, summary: str) -> None:
        def fn(s: Session) -> None:
            row = s.get(BubbleRow, bubble_id)
            if row is None:
                raise KeyError(bubble_id)
            row.auto_summary = summary
            row.episodes_since_summary = 0
            row.updated_at = datetime.now(UTC)
            s.add(row)

        await self._run(fn)

    async def episodes_since_summary(self, bubble_id: str) -> int:
        def fn(s: Session) -> int:
            row = s.get(BubbleRow, bubble_id)
            if row is None:
                raise KeyError(bubble_id)
            return row.episodes_since_summary

        return await self._run(fn)

    # --- sources ---
    async def upsert_source(self, src: Source) -> Source:
        def fn(s: Session) -> Source:
            s.merge(_source_row(src))
            return src.model_copy(deep=True)

        return await self._run(fn)

    async def get_source(self, id: str) -> Source | None:
        return await self._run(lambda s: (r := s.get(SourceRow, id)) and _source(r))

    async def list_sources(self) -> list[Source]:
        return await self._run(
            lambda s: [
                _source(r) for r in s.exec(select(SourceRow).order_by(SourceRow.id))
            ]
        )

    async def delete_source(self, id: str) -> None:
        def fn(s: Session) -> None:
            if row := s.get(SourceRow, id):
                s.delete(row)

        await self._run(fn)

    # --- seen items ---
    async def has_seen(self, item_hash: str) -> bool:
        return await self._run(lambda s: s.get(SeenItemRow, item_hash) is not None)

    async def mark_seen(self, item_hash: str, source_id: str, url: str = "") -> None:
        def fn(s: Session) -> None:
            stmt = (
                sqlite_insert(SeenItemRow)
                .values(
                    hash=item_hash,
                    source_id=source_id,
                    url=url,
                    first_seen_at=datetime.now(UTC).replace(tzinfo=None),
                )
                .on_conflict_do_nothing(index_elements=["hash"])
            )
            s.execute(stmt)

        await self._run(fn)

    # --- items ---
    async def create_item(self, item: ItemRow) -> ItemRow:
        def fn(s: Session) -> ItemRow:
            s.add(item)
            return item

        return await self._run(fn)

    async def get_item(self, id: str) -> ItemRow | None:
        return await self._run(lambda s: s.get(ItemRow, id))

    async def list_items(self, status: str | None = None) -> list[ItemRow]:
        def fn(s: Session) -> list[ItemRow]:
            q = select(ItemRow).order_by(ItemRow.id)
            if status is not None:
                q = q.where(ItemRow.status == status)
            return list(s.exec(q))

        return await self._run(fn)

    async def count_items_since(
        self, source_id: str, since: datetime, *, exclude_status: str = "filtered"
    ) -> int:
        """Items polled for `source_id` at or after `since` (drives the hourly cap)."""

        def fn(s: Session) -> int:
            q = (
                select(func.count())
                .select_from(ItemRow)
                .where(
                    ItemRow.source_id == source_id,
                    ItemRow.polled_at >= since,
                    ItemRow.status != exclude_status,
                )
            )
            return int(s.exec(q).one())

        return await self._run(fn)

    async def update_item(self, id: str, **changes: Any) -> ItemRow:
        def fn(s: Session) -> ItemRow:
            row = s.get(ItemRow, id)
            if row is None:
                raise KeyError(id)
            for k, v in changes.items():
                setattr(row, k, v)
            s.add(row)
            return row

        return await self._run(fn)

    # --- jobs ---
    async def enqueue_job(self, item_id: str) -> JobRow:
        def fn(s: Session) -> JobRow:
            job = JobRow(item_id=item_id)
            s.add(job)
            s.flush()
            return job

        return await self._run(fn)

    async def claim_job(self, now: datetime | None = None) -> JobRow | None:
        """Atomically move the oldest available queued job to running.

        The state flip is a conditional UPDATE, so two concurrent claimers can
        never receive the same job.
        """
        now = now or datetime.now(UTC)

        def fn(s: Session) -> JobRow | None:
            while True:
                job = s.exec(
                    select(JobRow)
                    .where(JobRow.state == "queued", JobRow.available_at <= now)
                    .order_by(JobRow.available_at, JobRow.id)
                ).first()
                if job is None:
                    return None
                res = s.execute(
                    update(JobRow)
                    .where(JobRow.id == job.id, JobRow.state == "queued")
                    .values(state="running", attempts=JobRow.attempts + 1)
                )
                s.commit()
                if res.rowcount == 1:
                    s.refresh(job)
                    return job

        return await self._run(fn)

    async def requeue_running_jobs(self) -> int:
        """Crash recovery: jobs left 'running' go back to the queue."""

        def fn(s: Session) -> int:
            res = s.execute(
                update(JobRow)
                .where(JobRow.state == "running")
                .values(state="queued", available_at=datetime.now(UTC))
            )
            return int(res.rowcount)

        return await self._run(fn)

    async def finish_job(
        self, job_id: int, state: str, retry_in: timedelta | None = None
    ) -> JobRow:
        def fn(s: Session) -> JobRow:
            job = s.get(JobRow, job_id)
            if job is None:
                raise KeyError(job_id)
            job.state = state
            if retry_in is not None:
                job.available_at = datetime.now(UTC) + retry_in
            s.add(job)
            return job

        return await self._run(fn)

    async def list_jobs(self, state: str | None = None) -> list[JobRow]:
        def fn(s: Session) -> list[JobRow]:
            q = select(JobRow).order_by(JobRow.id)
            if state is not None:
                q = q.where(JobRow.state == state)
            return list(s.exec(q))

        return await self._run(fn)

    # --- settings (overrides) ---
    async def get_setting(self, key: str, default: Any = None) -> Any:
        def fn(s: Session) -> Any:
            row = s.get(SettingRow, key)
            return default if row is None else row.value

        return await self._run(fn)

    async def set_setting(self, key: str, value: Any) -> None:
        def fn(s: Session) -> None:
            s.merge(SettingRow(key=key, value=value))

        await self._run(fn)

    async def all_settings(self) -> dict[str, Any]:
        return await self._run(
            lambda s: {r.key: r.value for r in s.exec(select(SettingRow))}
        )

    # --- query log / eval runs ---
    async def log_query(self, row: QueryLogRow) -> QueryLogRow:
        def fn(s: Session) -> QueryLogRow:
            s.add(row)
            s.flush()
            return row

        return await self._run(fn)

    async def rate_query(self, id: int, rating: int) -> None:
        def fn(s: Session) -> None:
            row = s.get(QueryLogRow, id)
            if row is None:
                raise KeyError(id)
            row.rating = rating
            s.add(row)

        await self._run(fn)

    async def list_queries(self) -> list[QueryLogRow]:
        return await self._run(
            lambda s: list(s.exec(select(QueryLogRow).order_by(QueryLogRow.id)))
        )

    async def add_eval_run(self, row: EvalRunRow) -> EvalRunRow:
        def fn(s: Session) -> EvalRunRow:
            s.add(row)
            s.flush()
            return row

        return await self._run(fn)

    async def list_eval_runs(self) -> list[EvalRunRow]:
        return await self._run(
            lambda s: list(s.exec(select(EvalRunRow).order_by(EvalRunRow.id)))
        )


def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()
