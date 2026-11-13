"""LLM-free own-mode tracing, all bubbles, to inspect E3 before answer runs end."""

import argparse
import asyncio
import json

from omnistream.eval.diagnostics.run import (
    CASE,
    DATA,
    GROUPS,
    OUT,
    append,
    build,
    gold_entities,
    install_traces,
)
from omnistream.retrieval.models import TimeScope


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    _, repo, rt = build()
    try:
        await rt.initialize()
        install_traces(rt)
        for question in DATA["questions"]:
            if question["type"] != "multi_hop":
                continue
            case = {
                "experiment": ("E4trace" if args.oracle else "E3")
                + ("history" if args.history else ""),
                "configuration": "own",
                "question_id": question["id"],
            }
            if args.oracle:
                case["oracle_entities"] = sorted(gold_entities(question, graph))
            CASE.set(case)
            result = await asyncio.to_thread(
                rt.dispatcher.retrieve,
                question["question"],
                mode="own",
                bubbles=GROUPS,
                time_scope=TimeScope() if args.history else None,
            )
            append("trace_results", {**case, "result": result})
            print(
                case["experiment"],
                question["id"],
                len(result.seeds),
                len(result.facts),
                flush=True,
            )
    finally:
        await rt.close()
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
