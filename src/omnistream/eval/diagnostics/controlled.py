"""Replay only oracle cases whose reroute changed material non-bubble fields."""

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

from omnistream.eval import evidence_ids
from omnistream.eval.diagnostics.run import (
    CASE,
    DATA,
    IDS,
    OUT,
    ProviderCapacityError,
    append,
    build,
    capacity_error,
    error_text,
    gold_entities,
    install_traces,
    primary_answers,
)
from omnistream.eval.judge import Judge
from omnistream.eval.metrics import retrieval_metrics
from omnistream.eval.resources import UsageMeter, stage
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.router import RoutingDecision


def decision(raw):
    values = dict(raw)
    scope = values.get("time_scope")
    values["time_scope"] = (
        TimeScope(
            **{k: datetime.fromisoformat(v) if v else None for k, v in scope.items()}
        )
        if scope
        else None
    )
    for key in ("bubbles", "excluded_bubbles", "hints"):
        values[key] = tuple(values[key])
    return RoutingDecision(**values)


async def main():
    stored = primary_answers()
    assert len(stored) == 370 and all(
        r.get("correctness") in (0, 1, 2) for r in stored
    ), "Finish all raw answer/judge cells before optional metadata replays"
    settings, repo, rt = build()
    judge = Judge(settings)
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    install_traces(rt)
    targets = {}

    def frozen_route(question, *, pins=(), exclude=()):
        case = CASE.get()
        return decision(
            targets[case["experiment"], case["configuration"], case["question_id"]]
        )

    rt.router.route = frozen_route
    with UsageMeter() as meter:
        try:
            await rt.initialize()
            for experiment in ("E1", "E4"):
                values = {
                    (r["experiment"], r["configuration"], r["question_id"]): r
                    for r in primary_answers()
                }
                for q in DATA["questions"]:
                    if q["type"] not in ("multi_hop", "time_sensitive") or (
                        experiment == "E4" and q["type"] != "multi_hop"
                    ):
                        continue
                    configs = (
                        ("own",)
                        if experiment == "E4"
                        else (
                            "classic",
                            "graphiti",
                            "own",
                            "own+subagents",
                            "classic+subagents",
                        )
                    )
                    for config in configs:
                        key = (experiment, config, q["id"])
                        current = values[key]
                        base = values[
                            "E0" if experiment == "E1" else "E1", config, q["id"]
                        ]
                        fields = ["time_scope"] + (
                            ["names_specific_item"]
                            if "+" not in config and config != "classic"
                            else []
                        )
                        mismatches = [
                            field
                            for field in fields
                            if current.get("routing", {}).get(field)
                            != base["routing"].get(field)
                        ]
                        if not mismatches and not current.get("error"):
                            continue
                        target = {
                            **base["routing"],
                            "bubbles": current.get("routing", base["routing"])[
                                "bubbles"
                            ],
                        }
                        targets[key] = target
                        case = {
                            "experiment": experiment,
                            "configuration": config,
                            "question_id": q["id"],
                            "controlled_replay": True,
                        }
                        if experiment == "E4":
                            case["oracle_entities"] = sorted(gold_entities(q, graph))
                        CASE.set(case)
                        stage.set("controlled:" + experiment + ":" + config)
                        row = {
                            **case,
                            "type": q["type"],
                            "gold_item_ids": [IDS[i] for i in q["gold"]],
                            "routing_material_mismatches": mismatches,
                        }
                        try:
                            result = await rt.answer(
                                q["question"],
                                mode=config.split("+")[0],
                                subagents="+" in config,
                            )
                            retrieved = evidence_ids(result)
                            row.update(
                                answer=result.answer.text,
                                routing=asdict(result.routing),
                                retrieved_item_ids=retrieved,
                                retrieval=result.retrieval,
                                multi_hop=result.multi_hop,
                            )
                            row.update(
                                retrieval_metrics(retrieved, row["gold_item_ids"])
                            )
                            row["recall_any"] = len(
                                set(retrieved) & set(row["gold_item_ids"])
                            ) / len(row["gold_item_ids"])
                            stage.set("controlled:judge")
                            judgement = await judge.correctness(q, row["answer"])
                            row.update(
                                correctness=judgement["score"], judgement=judgement
                            )
                        except Exception as exc:  # noqa: BLE001
                            row["error"] = error_text(exc)
                            row["provider_blocked"] = capacity_error(exc)
                        append("controlled_replays", row)
                        append(
                            "usage",
                            {"time": datetime.now(UTC), "usage": meter.summary()},
                        )
                        if row.get("provider_blocked"):
                            raise ProviderCapacityError(
                                "Provider capacity unavailable; replay checkpoint saved"
                            )
                        print(
                            "controlled",
                            experiment,
                            config,
                            q["id"],
                            mismatches,
                            row.get("correctness"),
                            row.get("error", ""),
                            flush=True,
                        )
        finally:
            append(
                "usage_final",
                {
                    "action": "controlled",
                    "time": datetime.now(UTC),
                    "usage": meter.summary(),
                },
            )
            await judge.close()
            await rt.close()
            await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
