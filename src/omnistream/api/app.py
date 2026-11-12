import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.repository import bubble_half_life
from omnistream.ingest.intake import Intake
from omnistream.ingest.normalize import content_hash
from omnistream.ingest.pipeline import ItemProcessor
from omnistream.ingest.queue import WorkerPool
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import ApiMapping, Bubble, IngestResult, Source
from omnistream.router.bubbles import BubbleLifecycle
from omnistream.router.router import Router
from omnistream.sources import UnsupportedDocumentError
from omnistream.sources.documents import document_ext, load_document
from omnistream.sources.replay import SnapshotRecorder
from omnistream.ui.routes import build_router, static_files


class BubbleIn(BaseModel):
    name: str
    description: str
    half_life_days: int | None = Field(default=None, ge=1)
    backfill_days: int | None = Field(default=None, ge=1)

    @field_validator("name", "description")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class SourceIn(BaseModel):
    type: Literal["rss", "api"]
    url: str
    credibility: float = 0.5
    poll_interval: int = 900
    bubble_ids: list[str] = Field(default_factory=list)
    api_mapping: ApiMapping | None = None
    max_items_per_hour: int = 30
    store_full_text: bool = True
    enabled: bool = True


class SourcePatch(BaseModel):
    enabled: bool | None = None
    credibility: float | None = Field(default=None, ge=0.0, le=1.0)
    poll_interval: int | None = Field(default=None, ge=60)
    bubble_ids: list[str] | None = None
    max_items_per_hour: int | None = Field(default=None, ge=1)
    store_full_text: bool | None = None


class AssignIn(BaseModel):
    bubble_ids: list[str] = Field(min_length=1)


def _mask(source: Source) -> Source:
    """API responses never expose header values (they may carry credentials)."""
    if source.api_mapping and source.api_mapping.headers:
        masked = source.api_mapping.model_copy(
            update={"headers": {k: "***" for k in source.api_mapping.headers}}
        )
        return source.model_copy(update={"api_mapping": masked})
    return source


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def create_app(
    repo: Repository,
    scheduler: IngestScheduler,
    lifecycle: BubbleLifecycle,
    intake: Intake,
    settings: Settings | None = None,
    lifespan=None,
    runtime_factory=None,
    evaluator=None,
) -> FastAPI:
    settings = settings or Settings(_env_file=None)
    from omnistream.api.c6 import Services, install

    services = Services(
        repo, lifecycle, scheduler, settings, runtime_factory, evaluator
    )

    @asynccontextmanager
    async def full_lifespan(app):
        await services.load()
        await services.get_runtime()
        if lifespan:
            async with lifespan(app):
                try:
                    yield
                finally:
                    await services.close()
        else:
            try:
                yield
            finally:
                await services.close()

    app = FastAPI(title="OmniStream", lifespan=full_lifespan)
    install(app, services)

    async def unknown_bubbles(ids: list[str]) -> list[str]:
        return [i for i in ids if await repo.get_bubble(i) is None]

    @app.post("/bubbles", status_code=201, response_model=Bubble)
    async def create_bubble(body: BubbleIn) -> Bubble:
        existing = await repo.list_bubbles()
        if body.name.casefold() in {b.name.strip().casefold() for b in existing}:
            raise HTTPException(409, f"bubble named {body.name!r} already exists")
        taken = {b.id for b in existing}
        base = _slug(body.name) or uuid.uuid4().hex
        bubble_id, n = base, 2
        while bubble_id in taken:
            bubble_id, n = f"{base}-{n}", n + 1
        await repo.set_setting(
            f"c6.half_life_custom.{bubble_id}", body.half_life_days is not None
        )
        return await lifecycle.create(
            Bubble(
                id=bubble_id,
                name=body.name,
                description=body.description,
                half_life_days=body.half_life_days
                if body.half_life_days is not None
                else bubble_half_life(body.name, services.settings),
                updated_at=datetime.now(UTC),
            ),
            body.backfill_days,
        )

    @app.get("/bubbles/{bubble_id}")
    async def get_bubble(bubble_id: str) -> dict:
        bubble = await repo.get_bubble(bubble_id)
        if bubble is None:
            raise HTTPException(404, f"unknown bubble {bubble_id!r}")
        return {
            **bubble.model_dump(mode="json", exclude={"description_embedding"}),
            "counts": await lifecycle.counts(bubble_id),
        }

    @app.delete("/bubbles/{bubble_id}", status_code=204)
    async def delete_bubble(bubble_id: str, confirmed_counts: str | None = None):
        if await repo.get_bubble(bubble_id) is None:
            raise HTTPException(404, f"unknown bubble {bubble_id!r}")
        if confirmed_counts is None:
            raise HTTPException(
                409,
                {
                    "counts": await lifecycle.counts(bubble_id),
                    "message": "Confirm current counts",
                },
            )
        endpoint = next(
            r.endpoint
            for r in app.routes
            if getattr(r, "path", "") == "/bubbles"
            and "DELETE" in getattr(r, "methods", set())
        )
        await endpoint(bubble_id, confirmed_counts)

    @app.get("/bubbles", response_model=list[Bubble])
    async def list_bubbles() -> list[Bubble]:
        return await repo.list_bubbles()

    @app.post("/sources", status_code=201, response_model=Source)
    async def create_source(body: SourceIn) -> Source:
        try:
            source = Source(id=uuid.uuid4().hex, **body.model_dump())
        except ValidationError as exc:
            raise HTTPException(
                422, exc.errors(include_url=False, include_context=False)
            ) from exc
        if missing := await unknown_bubbles(source.bubble_ids):
            raise HTTPException(422, f"unknown bubble ids: {missing}")
        await repo.upsert_source(source)
        scheduler.schedule_source(source)
        return _mask(source)

    @app.get("/sources", response_model=list[Source])
    async def list_sources() -> list[Source]:
        return [_mask(s) for s in await repo.list_sources()]

    @app.patch("/sources/{source_id}", response_model=Source)
    async def patch_source(source_id: str, body: SourcePatch) -> Source:
        source = await repo.get_source(source_id)
        if source is None:
            raise HTTPException(404, f"unknown source {source_id!r}")
        changes = body.model_dump(exclude_none=True)
        if missing := await unknown_bubbles(changes.get("bubble_ids", [])):
            raise HTTPException(422, f"unknown bubble ids: {missing}")
        source = await repo.upsert_source(source.model_copy(update=changes))
        scheduler.schedule_source(source)
        if not source.enabled:
            scheduler.unschedule_source(source.id)
        return _mask(source)

    @app.get("/items")
    async def list_items(status: str | None = None) -> list[dict]:
        return [r.model_dump(mode="json") for r in await repo.list_items(status=status)]

    @app.post("/items/{item_id}/assign")
    async def assign_item(item_id: str, body: AssignIn) -> dict:
        if missing := await unknown_bubbles(body.bubble_ids):
            raise HTTPException(422, f"unknown bubble ids: {missing}")
        try:
            row = await repo.assign_unsorted(item_id, body.bubble_ids)
        except KeyError as exc:
            raise HTTPException(404, f"unknown item {item_id!r}") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return row.model_dump(mode="json")

    @app.get("/items/{item_id}/text", response_class=PlainTextResponse)
    async def item_text(item_id: str, request: Request):
        if request.query_params.getlist("span"):
            endpoint = next(
                r.endpoint
                for r in app.routes
                if getattr(r, "path", "") == "/ui/items/{item_id}/text"
            )
            return await endpoint(item_id, request)
        row = await repo.get_item(item_id)
        if row is None or not row.text_path or not Path(row.text_path).exists():
            raise HTTPException(404, "no stored text for this item")
        return await asyncio.to_thread(Path(row.text_path).read_text, encoding="utf-8")

    @app.post("/sources/{source_id}/poll", response_model=list[IngestResult])
    async def poll_source(source_id: str) -> list[IngestResult]:
        if await repo.get_source(source_id) is None:
            raise HTTPException(404, f"unknown source {source_id!r}")
        return await scheduler.poll_source(source_id)

    @app.post("/documents", response_model=list[IngestResult])
    async def upload_document(
        file: Annotated[UploadFile, File()],
        bubble_ids: Annotated[str | None, Form()] = None,
        credibility: Annotated[float, Form(ge=0.0, le=1.0)] = 0.5,
    ) -> list[IngestResult]:
        data = await file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, "file exceeds max upload size")
        ids = [i.strip() for i in (bubble_ids or "").split(",") if i.strip()] or None
        if ids and (missing := await unknown_bubbles(ids)):
            raise HTTPException(422, f"unknown bubble ids: {missing}")
        source = Source(
            id=uuid.uuid4().hex,
            type="document",
            url=None,
            credibility=credibility,
            bubble_ids=ids or [],
        )
        # Parse before persisting the source so a bad file leaves no orphan.
        try:
            items = load_document(
                source.id,
                file.filename or "upload",
                data,
                settings.document_episode_tokens,
                ids,
            )
        except UnsupportedDocumentError as exc:
            raise HTTPException(415, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(422, f"could not parse document: {exc}") from exc
        await repo.upsert_source(source)
        # One original per upload; every episode points at it (spec §4.2).
        ext = document_ext(file.filename or "upload")
        results: list[IngestResult] = []
        for i, item in enumerate(items):
            row = await intake.accept(item, source, data, ext, part=i)
            results.append(
                IngestResult(
                    status="queued" if row else "duplicate",
                    item_hash=row.id if row else content_hash(item.url, item.text),
                )
            )
        return results

    app.mount("/ui/static", static_files(), name="ui-static")
    app.include_router(build_router(repo, scheduler))
    from omnistream.ui.c6 import build_pages

    app.include_router(build_pages(services))
    return app


@dataclass
class Components:
    repo: Repository
    lifecycle: BubbleLifecycle
    intake: Intake
    scheduler: IngestScheduler
    pool: WorkerPool
    http: httpx.AsyncClient


async def build_components(
    settings: Settings,
    *,
    repo: Repository | None = None,
    embedder=None,
    llm=None,
    writer=None,
    ops=None,
    chunks=None,
    http: httpx.AsyncClient | None = None,
    aps=None,
) -> Components:
    """Wire the whole ingestion stack. Every heavy part is injectable so unit
    tests pass fakes; anything left None is built for real."""
    repo = repo or Repository.from_path(
        str(Path(settings.data_dir) / "omnistream.db"), settings=settings
    )
    from omnistream.api.c6 import SettingsIn

    overrides = await repo.all_settings()
    settings = type(settings).model_validate(
        {
            **settings.model_dump(),
            **{
                k: v
                for k, v in overrides.items()
                if k in SettingsIn.model_fields and k != "retrieval_mode"
            },
            "_env_file": None,
        }
    )
    if embedder is None:
        from omnistream.embed import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder(settings.embed_model)
    if llm is None:
        from omnistream.llm import build_llm_client

        llm = build_llm_client(settings)
    if writer is None:
        from omnistream.graph.writer import build_graph_writer

        writer = await build_graph_writer(settings, repo, embedder, llm)
    ops = ops or writer.ops
    chunks = chunks or writer.chunks
    router = Router(
        llm,
        settings.llm_model,
        embedder,
        settings.router_threshold,
        settings.router_top_k,
    )
    http = http or httpx.AsyncClient()
    intake = Intake(repo, settings.data_dir, settings.prefilter_min_chars)
    recorder = (
        SnapshotRecorder(settings.data_dir, settings.record_snapshot)
        if settings.record_snapshot
        else None
    )
    return Components(
        repo=repo,
        lifecycle=BubbleLifecycle(repo, embedder, router, ops, chunks),
        intake=intake,
        scheduler=IngestScheduler(repo, http, intake, scheduler=aps, recorder=recorder),
        pool=WorkerPool(
            repo,
            ItemProcessor(repo, router, writer).process_item,
            workers=settings.queue_workers,
        ),
        http=http,
    )


def app_from_components(c: Components, settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await c.scheduler.start()
        await c.pool.start()
        try:
            yield
        finally:
            await c.pool.stop()
            await c.scheduler.shutdown()
            await _app.state.c6.close_ingestion_clients()
            await c.http.aclose()
            await c.repo.close()

    return create_app(c.repo, c.scheduler, c.lifecycle, c.intake, settings, lifespan)
