import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from omnistream.config import Settings
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import ApiFeedConfig, Bubble, IngestResult, Source
from omnistream.sources import UnsupportedDocumentError
from omnistream.sources.documents import load_document
from omnistream.store.base import GraphStore


class BubbleIn(BaseModel):
    name: str
    description: str

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
    auto_route: bool = True
    api_config: ApiFeedConfig | None = None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def create_app(
    store: GraphStore,
    pipeline: IngestPipeline,
    scheduler: IngestScheduler,
    embedder,
    settings: Settings | None = None,
    lifespan=None,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="OmniStream ingestion", lifespan=lifespan)

    async def unknown_bubbles(ids: list[str]) -> list[str]:
        return [i for i in ids if await store.get_bubble(i) is None]

    @app.post("/bubbles", status_code=201, response_model=Bubble)
    async def create_bubble(body: BubbleIn) -> Bubble:
        existing = await store.list_bubbles()
        if body.name.casefold() in {b.name.strip().casefold() for b in existing}:
            raise HTTPException(409, f"bubble named {body.name!r} already exists")
        taken = {b.id for b in existing}
        base = _slug(body.name) or uuid.uuid4().hex
        bubble_id, n = base, 2
        while bubble_id in taken:
            bubble_id, n = f"{base}-{n}", n + 1
        vec = (await embedder.embed([f"{body.name}: {body.description}"]))[0]
        return await store.create_bubble(
            Bubble(
                id=bubble_id,
                name=body.name,
                description=body.description,
                description_embedding=vec,
                updated_at=datetime.now(UTC),
            )
        )

    @app.get("/bubbles", response_model=list[Bubble])
    async def list_bubbles() -> list[Bubble]:
        return await store.list_bubbles()

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
        await store.upsert_source(source)
        scheduler.schedule_source(source)
        return source

    @app.get("/sources", response_model=list[Source])
    async def list_sources() -> list[Source]:
        return await store.list_sources()

    @app.post("/sources/{source_id}/poll", response_model=list[IngestResult])
    async def poll_source(source_id: str) -> list[IngestResult]:
        if await store.get_source(source_id) is None:
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
            auto_route=ids is None,
        )
        # Parse before persisting the source so a bad file leaves no orphan.
        try:
            items = load_document(
                source.id,
                file.filename or "upload",
                data,
                settings.chunk_size,
                settings.chunk_overlap,
                ids,
            )
        except UnsupportedDocumentError as exc:
            raise HTTPException(415, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(422, f"could not parse document: {exc}") from exc
        await store.upsert_source(source)
        return await pipeline.process_many(items, source)

    return app


def main_app() -> FastAPI:
    """Build the app with real components. Heavy imports and connections are
    deferred so importing this module has no side effects."""
    from omnistream.embed import SentenceTransformerEmbedder
    from omnistream.graph.extract import Extractor
    from omnistream.graph.resolve import EntityResolver
    from omnistream.graph.write import FactWriter
    from omnistream.llm import build_llm_client
    from omnistream.router.route import Router
    from omnistream.store.neo4j_store import Neo4jStore

    settings = Settings()
    store = Neo4jStore(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password,
        settings.embed_dim,
    )
    embedder = SentenceTransformerEmbedder(settings.embed_model)
    llm = build_llm_client(settings)
    pipeline = IngestPipeline(
        store,
        Router(llm, settings.llm_model),
        Extractor(llm, settings.llm_model),
        EntityResolver(
            store,
            embedder,
            settings.embed_match_threshold,
            settings.fuzzy_match_threshold,
        ),
        FactWriter(store),
        grounding_threshold=settings.grounding_threshold,
    )
    http = httpx.AsyncClient()
    scheduler = IngestScheduler(store, pipeline, http)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.init_schema()
        await scheduler.start()
        try:
            yield
        finally:
            await scheduler.shutdown()
            await http.aclose()
            await store.close()

    return create_app(store, pipeline, scheduler, embedder, settings, lifespan)
