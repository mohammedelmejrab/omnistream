from datetime import UTC, datetime, timedelta

import pytest

from omnistream.db import Repository
from omnistream.db.tables import EvalRunRow, ItemRow, QueryLogRow
from omnistream.models import ApiMapping, Bubble, Source

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.fixture
def repo():
    return Repository()


async def test_bubble_round_trip_with_embedding_and_utc(repo):
    b = Bubble(
        id="news",
        name="News",
        description="d",
        description_embedding=[0.25, -0.5],
        half_life_days=3,
        created_at=NOW,
        updated_at=NOW,
    )
    await repo.create_bubble(b)
    assert await repo.get_bubble("news") == b
    assert await repo.get_bubble("nope") is None
    assert await repo.list_bubbles() == [b]


async def test_bubble_update_and_delete(repo):
    await repo.create_bubble(Bubble(id="a", name="A", description="d"))
    updated = await repo.update_bubble("a", name="Alpha", half_life_days=365)
    assert (updated.name, updated.half_life_days) == ("Alpha", 365)
    with pytest.raises(KeyError):
        await repo.update_bubble("zzz", name="x")
    await repo.delete_bubble("a")
    assert await repo.list_bubbles() == []


async def test_episode_counter_and_summary_reset(repo):
    await repo.create_bubble(Bubble(id="a", name="A", description="d"))
    assert await repo.bump_episode_counter("a") == 1
    assert await repo.bump_episode_counter("a", 4) == 5
    await repo.set_auto_summary("a", "summary")
    assert await repo.episodes_since_summary("a") == 0
    assert (await repo.get_bubble("a")).auto_summary == "summary"


async def test_source_json_round_trip_and_overwrite(repo):
    mapping = ApiMapping(
        items="$.data[*]",
        body="$.text",
        url="$.link",
        title="$.t",
        date="$.d",
        headers={"X-Key": "k"},
    )
    s = Source(
        id="s1",
        type="api",
        url="http://api",
        bubble_ids=["news", "finance"],
        api_mapping=mapping,
        max_items_per_hour=10,
        store_full_text=False,
        enabled=False,
        last_polled_at=NOW,
    )
    await repo.upsert_source(s)
    assert await repo.get_source("s1") == s
    s2 = s.model_copy(update={"credibility": 0.9, "status": "error"})
    await repo.upsert_source(s2)
    assert await repo.get_source("s1") == s2
    assert await repo.list_sources() == [s2]
    assert await repo.get_source("nope") is None


async def test_source_defaults_match_spec(repo):
    s = await repo.upsert_source(Source(id="r", type="rss", url="http://f"))
    got = await repo.get_source("r")
    assert got == s
    assert (got.credibility, got.poll_interval, got.max_items_per_hour) == (
        0.5,
        900,
        30,
    )
    assert got.store_full_text and got.enabled and got.api_mapping is None


async def test_seen_hash_unique_and_idempotent(repo):
    assert not await repo.has_seen("h1")
    await repo.mark_seen("h1", "s1", "http://u")
    await repo.mark_seen("h1", "s2", "http://other")  # no error, first wins
    assert await repo.has_seen("h1")
    assert not await repo.has_seen("h2")


async def test_items_lifecycle_and_status_filter(repo):
    await repo.create_item(
        ItemRow(
            id="i1",
            source_id="s1",
            bubble_ids=["news"],
            url="http://u",
            polled_at=NOW,
            raw_path="data/raw/i1.html",
        )
    )
    await repo.create_item(ItemRow(id="i2", source_id="s1", status="unsorted"))
    got = await repo.get_item("i1")
    assert got.bubble_ids == ["news"] and got.status == "queued"
    assert got.polled_at == NOW
    await repo.update_item("i1", status="routed", routed_at=NOW, route_confidence=0.8)
    assert [i.id for i in await repo.list_items("routed")] == ["i1"]
    assert [i.id for i in await repo.list_items("unsorted")] == ["i2"]
    assert len(await repo.list_items()) == 2


async def test_job_claim_order_attempts_and_availability(repo):
    j1 = await repo.enqueue_job("i1")
    await repo.enqueue_job("i2")
    claimed = await repo.claim_job()
    assert claimed.id == j1.id and claimed.state == "running" and claimed.attempts == 1
    await repo.finish_job(claimed.id, "queued", retry_in=timedelta(hours=1))
    nxt = await repo.claim_job()
    assert nxt.item_id == "i2"
    assert await repo.claim_job() is None  # i1 is delayed
    await repo.finish_job(nxt.id, "done")
    assert [j.item_id for j in await repo.list_jobs("done")] == ["i2"]


async def test_settings_override_and_default(repo):
    assert await repo.get_setting("router_threshold", 0.5) == 0.5
    await repo.set_setting("router_threshold", 0.7)
    await repo.set_setting("prompts", {"a": [1, 2]})
    assert await repo.get_setting("router_threshold", 0.5) == 0.7
    await repo.set_setting("router_threshold", 0.6)  # overwrite
    assert await repo.all_settings() == {
        "router_threshold": 0.6,
        "prompts": {"a": [1, 2]},
    }


async def test_query_log_and_eval_runs(repo):
    q = await repo.log_query(
        QueryLogRow(
            query="q", bubbles=["news"], mode="own", latency_ms=12.5, tokens=100
        )
    )
    await repo.rate_query(q.id, 1)
    (row,) = await repo.list_queries()
    assert row.bubbles == ["news"] and row.rating == 1 and row.tokens == 100
    await repo.add_eval_run(EvalRunRow(config="own", scores={"acc": 0.8}))
    (run,) = await repo.list_eval_runs()
    assert run.scores == {"acc": 0.8}


async def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "sub" / "app.db")
    a = Repository.from_path(path)
    await a.mark_seen("h", "s")
    await a.close()
    b = Repository.from_path(path)
    assert await b.has_seen("h")
