"""Check whether the live clock could confound saved rankings/validity."""

import json
import sqlite3
from datetime import UTC, datetime

from omnistream.eval.diagnostics.run import OUT, SNAP, read
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts


def main():
    start = datetime.fromisoformat(read("metadata")[0]["time"])
    end = datetime.now(UTC)
    con = sqlite3.connect(f"file:{(SNAP / 'state.db').as_posix()}?mode=ro", uri=True)
    lives = dict(con.execute("SELECT id,half_life_days FROM bubbles"))
    con.close()
    checked = changed = 0
    changes = []
    for row in read("stages"):
        if row["event"] != "fusion":
            continue
        candidates = [
            FactCandidate(
                **{**c, "published_at": datetime.fromisoformat(c["published_at"])}
            )
            for c in row["candidates"]
        ]
        first = [
            f.fact.id
            for f in fuse_facts(candidates, now=start, half_lives=lives, top_n=None)
        ]
        last = [
            f.fact.id
            for f in fuse_facts(candidates, now=end, half_lives=lives, top_n=None)
        ]
        checked += 1
        if first != last:
            changed += 1
            changes.append(
                {k: row[k] for k in ("experiment", "configuration", "question_id")}
            )
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))

    def valid(fact, now):
        lo = datetime.fromisoformat(fact["valid_at"]) if fact.get("valid_at") else None
        hi = (
            datetime.fromisoformat(fact["invalid_at"])
            if fact.get("invalid_at")
            else None
        )
        return (
            not fact.get("expired_at")
            and (lo is None or lo <= now)
            and (hi is None or now < hi)
            and (lo is None or hi is None or lo < hi)
        )

    validity_changes = [
        f["fact"]["uuid"]
        for f in graph["facts"]
        if valid(f["fact"], start) != valid(f["fact"], end)
    ]
    result = {
        "start": str(start),
        "end": str(end),
        "rankings_checked": checked,
        "rankings_changed": changed,
        "changes": changes,
        "fact_validity_changes": validity_changes,
    }
    (OUT / "clock_sensitivity.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(result)


if __name__ == "__main__":
    main()
