import pytest

from omnistream.cli import seed
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.sources.api import _parse_date, expand_env
from tests.conftest import FakeEmbedder


class KeepOpen(Repository):
    async def close(self):  # seed closes the repo; keep it queryable for asserts
        pass


async def test_seed_creates_bubbles_and_sources_idempotently(monkeypatch, tmp_path):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    repo = KeepOpen()
    for _ in range(2):
        await seed(Settings(data_dir=str(tmp_path)), repo, FakeEmbedder())
    bubbles = {b.id: b for b in await repo.list_bubbles()}
    assert {k: v.half_life_days for k, v in bubbles.items()} == {
        "news": 3,
        "finance": 30,
        "research": 365,
    }
    assert all(b.description_embedding for b in bubbles.values())
    sources = {s.id: s for s in await repo.list_sources()}
    assert set(sources) == {
        "bbc-world",
        "guardian-world",
        "cnbc-markets",
        "arxiv-cs-cl",
    }
    assert sources["arxiv-cs-cl"].url == "https://rss.arxiv.org/rss/cs.CL"
    assert sources["bbc-world"].bubble_ids == ["news"]


async def test_seed_adds_finnhub_when_key_present(monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    repo = KeepOpen()
    await seed(Settings(data_dir=str(tmp_path)), repo, FakeEmbedder())
    s = await repo.get_source("finnhub-news")
    assert "${FINNHUB_API_KEY}" in s.url and s.api_mapping.date == "$.datetime"
    assert "k" not in s.url.replace("token", "")  # secret not stored


def test_expand_env_and_epoch_dates(monkeypatch):
    monkeypatch.setenv("TOK", "abc")
    assert expand_env("x?token=${TOK}&y=${MISSING_VAR_X}") == "x?token=abc&y="
    assert _parse_date(1_700_000_000).year == 2023
    assert _parse_date(True) is None


@pytest.mark.parametrize("name", ["a"])
def test_workerpool_import_has_no_settings_side_effect(name):
    import omnistream.ingest.queue as q

    assert not hasattr(q, "_settings")


async def test_seed_uses_configured_half_lives(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    repo = KeepOpen()
    try:
        await seed(
            Settings(
                _env_file=None,
                data_dir=str(tmp_path),
                half_life_news_days=8,
                half_life_finance_days=60,
                half_life_research_days=700,
            ),
            repo,
            FakeEmbedder(),
        )
        assert {b.id: b.half_life_days for b in await repo.list_bubbles()} == {
            "news": 8,
            "finance": 60,
            "research": 700,
        }
    finally:
        await Repository.close(repo)
