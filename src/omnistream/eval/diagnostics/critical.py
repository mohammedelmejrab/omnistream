"""Audit source-required atomic bridge assertions, beyond item-level recall."""

import json
import re

from omnistream.eval.diagnostics.run import DATA, IDS, OUT, read


def main():
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    traces = {}
    for row in read("stages"):
        if row["configuration"] == "own" and row["experiment"] in (
            "E3",
            "E3history",
            "E4trace",
            "E4tracehistory",
            "E1",
            "E4",
        ):
            traces.setdefault((row["experiment"], row["question_id"]), {})[
                row["event"]
            ] = row
    items = {i["id"]: i for i in DATA["items"]}
    rows = []
    for q in DATA["questions"]:
        if q["type"] != "multi_hop" or "visiting fellowship" not in q["question"]:
            continue
        leader = next(i for i in q["gold"] if i.endswith("-leader"))
        study = next(i for i in q["gold"] if i.endswith("-study"))
        person = re.search(
            r"appointed ([A-Z][A-Za-z ]+?) as chief executive", items[leader]["text"]
        )[1]
        for kind, item in (
            ("January appointment identifying the chief", leader),
            ("visiting fellowship at laboratory", study),
        ):

            def matches(entry, item=item, person=person, leader=leader):
                fact = entry["fact"]
                text = fact["fact"]
                return (
                    IDS[item] in {fact["item_id"], *fact.get("item_ids", [])}
                    and person in text
                    and (
                        "appoint" in text.lower() and "chief executive" in text.lower()
                        if item == leader
                        else "fellow" in text.lower() or "calibration" in text.lower()
                    )
                )

            matching = [f for f in graph["facts"] if matches(f)]
            ids = {f["fact"]["uuid"] for f in matching}
            conditions = {}
            for (experiment, qid), events in traces.items():
                if qid != q["id"]:
                    continue
                expanded_ids = {
                    f["id"]
                    for f in events.get("expansion", {})
                    .get("graph", {})
                    .get("facts", [])
                }
                ranking = events.get("fusion", {}).get("full_ranking", [])
                conditions[experiment] = {
                    "in_expansion": bool(ids & expanded_ids),
                    "fused_ranks": [
                        rank
                        for rank, f in enumerate(ranking, 1)
                        if f["fact"]["id"] in ids
                    ],
                }
            rows.append(
                {
                    "question_id": q["id"],
                    "person": person,
                    "required_bridge": kind,
                    "source_item": item,
                    "source_text": items[item]["text"],
                    "extracted_facts": [
                        {k: v for k, v in f["fact"].items() if "embedding" not in k}
                        for f in matching
                    ],
                    "conditions": conditions,
                }
            )
    (OUT / "critical_bridges.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    for row in rows:
        print(
            row["question_id"],
            row["required_bridge"],
            len(row["extracted_facts"]),
            row["conditions"].get("E4trace"),
            row["conditions"].get("E4tracehistory"),
        )


if __name__ == "__main__":
    main()
