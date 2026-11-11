import io
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
from omnistream.sources.documents import (
    estimate_tokens,
    load_document,
    split_episodes,
)
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


def _words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_split_episodes_short_text_single_episode():
    assert split_episodes("hello world", 1500) == ["hello world"]


def test_split_episodes_empty_returns_empty():
    assert split_episodes("  \n\n ", 1500) == []


def test_split_episodes_cuts_at_headings():
    text = (
        f"# One\n\n{_words(600)}\n\n# Two\n\n{_words(600)}\n\n# Three\n\n{_words(600)}"
    )
    eps = split_episodes(text, 1000)  # ~780 tokens per section: one per episode
    assert len(eps) == 3
    assert [e.split("\n", 1)[0] for e in eps] == ["# One", "# Two", "# Three"]
    assert all(estimate_tokens(e) <= 1000 for e in eps)


def test_split_episodes_packs_small_sections_together():
    text = "# A\n\nalpha beta\n\n# B\n\ngamma delta"
    assert len(split_episodes(text, 1500)) == 1


def test_split_episodes_oversize_section_cuts_at_paragraphs():
    paras = [_words(300, f"p{i}x") for i in range(6)]
    eps = split_episodes("# Big\n\n" + "\n\n".join(paras), 1000)
    assert len(eps) > 1
    assert all(estimate_tokens(e) <= 1000 for e in eps)
    assert "p5x299" in eps[-1]


def test_split_episodes_hard_splits_oversize_paragraph():
    eps = split_episodes(_words(3000), 1500)
    assert len(eps) >= 3
    assert all(estimate_tokens(e) <= 1500 for e in eps)
    assert sum(len(e.split()) for e in eps) == 3000


def test_load_pdf_extracts_text(pdf_bytes):
    items = load_document("doc1", "report.pdf", pdf_bytes, 1500, ["b1"])
    assert items
    assert "Zephyr protocol" in " ".join(i.text for i in items)
    assert items[0].source_id == "doc1"
    assert items[0].bubble_ids_override == ["b1"]
    assert items[0].title == f"report.pdf (part 1/{len(items)})"
    assert items[0].url.startswith("doc://") and items[0].url.endswith("#part-0")
    assert items[0].raw_ext == "pdf"


def test_load_pdf_uppercase_extension(pdf_bytes):
    assert load_document("d", "REPORT.PDF", pdf_bytes, 1500, None)


def test_load_pdf_without_text_returns_empty():
    pdf = FPDF()
    pdf.add_page()
    assert load_document("d", "scan.pdf", bytes(pdf.output()), 1500, None) == []


def test_load_txt_replaces_invalid_utf8():
    items = load_document("d", "a.txt", b"caf\xe9 au lait", 1500, None)
    assert "au lait" in items[0].text


def test_load_md_keeps_headings():
    items = load_document("d", "a.md", b"# Title\n\nbody text", 1500, None)
    assert items[0].text.startswith("# Title")
    assert items[0].raw_ext == "md"


def _docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Overview", level=1)
    doc.add_paragraph(_words(500, "ov"))
    doc.add_heading("Details", level=2)
    doc.add_paragraph(_words(500, "de"))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_load_docx_parses_and_splits_at_headings():
    items = load_document("d", "spec.docx", _docx_bytes(), 800, None)
    assert len(items) == 2
    assert items[0].text.startswith("# Overview") and "ov499" in items[0].text
    assert items[1].text.startswith("## Details") and "de499" in items[1].text
    assert items[0].raw_ext == "docx"


def test_same_file_bytes_same_urls_regardless_of_filename():
    data = (_words(400) + "\n\n") * 6
    a = load_document("d", "one.txt", data.encode(), 800, None)
    b = load_document("d", "two.md", data.encode(), 800, None)
    assert len(a) > 1
    assert [i.url for i in a] == [i.url for i in b]


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedDocumentError):
        load_document("d", "file.exe", b"x", 1500, None)
