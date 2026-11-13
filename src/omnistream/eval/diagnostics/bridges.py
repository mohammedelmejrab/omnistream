"""Audit whether source-discriminating entities have usable factual edges."""

import json
import re

from omnistream.eval.diagnostics.run import DATA, IDS, OUT, REVERSE, gold_entities


def main():
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    rows = []
    for item in DATA["items"]:
        if not item["id"].endswith("-recall"):
            continue
        phrase = re.search(r"identified a defective ([^.]+)\.", item["text"])[1]
        entities = [
            e
            for e in graph["entities"]
            if e["name"].casefold() in (phrase, "defective " + phrase)
        ]
        relevant = [
            f
            for f in graph["facts"]
            if IDS[item["id"]] in {f["fact"]["item_id"], *f["fact"].get("item_ids", [])}
        ]
        edges = [
            f
            for f in relevant
            if any(e["id"] in (f["subject"], f["object"]) for e in entities)
        ]
        rows.append(
            {
                "item": item["id"],
                "discriminator": phrase,
                "entities": entities,
                "source_facts": [
                    {k: v for k, v in f["fact"].items() if "embedding" not in k}
                    for f in edges
                ],
                "classification": "entity missing"
                if not entities
                else "fact missing"
                if not edges
                else "connected",
            }
        )
    (OUT / "discriminator_connectivity.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    print([(r["item"], r["classification"]) for r in rows])
    dates = [
        {
            "item": REVERSE[f["fact"]["item_id"]],
            "text": f["fact"]["fact"],
            "valid_at": f["fact"].get("valid_at"),
            "published_at": f["fact"].get("published_at"),
        }
        for f in graph["facts"]
        if "terminated" in f["fact"]["fact"].lower()
    ]
    (OUT / "termination_dates.json").write_text(
        json.dumps(dates, indent=2), encoding="utf-8"
    )
    bad_items = {r["item"] for r in rows if r["classification"] != "connected"}
    bad_global_ids = {
        "a94cb9e6ac37402dbdaed7c2a1461868",
        "e32f37a96b7940c4b7ec2ffa89200bb3",
    }
    bad_entities = {
        e["id"] for e in graph["entities"] if e["global_id"] in bad_global_ids
    }
    affected = {
        q["id"]
        for q in DATA["questions"]
        if q["type"] == "multi_hop" and set(q["gold"]) & bad_items
    }
    wrong_merge = {
        q["id"]
        for q in DATA["questions"]
        if q["type"] == "multi_hop" and gold_entities(q, graph) & bad_entities
    }
    connections = json.loads((OUT / "connectivity.json").read_text(encoding="utf-8"))
    alias = {
        r["question_id"]
        for r in connections
        if not r["single_entity_rooted_within_two"]
        and r["alias_join_rooted_within_two"]
    }
    (OUT / "cause_exposure.json").write_text(
        json.dumps(
            {
                "missing_discriminator": sorted(affected),
                "wrong_named_identity": sorted(wrong_merge),
                "alias_connectivity_failure": sorted(alias),
                "structural_union": sorted(affected | wrong_merge | alias),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
