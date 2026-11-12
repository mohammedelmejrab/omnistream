"""Server-rendered C6 pages and HTMX answer fragments."""

import re
from html import escape
from itertools import pairwise
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import ValidationError

from omnistream.api.c6 import QueryIn, SettingsIn


def answer_graph(result):
    nodes, edges = {}, []
    retrievals = [result.get("retrieval") or {}]
    for finding in (result.get("multi_hop") or {}).get("findings", []):
        retrievals.append(finding.get("retrieval") or finding.get("result") or {})
    for retrieval in retrievals:
        for seed in retrieval.get("seeds", []):
            nodes[seed["id"]] = {
                "id": seed["id"],
                "label": seed["name"],
                "group": seed["bubble"],
                "color": "#f6c453",
            }
        for scored in retrieval.get("facts", []):
            fact = scored["fact"]
            for endpoint in (fact["subject_id"], fact["object_id"]):
                nodes.setdefault(
                    endpoint,
                    {"id": endpoint, "label": endpoint, "group": fact["bubble"]},
                )
            edges.append(
                {
                    "from": fact["subject_id"],
                    "to": fact["object_id"],
                    "label": fact["relation"],
                    "title": fact["text"],
                }
            )
            path = scored.get("path", [])
            for a, b in pairwise(path):
                for endpoint in (a, b):
                    nodes.setdefault(endpoint, {"id": endpoint, "label": endpoint})
                edges.append(
                    {"from": a, "to": b, "dashes": True, "label": "hop / cross-bubble"}
                )
    return {"nodes": list(nodes.values()), "edges": edges}


def build_pages(services):
    router = APIRouter()
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

    async def render(request, page, **context):
        return templates.TemplateResponse(request, page + ".html", context)

    @router.get("/")
    async def root():
        return RedirectResponse("/ui/ask")

    @router.get("/ui/ask", response_class=HTMLResponse)
    async def ask(request: Request):
        return await render(
            request, "ask", title="Ask", bubbles=await services.repo.list_bubbles()
        )

    @router.post("/ui/ask", response_class=HTMLResponse)
    async def answer(request: Request):
        form = await request.form()
        try:
            body = QueryIn(
                question=str(form.get("question", "")),
                mode=form.get("mode") or None,
                subagents=form.get("subagents") == "on",
                pin=form.getlist("pin"),
                exclude=form.getlist("exclude"),
            )
            result = await services.query(body)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(422, "Invalid query") from exc
        for citation in result["answer"]["citations"]:
            citation["text_url"] = (
                "/ui/items/"
                + quote(citation["item_id"], safe="")
                + "/text?"
                + urlencode(
                    [("span", f"{a}:{b}") for a, b in citation.get("spans", [])]
                )
            )
        links = {str(c["number"]): c["text_url"] for c in result["answer"]["citations"]}

        def link(match):
            number = match.group(1)
            if number not in links:
                return match.group()
            return f'<a href="{escape(links[number], quote=True)}" target="_blank" rel="noopener">[{number}]</a>'

        answer_html = Markup(
            re.sub(r"\[(\d+)\]", link, escape(result["answer"]["text"]))
        )
        return await render(
            request,
            "_answer",
            result=result,
            graph=answer_graph(result),
            answer_html=answer_html,
        )

    @router.get("/ui/bubbles", response_class=HTMLResponse)
    async def bubbles(request: Request):
        return await render(
            request,
            "bubbles",
            title="Bubbles",
            bubbles=await services.repo.list_bubbles(),
        )

    @router.get("/ui/bubbles/{bubble_id}", response_class=HTMLResponse)
    async def bubble(request: Request, bubble_id: str):
        row = await services.repo.get_bubble(bubble_id)
        if row is None:
            raise HTTPException(404, "Unknown bubble")
        return await render(
            request,
            "bubble",
            title=row.name,
            bubble=row,
            counts=await services.lifecycle.counts(bubble_id),
            sources=[
                s
                for s in await services.repo.list_sources()
                if bubble_id in s.bubble_ids
            ],
            episodes=await services.lifecycle._ops.recent_episodes(bubble_id),
        )

    @router.get("/ui/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        return await render(
            request,
            "settings",
            title="Settings",
            settings=await services.public_settings(),
        )

    @router.post("/ui/settings", response_class=HTMLResponse)
    async def save(request: Request):
        form = await request.form()
        try:
            body = SettingsIn.model_validate(dict(form))
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_context=False)) from exc
        await services.save_settings(body)
        return HTMLResponse(
            '<p role="status">Settings saved. Provider and judge changes apply to queries, ingestion and evaluations after restart.</p>'
        )

    @router.get("/ui/eval", response_class=HTMLResponse)
    async def evaluations(request: Request):
        return await render(
            request,
            "eval",
            title="Eval",
            runs=jsonable_encoder(await services.repo.list_eval_runs()),
        )

    return router
