"""Supplement E2: isolate the historical router model, without changing Settings."""

import asyncio
from datetime import UTC, datetime

from omnistream.eval.diagnostics.run import DATA, append, build, read
from omnistream.eval.resources import UsageMeter, stage
from omnistream.llm import LLMClient
from omnistream.retrieval.router import QueryRouter


async def main():
    settings, repo, rt = build()
    old = LLMClient(settings, model="deepseek/deepseek-chat")
    router = QueryRouter(old, rt.embeddings, rt.catalog)
    done = {
        (r["question_id"], r["repeat"])
        for r in read("router_old_model")
        if not r.get("error")
    }
    with UsageMeter() as meter:
        try:
            for q in DATA["questions"]:
                if q["type"] != "multi_hop":
                    continue
                for repeat in range(5):
                    if (q["id"], repeat) in done:
                        continue
                    stage.set("E2:old_router_model")
                    decision = await asyncio.to_thread(router.route, q["question"])
                    append(
                        "router_old_model",
                        {
                            "question_id": q["id"],
                            "type": q["type"],
                            "repeat": repeat,
                            "model": old.model,
                            "time": datetime.now(UTC),
                            "decision": decision,
                        },
                    )
                append("usage", {"time": datetime.now(UTC), "usage": meter.summary()})
                print("old-router control", q["id"], flush=True)
        finally:
            append(
                "usage_final",
                {
                    "action": "old_router_control",
                    "time": datetime.now(UTC),
                    "usage": meter.summary(),
                },
            )
            if old._client is not None:
                await asyncio.to_thread(old._client.close)
            await rt.close()
            await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
