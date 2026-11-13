"""Verify frozen file bytes and graph properties against initial exports."""

import asyncio
import hashlib
import json

from omnistream.eval.diagnostics.run import (
    OUT,
    SNAP,
    append,
    build,
    digest,
    encode,
    graph_export,
    read,
)


def fingerprint(graph):
    canonical = {
        "entities": sorted(graph["entities"], key=lambda e: e["id"]),
        "facts": sorted(graph["facts"], key=lambda f: f["fact"]["uuid"]),
        "episodes": sorted(
            [{**ep, "entities": sorted(ep["entities"])} for ep in graph["episodes"]],
            key=lambda ep: ep["id"],
        ),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


async def main():
    initial = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    _, repo, rt = build()
    try:
        current = json.loads(
            json.dumps(
                graph_export(rt),
                default=encode,
            )
        )
        before = read("metadata")[0]["snapshot_hashes"]
        after = {
            str(p.relative_to(SNAP)): digest(p)
            for p in SNAP.rglob("*")
            if p.is_file() and "runs" not in p.parts
        }
        result = {
            "action": "final_verification",
            "unchanged": before == after,
            "changed": [p for p in before if before[p] != after.get(p)],
            "graph_unchanged": fingerprint(initial) == fingerprint(current),
            "graph_before_sha256": fingerprint(initial),
            "graph_after_sha256": fingerprint(current),
        }
        append("integrity", result)
        print(result)
    finally:
        await rt.close()
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
