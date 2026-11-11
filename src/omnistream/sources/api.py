import json
from datetime import UTC, datetime
from typing import Any

import httpx
from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as parse_jsonpath

from omnistream.models import RawItem, Source
from omnistream.sources import SourceFetchError


def _find(data: Any, path: str) -> list[Any]:
    try:
        return [m.value for m in parse_jsonpath(path).find(data)]
    except JsonPathParserError as e:
        raise SourceFetchError(f"invalid JSONPath {path!r}: {e}") from e


def _text_value(item: Any, path: str) -> str | None:
    found = _find(item, path)
    if not found or found[0] is None:
        return None
    text = str(found[0]).strip()
    return text or None


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def fetch_api(source: Source, http: httpx.AsyncClient) -> list[RawItem]:
    assert source.url is not None and source.api_mapping is not None
    cfg = source.api_mapping
    response = await http.get(source.url, headers=cfg.headers, timeout=20.0)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise SourceFetchError(f"{source.url}: HTTP {e.response.status_code}") from e
    try:
        payload = response.json()
    except ValueError as e:
        raise SourceFetchError(f"{source.url}: invalid JSON") from e

    # `$.data.items` resolves to one list; `$.data.items[*]` to many entries.
    matches = _find(payload, cfg.items)
    if len(matches) == 1 and isinstance(matches[0], list):
        entries = matches[0]
    elif len(matches) > 1:
        entries = matches
    else:
        raise SourceFetchError(
            f"{source.url}: items path {cfg.items!r} did not resolve to a list"
        )

    items: list[RawItem] = []
    for entry in entries:
        text = _text_value(entry, cfg.body)
        url = _text_value(entry, cfg.url)
        if text is None or url is None:
            continue
        title = (_text_value(entry, cfg.title) if cfg.title else None) or ""
        published = None
        if cfg.date:
            found = _find(entry, cfg.date)
            published = _parse_date(found[0] if found else None)
        items.append(
            RawItem(
                source_id=source.id,
                url=url,
                title=title,
                text=text,
                published_at=published,
                raw_content=json.dumps(entry, ensure_ascii=False, default=str),
                raw_ext="json",
            )
        )
    return items
