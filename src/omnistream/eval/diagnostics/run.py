"""Run with python -m omnistream.eval.diagnostics.run [answers|routes|graph]."""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

from omnistream.agents.tools import ToolExecutor
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval import evidence_ids
from omnistream.eval.judge import Judge
from omnistream.eval.metrics import retrieval_metrics
from omnistream.eval.resources import UsageMeter, stage
from omnistream.retrieval import runtime
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm import pipeline
from omnistream.retrieval.own_algorithm.seeding import Seed
from omnistream.retrieval.router import RoutingDecision

OUT = Path("data/diagnostics/eval-v2")
SNAP = Path("data/snapshots/eval-v2").resolve()
GROUPS = ("eval-v2-news", "eval-v2-finance", "eval-v2-research")
CASE = contextvars.ContextVar("diagnostic_case", default=None)
DATA = json.loads(Path("src/omnistream/eval/corpus/eval-v2.json").read_text())
MANIFEST = json.loads((SNAP / "manifest.json").read_text())
IDS = {k: v["runtime_id"] for k, v in MANIFEST["items"].items()}
REVERSE = {v: k for k, v in IDS.items()}


def encode(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, Path)):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if hasattr(value, "to_native"):
        return str(value.to_native())
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(type(value).__name__)


def append(name, value):
    with (OUT / (name + ".jsonl")).open("a", encoding="utf-8") as file:
        file.write(json.dumps(value, default=encode, ensure_ascii=False) + "\n")
        file.flush()
        if name in {"answers", "controlled_replays", "offline_retrieval"}:
            os.fsync(file.fileno())


def read(name):
    path = OUT / (name + ".jsonl")
    return (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )


def primary_answers():
    """Use metadata-controlled replays where an oracle reroute changed a flag."""
    rows = {}
    for row in [*read("answers"), *read("controlled_replays")]:
        key = row["experiment"], row["configuration"], row["question_id"]
        if "correctness" in row or "correctness" not in rows.get(key, {}):
            rows[key] = row
    return list(rows.values())


class ProviderCapacityError(RuntimeError):
    """A checkpointed capacity error; do not flood remaining cells with calls."""


def capacity_error(exc):
    return "key limit exceeded" in str(exc).casefold()


def error_text(exc):
    if capacity_error(exc):
        return "ProviderCapacityError: OpenRouter key lifetime limit exceeded (403)"
    return f"{type(exc).__name__}: {exc}"[:1500]


def decode_route(raw):
    values = dict(raw)
    scope = values.get("time_scope")
    values["time_scope"] = (
        TimeScope(
            **{
                k: (v if isinstance(v, datetime) else datetime.fromisoformat(v))
                if v
                else None
                for k, v in scope.items()
            }
        )
        if scope
        else None
    )
    for key in ("bubbles", "excluded_bubbles", "hints"):
        values[key] = tuple(values[key])
    return RoutingDecision(**values)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(*, now=None):
    os.environ["NEO4J_PASSWORD"] = (
        Path(
            "C:/Users/mehme/AppData/Local/Temp/claude/803928835945f44b/"
            "3875a788-004a-4920-9803-352914729589/scratchpad/neo4j_pw.txt"
        )
        .read_text()
        .strip()
    )
    settings = Settings().model_copy(update={"data_dir": str(SNAP)})
    # Avoid Repository.__init__: it provisions schema and sets writable pragmas.
    repo = Repository.__new__(Repository)
    repo._settings = settings
    repo._engine = create_engine(
        f"sqlite:///file:{(SNAP / 'state.db').as_posix()}?mode=ro&uri=true",
        connect_args={"check_same_thread": False},
    )
    # Chroma's reader can update its local database; operate on an exact copy.
    copied = OUT / "chroma-reader-copy"
    if not copied.exists():
        shutil.copytree(SNAP / "chroma", copied)
    original = runtime.make_chroma_client
    with patch.object(runtime, "make_chroma_client", lambda _: original(copied)):
        rt = runtime.build_query_runtime(settings, repo, now=now)
    return settings, repo, rt


def graph_export(rt):
    entities = rt.graph.entities_in(GROUPS)
    facts = rt.graph._run(
        "MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity) WHERE r.group_id IN $groups "
        "RETURN s.uuid AS subject, o.uuid AS object, properties(r) AS fact",
        groups=list(GROUPS),
    )
    episodes = rt.graph._run(
        "MATCH (ep:Episodic) WHERE ep.group_id IN $groups "
        "OPTIONAL MATCH (ep)-[:MENTIONS]->(e:Entity) "
        "RETURN ep.uuid AS id, properties(ep) AS episode, collect(e.uuid) AS entities",
        groups=list(GROUPS),
    )
    payload = {
        "entities": entities,
        "facts": [dict(r) for r in facts],
        "episodes": [dict(r) for r in episodes],
    }
    (OUT / "graph.json").write_text(
        json.dumps(payload, default=encode), encoding="utf-8"
    )
    return payload


def gold_entities(q, graph):
    gold = {IDS[i] for i in q["gold"]}
    # Graphiti episodes carry runtime item_id in their custom provenance.
    return {
        eid
        for ep in graph["episodes"]
        if ep["episode"].get("item_id") in gold
        for eid in ep["entities"]
    }


def install_traces(rt):
    seed_original = pipeline.seed_entities
    expand_original = rt.graph.expand
    fusion_original = pipeline.fuse_facts
    tool_original = ToolExecutor.execute
    chat_original = rt.async_llm.chat_with_tools

    def seeds(*args, **kwargs):
        found = seed_original(*args, **kwargs)
        case = CASE.get() or {}
        if case.get("oracle_entities") is not None:
            found = [
                Seed(e, 1.0, "fuzzy")
                for e in rt.graph.entities_in(GROUPS)
                if e.id in case["oracle_entities"]
            ]
        append(
            "stages",
            {
                **case,
                "event": "seeds",
                "query": args[0],
                "bubbles": kwargs["bubbles"],
                "seeds": found,
            },
        )
        return found

    def expand(*args, **kwargs):
        result = expand_original(*args, **kwargs)
        append(
            "stages",
            {
                **(CASE.get() or {}),
                "event": "expansion",
                "seed_ids": args[0],
                "graph": result,
            },
        )
        return result

    def fusion(*args, **kwargs):
        result = fusion_original(*args, **kwargs)
        # Recompute only for observation, with unchanged signals and no truncation.
        full = fusion_original(*args, **{**kwargs, "top_n": None})
        append(
            "stages",
            {
                **(CASE.get() or {}),
                "event": "fusion",
                "candidates": args[0],
                "full_ranking": full,
            },
        )
        return result

    async def tool(executor, call):
        result = await tool_original(executor, call)
        append(
            "tools",
            {
                **(CASE.get() or {}),
                "bubble": executor.bubble,
                "mode": executor.mode,
                "call": call,
                "result": json.loads(result),
            },
        )
        return result

    async def chat(messages, tools, **kwargs):
        result = await chat_original(messages, tools, **kwargs)
        append(
            "agent_turns", {**(CASE.get() or {}), "messages": messages, "turn": result}
        )
        return result

    pipeline.seed_entities = seeds
    rt.graph.expand = expand
    pipeline.fuse_facts = fusion
    ToolExecutor.execute = tool
    rt.async_llm.chat_with_tools = chat


async def answers(rt, judge, graph, meter):
    questions = [
        q for q in DATA["questions"] if q["type"] in ("multi_hop", "time_sensitive")
    ]
    stored = read("answers")
    completed = {
        (r["experiment"], r["configuration"], r["question_id"])
        for r in stored
        if r.get("correctness") in (0, 1, 2) and not r.get("error")
    }
    answer_cache = {
        (r["experiment"], r["configuration"], r["question_id"]): r
        for r in stored
        if "answer" in r and "retrieved_item_ids" in r
    }
    routed = {
        (r["experiment"], r["configuration"], r["question_id"]): r["routing"]
        for r in stored
        if "routing" in r
    }
    normal_route = rt.router.route

    def controlled_route(question, *, pins=(), exclude=()):
        case = CASE.get() or {}
        experiment = case.get("experiment")
        if experiment in ("E1", "E4"):
            base_experiment = "E0" if experiment == "E1" else "E1"
            base = decode_route(
                routed[base_experiment, case["configuration"], case["question_id"]]
            )
            return RoutingDecision(
                **{
                    **asdict(base),
                    "bubbles": tuple(dict.fromkeys((*base.bubbles, *GROUPS))),
                    "time_scope": base.time_scope,
                }
            )
        return normal_route(question, pins=pins, exclude=exclude)

    rt.router.route = controlled_route
    configs = ("classic", "graphiti", "own", "own+subagents", "classic+subagents")

    async def one(experiment, config, q):
        key = (experiment, config, q["id"])
        if key in completed:
            return
        case = {
            "experiment": experiment,
            "configuration": config,
            "question_id": q["id"],
        }
        if experiment == "E4":
            case["oracle_entities"] = sorted(gold_entities(q, graph))
        CASE.set(case)
        stage.set(experiment + ":" + config)
        start = time.monotonic()
        row = {**case, "type": q["type"], "gold_item_ids": [IDS[i] for i in q["gold"]]}
        if experiment in ("E1", "E4"):
            row["routing_reused_from"] = "E0" if experiment == "E1" else "E1"
        try:
            if key in answer_cache:
                row.update(
                    {
                        k: v
                        for k, v in answer_cache[key].items()
                        if k not in {"error", "provider_blocked"}
                    }
                )
                row["resume_judge_only"] = True
            else:
                result = await rt.answer(
                    q["question"],
                    mode=config.split("+")[0],
                    subagents="+" in config,
                    pin=GROUPS if experiment != "E0" else (),
                )
                retrieved = evidence_ids(result)
                row.update(
                    answer=result.answer.text,
                    routing=asdict(result.routing),
                    retrieved_item_ids=retrieved,
                    retrieval=result.retrieval,
                    multi_hop=result.multi_hop,
                )
                row.update(retrieval_metrics(retrieved, row["gold_item_ids"]))
                row["recall_any"] = len(
                    set(retrieved) & set(row["gold_item_ids"])
                ) / len(row["gold_item_ids"])
            routed[key] = row["routing"]
            stage.set(experiment + ":judge")
            judgement = await judge.correctness(q, row["answer"])
            row.update(correctness=judgement["score"], judgement=judgement)
        except Exception as exc:  # noqa: BLE001
            row["error"] = error_text(exc)
            row["provider_blocked"] = capacity_error(exc)
        row["seconds"] = time.monotonic() - start
        append("answers", row)
        append("usage", {"time": datetime.now(UTC), "usage": meter.summary()})
        print(
            experiment,
            config,
            q["id"],
            row.get("correctness"),
            row.get("recall_any"),
            row.get("error", ""),
            flush=True,
        )
        return row

    for experiment in ("E0", "E1", "E4"):
        for config in ("own",) if experiment == "E4" else configs:
            selected = [
                q for q in questions if experiment != "E4" or q["type"] == "multi_hop"
            ]
            for offset in range(0, len(selected), 2):
                results = await asyncio.gather(
                    *(one(experiment, config, q) for q in selected[offset : offset + 2])
                )
                if any(r and r.get("provider_blocked") for r in results):
                    raise ProviderCapacityError(
                        "Provider capacity is unavailable; completed cells were checkpointed. Restore the key's capacity before resuming."
                    )


async def routes(rt, meter):
    done = {(r["question_id"], r["repeat"]) for r in read("routes")}
    for q in DATA["questions"]:
        for repeat in range(5):
            if (q["id"], repeat) in done:
                continue
            stage.set("E2:router")
            decision = await asyncio.to_thread(rt.router.route, q["question"])
            append(
                "routes",
                {
                    "question_id": q["id"],
                    "type": q["type"],
                    "repeat": repeat,
                    "expected_bubbles": q["expected_bubbles"],
                    "decision": decision,
                },
            )
        append("usage", {"time": datetime.now(UTC), "usage": meter.summary()})
        print("E2", q["id"], flush=True)


async def main(action=None):
    if action is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("action", choices=("answers", "routes", "graph"))
        args = parser.parse_args()
    else:
        args = argparse.Namespace(action=action)
    logging.basicConfig(level=logging.ERROR)
    OUT.mkdir(parents=True, exist_ok=True)
    before = {
        str(p.relative_to(SNAP)): digest(p)
        for p in SNAP.rglob("*")
        if p.is_file() and "runs" not in p.parts
    }
    previous_metadata = read("metadata")
    frozen = (
        datetime.fromisoformat(previous_metadata[0]["time"])
        if previous_metadata and args.action == "answers"
        else None
    )
    settings, repo, rt = build(now=(lambda: frozen) if frozen else None)
    judge = Judge(settings)
    with UsageMeter() as meter:
        try:
            if args.action == "answers" and previous_metadata:
                first = previous_metadata[0]
                if (
                    settings.llm_model != first["answer_model"]
                    or settings.judge_model != first["judge_model"]
                ):
                    raise ValueError(
                        "Resume models differ from the checkpoint; do not mix model baselines"
                    )
                if before != first["snapshot_hashes"]:
                    raise ValueError(
                        "Frozen snapshot bytes differ from the initial checkpoint"
                    )
            await rt.initialize()
            graph = graph_export(rt)
            append(
                "metadata",
                {
                    "time": datetime.now(UTC),
                    "action": args.action,
                    "answer_model": settings.llm_model,
                    "judge_model": settings.judge_model,
                    "catalog": rt.router.catalog,
                    "snapshot_hashes": before,
                    "clock_frozen_at": str(frozen) if frozen else None,
                },
            )
            install_traces(rt)
            if args.action == "answers":
                await answers(rt, judge, graph, meter)
            elif args.action == "routes":
                await routes(rt, meter)
        finally:
            append(
                "usage_final",
                {
                    "action": args.action,
                    "time": datetime.now(UTC),
                    "usage": meter.summary(),
                },
            )
            await judge.close()
            await rt.close()
            await repo.close()
            after = {
                str(p.relative_to(SNAP)): digest(p)
                for p in SNAP.rglob("*")
                if p.is_file() and "runs" not in p.parts
            }
            append(
                "integrity",
                {
                    "action": args.action,
                    "unchanged": before == after,
                    "changed": [p for p in before if before[p] != after.get(p)],
                },
            )


if __name__ == "__main__":
    asyncio.run(main())
