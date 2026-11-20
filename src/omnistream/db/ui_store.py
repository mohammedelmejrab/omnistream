"""Persistence for the UI surface: chats, messages, runs and run steps (spec 10.1, 10.6).

Mixed into ``Repository``. Steps are written synchronously from worker threads
through ``save_step`` (the trace recorder runs inside ``asyncio.to_thread``);
everything else goes through the async ``_run`` helper like the other tables.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import delete, update
from sqlmodel import Session, select

from omnistream.db.tables import ChatRow, MessageRow, RunRow, RunStepRow

T = TypeVar("T")


class UIStoreMixin:
    """Requires the host class to provide ``_engine`` and ``async _run(fn)``."""

    _engine: Any

    async def _run(self, fn: Callable[[Session], T]) -> T:  # pragma: no cover - supplied by Repository
        raise NotImplementedError

    # --- chats ---
    async def create_chat(self, row: ChatRow) -> ChatRow:
        def fn(s: Session) -> ChatRow:
            s.add(row)
            return row

        return await self._run(fn)

    async def get_chat(self, chat_id: str) -> ChatRow | None:
        return await self._run(lambda s: s.get(ChatRow, chat_id))

    async def list_chats(self) -> list[ChatRow]:
        return await self._run(
            lambda s: list(
                s.exec(select(ChatRow).order_by(ChatRow.updated_at.desc(), ChatRow.id))
            )
        )

    async def update_chat(self, chat_id: str, **changes: Any) -> ChatRow:
        def fn(s: Session) -> ChatRow:
            row = s.get(ChatRow, chat_id)
            if row is None:
                raise KeyError(chat_id)
            for key, value in changes.items():
                setattr(row, key, value)
            s.add(row)
            return row

        return await self._run(fn)

    async def delete_chat(self, chat_id: str) -> bool:
        """Remove a chat and its messages. Runs are kept as orphan traces."""

        def fn(s: Session) -> bool:
            row = s.get(ChatRow, chat_id)
            s.execute(delete(MessageRow).where(MessageRow.chat_id == chat_id))
            if row is None:
                return False
            s.delete(row)
            return True

        return await self._run(fn)

    # --- messages ---
    async def add_message(self, row: MessageRow) -> MessageRow:
        def fn(s: Session) -> MessageRow:
            s.add(row)
            return row

        return await self._run(fn)

    async def list_messages(self, chat_id: str) -> list[MessageRow]:
        return await self._run(
            lambda s: list(
                s.exec(
                    select(MessageRow)
                    .where(MessageRow.chat_id == chat_id)
                    .order_by(MessageRow.created_at, MessageRow.id)
                )
            )
        )

    async def set_message_content_for_run(self, run_id: str, content: str) -> None:
        """Show a run's outcome (for example 'Stopped') on its assistant message."""

        def fn(s: Session) -> None:
            s.execute(
                update(MessageRow)
                .where(MessageRow.run_id == run_id, MessageRow.role == "assistant")
                .values(content=content)
            )

        await self._run(fn)

    # --- runs ---
    async def create_run(self, row: RunRow) -> RunRow:
        def fn(s: Session) -> RunRow:
            s.add(row)
            return row

        return await self._run(fn)

    async def get_run(self, run_id: str) -> RunRow | None:
        return await self._run(lambda s: s.get(RunRow, run_id))

    async def update_run(self, run_id: str, **changes: Any) -> RunRow:
        def fn(s: Session) -> RunRow:
            row = s.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            for key, value in changes.items():
                setattr(row, key, value)
            s.add(row)
            return row

        return await self._run(fn)

    # --- steps ---
    def save_step(self, row: RunStepRow) -> None:
        """Synchronous write, safe from worker threads (see module docstring)."""
        with Session(self._engine) as session:
            session.merge(row)
            session.commit()

    async def list_steps(self, run_id: str) -> list[RunStepRow]:
        return await self._run(
            lambda s: list(
                s.exec(
                    select(RunStepRow)
                    .where(RunStepRow.run_id == run_id)
                    .order_by(RunStepRow.seq, RunStepRow.id)
                )
            )
        )

    # --- sweeps ---
    async def interrupt_running_runs(self, message: str) -> list[str]:
        """Stale-run sweep: runs still marked running belong to a dead process."""

        def fn(s: Session) -> list[str]:
            now = datetime.now(UTC)
            runs = list(s.exec(select(RunRow).where(RunRow.status == "running")))
            for run in runs:
                run.status = "interrupted"
                run.error = message
                run.finished_at = now
                s.add(run)
                s.execute(
                    update(MessageRow)
                    .where(MessageRow.run_id == run.id, MessageRow.role == "assistant")
                    .values(content=message)
                )
            return [run.id for run in runs]

        return await self._run(fn)

    async def purge_steps_started_before(self, cutoff: datetime) -> int:
        """Retention (spec 10.1): delete the steps of runs started before the cutoff.

        The run row stays, so an expired trace can answer 410 rather than 404.
        Returns the number of step rows removed.
        """

        def fn(s: Session) -> int:
            old = select(RunRow.id).where(RunRow.started_at < cutoff)
            result = s.execute(delete(RunStepRow).where(RunStepRow.run_id.in_(old)))
            return int(result.rowcount or 0)

        return await self._run(fn)
