import json
from datetime import UTC
from pathlib import Path

import httpx
import pytest
import respx
from fpdf import FPDF

from omnistream.models import ApiMapping, Source
from omnistream.sources import SourceFetchError, UnsupportedDocumentError
from omnistream.sources.api import fetch_api
from omnistream.sources.documents import chunk_text, load_document
from omnistream.sources.rss import fetch_rss

FIXTURES = Path(__file__).parent.parent / "fixtures"
FEED_URL = "https://gazette.example.com/feed.xml"
API_URL = "https://api.example.com/items"


def _rss_source() -> Source:
    return Source(id="gazette", type="rss", url=FEED_URL)


def _api_source(items_path: str = "$.data.articles") -> Source:
    return Source(
        id="api1",
        type="api",
        url=API_URL,
        api_mapping=ApiMapping(
            items=items_path,
            body="$.body",
            url="$.meta.url",
            title="$.headline",
            date="$.published",
            headers={"X-Key": "secret"},
        ),
    )


@pytest.fixture
def pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.cell(text="Page one talks about glaciers.")
    pdf.add_page()
    pdf.cell(text="Page two mentions the Zephyr protocol.")
    return bytes(pdf.output())


@respx.mock
async def test_rss_parses_entries_and_strips_html():
    xml = (FIXTURES / "feeds" / "news.xml").read_bytes()
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=xml))
    async with httpx.AsyncClient() as http:
        items = await fetch_rss(_rss_source(), http)
    assert len(items) == 3
    assert all(i.text for i in items)
    assert all("<p>" not in i.text for i in items)
    assert "voted 7 to 2 on Monday" in items[0].text.replace("  ", " ")
    assert items[0].source_id == "gazette"
    assert items[0].url == "https://gazette.example.com/ferry-terminal"


@respx.mock
async def test_rss_entry_without_link_gets_synthetic_url():
    xml = (FIXTURES / "feeds" / "news.xml").read_bytes()
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=xml))
    async with httpx.AsyncClient() as http:
        items = await fetch_rss(_rss_source(), http)
    assert items[1].url.startswith("rss://gazette/")


@respx.mock
async def test_rss_published_at_is_utc():
    xml = (FIXTURES / "feeds" / "news.xml").read_bytes()
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=xml))
    async with httpx.AsyncClient() as http:
        items = await fetch_rss(_rss_source(), http)
    p = items[0].published_at
    assert p is not None and p.tzinfo is UTC
    assert (p.year, p.month, p.day, p.hour, p.minute) == (2026, 11, 3, 9, 30)


@respx.mock
async def test_rss_broken_feed_raises_source_fetch_error():
    xml = (FIXTURES / "feeds" / "broken.xml").read_bytes()
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=xml))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceFetchError):
            await fetch_rss(_rss_source(), http)


@respx.mock
async def test_rss_http_404_raises_source_fetch_error():
    respx.get(FEED_URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceFetchError):
            await fetch_rss(_rss_source(), http)


@respx.mock
async def test_api_extracts_jsonpaths_and_skips_incomplete_items():
    payload = json.loads((FIXTURES / "api" / "items.json").read_text())
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as http:
        items = await fetch_api(_api_source(), http)
    assert route.calls.last.request.headers["X-Key"] == "secret"
    assert [i.url for i in items] == [
        "https://api.example.com/a1",
        "https://api.example.com/a3",
    ]
    assert items[0].title == "Solar farm opens"
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo is not None
    assert items[0].published_at.hour == 10
    assert items[1].published_at is None  # unparsable date


@respx.mock
async def test_api_non_list_items_path_raises():
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"articles": {}}})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceFetchError):
            await fetch_api(_api_source(), http)


@respx.mock
async def test_api_missing_items_path_raises():
    respx.get(API_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceFetchError):
            await fetch_api(_api_source(), http)


@respx.mock
async def test_api_wildcard_items_path():
    payload = json.loads((FIXTURES / "api" / "items.json").read_text())
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as http:
        items = await fetch_api(_api_source(items_path="$.data.articles[*]"), http)
    assert len(items) == 2


@respx.mock
async def test_api_invalid_json_raises():
    respx.get(API_URL).mock(return_value=httpx.Response(200, content=b"<html>"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceFetchError):
            await fetch_api(_api_source(), http)


@respx.mock
async def test_api_root_list_with_empty_items_path():
    payload = [{"body": "hello there", "meta": {"url": "https://x.example.com/1"}}]
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as http:
        items = await fetch_api(_api_source(items_path="$"), http)
    assert len(items) == 1 and items[0].title == ""


def _long_text(n: int = 5000) -> str:
    paras = []
    i = 0
    while sum(len(p) + 2 for p in paras) < n:
        paras.append(" ".join(f"word{i + j}" for j in range(40)))
        i += 40
    return "\n\n".join(paras)[:n]


def test_chunk_text_respects_size_and_overlap():
    text = _long_text(5000)
    assert len(text) == 5000
    chunks = chunk_text(text, size=2000, overlap=200)
    assert len(chunks) == 3
    assert all(len(c) <= 2000 for c in chunks)
    assert chunks[1][:50] in chunks[0][-400:]
    assert chunks[-1].endswith(text.rstrip()[-20:])


def test_chunk_text_is_deterministic():
    text = _long_text(5000)
    assert chunk_text(text, 2000, 200) == chunk_text(text, 2000, 200)


def test_chunk_text_short_text_single_chunk():
    assert chunk_text("hello world", 2000, 200) == ["hello world"]


def test_chunk_text_empty_returns_empty():
    assert chunk_text("  \n\n ", 2000, 200) == []


def test_chunk_text_hard_splits_unbroken_text():
    chunks = chunk_text("x" * 5000, size=1000, overlap=100)
    assert all(len(c) <= 1000 for c in chunks)
    assert len(chunks) >= 5
    assert "".join(c for c in chunks).count("x") >= 5000


def test_load_pdf_extracts_text(pdf_bytes):
    items = load_document(
        "doc1", "report.pdf", pdf_bytes, size=2000, overlap=200, bubble_ids=["b1"]
    )
    assert items
    assert "Zephyr protocol" in " ".join(i.text for i in items)
    assert items[0].source_id == "doc1"
    assert items[0].bubble_ids_override == ["b1"]
    assert items[0].title == f"report.pdf (part 1/{len(items)})"
    assert items[0].url.startswith("doc://") and items[0].url.endswith("#chunk-0")


def test_load_pdf_uppercase_extension(pdf_bytes):
    assert load_document("d", "REPORT.PDF", pdf_bytes, 2000, 200, None)


def test_load_pdf_without_text_returns_empty():
    pdf = FPDF()
    pdf.add_page()
    assert load_document("d", "scan.pdf", bytes(pdf.output()), 2000, 200, None) == []


def test_load_txt_replaces_invalid_utf8():
    items = load_document("d", "a.txt", b"caf\xe9 au lait", 2000, 200, None)
    assert "au lait" in items[0].text


def test_same_file_bytes_same_urls_regardless_of_filename():
    data = b"Some shared content. " * 300
    a = load_document("d", "one.txt", data, 1000, 100, None)
    b = load_document("d", "two.md", data, 1000, 100, None)
    assert len(a) > 1
    assert [i.url for i in a] == [i.url for i in b]


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedDocumentError):
        load_document("d", "file.docx", b"x", 2000, 200, None)
