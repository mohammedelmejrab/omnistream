"""Offline policy fixtures for real-v2; no network or environment-file access."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from omnistream.eval.real.collect import PublicHTTP, SECSubmissionHTTP
from omnistream.eval.real.v2 import (
    arxiv_query,
    body_date_hint,
    documented_api_allows,
    exhibit_links,
    expand_exhibits,
    validate_changed_facts,
)


def test_documented_api_endpoint_scope():
    policy = {
        "access": "documented_api",
        "terms_url": "https://info.arxiv.org/help/api/tou.html",
    }
    assert documented_api_allows(
        policy, "https://export.arxiv.org/api/query?search_query=cat:cs.AI"
    )
    for url in [
        "https://export.arxiv.org/abs/123",
        "http://export.arxiv.org/api/query",
        "https://evil.org/api/query",
        "https://export.arxiv.org/api/query/else",
    ]:
        assert not documented_api_allows(policy, url)
    assert not documented_api_allows(
        dict(policy, terms_url=""), "https://export.arxiv.org/api/query"
    )


@pytest.mark.asyncio
async def test_documented_api_skips_robots_only_at_endpoint(tmp_path):
    calls, waits = [], []
    now = [0.0]

    async def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /"
            if request.url.path == "/robots.txt"
            else "ok",
        )

    client = PublicHTTP(
        tmp_path,
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        clock=lambda: now[0],
    )
    client.access_policy = {
        "access": "documented_api",
        "terms_url": "https://info.arxiv.org/help/api/tou.html",
        "delay_seconds": 3,
    }
    try:
        await client.get("https://export.arxiv.org/api/query?a=1")
        await client.get("https://export.arxiv.org/api/query?a=2")
        assert calls == ["/api/query", "/api/query"] and waits == [3]
        with pytest.raises(PermissionError):
            await client.get("https://export.arxiv.org/help")
        assert calls[-1] == "/robots.txt"
    finally:
        await client.close()


def test_arxiv_query_builder():
    query = parse_qs(
        urlsplit(arxiv_query("2026-09-18", "2026-11-13", names=["AMD", "OpenAI"])).query
    )
    assert "submittedDate:[202609180000 TO 202611132359]" in query["search_query"][0]
    assert "cat:cs.AR" in query["search_query"][0]
    assert 'all:"AMD"' in query["search_query"][0]
    with pytest.raises(ValueError):
        arxiv_query("2026-11-13", "2026-09-18")
    with pytest.raises(ValueError):
        arxiv_query("2026-09-18", "2026-11-13", names=['AMD" OR all:x'])


@pytest.mark.asyncio
async def test_exhibits_are_separate_linked_documents():
    from omnistream.models import RawItem

    url = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/main.htm"
    html = '<table><tr><td>1</td><td><a href="ex99.htm">Press release</a></td><td>EX-99.1</td></tr><tr><td><a href="other.htm">Other</a></td><td>EX-10.1</td></tr><tr><td><a href="https://evil.org/a.htm">Bad</a></td><td>EX-99.2</td></tr></table>'
    assert exhibit_links(html, url) == [url.replace("main.htm", "ex99.htm")]

    class Client:
        async def get(self, index):
            assert index.endswith("/0000000001-26-000001-index.html")
            return httpx.Response(200, text=html, request=httpx.Request("GET", index))

    item = RawItem(
        source_id="s",
        url=url,
        text="filing",
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    errors = []
    result = await expand_exhibits([item], Client(), errors)
    assert len(result) == 2 and not errors
    assert result[1].published_at == item.published_at
    assert result[1].url.rsplit("/", 1)[0] == item.url.rsplit("/", 1)[0]


@pytest.mark.asyncio
async def test_sec_submissions_include_foreign_6k(tmp_path):
    payload = {
        "name": "Issuer",
        "cik": 1,
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-26-000001"],
                "filingDate": ["2026-10-01"],
                "form": ["6-K"],
                "primaryDocument": ["main.htm"],
            }
        },
    }

    class Client:
        async def get(self, url, **kwargs):
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    adapter = SECSubmissionHTTP(Client(), 3, "2026-09-18", "2026-11-13")
    response = await adapter.get("https://data.sec.gov/submissions/CIK0000000001.json")
    assert len(response.json()["items"]) == 1
    assert "6-K" in response.json()["items"][0]["title"]


def test_changed_fact_reference_quote_and_date_validation():
    rows = [
        {"id": "a", "published_at": "2026-10-01T00:00:00+00:00"},
        {"id": "b", "published_at": "2026-11-01T00:00:00+00:00"},
    ]
    texts = {"a": "Revenue was 10 billion.", "b": "Revenue was 12 billion."}
    fact = {
        "entity": "Issuer",
        "attribute": "quarterly revenue",
        "note": "Later quarterly result supersedes the previous report.",
        "verified": True,
        "old": {
            "item_id": "a",
            "date": "2026-10-01",
            "value": "10 billion",
            "quote": "Revenue was 10 billion.",
        },
        "new": {
            "item_id": "b",
            "date": "2026-11-01",
            "value": "12 billion",
            "quote": "Revenue was 12 billion.",
        },
    }
    assert validate_changed_facts([fact], rows, texts) == []
    fact["new"]["quote"] = "invented quotation"
    assert validate_changed_facts([fact], rows, texts)
    fact["new"]["item_id"] = "missing"
    assert validate_changed_facts([fact], rows, texts)


def test_event_date_is_displayed_prefix_only():
    assert body_date_hint("July 24, 2025 Welcome to our blog") == "2025-07-24"
    assert body_date_hint("Today we recall July 24, 2025 as a milestone") is None


def test_url_dates_and_balanced_selection():
    from omnistream.eval.real.v2 import select_balanced, url_date_hint

    assert url_date_hint("https://www.nist.gov/news/2026/06/old-story") == "2026-06-30"
    assert url_date_hint("https://example.org/2026/10/03/story") == "2026-10-03"
    rows = [
        {
            "id": str(i),
            "source": "a" if i < 8 else "b",
            "bubble_hint": "news",
            "published_at": "2026-10-01",
        }
        for i in range(10)
    ]
    selected = select_balanced(rows, {"news": 4})
    assert len(selected) == 4 and sum(r["source"] == "b" for r in selected) == 2
    assert selected == select_balanced(list(reversed(rows)), {"news": 4})


def test_arxiv_queries_do_not_evade_source_cap():
    from omnistream.eval.real.verify_v2 import requirements

    rows = [{"source": f"arxiv-{i % 2}", "bubble_hint": "research"} for i in range(100)]
    config = {
        "sources": [{"id": f"arxiv-{i}", "source_group": "arxiv"} for i in range(2)]
    }
    failures = requirements(rows, config, complete_share=1, integrity=[])
    assert any("arxiv has 100/100" in failure for failure in failures)


def test_missing_llm_cache_is_explicit(tmp_path):
    from omnistream.eval.real.entities_v2 import cached_entities

    entities, info = cached_entities([{"id": "absent", "sha256": "hash"}], tmp_path)
    assert entities == {"absent": []}
    assert info["missing_items"] == ["absent"] and info["calls"] == 0


def test_ixbrl_exhibit_links_unwrap_only_same_accession():
    base = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/"
    html = '<table><tr><td><a href="/ix?doc=/Archives/edgar/data/1/000000000126000001/ex99.htm">Release</a></td><td>EX-99.1</td></tr><tr><td><a href="/ix?doc=/Archives/edgar/data/2/other/evil.htm">Other accession</a></td><td>EX-99.2</td></tr></table>'
    assert exhibit_links(html, base + "main.htm") == [base + "ex99.htm"]
