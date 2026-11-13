"""Local real-corpus loading and deterministic, split-isolated selection."""

import hashlib
import json
import random
from pathlib import Path

SEED = 20261113


def referenced_ids(question):
    result = set(question["gold"])
    for field in ("evidence", "distractors", "acceptable_evidence"):
        for entry in question.get(field, []):
            result.add(entry["item_id"] if isinstance(entry, dict) else entry)
    return result


def selection_digest(ids):
    return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()


def load_real_dataset(split, *, background=None, root=None):
    if split not in ("dev", "test"):
        raise ValueError("real-v2 requires --split dev or test")
    if background is None:
        background = 40 if split == "dev" else 60
    if background < 0:
        raise ValueError("background must be nonnegative")
    root = Path(root) if root else Path(__file__).resolve().parents[4]
    base = root / "src/omnistream/eval"
    rows = [
        json.loads(line)
        for line in (base / "real/real-v2-manifest.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    manifest = {r["id"]: r for r in rows}
    if len(manifest) != len(rows):
        raise ValueError("duplicate manifest item IDs")
    annotations = json.loads(
        (base / "corpus/real-v2-questions.json").read_text(encoding="utf-8")
    )
    if annotations["corpus"] != "real-v2":
        raise ValueError("question corpus mismatch")
    questions = annotations["questions"]
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("duplicate question IDs")
    gold = {s: set() for s in ("dev", "test")}
    support = {s: set() for s in gold}
    fresh = annotations["freshness_item_ids"]
    for s in gold:
        if not set(fresh[s]) <= manifest.keys():
            raise ValueError("unknown freshness item IDs")
        question_fresh = {
            i
            for q in questions
            if q["split"] == s and q["type"] == "freshness"
            for i in q["gold"]
        }
        if not set(fresh[s]) <= question_fresh:
            raise ValueError("freshness item has no probe question")
    if set(fresh["dev"]) & set(fresh["test"]):
        raise ValueError("freshness split overlap")
    for q in questions:
        if q["split"] not in gold:
            raise ValueError("invalid question split")
        if not q["gold"] or not referenced_ids(q) <= manifest.keys():
            raise ValueError("unknown or empty question item IDs")
        if not all(
            q.get(k)
            for k in ("question", "reference_answer", "key_facts", "expected_bubbles")
        ):
            raise ValueError("missing scoring fields")
        if not set(q["expected_bubbles"]) <= {"News", "Finance", "Research"}:
            raise ValueError("invalid expected bubbles")
        if q["type"] not in {"single", "multi_hop", "time_sensitive", "freshness"}:
            raise ValueError("invalid question type")
        if q["type"] == "freshness" and not set(q["gold"]) & set(fresh[q["split"]]):
            raise ValueError("freshness question needs held-back gold")
        acceptable = q.get("acceptable_evidence", [])
        if not isinstance(acceptable, list) or any(not isinstance(i, str) for i in acceptable):
            raise ValueError("acceptable_evidence must be a list of item IDs")
        if len(acceptable) != len(set(acceptable)) or set(acceptable) & set(q["gold"]):
            raise ValueError("acceptable evidence must be distinct from gold")
        if set(acceptable) & set(q.get("distractors", [])):
            raise ValueError("acceptable evidence cannot be a distractor")
        for field in ("exclude_from_scoring", "date_order_unavailable", "exclude_from_freshness_scoring"):
            if field in q and not isinstance(q[field], bool):
                raise ValueError(field + " must be boolean")
        if q.get("exclude_from_scoring") and (not isinstance(q.get("exclusion_reason"), str) or not q["exclusion_reason"].strip()):
            raise ValueError("excluded question requires exclusion_reason")
        if (q.get("date_order_unavailable") or q.get("exclude_from_freshness_scoring")) and not q.get("exclude_from_scoring"):
            raise ValueError("special scoring exclusion requires exclude_from_scoring")
        gold[q["split"]].update(q["gold"])
        support[q["split"]].update(q["gold"] + acceptable)
        support[q["split"]].update(e["item_id"] for e in q.get("evidence", []))
    if gold["dev"] & gold["test"]:
        raise ValueError("dev/test gold overlap")
    if gold["dev"] & support["test"] or gold["test"] & support["dev"]:
        raise ValueError("dev/test gold versus evidence overlap")
    split_questions = [dict(q) for q in questions if q["split"] == split]
    selected_questions = [q for q in split_questions if not q.get("exclude_from_scoring", False)]
    excluded_questions = [q for q in split_questions if q.get("exclude_from_scoring", False)]
    if not selected_questions:
        raise ValueError("split has no questions")
    needed = set(fresh[split])
    for q in split_questions:
        needed.update(referenced_ids(q))
        # Evidence quotes are annotations, not alternative sufficient evidence.
        q["acceptable_evidence"] = sorted(
            set(q.get("acceptable_evidence", [])) - set(q["gold"])
        )
    other = "test" if split == "dev" else "dev"
    forbidden = gold[other] | set(fresh[other])
    if needed & forbidden:
        raise ValueError("split references held-out gold/freshness")
    candidates = sorted(manifest.keys() - needed - forbidden)
    sampled = random.Random(SEED).sample(candidates, min(background, len(candidates)))
    selected = sorted(needed | set(sampled))
    labels = {
        r["item_id"]: r["routing_labels"] for r in annotations.get("routing_labels", [])
    }
    if not labels.keys() <= manifest.keys() or any(
        not set(values) <= {"News", "Finance", "Research"} for values in labels.values()
    ):
        raise ValueError("invalid routing annotation")
    items = []
    for item_id in selected:
        row = manifest[item_id]
        path = (root / row["text_path"]).resolve()
        if not path.is_relative_to((root / "data/real/real-v2").resolve()):
            raise ValueError("text path outside local corpus")
        text = path.read_text(encoding="utf-8")
        if (
            row.get("sha256")
            and hashlib.sha256(text.encode()).hexdigest() != row["sha256"]
        ):
            raise ValueError("clean text SHA-256 mismatch: " + item_id)
        items.append(
            {
                "id": item_id,
                "text": text,
                "title": row["title"],
                "url": row["url"],
                "published_at": row["published_at"],
                "source": row["source"],
                "credibility": row.get("credibility", 0.5),
                "bubbles": [],
                "routing_label": labels.get(item_id, []),
                "freshness": item_id in fresh[split],
            }
        )
    return {
        "version": "2-real",
        "corpus": "real-v2",
        "split": split,
        "background": background,
        "selection_seed": SEED,
        "selected_item_ids": selected,
        "selected_item_ids_sha256": selection_digest(selected),
        "items": items,
        "questions": selected_questions,
        "excluded_questions": excluded_questions,
    }
