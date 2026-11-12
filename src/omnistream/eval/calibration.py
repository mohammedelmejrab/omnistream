"""Real answer calibration export and independent human agreement (O3)."""

import json
from collections import Counter, defaultdict
from pathlib import Path

SAMPLE = Path(__file__).parent / "calibration/eval-v2-calibration.jsonl"


def export_sample(
    root, destination=SAMPLE, minimum=30, run="latest", dataset_name="eval-v2"
):
    """Sample one v2 checkpoint by score, balancing configurations/types; blind labels."""
    from .dataset import load_dataset

    if dataset_name != "eval-v2":
        raise ValueError("Calibration requires a v2 run")
    root, destination = Path(root), Path(destination)
    if destination.exists() and any(
        str(json.loads(line).get("human_score", "")).strip()
        for line in destination.read_text(encoding="utf-8").splitlines()
    ):
        raise ValueError("Existing calibration has human labels; refusing to overwrite")
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    chosen = (
        max(candidates, key=lambda p: int(p.name))
        if run == "latest" and candidates
        else root / str(run)
    )
    path = chosen / "answers.jsonl"
    references = {q["id"]: q for q in load_dataset(dataset_name)["questions"]}
    buckets = defaultdict(list)
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        pair = (row["configuration"], row["question_id"])
        if row["question_id"] not in references:
            raise ValueError("Checkpoint contains non-v2 questions")
        if (
            pair in seen
            or row.get("correctness") not in (0, 1, 2)
            or not row.get("answer")
        ):
            continue
        seen.add(pair)
        buckets[row["correctness"]].append(row)
    available = sum(map(len, buckets.values()))
    if available < minimum:
        raise ValueError(
            f"Need {minimum} real v2 rows from one run; found {available} in {path}. No export written."
        )
    sample, configs, kinds = [], Counter(), Counter()
    while len(sample) < minimum:
        for score in (0, 1, 2):
            if not buckets[score] or len(sample) == minimum:
                continue
            row = min(
                buckets[score],
                key=lambda r: (
                    configs[r["configuration"]],
                    kinds[r["type"]],
                    r["question_id"],
                ),
            )
            buckets[score].remove(row)
            sample.append(row)
            configs[row["configuration"]] += 1
            kinds[row["type"]] += 1
    labels, keys = [], []
    # Deterministic shuffle hides the score-stratified selection order.
    import random

    random.Random(713).shuffle(sample)
    for index, row in enumerate(sample, 1):
        q = references[row["question_id"]]
        sample_id = f"c{index:03}"
        labels.append(
            {
                "sample_id": sample_id,
                "question": q["question"],
                "answer": row["answer"],
                "reference_answer": q["reference_answer"],
                "key_facts": q["key_facts"],
                "key_fact_alternatives": q.get("key_fact_alternatives", []),
                "human_score": "",
            }
        )
        keys.append(
            {
                "sample_id": sample_id,
                "judge_score": row["correctness"],
                "configuration": row["configuration"],
                "question_id": row["question_id"],
                "type": q["type"],
                "source_checkpoint": str(path),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    for target, rows in (
        (destination, labels),
        (destination.with_suffix(".key.jsonl"), keys),
    ):
        target.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return len(sample)


def agreement(rows):
    labelled = [
        r for r in rows if str(r.get("human_score", "")).strip() in ("0", "1", "2")
    ]
    if not labelled:
        return {"status": "pending human labels", "n": len(rows), "labelled": 0}
    pairs = [(int(r["human_score"]), int(r["judge_score"])) for r in labelled]
    exact = sum(a == b for a, b in pairs) / len(pairs)
    humans = Counter(a for a, b in pairs)
    judges = Counter(b for a, b in pairs)
    chance = sum(humans[k] * judges[k] for k in (0, 1, 2)) / len(pairs) ** 2
    return {
        "status": "complete" if len(labelled) == len(rows) else "partial human labels",
        "n": len(rows),
        "labelled": len(pairs),
        "exact_agreement": exact,
        "cohens_kappa": (exact - chance) / (1 - chance) if chance < 1 else None,
    }


def calibration_report(path=SAMPLE):
    if not path.exists():
        return {"status": "pending real sample", "n": 0, "labelled": 0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    keys = {
        r["sample_id"]: r
        for r in map(
            json.loads,
            path.with_suffix(".key.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    return agreement([{**keys[r["sample_id"]], **r} for r in rows])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--export-from", type=Path)
    args = parser.parse_args()
    if args.export_from:
        print("Real calibration triples:", export_sample(args.export_from))
    print(json.dumps(calibration_report(), indent=2))
