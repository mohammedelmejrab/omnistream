from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from omnistream.db import Repository
from omnistream.ingest.intake import Intake
from omnistream.ingest.normalize import content_hash, normalize_url
from omnistream.models import RawItem, Source
from omnistream.sources.replay import SnapshotRecorder, load_snapshot

PUB = datetime(2026, 1, 1, tzinfo=UTC)
BODY = "Alice became chief executive of Acme Corp this week. " * 6  # > 200 chars


def src(**kw) -> Source:
    return Source(id="s1", type="rss", url="https://a.test/f.xml", **kw)


def raw(n: int = 1, text: str = BODY, **kw) -> RawItem:
    return RawItem(
        source_id="s1",
        url=f"https://a.test/{n}",
        title=f"T{n}",
        text=f"{text} #{n}",
        published_at=kw.pop("published_at", PUB),
        **kw,
    )


@pytest.fixture
async def env(tmp_path):
    repo = Repository()
    await repo.upsert_source(src())
    return repo, Intake(repo, str(tmp_path)), tmp_path


async def test_accept_stores_item_job_and_files(env):
    repo, intake, root = env
    row = await intake.accept(raw(), src(), b"<p>raw html</p>", "html")
    assert row is not None and row.status == "queued"
    assert row.polled_at and row.deduplicated_at
    assert (await repo.get_item(row.id)).status == "queued"
    jobs = await repo.list_jobs()
    assert [j.item_id for j in jobs] == [row.id]
    raw_path, text_path = Path(row.raw_path), Path(row.text_path)
    assert raw_path.parent == root / "raw" / "s1"
    assert raw_path.suffix == ".html" and raw_path.read_bytes() == b"<p>raw html</p>"
    assert text_path.suffix == ".txt" and text_path.stem == raw_path.stem
    assert "Alice became" in text_path.read_text()
    assert len(raw_path.stem) == 64  # sha256 of the raw bytes


async def test_repoll_adds_zero_items(env):
    repo, intake, _ = env
    items = [raw(i) for i in range(3)]
    for it in items:
        assert await intake.accept(it, src(), b"x", "html")
    for it in items:
        assert await intake.accept(it, src(), b"x", "html") is None
    assert len(await repo.list_items()) == 3
    assert len(await repo.list_jobs()) == 3


async def test_dedup_ignores_tracking_params_and_whitespace(env):
    _, intake, _ = env
    a = raw(1)
    b = a.model_copy(
        update={
            "url": "https://a.test/1?utm_source=x&fbclid=1&ref=h",
            "text": a.text.upper(),
        }
    )
    assert await intake.accept(a, src(), b"x", "html")
    assert await intake.accept(b, src(), b"x", "html") is None


def test_tracking_params_removed():
    url = "https://a.test/p?mc_cid=1&mc_eid=2&ref=x&ref_src=y&gclid=3&keep=1"
    assert normalize_url(url) == "https://a.test/p?keep=1"


async def test_prefilter_short_and_undated_feed_items(env):
    repo, intake, _ = env
    assert await intake.accept(raw(1, text="too short"), src(), b"x", "html") is None
    assert await intake.accept(raw(2, published_at=None), src(), b"x", "html") is None
    items = await repo.list_items()
    assert {i.status for i in items} == {"filtered"}
    assert await repo.list_jobs() == []
    # filtered items are marked seen: re-poll does not duplicate rows
    await intake.accept(raw(1, text="too short"), src(), b"x", "html")
    assert len(await repo.list_items()) == 2


async def test_cap_leaves_excess_unseen_for_next_poll(env):
    repo, intake, _ = env
    s = src(max_items_per_hour=2)
    results = [await intake.accept(raw(i), s, b"x", "html") for i in range(4)]
    assert [r is not None for r in results] == [True, True, False, False]
    assert not await repo.has_seen(content_hash(raw(3).url, raw(3).text))
    # an hour later the capped items are accepted
    old = datetime.now(UTC) - timedelta(hours=2)
    for item in await repo.list_items():
        await repo.update_item(item.id, polled_at=old)
    assert await intake.accept(raw(2), s, b"x", "html")


async def test_store_full_text_false_keeps_title_and_500_chars(env):
    _, intake, _ = env
    long = "word " * 400
    row = await intake.accept(
        raw(1, text=long), src(store_full_text=False), b"r", "html"
    )
    text = Path(row.text_path).read_text()
    assert row.text_truncated is True
    assert text.startswith("T1\n\n") and len(text) == len("T1\n\n") + 500
    assert Path(row.raw_path).read_bytes() == b"r"  # original still kept


async def test_documents_skip_prefilter_and_share_one_original(env):
    _repo, intake, root = env
    doc = Source(id="d1", type="document")
    data = b"%PDF fake original"
    parts = [
        RawItem(source_id="d1", url=f"doc://abc#part-{i}", title=f"f ({i})", text=t)
        for i, t in enumerate(["short", "another short part"])
    ]
    rows = [
        await intake.accept(p, doc, data, "pdf", part=i) for i, p in enumerate(parts)
    ]
    assert all(rows)
    assert rows[0].raw_path == rows[1].raw_path
    assert rows[0].text_path != rows[1].text_path
    assert len(list((root / "raw" / "d1").glob("*.pdf"))) == 1
    assert Path(rows[1].text_path).read_text() == "another short part"
    assert rows[0].published_at is not None  # upload time


async def test_replay_round_trip(env):
    repo, intake, root = env
    items = [raw(i, raw_content=f"<p>{i}</p>", raw_ext="html") for i in (3, 1, 2)]
    rec = SnapshotRecorder(root, "run1")
    rec.record(items)
    loaded = load_snapshot(root, "run1")
    assert loaded == items  # order and published_at preserved
    for it in loaded:
        await intake.accept(it, src(), it.raw_content.encode(), it.raw_ext)
    stored = sorted(await repo.list_items(), key=lambda i: i.polled_at)
    assert [i.url for i in stored] == [i.url for i in items]  # polled order kept


async def test_replay_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_DATA_DIR", str(tmp_path))
    repo = Repository.from_path(str(tmp_path / "omnistream.db"))
    await repo.upsert_source(src())
    await repo.close()
    SnapshotRecorder(tmp_path, "snap").record([raw(1), raw(2)])
    from omnistream.cli import replay
    from omnistream.config import Settings

    assert await replay("snap", Settings()) == 0
    repo = Repository.from_path(str(tmp_path / "omnistream.db"))
    assert len(await repo.list_items(status="queued")) == 2
