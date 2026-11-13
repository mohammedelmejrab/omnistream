"""Complete oracle retrieval cells locally; prohibit all model API calls."""

import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch

from openai.resources.chat.completions import AsyncCompletions, Completions

from omnistream.eval import evidence_ids
from omnistream.eval.diagnostics.controlled import decision
from omnistream.eval.diagnostics.run import (
    CASE,
    DATA,
    GROUPS,
    IDS,
    OUT,
    append,
    build,
    install_traces,
    primary_answers,
    read,
)
from omnistream.eval.metrics import retrieval_metrics


def metrics(row, result):
    if isinstance(result, dict):
        retrieved = []
        for entry in result.get("facts", []):
            fact = entry["fact"]
            retrieved.extend([fact["item_id"], *fact.get("item_ids", [])])
        retrieved.extend(c["item_id"] for c in result.get("chunks", []))
        retrieved = list(dict.fromkeys(retrieved))
    else:
        retrieved = evidence_ids(SimpleNamespace(retrieval=result, multi_hop=None))
    row.update(retrieved_item_ids=retrieved, retrieval=result)
    row.update(retrieval_metrics(retrieved, row["gold_item_ids"]))
    row["recall_any"] = len(set(retrieved) & set(row["gold_item_ids"])) / len(
        row["gold_item_ids"]
    )
    return row


async def main():
    def forbidden(*args, **kwargs):
        raise AssertionError("Model calls are forbidden in offline diagnostics")

    async def async_forbidden(*args, **kwargs):
        raise AssertionError("Model calls are forbidden in offline diagnostics")

    with (
        patch.object(Completions, "create", forbidden),
        patch.object(AsyncCompletions, "create", async_forbidden),
    ):
        _, repo, rt = build()
        try:
            await rt.initialize()
            install_traces(rt)
            baseline = {
                (r["configuration"], r["question_id"]): r
                for r in primary_answers()
                if r["experiment"] == "E0" and "routing" in r
            }
            done = {
                (r["experiment"], r["configuration"], r["question_id"])
                for r in read("offline_retrieval")
                if not r.get("error")
            }
            for q in DATA["questions"]:
                if q["type"] not in ("multi_hop", "time_sensitive"):
                    continue
                for config in ("classic", "graphiti", "own"):
                    key = ("E1", config, q["id"])
                    if key in done:
                        continue
                    route = decision(baseline[config, q["id"]]["routing"])
                    groups = tuple(dict.fromkeys((*route.bubbles, *GROUPS)))
                    case = {
                        "experiment": "E1",
                        "configuration": config,
                        "question_id": q["id"],
                        "retrieval_only": True,
                    }
                    CASE.set(case)
                    row = {
                        **case,
                        "type": q["type"],
                        "gold_item_ids": [IDS[g] for g in q["gold"]],
                        "routing": {**asdict(route), "bubbles": groups},
                    }
                    try:
                        result = await asyncio.to_thread(
                            rt.dispatcher.retrieve,
                            q["question"],
                            mode=config,
                            bubbles=groups,
                            time_scope=route.time_scope,
                        )
                        metrics(row, result)
                    except Exception as exc:  # noqa: BLE001
                        row["error"] = f"{type(exc).__name__}: {exc}"[:1000]
                    append("offline_retrieval", row)
                    print(
                        "offline",
                        *key,
                        row.get("recall_any"),
                        row.get("error", ""),
                        flush=True,
                    )
            traces = {
                r["question_id"]: r
                for r in read("trace_results")
                if r.get("experiment") == "E4trace"
            }
            for q in DATA["questions"]:
                if q["type"] != "multi_hop" or ("E4", "own", q["id"]) in done:
                    continue
                row = {
                    "experiment": "E4",
                    "configuration": "own",
                    "question_id": q["id"],
                    "type": q["type"],
                    "gold_item_ids": [IDS[g] for g in q["gold"]],
                    "retrieval_only": True,
                    "source_trace": "E4trace",
                }
                append("offline_retrieval", metrics(row, traces[q["id"]]["result"]))
            (OUT / "offline_guard.json").write_text(
                json.dumps(
                    {
                        "sync_model_calls": "blocked by diagnostic guard",
                        "async_model_calls": "blocked by diagnostic guard",
                        "allowed_operations": "local embeddings and read-only graph/Chroma retrieval",
                    }
                ),
                encoding="utf-8",
            )
        finally:
            await rt.close()
            await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
