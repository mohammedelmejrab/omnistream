"""Bubble-scoped C5 function schemas and bounded JSON tool execution."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from omnistream.llm import ToolCall
from omnistream.retrieval.models import RetrievalMode, TimeScope, _utc, fact_in_scope
from omnistream.retrieval.protocols import GraphStore, ItemStore, Retriever

MAX_RESULT_CHARS = 64000


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_STRING = {"type": "string", "minLength": 1}
TOOL_DEFINITIONS = (
    _schema(
        "search",
        "Search evidence in this bubble using the active retrieval mode.",
        {"query": _STRING},
        ["query"],
    ),
    _schema(
        "neighbors",
        "Inspect an entity's graph neighborhood, at most two hops.",
        {
            "entity_id": _STRING,
            "depth": {"type": "integer", "minimum": 1, "maximum": 2},
        },
        ["entity_id"],
    ),
    _schema(
        "facts",
        "Read facts about an entity within optional ISO date bounds.",
        {"entity_id": _STRING, "from": {"type": "string"}, "to": {"type": "string"}},
        ["entity_id"],
    ),
    _schema(
        "read_item",
        "Read original text, about 2000 tokens per part, up to three parts.",
        {
            "item_id": _STRING,
            "part": {
                "oneOf": [
                    {"type": "integer", "minimum": 1},
                    {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "integer", "minimum": 1},
                    },
                ]
            },
        },
        ["item_id"],
    ),
)


def tools_for_mode(mode: RetrievalMode) -> list[dict]:
    if mode not in {"classic", "graphiti", "own"}:
        raise ValueError(f"unknown retrieval mode: {mode}")
    return [
        tool
        for tool in TOOL_DEFINITIONS
        if mode != "classic" or tool["function"]["name"] in {"search", "read_item"}
    ]


def tool_error(message: str) -> str:
    return json.dumps({"error": message[:1000]}, ensure_ascii=False)


def _json(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _bounded_json(payload: dict) -> str:
    # Remove complete evidence entries instead of cutting JSON in mid-string.
    text = json.dumps(payload, default=_json, ensure_ascii=False)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    payload["truncated"] = True
    for key in ("parts", "facts", "chunks", "entities", "same_as"):
        entries = payload.get(key)
        while entries and len(text) > MAX_RESULT_CHARS:
            entries.pop()
            text = json.dumps(payload, default=_json, ensure_ascii=False)
    return text


async def _invoke(function, *args, **kwargs):
    # The shared store contracts are synchronous; keep their IO off the event loop.
    if inspect.iscoroutinefunction(function):
        return await function(*args, **kwargs)
    result = await asyncio.to_thread(function, *args, **kwargs)
    return await result if inspect.isawaitable(result) else result


class ToolExecutor:
    def __init__(
        self,
        *,
        bubble: str,
        mode: RetrievalMode,
        retriever: Retriever,
        graph_store: GraphStore | None,
        item_store: ItemStore,
        time_scope: TimeScope | None = None,
        excluded_bubbles: tuple[str, ...] = (),
    ) -> None:
        self.bubble, self.mode = bubble, mode
        self.retriever, self.graph_store, self.item_store = (
            retriever,
            graph_store,
            item_store,
        )
        self.excluded_bubbles = excluded_bubbles
        self.time_scope = time_scope
        self.tools = tools_for_mode(mode)
        self.scored_facts = {}
        self.seeds = {}

    async def _entities(self, facts) -> list:
        if self.graph_store is None or not facts:
            return []
        ids = {id for fact in facts for id in (fact.subject_id, fact.object_id)}
        return [
            asdict(entity)
            for entity in await _invoke(self.graph_store.entities_in, [self.bubble])
            if entity.id in ids
        ]

    async def execute(self, call: ToolCall) -> str:
        try:
            if call.name not in {t["function"]["name"] for t in self.tools}:
                return tool_error(f"unavailable tool: {call.name}")
            if call.arguments_error:
                return tool_error(f"invalid arguments: {call.arguments_error}")
            args = call.arguments
            allowed = next(
                t["function"]["parameters"]["properties"]
                for t in self.tools
                if t["function"]["name"] == call.name
            )
            if set(args) - set(allowed):
                raise ValueError("unexpected arguments")
            key = (
                "query"
                if call.name == "search"
                else "item_id"
                if call.name == "read_item"
                else "entity_id"
            )
            if not isinstance(args.get(key), str) or not args[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
            if call.name == "search":
                result = await _invoke(
                    self.retriever.retrieve,
                    args["query"],
                    bubbles=[self.bubble],
                    time_scope=self.time_scope,
                    **(
                        {"excluded_bubbles": self.excluded_bubbles}
                        if self.excluded_bubbles and self.mode == "own"
                        else {}
                    ),
                )
                for entry in result.facts:
                    self.scored_facts.setdefault(entry.fact.id, entry)
                for seed in result.seeds:
                    self.seeds.setdefault(seed.id, seed)
                facts = [entry.fact for entry in result.facts]
                payload = {
                    "facts": [asdict(f) for f in facts],
                    "chunks": [asdict(c) for c in result.chunks],
                    "entities": await self._entities(facts),
                }
            elif call.name == "read_item":
                parts = args.get("part", 1)
                parts = parts if isinstance(parts, list) else [parts]
                if not 1 <= len(parts) <= 3 or any(
                    type(p) is not int or p < 1 for p in parts
                ):
                    raise ValueError(
                        "part must be a positive integer or a list of 1..3 positive integers"
                    )
                payload = {"parts": []}
                for part in parts:
                    entry = asdict(
                        await _invoke(self.item_store.read_item, args["item_id"], part)
                    )
                    entry["text"] = " ".join(entry["text"].split()[:2000])[:16000]
                    payload["parts"].append(entry)
            else:
                if self.graph_store is None:
                    raise ValueError("graph store is unavailable")
                if call.name == "neighbors":
                    depth = args.get("depth", 1)
                    if type(depth) is not int or not 1 <= depth <= 2:
                        raise ValueError("depth must be within 1..2")
                    if self.time_scope is not None and callable(
                        getattr(self.graph_store, "expand", None)
                    ):
                        graph = await _invoke(
                            self.graph_store.expand,
                            [args["entity_id"]],
                            bubbles=[self.bubble],
                            time_scope=self.time_scope,
                            **(
                                {"excluded_bubbles": self.excluded_bubbles}
                                if self.excluded_bubbles and self.mode == "own"
                                else {}
                            ),
                            max_hops=depth,
                            **(
                                {"excluded_bubbles": self.excluded_bubbles}
                                if self.excluded_bubbles
                                else {}
                            ),
                        )
                    else:
                        graph = await _invoke(
                            self.graph_store.neighbors,
                            args["entity_id"],
                            depth=depth,
                            **(
                                {"excluded_bubbles": self.excluded_bubbles}
                                if self.excluded_bubbles
                                else {}
                            ),
                        )
                    scope = self.time_scope
                    facts = [
                        f
                        for f in graph.facts
                        if f.grounded is True
                        and fact_in_scope(
                            f, scope, now=getattr(self.retriever, "now", None)
                        )
                    ]
                    # Prune only orphaned identities belonging to rejected evidence.
                    # Standalone entities can still provide cross-bubble identity joins.
                    kept = {f.id for f in facts}
                    rejected_ids = {
                        id
                        for f in graph.facts
                        if f.id not in kept
                        for id in (f.subject_id, f.object_id)
                    }
                    while True:
                        connected = rejected_ids | {
                            id
                            for pair in graph.same_as
                            if rejected_ids.intersection(pair)
                            for id in pair
                        }
                        if connected == rejected_ids:
                            break
                        rejected_ids = connected
                    ids = (set(graph.entities) - rejected_ids) | {args["entity_id"]}
                    ids.update(id for f in facts for id in (f.subject_id, f.object_id))
                    while True:
                        connected = ids | {
                            id
                            for pair in graph.same_as
                            if ids.intersection(pair)
                            for id in pair
                        }
                        if connected == ids:
                            break
                        ids = connected
                    payload = {
                        "entities": [
                            asdict(e) for e in graph.entities.values() if e.id in ids
                        ],
                        "facts": [asdict(f) for f in facts],
                        "same_as": [pair for pair in graph.same_as if set(pair) <= ids],
                    }
                else:
                    start = (
                        datetime.fromisoformat(args["from"])
                        if args.get("from")
                        else None
                    )
                    end = datetime.fromisoformat(args["to"]) if args.get("to") else None
                    TimeScope(start, end)  # validate ordering
                    if self.time_scope is not None:
                        starts = [
                            d for d in (start, self.time_scope.start) if d is not None
                        ]
                        ends = [d for d in (end, self.time_scope.end) if d is not None]
                        start = max(starts, key=_utc) if starts else None
                        end = min(ends, key=_utc) if ends else None
                    if (
                        start is not None
                        and end is not None
                        and _utc(start) > _utc(end)
                    ):
                        facts = []  # Disjoint explicit and routed bounds are a valid empty query.
                    else:
                        scope = (
                            TimeScope(start, end)
                            if start is not None or end is not None
                            else None
                        )
                        facts = await _invoke(
                            self.graph_store.facts_about,
                            args["entity_id"],
                            start=start,
                            end=end,
                            **(
                                {"excluded_bubbles": self.excluded_bubbles}
                                if self.excluded_bubbles
                                else {}
                            ),
                        )
                        facts = [
                            f
                            for f in facts
                            if f.grounded is True
                            and fact_in_scope(
                                f, scope, now=getattr(self.retriever, "now", None)
                            )
                        ]
                    payload = {
                        "facts": [asdict(f) for f in facts],
                        "entities": await self._entities(facts),
                    }
            return _bounded_json(payload)
        except Exception as exc:  # noqa: BLE001 - tool errors are reported to the model
            return tool_error(f"{type(exc).__name__}: {exc}")
