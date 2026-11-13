"""Export preserved manual readings and the reviewed generic-name rule."""

import json
import re
from pathlib import Path

from omnistream.eval.diagnostics.run import OUT, read


def main():
    reviews = json.loads(
        Path(__file__).with_name("manual_reviews.json").read_text(encoding="utf-8")
    )
    sample = {r["id"]: r for r in read("fact_quality")}
    for row in reviews["facts"]:
        assert row["id"] in sample and row["index"] == sample[row["id"]]["index"]
        row["judge_label"] = sample[row["id"]]["label"]
    (OUT / "fact_quality_manual20.jsonl").write_text(
        "\n".join(json.dumps(r) for r in reviews["facts"]) + "\n", encoding="utf-8"
    )
    (OUT / "merge_quality_review.json").write_text(
        json.dumps(reviews["merges"], indent=2), encoding="utf-8"
    )
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    labels = {
        "Accountants",
        "DATA DEPOSIT",
        "ANALYST NOTE",
        "SAFETY WIRE",
        "Resolution adopted September 18",
        "September product inspection",
        "October deadline",
    }
    generic = [
        e
        for e in graph["entities"]
        if e["name"][0].islower()
        or e["name"] in labels
        or re.fullmatch(r"[A-Z]{2,6} chief", e["name"])
    ]
    (OUT / "generic_entities.json").write_text(
        json.dumps(
            {
                "definition": "Common-noun descriptions, roles (including acronym-qualified chiefs) and document/event labels; excludes proper names, specific monetary amounts and accession identifiers. Reviewed over the full node-name inventory.",
                "count": len(generic),
                "denominator": len(graph["entities"]),
                "entities": generic,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("generic", len(generic), "/", len(graph["entities"]))


if __name__ == "__main__":
    main()
