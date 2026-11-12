"""C6 query, settings, graph and evaluation HTTP surfaces."""

import asyncio
import inspect
import logging
import os
from html import escape
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    mode: Literal["classic", "graphiti", "own"] | None = None
    subagents: bool | None = None
    pin: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retrieval_mode: Literal["classic", "graphiti", "own"] = "own"
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1", pattern=r"^https?://[^\s@]+$"
    )
    llm_model: str = ""
    judge_model: str = ""
    half_life_news_days: int = Field(default=3, ge=1)
    half_life_finance_days: int = Field(default=30, ge=1)
    half_life_research_days: int = Field(default=365, ge=1)
    router_threshold: float = Field(default=0.5, ge=0, le=1)

    @field_validator("llm_model", "llm_base_url")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class EvalIn(BaseModel):
    rows: list[str] | None = None
    snapshot: str = Field(min_length=1, pattern=r"^[\w.-]+$")


async def invoke(fn, *args, **kwargs):
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    result = await asyncio.to_thread(fn, *args, **kwargs)
    return await result if inspect.isawaitable(result) else result


class Services:
    def __init__(
        self, repo, lifecycle, scheduler, settings, runtime_factory=None, evaluator=None
    ):
        self.repo, self.lifecycle, self.scheduler = repo, lifecycle, scheduler
        self.settings = settings
        self.runtime_factory = runtime_factory
        self.evaluator = evaluator
        self.startup_settings = settings
        self.closing = False
        self.runtime = None
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.task_runs = {}
        self.active_queries = set()
        self.provider_restart_required = False
        self.default_mode = "own"
        self.retired_ingestion_clients = []

    async def load(self):
        persisted = await self.repo.all_settings()
        allowed = SettingsIn.model_fields
        values = {k: v for k, v in persisted.items() if k in allowed}
        self.default_mode = values.pop("retrieval_mode", "own")
        self.settings = type(self.settings).model_validate(
            {**self.settings.model_dump(), **values, "_env_file": None}
        )

        self.startup_settings = self.settings

    async def get_runtime(self):
        async with self.lock:
            if self.runtime is None:
                from omnistream.retrieval.runtime import build_query_runtime

                self.runtime = await invoke(
                    self.runtime_factory or build_query_runtime,
                    self.startup_settings,
                    self.repo,
                )
            return self.runtime

    async def query(self, body):
        if not body.question.strip():
            raise HTTPException(422, "Question must not be blank")
        known = {b.id for b in await self.repo.list_bubbles()}
        if set(body.pin + body.exclude) - known or set(body.pin) & set(body.exclude):
            raise HTTPException(422, "Unknown or conflicting bubble selection")
        runtime = await self.get_runtime()
        async with self.lock:
            task = asyncio.create_task(
                invoke(
                    runtime.answer,
                    body.question,
                    mode=body.mode or self.default_mode,
                    subagents=body.subagents,
                    pin=body.pin,
                    exclude=body.exclude,
                )
            )
            self.active_queries.add(task)
        try:
            return jsonable_encoder(await task)
        finally:
            self.active_queries.discard(task)

    async def public_settings(self):
        values = {
            k: getattr(self.settings, k)
            for k in SettingsIn.model_fields
            if k != "retrieval_mode"
        }
        return {"retrieval_mode": self.default_mode, **values}

    async def save_settings(self, body):
        values = body.model_dump(exclude_unset=True)
        async with self.lock:
            old = self.settings
            changes = {k: v for k, v in values.items() if k != "retrieval_mode"}
            validated = type(old).model_validate(
                {**old.model_dump(), **changes, "_env_file": None}
            )
            for key, value in values.items():
                await self.repo.set_setting(key, value)
            self.default_mode = values.get("retrieval_mode", self.default_mode)
            provider_keys = {"llm_model", "llm_base_url", "judge_model"}
            self.provider_restart_required |= any(
                getattr(validated, k) != getattr(old, k) for k in provider_keys
            )
            # Provider clients remain a coherent set until process restart.
            self.settings = validated
            self.lifecycle._router._threshold = validated.router_threshold
            persisted = await self.repo.all_settings()
            for bubble in await self.repo.list_bubbles():
                key = f"half_life_{bubble.name.casefold()}_days"
                marker = f"c6.half_life_custom.{bubble.id}"
                if (
                    key in changes
                    and changes[key] != getattr(old, key)
                    and not persisted.get(
                        marker, bubble.half_life_days != getattr(old, key)
                    )
                ):
                    await self.repo.update_bubble(
                        bubble.id, half_life_days=changes[key]
                    )
        return await self.public_settings()

    async def graph(self, bubble_id):
        if await self.repo.get_bubble(bubble_id) is None:
            raise HTTPException(404, "Unknown bubble")
        return await self.lifecycle._ops.bubble_graph(bubble_id)

    async def bubble_map(self):
        return {
            "nodes": [
                {"id": b.id, "label": b.name} for b in await self.repo.list_bubbles()
            ],
            "edges": await self.lifecycle._ops.bubble_map(),
        }

    async def evaluate(self, body, run_id):
        try:
            if self.evaluator is None:
                from omnistream.eval import run_evaluation

                evaluator = run_evaluation
            else:
                evaluator = self.evaluator
            kwargs = {"rows": body.rows, "snapshot": body.snapshot}
            if "run_id" in inspect.signature(evaluator).parameters:
                kwargs["run_id"] = run_id
            await self.repo.update_eval_run(run_id, status="running")
            repository = self.repo
            if "run_id" not in kwargs:
                # Older evaluators create their own record. Bind that creation
                # to the API's queued record without changing the eval package.
                class BoundRepository:
                    def __getattr__(bound, name):
                        return getattr(repository, name)

                    async def create_eval_run(bound, **values):
                        snapshot = values.pop("snapshot")
                        rows = values.pop("rows")
                        return await repository.update_eval_run(
                            run_id,
                            snapshot=snapshot,
                            rows=rows,
                            config=",".join(rows),
                            **values,
                        )

                repository_arg = BoundRepository()
            else:
                repository_arg = repository
            result = await invoke(
                evaluator, self.startup_settings, repository_arg, **kwargs
            )
            if self.closing:
                return result
            run = await self.repo.get_eval_run(run_id)
            if run.status in {"queued", "running"}:
                await self.repo.update_eval_run(run_id, status="completed")
            return result
        except asyncio.CancelledError:
            if not self.closing:
                await self.repo.update_eval_run(run_id, status="cancelled")
            raise
        except Exception:
            if self.closing:
                return None
            logging.getLogger(__name__).exception("Evaluation run %s failed", run_id)
            await self.repo.update_eval_run(run_id, status="failed")

    async def close_ingestion_clients(self):
        current = getattr(
            getattr(self.lifecycle._router, "_llm", None), "_client", None
        )
        resources = [*self.retired_ingestion_clients, current]
        self.retired_ingestion_clients.clear()
        seen = set()
        for resource in resources:
            if resource is not None and id(resource) not in seen:
                seen.add(id(resource))
                await invoke(resource.close)

    async def close(self):
        self.closing = True
        if self.tasks:
            tasks = tuple(self.tasks)
            run_ids = {task: self.task_runs[task] for task in tasks}
            for task in tasks:
                task.cancel()
            for run_id in run_ids.values():
                await self.repo.update_eval_run(run_id, status="cancelled")
            await asyncio.wait(tasks, timeout=2)
        if self.runtime is not None:
            await invoke(self.runtime.close)


def install(app, services):
    app.state.c6 = services
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    allowed_hosts.update(
        host.strip().casefold().strip("[]")
        for host in os.environ.get("OMNI_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )

    @app.middleware("http")
    async def same_origin(request, call_next):
        try:
            authority = urlsplit("//" + request.headers.get("host", ""))
            host = authority.hostname
            if (
                authority.username is not None
                or authority.path
                or authority.query
                or authority.fragment
            ):
                host = None
            _ = authority.port  # Validate port syntax and range too.
        except ValueError:
            host = None
        if host is None or host.casefold() not in allowed_hosts:
            allowed = ", ".join(
                ["localhost", "127.0.0.1", "[::1]"]
                + sorted(allowed_hosts - {"localhost", "127.0.0.1", "::1"})
            )
            return JSONResponse(
                {
                    "detail": f"Invalid host {request.headers.get('host', '')!r}. "
                    f"Allowed: {allowed}. Set OMNI_ALLOWED_HOSTS=host1,host2 "
                    "to allow more (e.g. when serving on 0.0.0.0)."
                },
                status_code=400,
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected = urlsplit(str(request.base_url))
            try:
                supplied = urlsplit(origin) if origin else None
            except ValueError:
                return JSONResponse({"detail": "Invalid origin"}, status_code=403)
            if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"} or (
                supplied
                and (supplied.scheme, supplied.netloc)
                != (expected.scheme, expected.netloc)
            ):
                return JSONResponse(
                    {"detail": "Cross-origin request rejected"}, status_code=403
                )
            content_type = request.headers.get("content-type", "").split(";")[0].lower()
            if (
                not request.url.path.startswith("/ui/")
                and request.url.path != "/documents"
                and (
                    content_type
                    or request.headers.get("transfer-encoding")
                    or request.url.path
                    in {"/query", "/settings", "/eval/runs", "/settings/test"}
                )
                and content_type != "application/json"
            ):
                return JSONResponse(
                    {"detail": "application/json required"}, status_code=415
                )
        return await call_next(request)

    @app.post("/query")
    async def query(body: QueryIn):
        return await services.query(body)

    @app.get("/settings")
    async def get_settings():
        return JSONResponse(
            await services.public_settings(),
            headers={
                "X-Settings-Applies": "provider changes apply to queries, ingestion and evaluations after restart",
                "X-Settings-Restart-Required": str(
                    services.provider_restart_required
                ).lower(),
            },
        )

    @app.put("/settings")
    async def put_settings(body: SettingsIn):
        result = await services.save_settings(body)
        return JSONResponse(
            result,
            headers={
                "X-Settings-Applies": "provider changes apply to queries, ingestion and evaluations after restart"
            },
        )

    @app.post("/settings/test")
    async def connection_test():
        from omnistream.llm import build_llm_client

        client = build_llm_client(services.settings)
        try:
            return await client.connection_test(services.settings.llm_model)
        finally:
            await client._client.close()

    @app.get("/bubbles/map")
    async def bubble_map():
        return await services.bubble_map()

    @app.get("/bubbles/{bubble_id}/graph")
    async def bubble_graph(bubble_id: str):
        return await services.graph(bubble_id)

    @app.get("/bubbles/{bubble_id}/counts")
    async def counts(bubble_id: str):
        if await services.repo.get_bubble(bubble_id) is None:
            raise HTTPException(404, "Unknown bubble")
        return await services.lifecycle.counts(bubble_id)

    @app.delete("/bubbles", status_code=204)
    async def delete_bubble(id: str, confirmed_counts: str):
        import json

        if await services.repo.get_bubble(id) is None:
            raise HTTPException(404, "Unknown bubble")
        counts = await services.lifecycle.counts(id)
        try:
            confirmed = json.loads(confirmed_counts)
        except ValueError as exc:
            raise HTTPException(422, "Invalid counts confirmation") from exc
        if confirmed != counts:
            raise HTTPException(
                409,
                {"counts": counts, "message": "Review current counts before deleting"},
            )
        await services.lifecycle.delete(id)
        for source in await services.repo.list_sources():
            if not source.enabled:
                services.scheduler.unschedule_source(source.id)

    @app.get("/eval/runs")
    async def runs():
        return jsonable_encoder(await services.repo.list_eval_runs())

    @app.post("/eval/runs", status_code=202)
    async def start_eval(body: EvalIn):
        run = await services.repo.create_eval_run(
            snapshot=body.snapshot, rows=body.rows or [], status="queued"
        )
        task = asyncio.create_task(services.evaluate(body, run.id))
        services.task_runs[task] = run.id
        services.tasks.add(task)

        def finished(task):
            services.tasks.discard(task)
            services.task_runs.pop(task, None)
            if not task.cancelled():
                task.exception()  # consume failures; the evaluation records failed status

        task.add_done_callback(finished)
        return {"status": "queued", "snapshot": body.snapshot, "run_id": run.id}

    @app.get("/eval/runs/{run_id}")
    async def run_detail(run_id: int):
        run = await services.repo.get_eval_run(run_id)
        if run is None:
            raise HTTPException(404, "Unknown evaluation run")
        return jsonable_encoder(run)

    @app.get("/eval/runs/{run_id}/csv")
    async def run_csv(run_id: int):
        run = await services.repo.get_eval_run(run_id)
        if run is None:
            raise HTTPException(404, "Unknown evaluation run")
        path = getattr(run, "csv_path", None)
        if not path or not Path(path).is_file():
            raise HTTPException(404, "CSV not available")
        return FileResponse(
            path, media_type="text/csv", filename=f"evaluation-{run_id}.csv"
        )

    @app.get("/ui/items/{item_id}/text", response_class=HTMLResponse)
    async def original(item_id: str, request: Request):
        row = await services.repo.get_item(item_id)
        if row is None or not row.text_path or not Path(row.text_path).is_file():
            raise HTTPException(404, "No stored text")
        text = await asyncio.to_thread(Path(row.text_path).read_text, encoding="utf-8")
        # Escape each segment before inserting markup, retaining original offsets.
        spans = []
        for raw in request.query_params.getlist("span"):
            try:
                a, b = map(int, raw.split(":"))
            except ValueError:
                raise HTTPException(422, "Span must be start:end") from None
            if not 0 <= a < b <= len(text):
                raise HTTPException(422, "Span outside stored text")
            spans.append((a, b))
        from omnistream.retrieval.citations import _merge_spans

        parts, cursor = [], 0
        for a, b in _merge_spans(spans):
            parts.extend(
                [escape(text[cursor:a]), "<mark>", escape(text[a:b]), "</mark>"]
            )
            cursor = b
        parts.append(escape(text[cursor:]))
        return HTMLResponse(
            '<!doctype html><meta charset="utf-8"><title>Stored original</title><pre style="white-space:pre-wrap">'
            + "".join(parts)
            + "</pre>"
        )
