"""JSON API for the React app (spec section 12), mounted under ``/api``.

``UIServices`` owns the run lifecycle: it starts each answer as a background
task, records its steps through ``ui_trace``, publishes SSE events, and handles
cancel, delete-during-run, the stale-run sweep at startup and 30-day retention.
The existing ``/query`` and ``/ui/...`` surfaces are untouched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import openai
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator

from omnistream.api.c6 import Services
from omnistream.api.ui_trace import (
    PipelineTrace,
    RunBus,
    RunRecorder,
    run_payload,
    step_payload,
    utc,
)
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ChatRow, MessageRow, RunRow
from omnistream.qa import answer_question

logger = logging.getLogger(__name__)

PROVIDER_KEY_SETTING = "provider.api_key"
INTERRUPTED_MESSAGE = "Interrupted when OmniStream restarted"
STOPPED_MESSAGE = "Stopped"
RETENTION = timedelta(days=30)


def trace_expired(row: RunRow, now: datetime | None = None) -> bool:
    """A run's trace is gone once it is older than the retention window (spec 10.1)."""
    started = row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=UTC)
    return started < (now or datetime.now(UTC)) - RETENTION
PURGE_INTERVAL_SECONDS = 3600
SSE_KEEPALIVE_SECONDS = 15
GRAPH_FETCH_LIMIT = 1000
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
BASE_URL_PATTERN = r"^https?://[^\s@]+$"
NO_STORE = {"Cache-Control": "no-store"}


class EmptyAnswer(Exception):
    """The provider answered with no text. Shown as a failed run with Retry."""


# ----------------------------------------------------------------- schemas


class ChatCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    mode: Literal["normal", "agentic"] = "normal"
    bubble_ids: list[str] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ChatOut(BaseModel):
    id: str
    title: str
    mode: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    run_id: str | None
    mode: str | None
    created_at: str


class ChatDetail(BaseModel):
    chat: ChatOut
    messages: list[MessageOut]


class RunOut(BaseModel):
    id: str
    chat_id: str
    mode: str
    question: str
    status: str
    answer: str | None
    error: str | None
    started_at: str
    finished_at: str | None


class StepOut(BaseModel):
    id: str
    run_id: str
    seq: int
    parent_step_id: str | None
    kind: str
    bubble: str | None
    started_at: str
    duration_ms: float | None
    status: str
    summary: dict[str, Any]
    node_ids: list[str]
    edge_ids: list[str]
    citations: list[dict[str, Any]]
    error: str | None


class SendOut(BaseModel):
    run_id: str
    run: RunOut
    user_message: MessageOut
    assistant_message: MessageOut


class ProviderIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    base_url: str = Field(pattern=BASE_URL_PATTERN)
    model: str = Field(min_length=1, max_length=200)

    @field_validator("api_key")
    @classmethod
    def _strip_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank; omit the field to keep the saved key")
        return value

    @field_validator("base_url", "model")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProviderOut(BaseModel):
    """Never contains the key. ``key_hint`` is shown only for a key saved in the UI."""

    key_set: bool
    key_hint: str | None
    key_source: Literal["ui", "env"] | None
    base_url: str
    model: str


class ProbeOut(BaseModel):
    ok: bool
    message: str


class GraphNodeOut(BaseModel):
    id: str
    label: str
    bubble: str
    kind: str


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    label: str


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    total: int


def chat_payload(row: ChatRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "mode": row.mode,
        "created_at": utc(row.created_at).isoformat(),
        "updated_at": utc(row.updated_at).isoformat(),
    }


def message_payload(row: MessageRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "role": row.role,
        "content": row.content,
        "run_id": row.run_id,
        "mode": row.mode,
        "created_at": utc(row.created_at).isoformat(),
    }


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --------------------------------------------------------------- provider


async def _probe_provider(settings: Settings, api_key: str) -> tuple[bool, str]:
    """One small completion. Errors map to fixed messages so no secret or raw body reaches the UI."""
    client = openai.AsyncOpenAI(
        base_url=settings.llm_base_url, api_key=api_key, timeout=20.0, max_retries=0
    )
    try:
        await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
        )
        return True, "Connected. The model replied."
    except openai.AuthenticationError:
        return False, "The provider rejected the API key."
    except openai.NotFoundError:
        return False, "The model name or the endpoint was not found."
    except openai.BadRequestError:
        return False, "The provider rejected the request. Check the model name."
    except openai.RateLimitError:
        return False, "The provider is rate limiting requests. Try again later."
    except openai.APIConnectionError:
        return False, "Could not reach the endpoint. Check the base URL."
    except openai.APIStatusError as exc:
        return False, f"The provider returned HTTP {exc.status_code}."
    except openai.OpenAIError:
        return False, "The connection test failed."
    finally:
        await client.close()


# ------------------------------------------------------------------- runs


@dataclass(eq=False)
class RunState:
    run_id: str
    chat_id: str
    mode: str
    question: str
    bubble_ids: list[str]
    recorder: RunRecorder
    runtime: Any = None
    task: asyncio.Task | None = None
    finalized: bool = False


class UIServices:
    """Run lifecycle, provider settings and the UI's persistence wiring."""

    def __init__(
        self,
        repo: Repository,
        services: Services,
        scheduler: Any,
        *,
        web_dist: Path = DEFAULT_WEB_DIST,
        probe: Callable[[Settings, str], Any] | None = None,
    ) -> None:
        self.repo = repo
        self.c6 = services
        self.scheduler = scheduler
        self.web_dist = web_dist
        self._probe = probe or _probe_provider
        self.bus: RunBus | None = None
        self.active: dict[str, RunState] = {}
        self._tasks: set[asyncio.Task] = set()
        self._purge_task: asyncio.Task | None = None
        self._closing = False
        self._env_key = ""
        self._ui_key: str | None = None

    # ---------------------------------------------------------- lifecycle
    async def startup(self) -> None:
        """Load the saved key, sweep stale runs, and apply retention. Call after Services.load()."""
        self.bus = RunBus(asyncio.get_running_loop())
        self._closing = False
        self._env_key = self.c6.startup_settings.llm_api_key.get_secret_value()
        saved = await self.repo.get_setting(PROVIDER_KEY_SETTING)
        self._ui_key = saved.strip() if isinstance(saved, str) and saved.strip() else None
        self._apply_key()
        swept = await self.repo.interrupt_running_runs(INTERRUPTED_MESSAGE)
        if swept:
            logger.warning("Marked %d run(s) interrupted at startup", len(swept))
        await self.purge_expired()
        self._purge_task = asyncio.create_task(self._purge_forever())

    async def shutdown(self) -> None:
        """Runs still active at shutdown finish as interrupted (see _execute)."""
        self._closing = True
        if self._purge_task is not None:
            self._purge_task.cancel()
        for state in list(self.active.values()):
            if state.task is not None:
                state.task.cancel()
        if self._tasks:
            _, pending = await asyncio.wait(set(self._tasks), timeout=20)
            if pending:
                logger.warning("%d background task(s) did not stop in time", len(pending))

    async def purge_expired(self) -> int:
        cutoff = datetime.now(UTC) - RETENTION
        return await self.repo.purge_steps_started_before(cutoff)

    async def _purge_forever(self) -> None:
        while True:
            await asyncio.sleep(PURGE_INTERVAL_SECONDS)
            try:
                await self.purge_expired()
            except Exception:  # retention must not stop the server
                logger.exception("trace retention sweep failed")

    def _spawn(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ----------------------------------------------------------- provider
    def effective_key(self) -> str:
        return self._ui_key or self._env_key

    def key_source(self) -> str | None:
        if self._ui_key:
            return "ui"
        return "env" if self._env_key else None

    def _redact(self, text: str) -> str:
        for secret in {self._ui_key, self._env_key}:
            if secret:
                text = text.replace(secret, "[redacted]")
        return text

    def _apply_key(self) -> None:
        """Push the effective key into the settings the query runtime is built from."""
        key = SecretStr(self.effective_key())
        self.c6.startup_settings = self.c6.startup_settings.model_copy(
            update={"llm_api_key": key}
        )
        self.c6.settings = self.c6.settings.model_copy(update={"llm_api_key": key})

    def provider_view(self) -> ProviderOut:
        settings = self.c6.settings
        source = self.key_source()
        return ProviderOut(
            key_set=bool(self.effective_key()),
            key_hint=self._ui_key[-4:] if self._ui_key and len(self._ui_key) >= 4 else None,
            key_source=source,  # type: ignore[arg-type]
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )

    async def save_provider(self, body: ProviderIn) -> ProviderOut:
        if body.api_key:
            self._ui_key = body.api_key
            await self.repo.set_setting(PROVIDER_KEY_SETTING, body.api_key)
        # Same keys as PUT /settings, so the existing settings table stays the source of truth.
        await self.repo.set_setting("llm_base_url", body.base_url)
        await self.repo.set_setting("llm_model", body.model)
        update = {"llm_base_url": body.base_url, "llm_model": body.model}
        self.c6.startup_settings = self.c6.startup_settings.model_copy(update=update)
        self.c6.settings = self.c6.settings.model_copy(update=update)
        self._apply_key()
        await self._retire_runtime()
        return self.provider_view()

    async def clear_key(self) -> ProviderOut:
        self._ui_key = None
        await self.repo.set_setting(PROVIDER_KEY_SETTING, None)
        self._apply_key()
        await self._retire_runtime()
        return self.provider_view()

    async def test_provider(self) -> ProbeOut:
        key = self.effective_key()
        if not key:
            return ProbeOut(ok=False, message="No API key is configured.")
        ok, message = await self._probe(self.c6.settings, key)
        return ProbeOut(ok=ok, message=message)

    async def _retire_runtime(self) -> None:
        """Rebuild the query runtime lazily. The old one closes after its in-flight runs finish."""
        async with self.c6.lock:
            old, self.c6.runtime = self.c6.runtime, None
        if old is None:
            return
        waiting = [s.task for s in self.active.values() if s.runtime is old and s.task and not s.task.done()]

        async def close_when_idle() -> None:
            if waiting:
                await asyncio.wait(waiting)
            try:
                await old.close()
            except Exception:
                logger.exception("closing a replaced query runtime failed")

        self._spawn(close_when_idle())

    # --------------------------------------------------------------- runs
    async def send_message(self, chat_id: str, body: MessageIn) -> SendOut:
        chat = await self.repo.get_chat(chat_id)
        if chat is None:
            raise HTTPException(404, "Unknown chat")
        if self._closing:
            raise HTTPException(503, "OmniStream is shutting down")
        if not self.effective_key():
            raise HTTPException(409, "No provider key is configured. Add one in Settings.")
        known = {b.id for b in await self.repo.list_bubbles()}
        if not known:
            raise HTTPException(409, "There are no bubbles to search yet. Add a source first.")
        if missing := [b for b in body.bubble_ids if b not in known]:
            raise HTTPException(422, f"unknown bubble ids: {missing}")

        now = datetime.now(UTC)
        run_id = uuid.uuid4().hex
        earlier = await self.repo.list_messages(chat_id)
        title = chat.title
        if not earlier:
            title = " ".join(body.content.split())[:60] or chat.title
        user = MessageRow(
            id=uuid.uuid4().hex, chat_id=chat_id, role="user", content=body.content,
            mode=body.mode, created_at=now,
        )
        assistant = MessageRow(
            id=uuid.uuid4().hex, chat_id=chat_id, role="assistant", content="",
            run_id=run_id, mode=body.mode, created_at=now + timedelta(microseconds=1),
        )
        run = RunRow(
            id=run_id, chat_id=chat_id, mode=body.mode, question=body.content,
            status="running", started_at=now,
        )
        await self.repo.update_chat(chat_id, mode=body.mode, title=title, updated_at=now)
        await self.repo.add_message(user)
        await self.repo.add_message(assistant)
        await self.repo.create_run(run)

        recorder = RunRecorder(self.repo.save_step, self._bus(), run_id)
        state = RunState(
            run_id=run_id, chat_id=chat_id, mode=body.mode, question=body.content,
            bubble_ids=list(body.bubble_ids), recorder=recorder,
        )
        self.active[run_id] = state
        state.task = self._spawn(self._execute(state))
        state.task.add_done_callback(lambda task: self._reap(state, task))
        return SendOut(
            run_id=run_id,
            run=RunOut(**run_payload(run)),
            user_message=MessageOut(**message_payload(user)),
            assistant_message=MessageOut(**message_payload(assistant)),
        )

    def _bus(self) -> RunBus:
        if self.bus is None:
            raise RuntimeError("UIServices.startup() has not run")
        return self.bus

    async def _execute(self, state: RunState) -> None:
        trace = PipelineTrace(state.recorder, agentic=state.mode == "agentic")
        recorder = state.recorder
        try:
            runtime = await self.c6.get_runtime()
            state.runtime = runtime
            await runtime.initialize()
            result = await self._answer(runtime, trace, state)
            text = result.answer.text.strip()
            if not text:
                raise EmptyAnswer("The model returned no answer.")
            citations = await self._citations(result.answer.citations)
            trace.record_untraced_subagents(result.multi_hop.findings if result.multi_hop else ())
            if trace.answer_step is None:
                trace.open_answer()
            recorder.finish(
                trace.answer_step,
                "ok",
                summary={
                    "citations": len(citations),
                    "citation_count": len(citations),
                    "invalid_citations": list(result.answer.invalid_citations),
                    "conflicts": len(result.conflicts),
                },
                citations=citations,
            )
            recorder.close("ok")
            await self._finalize(state, "ok", answer=text, error=None, message=text)
        except asyncio.CancelledError:
            recorder.close("cancelled")
            if self._closing:
                await self._finalize(
                    state, "interrupted", answer=None, error=INTERRUPTED_MESSAGE,
                    message=INTERRUPTED_MESSAGE,
                )
            else:
                await self._finalize(
                    state, "cancelled", answer=None, error=None, message=STOPPED_MESSAGE
                )
            raise
        except Exception as exc:  # noqa: BLE001 - every failure becomes a failed run
            text = self._redact(str(exc) or type(exc).__name__)[:500]
            recorder.close("error", text)
            await self._finalize(
                state, "failed", answer=None, error=text, message=f"This answer failed: {text}"
            )
        finally:
            self.active.pop(state.run_id, None)

    async def _answer(self, runtime: Any, trace: PipelineTrace, state: RunState) -> Any:
        agentic = state.mode == "agentic"
        dispatcher = (
            trace.agentic_dispatcher(runtime.dispatcher)
            if agentic
            else trace.dispatcher(runtime.dispatcher)
        )
        return await answer_question(
            state.question,
            router=trace.router(runtime.router),
            dispatcher=dispatcher,
            llm=trace.llm(runtime.llm),
            async_llm=runtime.async_llm,
            graph_store=runtime.graph,
            item_store=runtime.items,
            settings=runtime.settings,
            mode="own",
            pins=tuple(state.bubble_ids),
            subagents=agentic,
        )

    async def _citations(self, citations: Any) -> list[dict[str, Any]]:
        out = []
        for citation in citations:
            item = await self.repo.get_item(citation.item_id)
            out.append(
                {
                    "number": citation.number,
                    "item_id": citation.item_id,
                    "url": citation.source_url or (item.url if item and item.url else None),
                    "title": (item.title if item and item.title else "") or citation.item_id,
                }
            )
        return out

    def _reap(self, state: RunState, task: asyncio.Task) -> None:
        """Safety net: a run cancelled before its coroutine first ran never reaches its own handlers."""
        self.active.pop(state.run_id, None)
        if state.finalized or not task.cancelled():
            return
        state.recorder.close("cancelled")
        if self._closing:
            self._spawn(self._finalize(
                state, "interrupted", answer=None, error=INTERRUPTED_MESSAGE, message=INTERRUPTED_MESSAGE,
            ))
        else:
            self._spawn(self._finalize(
                state, "cancelled", answer=None, error=None, message=STOPPED_MESSAGE,
            ))

    async def _finalize(
        self, state: RunState, status: str, *, answer: str | None, error: str | None, message: str
    ) -> None:
        if state.finalized:
            return
        state.finalized = True
        try:
            run = await self.repo.update_run(
                state.run_id,
                status=status,
                answer=answer,
                error=error,
                finished_at=datetime.now(UTC),
            )
            await self.repo.set_message_content_for_run(state.run_id, message)
        except KeyError:
            logger.warning("run %s vanished before it finished", state.run_id)
            return
        bus = self._bus()
        bus.publish(state.run_id, "run", run_payload(run))
        bus.publish(state.run_id, "done", {"run_id": state.run_id, "status": status})

    async def cancel(self, run_id: str) -> RunRow:
        state = self.active.get(run_id)
        if state is not None and state.task is not None and not state.task.done():
            state.task.cancel()
            await asyncio.wait({state.task}, timeout=10)
        run = await self.repo.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Trace no longer available")
        return run

    async def step_snapshot(self, run_id: str) -> list[dict[str, Any]]:
        """Finished steps from storage plus any still running. Live steps are read first (see ui_trace)."""
        state = self.active.get(run_id)
        live = state.recorder.live_payloads() if state is not None else []
        merged = {p["id"]: p for p in live}
        for row in await self.repo.list_steps(run_id):
            merged[row.id] = step_payload(row)
        return sorted(merged.values(), key=lambda p: p["seq"])

    async def delete_chat(self, chat_id: str) -> None:
        for state in [s for s in self.active.values() if s.chat_id == chat_id]:
            if state.task is not None and not state.task.done():
                state.task.cancel()
                await asyncio.wait({state.task}, timeout=10)
        await self.repo.delete_chat(chat_id)

    # ------------------------------------------------------------- graph
    async def graph(self, bubble: str | None, limit: int, offset: int) -> GraphOut:
        if bubble is not None:
            if await self.repo.get_bubble(bubble) is None:
                raise HTTPException(404, "Unknown bubble")
            bubble_ids = [bubble]
        else:
            bubble_ids = [b.id for b in await self.repo.list_bubbles()]
        ops = self.c6.lifecycle._ops
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for bubble_id in bubble_ids:
            data = await ops.bubble_graph(bubble_id, GRAPH_FETCH_LIMIT)
            for node in data["nodes"]:
                nodes.append(
                    {
                        "id": node["id"],
                        "label": node.get("label") or node["id"],
                        "bubble": bubble_id,
                        "kind": "entity",
                    }
                )
            for edge in data["edges"]:
                edges.append(
                    {
                        "id": edge["id"],
                        "source": edge["from"],
                        "target": edge["to"],
                        "label": edge.get("label") or "",
                    }
                )
        page = nodes[offset : offset + limit]
        keep = {node["id"] for node in page}
        page_edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        return GraphOut(nodes=page, edges=page_edges, total=len(nodes))


# ----------------------------------------------------------------- router


def build_ui_router(ui: UIServices) -> APIRouter:
    router = APIRouter(prefix="/api")
    repo = ui.repo

    async def _known_run(run_id: str) -> RunRow:
        row = await repo.get_run(run_id)
        if row is None:
            raise HTTPException(404, "Unknown run")
        if trace_expired(row):
            raise HTTPException(410, "Trace no longer available")
        return row

    # chats
    @router.post("/chats", status_code=201, response_model=ChatOut)
    async def create_chat(body: ChatCreate | None = None) -> dict:
        now = datetime.now(UTC)
        title = ((body.title if body else None) or "").strip() or "New chat"
        row = await repo.create_chat(
            ChatRow(id=uuid.uuid4().hex, title=title, created_at=now, updated_at=now)
        )
        return chat_payload(row)

    @router.get("/chats", response_model=list[ChatOut])
    async def list_chats() -> list[dict]:
        return [chat_payload(row) for row in await repo.list_chats()]

    @router.get("/chats/{chat_id}", response_model=ChatDetail)
    async def get_chat(chat_id: str) -> dict:
        row = await repo.get_chat(chat_id)
        if row is None:
            raise HTTPException(404, "Unknown chat")
        messages = [message_payload(m) for m in await repo.list_messages(chat_id)]
        return {"chat": chat_payload(row), "messages": messages}

    @router.patch("/chats/{chat_id}", response_model=ChatOut)
    async def rename_chat(chat_id: str, body: ChatPatch) -> dict:
        if await repo.get_chat(chat_id) is None:
            raise HTTPException(404, "Unknown chat")
        row = await repo.update_chat(chat_id, title=body.title, updated_at=datetime.now(UTC))
        return chat_payload(row)

    @router.delete("/chats/{chat_id}", status_code=204)
    async def remove_chat(chat_id: str) -> None:
        if await repo.get_chat(chat_id) is None:
            raise HTTPException(404, "Unknown chat")
        await ui.delete_chat(chat_id)

    @router.post("/chats/{chat_id}/messages", status_code=202, response_model=SendOut)
    async def send_message(chat_id: str, body: MessageIn) -> SendOut:
        return await ui.send_message(chat_id, body)

    # runs
    @router.get("/runs/{run_id}", response_model=RunOut)
    async def get_run(run_id: str) -> dict:
        row = await _known_run(run_id)
        return run_payload(row)

    @router.get("/runs/{run_id}/steps", response_model=list[StepOut])
    async def run_steps(run_id: str) -> list[dict]:
        await _known_run(run_id)
        return await ui.step_snapshot(run_id)

    @router.post("/runs/{run_id}/cancel", response_model=RunOut)
    async def cancel_run(run_id: str) -> dict:
        return run_payload(await ui.cancel(run_id))

    @router.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        await _known_run(run_id)
        return StreamingResponse(
            _event_stream(ui, run_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # provider settings
    @router.get("/settings/provider", response_model=ProviderOut)
    async def get_provider() -> ProviderOut:
        return ui.provider_view()

    @router.put("/settings/provider", response_model=ProviderOut)
    async def put_provider(body: ProviderIn) -> ProviderOut:
        return await ui.save_provider(body)

    @router.delete("/settings/provider/key", response_model=ProviderOut)
    async def delete_provider_key() -> ProviderOut:
        return await ui.clear_key()

    @router.post("/settings/provider/test", response_model=ProbeOut)
    async def test_provider() -> ProbeOut:
        return await ui.test_provider()

    # sources (DELETE is new; the rest are aliases registered in app.py)
    @router.delete("/sources/{source_id}", status_code=204)
    async def delete_source(source_id: str) -> None:
        if await repo.get_source(source_id) is None:
            raise HTTPException(404, f"unknown source {source_id!r}")
        ui.scheduler.unschedule_source(source_id)
        await repo.delete_source(source_id)

    # graph
    @router.get("/graph", response_model=GraphOut)
    async def graph(
        bubble: str | None = None,
        limit: int = Query(300, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> GraphOut:
        return await ui.graph(bubble, limit, offset)

    return router


async def _event_stream(ui: UIServices, run_id: str) -> AsyncIterator[str]:
    """SSE: snapshot of steps so far, then live events until ``done``. Duplicates are dropped by key."""
    queue = ui._bus().subscribe(run_id)
    sent: set[tuple[str, str]] = set()
    last_run_status: str | None = None
    try:
        current = await ui.repo.get_run(run_id)
        if current is None:
            yield sse("done", {"run_id": run_id, "status": "missing"})
            return
        last_run_status = current.status
        yield sse("run", run_payload(current))
        for step in await ui.step_snapshot(run_id):
            sent.add((step["id"], step["status"]))
            yield sse("step", step)
        if current.status != "running":
            yield sse("done", {"run_id": run_id, "status": current.status})
            return
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event == "step":
                key = (data["id"], data["status"])
                if key in sent:
                    continue
                sent.add(key)
            elif event == "run":
                if data["status"] == last_run_status:
                    continue
                last_run_status = data["status"]
            yield sse(event, data)
            if event == "done":
                return
    finally:
        ui._bus().unsubscribe(run_id, queue)


def install_web_app(app: Any, dist: Path) -> None:
    """Serve the built React app under /app with an SPA fallback to index.html."""
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def web_app(path: str = "") -> Any:
        if not index.is_file():
            return HTMLResponse(
                "<!doctype html><meta charset='utf-8'><title>OmniStream</title>"
                "<h1>The web app is not built</h1>"
                "<p>Run <code>npm run build</code> in the <code>web</code> folder, "
                "then reload this page.</p>",
                status_code=503,
            )
        if path:
            candidate = (dist / path).resolve()
            if candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            if Path(path).suffix:
                raise HTTPException(404, "Not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
