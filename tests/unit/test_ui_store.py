"""Persistence for chats, messages, runs and steps (spec 10.1, 10.6, 14 unit)."""

from datetime import UTC, datetime, timedelta

from omnistream.db import Repository
from omnistream.db.tables import ChatRow, MessageRow, RunRow, RunStepRow

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _chat(chat_id: str, updated: datetime = NOW) -> ChatRow:
    return ChatRow(id=chat_id, title=chat_id, created_at=NOW, updated_at=updated)


def _step(run_id: str, step_id: str, seq: int, **over) -> RunStepRow:
    values = {
        "id": step_id, "run_id": run_id, "seq": seq, "kind": "route", "started_at": NOW,
        "duration_ms": 1.5, "status": "ok",
    }
    values.update(over)
    return RunStepRow(**values)


async def test_chats_list_most_recent_first_and_rename_and_delete_keeps_runs():
    repo = Repository("sqlite://")
    await repo.create_chat(_chat("old", NOW - timedelta(days=1)))
    await repo.create_chat(_chat("new", NOW))
    assert [c.id for c in await repo.list_chats()] == ["new", "old"]

    renamed = await repo.update_chat("old", title="Renamed")
    assert renamed.title == "Renamed"

    await repo.add_message(MessageRow(id="m1", chat_id="new", role="user", content="hi"))
    await repo.create_run(RunRow(id="r1", chat_id="new", mode="normal", started_at=NOW))
    assert await repo.delete_chat("new") is True
    assert await repo.get_chat("new") is None
    assert await repo.list_messages("new") == []
    # Traces outlive their chat (orphan trace, spec 10.4).
    assert (await repo.get_run("r1")).chat_id == "new"
    assert await repo.delete_chat("new") is False
    await repo.close()


async def test_messages_come_back_in_creation_order():
    repo = Repository("sqlite://")
    await repo.create_chat(_chat("c"))
    for offset, role in enumerate(["user", "assistant", "user"]):
        await repo.add_message(
            MessageRow(
                id=f"m{offset}", chat_id="c", role=role, content=role,
                created_at=NOW + timedelta(seconds=offset),
            )
        )
    assert [m.role for m in await repo.list_messages("c")] == ["user", "assistant", "user"]
    await repo.close()


async def test_steps_are_listed_by_start_order_not_finish_order():
    repo = Repository("sqlite://")
    await repo.create_run(RunRow(id="r", chat_id="c", mode="agentic", started_at=NOW))
    # Finished in reverse order: child first, then parent.
    repo.save_step(_step("r", "child", 2, kind="retrieve", parent_step_id="parent"))
    repo.save_step(_step("r", "parent", 1, kind="subagent"))
    steps = await repo.list_steps("r")
    assert [s.id for s in steps] == ["parent", "child"]
    assert steps[1].parent_step_id == "parent"
    await repo.close()


async def test_stale_run_sweep_marks_running_runs_interrupted_and_updates_the_chat():
    repo = Repository("sqlite://")
    await repo.create_chat(_chat("c"))
    await repo.create_run(RunRow(id="live", chat_id="c", mode="normal", started_at=NOW))
    await repo.create_run(
        RunRow(id="done", chat_id="c", mode="normal", status="ok", answer="x", started_at=NOW, finished_at=NOW)
    )
    await repo.add_message(MessageRow(id="a1", chat_id="c", role="assistant", content="", run_id="live"))
    await repo.add_message(MessageRow(id="a2", chat_id="c", role="assistant", content="x", run_id="done"))
    repo.save_step(_step("live", "s1", 1))

    swept = await repo.interrupt_running_runs("Interrupted when OmniStream restarted")

    assert swept == ["live"]
    live = await repo.get_run("live")
    assert live.status == "interrupted"
    assert live.error == "Interrupted when OmniStream restarted"
    assert live.finished_at is not None
    assert (await repo.get_run("done")).status == "ok"
    contents = {m.id: m.content for m in await repo.list_messages("c")}
    assert contents["a1"] == "Interrupted when OmniStream restarted"
    assert contents["a2"] == "x"
    assert [s.id for s in await repo.list_steps("live")] == ["s1"]
    await repo.close()


async def test_retention_purges_steps_older_than_the_cutoff_and_keeps_the_run_row():
    repo = Repository("sqlite://")
    old_start = NOW - timedelta(days=31)
    await repo.create_run(RunRow(id="old", chat_id="c", mode="normal", status="ok", started_at=old_start))
    await repo.create_run(RunRow(id="new", chat_id="c", mode="normal", status="ok", started_at=NOW))
    repo.save_step(_step("old", "s-old", 1, started_at=old_start))
    repo.save_step(_step("new", "s-new", 1))

    purged = await repo.purge_steps_started_before(NOW - timedelta(days=30))

    assert purged == 1  # one step row removed
    assert await repo.get_run("old") is not None  # the run stays, so its trace can answer 410
    assert await repo.list_steps("old") == []
    assert await repo.get_run("new") is not None
    assert [s.id for s in await repo.list_steps("new")] == ["s-new"]
    await repo.close()


async def test_step_round_trip_keeps_summary_and_ids():
    repo = Repository("sqlite://")
    await repo.create_run(RunRow(id="r", chat_id="c", mode="normal", started_at=NOW))
    repo.save_step(
        _step(
            "r", "s", 1, kind="retrieve", bubble="news",
            summary={"facts": 2, "top_facts": [{"id": "f1", "score": 0.5}]},
            node_ids=["e1", "e2"], edge_ids=["f1"],
            citations=[{"item_id": "i1", "url": None, "title": "Item"}],
        )
    )
    (row,) = await repo.list_steps("r")
    assert row.summary == {"facts": 2, "top_facts": [{"id": "f1", "score": 0.5}]}
    assert row.node_ids == ["e1", "e2"]
    assert row.edge_ids == ["f1"]
    assert row.citations == [{"item_id": "i1", "url": None, "title": "Item"}]
    assert row.started_at == NOW
    await repo.close()
