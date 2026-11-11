import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from omnistream.db import Repository
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import ApiMapping, Source

UI_DIR = Path(__file__).parent
SNIPPET_CHARS = 240


def static_files() -> StaticFiles:
    return StaticFiles(directory=UI_DIR / "static")


def _snippet(text_path: str | None) -> str:
    if not text_path or not Path(text_path).exists():
        return ""
    return Path(text_path).read_text(encoding="utf-8")[:SNIPPET_CHARS]


def _parse_headers(raw: str) -> dict[str, str]:
    out = {}
    for line in raw.splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip():
            out[name.strip()] = value.strip()
    return out


def build_router(repo: Repository, scheduler: IngestScheduler) -> APIRouter:
    templates = Jinja2Templates(directory=UI_DIR / "templates")
    router = APIRouter(prefix="/ui")

    async def sources_fragment(request: Request, error: str | None = None):
        return templates.TemplateResponse(
            request,
            "_sources_table.html",
            {"sources": await repo.list_sources(), "error": error},
        )

    async def unsorted_fragment(request: Request, error: str | None = None):
        items = await repo.list_items(status="unsorted")
        return templates.TemplateResponse(
            request,
            "_unsorted_list.html",
            {
                "items": items,
                "snippets": {i.id: _snippet(i.text_path) for i in items},
                "bubbles": await repo.list_bubbles(),
                "error": error,
            },
        )

    @router.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request):
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "title": "Sources",
                "sources": await repo.list_sources(),
                "bubbles": await repo.list_bubbles(),
                "error": None,
            },
        )

    @router.post("/sources", response_class=HTMLResponse)
    async def add_source(request: Request):
        form = await request.form()
        g = lambda k: str(form.get(k) or "").strip()
        try:
            mapping = None
            if g("type") == "api":
                if not (g("map_items") and g("map_body") and g("map_url")):
                    raise ValueError("api mapping needs items, body and url")
                mapping = ApiMapping(
                    items=g("map_items"),
                    title=g("map_title") or None,
                    body=g("map_body"),
                    date=g("map_date") or None,
                    url=g("map_url"),
                    headers=_parse_headers(g("map_headers")),
                )
            source = Source(
                id=uuid.uuid4().hex,
                type=g("type"),
                url=g("url"),
                credibility=float(g("credibility") or 0.5),
                poll_interval=int(g("poll_interval") or 900),
                bubble_ids=[str(v) for v in form.getlist("bubble_ids")],
                api_mapping=mapping,
            )
        except (ValidationError, ValueError) as exc:
            return await sources_fragment(
                request, f"Invalid source: {exc.__class__.__name__}"
            )
        known = {b.id for b in await repo.list_bubbles()}
        if missing := [b for b in source.bubble_ids if b not in known]:
            return await sources_fragment(request, f"Unknown bubbles: {missing}")
        await repo.upsert_source(source)
        scheduler.schedule_source(source)
        return await sources_fragment(request)

    @router.post("/sources/{source_id}/toggle", response_class=HTMLResponse)
    async def toggle_source(request: Request, source_id: str):
        source = await repo.get_source(source_id)
        if source is None:
            return await sources_fragment(request, "Unknown source")
        source = await repo.upsert_source(
            source.model_copy(update={"enabled": not source.enabled})
        )
        if source.enabled:
            scheduler.schedule_source(source)
        else:
            scheduler.unschedule_source(source.id)
        return await sources_fragment(request)

    @router.post("/sources/{source_id}/poll", response_class=HTMLResponse)
    async def poll_now(request: Request, source_id: str):
        if await repo.get_source(source_id) is None:
            return await sources_fragment(request, "Unknown source")
        await scheduler.poll_source(source_id)
        return await sources_fragment(request)

    @router.get("/unsorted", response_class=HTMLResponse)
    async def unsorted_page(request: Request):
        return templates.TemplateResponse(
            request,
            "unsorted.html",
            {
                "title": "Unsorted",
                "items": (items := await repo.list_items(status="unsorted")),
                "snippets": {i.id: _snippet(i.text_path) for i in items},
                "bubbles": await repo.list_bubbles(),
                "error": None,
            },
        )

    @router.post("/items/{item_id}/assign", response_class=HTMLResponse)
    async def assign(request: Request, item_id: str):
        ids = [str(v) for v in (await request.form()).getlist("bubble_ids")]
        known = {b.id for b in await repo.list_bubbles()}
        if not ids or any(i not in known for i in ids):
            return await unsorted_fragment(request, "Pick at least one existing bubble")
        try:
            await repo.assign_unsorted(item_id, ids)
        except (KeyError, ValueError) as exc:
            return await unsorted_fragment(request, str(exc))
        return await unsorted_fragment(request)

    return router
