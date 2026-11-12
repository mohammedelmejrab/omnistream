"""Versioned fictional evaluation data and validation."""

import json
import re
from collections import Counter
from pathlib import Path

CONFIGURATIONS = (
    "external",
    "classic",
    "graphiti",
    "own",
    "own+subagents",
    "classic+subagents",
)
COUNTS = {"single": 15, "multi_hop": 20, "time_sensitive": 15, "freshness": 10}


def parse_rows(rows=None):
    if not rows or rows == ["all"]:
        return list(CONFIGURATIONS)
    names = [part.strip() for row in rows for part in row.split(",")]
    if not names or any(n not in CONFIGURATIONS for n in names):
        raise ValueError(
            "rows must be all or comma-separated configurations: "
            + ", ".join(CONFIGURATIONS)
        )
    return list(dict.fromkeys(names))


def load_dataset(name="eval-v1"):
    data = json.loads(
        (Path(__file__).parent / "corpus" / (name + ".json")).read_text(
            encoding="utf-8"
        )
    )
    validate_dataset(data)
    return data


def validate_dataset(data):
    assert Counter(q["type"] for q in data["questions"]) == COUNTS
    ids = {i["id"] for i in data["items"]}
    assert len(ids) == len(data["items"]) and 60 <= len(ids) <= 100
    assert sum(i["freshness"] for i in data["items"]) == 10
    assert len({q["id"] for q in data["questions"]}) == 60
    for i in data["items"]:
        assert 80 <= len(i["text"].split()) <= 250
        assert i["bubbles"] and 0 <= i["credibility"] <= 1 and i["published_at"]
    freshness_ids = {i["id"] for i in data["items"] if i["freshness"]}
    for q in data["questions"]:
        if q["type"] == "freshness":
            assert set(q["gold"]) & freshness_ids
            injected_text = " ".join(
                i["text"]
                for i in data["items"]
                if i["id"] in set(q["gold"]) & freshness_ids
            )
            assert all(f.casefold() in injected_text.casefold() for f in q["key_facts"])
        assert set(q.get("acceptable_evidence", [])) <= ids
        assert not set(q.get("acceptable_evidence", [])) & set(q["gold"])
        assert q["gold"] and set(q["gold"]) <= ids
        assert q["expected_bubbles"] and q["reference_answer"] and q["key_facts"]
        assert set(q["expected_bubbles"]) <= {"News", "Finance", "Research"}

    if data["version"].startswith("2"):
        assert 80 <= len(ids) <= 100
        assert sum(bool(i.get("routing_label")) for i in data["items"]) >= 50
        items = {i["id"]: i for i in data["items"]}
        for q in data["questions"]:
            if q["type"] != "multi_hop":
                continue
            gold = [items[i] for i in q["gold"]]
            assert len(gold) >= 2
            assert len({b for i in gold for b in i["bubbles"]}) >= 2
            # Capitalized proper-name tokens, excluding sentence starters/domain nouns.
            stop = {
                "Which",
                "What",
                "Who",
                "The",
                "After",
                "Before",
                "News",
                "Finance",
                "Research",
            }
            names = set(re.findall(r"\b[A-Z][a-zA-Z-]{3,}\b", q["question"])) - stop
            for token in names:
                assert not all(
                    re.search(
                        r"\b" + re.escape(token) + r"\b", i["text"], re.IGNORECASE
                    )
                    for i in gold
                ), (q["id"], token)
