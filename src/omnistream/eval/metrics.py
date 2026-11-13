"""Deterministic metrics. Items are deduplicated in first-retrieval order."""

from statistics import mean


def retrieval_metrics(retrieved, gold, acceptable=()):
    ranked = list(dict.fromkeys(retrieved))
    gold = set(gold)
    rank = next(
        (i for i, item in enumerate(ranked, 1) if item in gold | set(acceptable)), None
    )
    return {
        "recall_at_10": len(set(ranked[:10]) & gold) / len(gold) if gold else 0.0,
        "mrr": 1 / rank if rank else 0.0,
        "hits_at_1": float(rank == 1),
    }


def routing_metrics(selected, expected):
    selected, expected = set(selected), set(expected)
    overlap = len(selected & expected)
    return {
        "routing_recall": overlap / len(expected) if expected else 1.0,
        "routing_precision": overlap / len(selected) if selected else 0.0,
    }


def aggregate(results):
    def group(values):
        metrics = {}
        for key in (
            "recall_at_10",
            "mrr",
            "hits_at_1",
            "correctness",
            "routing_recall",
            "routing_precision",
            "latency_seconds",
        ):
            vals = [r[key] for r in values if r.get(key) is not None]
            metrics[key] = mean(vals) if vals else None
        judged = [r for r in values if r.get("citation_count") is not None]
        total = sum(r["citation_count"] for r in judged)
        metrics["citation_faithfulness_micro"] = (
            sum(r.get("faithful_citations", 0) for r in judged) / total
            if total
            else None
        )
        metrics["citation_faithfulness"] = (
            mean(
                r.get("faithful_citations", 0) / r["citation_count"]
                if r["citation_count"]
                else 0.0
                for r in judged
            )
            if judged
            else None
        )
        metrics["citation_faithfulness_macro"] = metrics["citation_faithfulness"]
        changed = [
            r
            for r in values
            if r["type"] == "time_sensitive" and r.get("correctness") is not None
        ]
        metrics["changed_fact_accuracy"] = (
            mean(float(r["correctness"] == 2) for r in changed) if changed else None
        )
        metrics["errors"] = sum(
            bool(r.get("error") or r.get("judgement_errors")) for r in values
        )
        metrics["correctness_errors"] = sum(
            "correctness" in r.get("judgement_errors", {}) for r in values
        )
        metrics["faithfulness_errors"] = sum(
            "faithfulness" in r.get("judgement_errors", {}) for r in values
        )
        metrics["zero_citation_answers"] = sum(
            r.get("citation_count") == 0 for r in values
        )
        metrics["abstentions"] = sum(
            r.get("correctness") == 0 and r.get("citation_count") == 0 for r in values
        )
        metrics["questions"] = len(values)
        return metrics

    output = {}
    for config in dict.fromkeys(r["configuration"] for r in results):
        values = [r for r in results if r["configuration"] == config]
        output[config] = group(values)
        output[config]["by_type"] = {
            kind: group([r for r in values if r["type"] == kind])
            for kind in dict.fromkeys(r["type"] for r in values)
        }
    return output


def success_criteria(metrics, global_metrics):
    checks = {}

    def threshold(label, value, target, lower=True):
        checks[label] = {
            "value": value,
            "target": target,
            "status": "UNMEASURED"
            if value is None
            else (
                "PASS" if (value >= target if lower else value <= target) else "FAIL"
            ),
        }

    for name, m in metrics.items():
        if name != "external":
            threshold(name + ": query routing recall", m["routing_recall"], 0.9)
            threshold(name + ": query routing precision", m["routing_precision"], 0.7)
        threshold(name + ": citation faithfulness", m["citation_faithfulness"], 0.9)
        threshold(name + ": changed-fact accuracy", m["changed_fact_accuracy"], 0.8)
        checks[name + ": MRR / Hits@1 reported"] = {
            "value": [m["mrr"], m["hits_at_1"]],
            "target": "reported",
            "status": "PASS",
        }
    classic = metrics.get("classic", {}).get("by_type", {}).get("multi_hop", {})
    for name in ("graphiti", "own", "own+subagents"):
        v = (
            metrics.get(name, {})
            .get("by_type", {})
            .get("multi_hop", {})
            .get("recall_at_10")
        )
        base = classic.get("recall_at_10")
        threshold(
            name + ": multi-hop recall improvement",
            v - base if v is not None and base is not None else None,
            1e-12,
        )
    full = (
        metrics.get("own+subagents", {})
        .get("by_type", {})
        .get("multi_hop", {})
        .get("correctness")
    )
    for base in ("classic", "external"):
        value = (
            metrics.get(base, {})
            .get("by_type", {})
            .get("multi_hop", {})
            .get("correctness")
        )
        threshold(
            "Full system multi-hop correctness gain vs " + base,
            full - value if full is not None and value is not None else None,
            0.3,
        )
    for key, target, lower in [
        ("ingestion_routing_accuracy", 0.85, True),
        ("duplicate_entity_rate", 0.05, False),
        ("peak_memory_bytes", 4 * 1024**3, False),
    ]:
        threshold(key, global_metrics.get(key), target, lower)
    threshold(
        "freshness max answerable lag seconds",
        global_metrics.get("freshness_max_lag_seconds"),
        global_metrics.get("freshness_target_seconds", 1200),
        False,
    )
    if global_metrics.get("freshness_answerable_count", 10) < 10:
        checks["freshness max answerable lag seconds"]["status"] = "FAIL"
        checks["freshness max answerable lag seconds"]["reason"] = (
            "Not all ten injected items became answerable"
        )
    if "audit_sample_size" in global_metrics:
        threshold("entity audit sample size", global_metrics["audit_sample_size"], 100)
    checks["ungrounded entity rate reported"] = {
        "value": global_metrics.get("ungrounded_entity_rate"),
        "target": "reported",
        "status": "PASS"
        if global_metrics.get("ungrounded_entity_rate") is not None
        else "UNMEASURED",
    }
    for label, check in checks.items():
        dependencies = []
        if label.endswith(": citation faithfulness"):
            dependencies = [(label.split(":")[0], "faithfulness_errors")]
        elif label.endswith(": changed-fact accuracy"):
            dependencies = [(label.split(":")[0], "correctness_errors")]
        elif label.startswith("Full system multi-hop correctness gain vs "):
            dependencies = [
                ("own+subagents", "correctness_errors"),
                (label.rsplit(" ", 1)[1], "correctness_errors"),
            ]
        failed = sum(metrics.get(name, {}).get(key, 0) for name, key in dependencies)
        if failed:
            check.update(
                status="UNMEASURED",
                failed_judgements=failed,
                reason=f"{failed} failed judgements; value is partial",
            )
    return checks


def ingestion_routing_metrics(items, entries, groups):
    exact = primary = wrong = extras = 0
    categories = {}
    for item in items:
        labelled = {groups[b] for b in item["bubbles"]}
        assigned = set(entries[item["id"]].get("bubbles", []))
        extra = len(assigned - labelled)
        exact += assigned == labelled
        primary += labelled <= assigned
        wrong += not labelled <= assigned
        extras += extra
        category = item.get("category") or item["id"].split("-", 1)[-1]
        bucket = categories.setdefault(category, {"items": 0, "over_assignments": 0})
        bucket["items"] += 1
        bucket["over_assignments"] += extra
    n = len(items)
    return {
        "ingestion_routing_accuracy": exact / n if n else None,
        "ingestion_primary_label_recall": primary / n if n else None,
        "ingestion_over_assignment_rate": extras / n if n else None,
        "ingestion_wrong_routing_rate": wrong / n if n else None,
        "ingestion_over_assignments_by_category": categories,
    }
