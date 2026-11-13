"""Offline fixtures exercise policy, C1, C2 replay and QA failure modes."""

import gzip
import hashlib
import json
from datetime import UTC, date, datetime

import httpx
import numpy as np
import pytest

from omnistream.eval.real.collect import (
    PublicHTTP,
    clean_html,
    collect,
    content_kind,
    corpus_paths,
    rejection,
)
from omnistream.eval.real.verify import (
    changed_candidates,
    cleanliness,
    connected_clusters,
    entity_key,
    length_stats,
    overlap,
)
from omnistream.models import RawItem, Source
from omnistream.sources.replay import load_snapshot
from omnistream.sources.rss import fetch_rss


def test_names_and_prefilter():
    for name in ("../x", "eval-v1", "real-../x", "real-"):
        with pytest.raises(ValueError):
            corpus_paths(name)
    item = RawItem(source_id="s", url="https://example.org/1", text="x" * 200)
    assert rejection(item, date(2026, 1, 1), date(2026, 1, 30), lang="en") == "no_date"
    item.text = "x" * 199
    assert (
        rejection(item, date(2026, 1, 1), date(2026, 1, 30), lang="en") == "too_short"
    )
    item.text = "x" * 200
    item.published_at = datetime(2026, 1, 15, tzinfo=UTC)
    assert rejection(item, date(2026, 1, 1), date(2026, 1, 30), lang="en") is None
    assert (
        rejection(item, date(2026, 1, 1), date(2026, 1, 30), lang="fr") == "non_english"
    )
    assert (
        rejection(item, date(2026, 1, 20), date(2026, 1, 30), lang="en")
        == "before_window"
    )
    assert (
        rejection(item, date(2026, 1, 1), date(2026, 1, 10), lang="en")
        == "future_or_after_window"
    )


@pytest.mark.asyncio
async def test_rss_empty_markup_falls_back_and_empty_optin():
    feed = b"""<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0"><channel><title>Fixture</title>
    <item><title>First</title><link>https://example.org/1</link><content:encoded><![CDATA[<p> </p>]]></content:encoded><description>Nonempty summary</description><pubDate>Thu, 15 Jan 2026 10:00:00 -0500</pubDate></item>
    <item><title>Empty body</title><link>https://example.org/2</link><description></description></item></channel></rss>"""
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=feed))
    ) as client:
        source = Source(id="fixture", type="rss", url="https://example.org/rss")
        normal = await fetch_rss(source, client)
        audit = await fetch_rss(source, client, include_empty=True)
    assert len(normal) == 1
    assert normal[0].text == "Nonempty summary"
    assert normal[0].published_at == datetime(2026, 1, 15, 15, tzinfo=UTC)
    assert len(audit) == 2 and audit[1].text == ""


@pytest.mark.asyncio
async def test_http_robots_delay_redirect_and_compressed_cache(tmp_path):
    calls, waits = [], []
    now = [0.0]

    async def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: *\nDisallow: /private\nCrawl-delay: 10"
            )
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": "https://other.example/final"}
            )
        return httpx.Response(
            200,
            content=gzip.compress(b"original feed"),
            headers={"content-encoding": "gzip"},
        )

    http = PublicHTTP(
        tmp_path,
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        clock=lambda: now[0],
    )
    assert (await http.get("https://example.org/feed")).content == b"original feed"
    assert waits == [10]
    count = len(calls)
    assert (await http.get("https://example.org/feed")).content == b"original feed"
    assert len(calls) == count
    with pytest.raises(PermissionError):
        await http.get("https://example.org/private")
    assert "https://example.org/private" not in calls
    assert (await http.get("https://example.org/start")).content == b"original feed"
    assert "https://other.example/robots.txt" in calls
    assert waits[-1] == 10
    await http.close()


@pytest.mark.asyncio
async def test_http_fail_closed(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(403)

    http = PublicHTTP(tmp_path, transport=httpx.MockTransport(handler))
    with pytest.raises(PermissionError):
        await http.get("https://example.org/feed")
    assert calls == ["/robots.txt"]
    await http.close()


@pytest.mark.asyncio
async def test_collect_idempotent_replay_and_no_production_db(tmp_path, monkeypatch):
    import omnistream.eval.real.collect as module
    from omnistream.ingest.normalize import content_hash

    body = "Microsoft announced a new research platform for developers. " * 12
    escaped = body.replace("&", "&amp;")
    feed = f'<rss version="2.0"><channel><title>Fixture</title><item><title>Platform</title><link>https://example.org/article?utm_source=x</link><description>{escaped}</description><pubDate>Thu, 15 Jan 2026 10:00:00 GMT</pubDate></item></channel></rss>'

    class OfflineHTTP(PublicHTTP):
        def __init__(self, folder):
            def handler(request):
                if request.url.path == "/robots.txt":
                    return httpx.Response(404)
                return httpx.Response(200, text=feed)

            async def sleep(_):
                return None

            super().__init__(
                folder, transport=httpx.MockTransport(handler), sleep=sleep
            )

    monkeypatch.setattr(module, "PublicHTTP", OfflineHTTP)
    monkeypatch.setattr(module, "language", lambda _: ("en", 1.0))
    config = {
        "since": "2026-01-01",
        "until": "2026-01-31",
        "sources": [
            {
                "id": "fixture",
                "type": "rss",
                "url": "https://example.org/feed",
                "credibility": 0.9,
                "bubble_hint": "news",
                "enabled": True,
                "full_text_policy": "feed_only",
                "max_items": 28,
            }
        ],
    }
    source = tmp_path / "sources.json"
    source.write_text(json.dumps(config))
    first = await collect("real-test", root=tmp_path, source_file=source)
    manifest = tmp_path / "src/omnistream/eval/real/real-test-manifest.jsonl"
    original = manifest.read_bytes()
    second = await collect("real-test", root=tmp_path, source_file=source)
    assert first["manifest_count"] == second["manifest_count"] == 1
    assert manifest.read_bytes() == original
    assert not (tmp_path / "data/omnistream.db").exists()
    replay = load_snapshot(tmp_path / "data/real/real-test", "real-test")
    assert len(replay) == 1 and replay[0].bubble_ids_override == ["news"]
    row = json.loads(original)
    assert row["id"] == content_hash(replay[0].url, body.strip())
    assert row["sha256"] == hashlib.sha256(body.strip().encode()).hexdigest()
    assert "text" not in row
    with pytest.raises(ValueError, match="immutable"):
        await collect(
            "real-test", since="2026-01-02", root=tmp_path, source_file=source
        )


def test_cleanliness_depth_and_stats():
    assert (
        clean_html(
            "<p>Real text</p><script>bad()</script><nav>Menu</nav><div hidden>Invisible</div>"
        )
        == "Real text"
    )
    assert content_kind("word " * 500, "abstract", "<p>x</p>" * 10) == "abstract"
    assert (
        content_kind("word " * 500, "feed_only", "<p>x</p>" * 10) == "full_text_likely"
    )
    assert content_kind("Read more", "feed_only") == "summary_or_truncated"
    assert "mojibake" in cleanliness("broken \ufffd text")
    assert "navigation_cookie" in cleanliness("Accept all cookies")
    assert length_stats([10, 20, 100])["median"] == 20
    assert length_stats([])["max"] == 0


def test_entity_overlap_unique_pairs_and_changed_signals():
    assert entity_key("Microsoft Corporation") == "microsoft"
    assert entity_key("Alphabet") != entity_key("Google")
    rows = [
        {
            "id": "a",
            "bubble_hint": "news",
            "published_at": "2026-01-01",
            "source": "s",
            "url": "https://e/a",
        },
        {
            "id": "b",
            "bubble_hint": "finance",
            "published_at": "2026-01-02",
            "source": "t",
            "url": "https://e/b",
        },
        {
            "id": "c",
            "bubble_hint": "research",
            "published_at": "2026-01-03",
            "source": "u",
            "url": "https://e/c",
        },
    ]
    entities = {r["id"]: ["microsoft", "nvidia"] for r in rows}
    result = overlap(rows, entities)
    assert result["entities_in_all_3_bubbles"] == 2
    assert result["cross_bubble_item_pairs"] == 3
    changes = changed_candidates(
        rows,
        [
            "Microsoft released a version.",
            "Microsoft revised the version.",
            "Nvidia published results.",
        ],
        entities,
    )
    assert [v["entity"] for v in changes] == ["microsoft"]
    assert connected_clusters(
        [{"left": "a", "right": "b"}, {"left": "b", "right": "c"}]
    ) == [["a", "b", "c"]]
    assert np.isfinite(length_stats([1, 2])["p90"])


@pytest.mark.asyncio
async def test_api_html_cleaning_preserves_original_json():
    from omnistream.models import ApiMapping
    from omnistream.sources.api import fetch_api

    payload = {
        "items": [
            {
                "url": "https://example.org/paper",
                "body": "<h4>Results</h4><p>A readable abstract.</p><script>tracking()</script>",
            }
        ]
    }
    source = Source(
        id="papers",
        type="api",
        url="https://example.org/api",
        api_mapping=ApiMapping(items="$.items", body="$.body", url="$.url"),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        items = await fetch_api(source, client)
    assert items[0].text == "Results A readable abstract."
    assert json.loads(items[0].raw_content)["body"] == payload["items"][0]["body"]


@pytest.mark.asyncio
async def test_rss_discards_script_style_navigation():
    feed = b'<rss version="2.0"><channel><item><title>Body</title><link>https://example.org/a</link><description><![CDATA[<p>Actual article.</p><script>tracker()</script><style>.menu{}</style><nav>Menus</nav>]]></description></item></channel></rss>'
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=feed))
    ) as client:
        items = await fetch_rss(
            Source(id="s", type="rss", url="https://example.org/feed"), client
        )
    assert items[0].text == "Actual article."
    assert "Menus" in items[0].raw_content


def test_bge_duplicate_candidates_and_cache(tmp_path, monkeypatch):
    from omnistream.eval.real.verify import near_duplicates

    calls = []

    class Embedder:
        index_signature = "test:384"

        def __init__(self, **_):
            pass

        def embed_documents(self, segments):
            calls.append(segments)
            matrix = np.zeros((len(segments), 384), dtype=np.float32)
            matrix[:, 0] = 1
            return matrix

    monkeypatch.setattr("omnistream.embeddings.EmbeddingService", Embedder)
    rows = [
        {"id": "a", "sha256": "first", "source": "one"},
        {"id": "b", "sha256": "second", "source": "two"},
    ]
    result = near_duplicates(rows, ["A long story", "A syndicated story"], tmp_path)
    assert result["pairs"][0]["cross_source"] is True
    assert result["clusters"] == [["a", "b"]]
    assert (
        near_duplicates(rows, ["A long story", "A syndicated story"], tmp_path)
        == result
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_sec_columnar_adapter_filters_window_and_form():
    from omnistream.eval.real.collect import SECSubmissionHTTP

    payload = {
        "cik": "0001045810",
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "filingDate": ["2026-01-15", "2026-01-16", "2025-01-01"],
                "form": ["8-K", "4", "8-K"],
                "accessionNumber": [
                    "0001-26-000001",
                    "0001-26-000002",
                    "0001-25-000001",
                ],
                "primaryDocument": ["event.htm", "ownership.xml", "old.htm"],
            }
        },
    }

    class HTTP:
        async def get(self, url, **_):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    client = SECSubmissionHTTP(HTTP(), 3, "2026-01-01", "2026-01-31")
    response = await client.get("https://data.sec.gov/submissions/CIK0001045810.json")
    assert len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert item["date"] == "2026-01-15"
    assert (
        item["url"]
        == "https://www.sec.gov/Archives/edgar/data/1045810/000126000001/event.htm"
    )
    payload["filings"]["recent"]["form"].pop()
    with pytest.raises(ValueError, match="inconsistent"):
        await client.get("https://data.sec.gov/submissions/CIK0001045810.json")


def test_filing_hidden_metadata_removed():
    assert (
        clean_html(
            '<ix:header>CIK hidden</ix:header><p>Actual filing.</p><div style="display:none">Hidden metadata</div>'
        )
        == "Actual filing."
    )


@pytest.mark.asyncio
async def test_article_redirect_cannot_leave_opted_in_host(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            302, headers={"location": "https://unreviewed.example/article"}
        )

    async def sleep(_):
        return None

    http = PublicHTTP(tmp_path, transport=httpx.MockTransport(handler), sleep=sleep)
    with pytest.raises(PermissionError, match="opted-in"):
        await http.get("https://example.org/article", allowed_hosts=["example.org"])
    assert not any("unreviewed" in u for u in calls)
    await http.close()
