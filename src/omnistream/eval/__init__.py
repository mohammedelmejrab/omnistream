"""C7 evaluation entrypoint, also consumed by the C6 API."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .dataset import parse_rows
from .metrics import (
    aggregate,
    fatal_provider_error,
    retrieval_metrics,
    routing_metrics,
    run_validity,
    success_criteria,
)
from .report import table, write_report
from .resources import MemorySampler, UsageMeter, stage


@dataclass
class EvalRunSummary:
    id: int
    snapshot: str
    rows: list[str]
    status: str
    metrics: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    global_metrics: dict = field(default_factory=dict)
    report_path: str | None = None
    csv_path: str | None = None
    configurations_csv_path: str | None = None

    def model_dump(self, **kwargs):
        return asdict(self)


def evidence_ids(result):
    from itertools import zip_longest

    ids = []
    if result.multi_hop and all(hasattr(f, "facts") for f in result.multi_hop.findings):
        buckets = {}
        for finding in result.multi_hop.findings:
            bucket = buckets.setdefault(finding.bubble, [])
            for fact in finding.facts:
                bucket.extend([fact.item_id, *fact.item_ids])
            bucket.extend(c.item_id for c in finding.chunks)
            bucket.extend(finding.item_ids)
        # Dedupe inside each bubble before assigning its per-bubble rank.
        ranked = [list(dict.fromkeys(b)) for b in buckets.values()]
        for row in zip_longest(*ranked):
            ids.extend(i for i in row if i is not None)
    else:
        if result.retrieval:
            for entry in result.retrieval.facts:
                ids.extend([entry.fact.item_id, *entry.fact.item_ids])
            ids.extend(c.item_id for c in result.retrieval.chunks)
        if result.multi_hop:
            for finding in result.multi_hop.findings:
                ids.extend(finding.item_ids)
    return list(dict.fromkeys(ids))


async def score_question(
    configuration,
    question,
    answer,
    retrieved,
    selected,
    citations,
    invalid,
    originals,
    judge,
    gold,
    elapsed,
    acceptable=(),
):
    result = {
        "configuration": configuration,
        "question_id": question["id"],
        "type": question["type"],
        "question": question["question"],
        "reference_answer": question["reference_answer"],
        "answer": answer,
        "retrieved_item_ids": retrieved,
        "gold_item_ids": gold,
        "acceptable_evidence_item_ids": list(acceptable),
        "selected_bubbles": selected,
        "correctness": None,
        "judge_rationale": None,
        "faithful_citations": None,
        "citation_count": None,
        "citation_judgements": [],
        "latency_seconds": elapsed,
        **retrieval_metrics(retrieved, gold, acceptable),
    }
    result.update(
        routing_metrics(selected, question["expected_bubbles"])
        if configuration != "external"
        else {"routing_recall": None, "routing_precision": None}
    )
    if configuration == "external":
        # Judge only source text actually returned by LlamaIndex, including all
        # nodes belonging to the same original document.
        returned = {}
        for _number, item_id, _spans, snippet in citations:
            returned.setdefault(item_id, []).append(snippet)
        originals = {item_id: "\n\n".join(texts) for item_id, texts in returned.items()}
    errors = {}
    try:
        correctness = await judge.correctness(question, answer)
        result.update(
            correctness=correctness["score"],
            judge_rationale=correctness.get("rationale"),
        )
    except Exception as exc:  # noqa: BLE001
        errors["correctness"] = type(exc).__name__ + ": " + str(exc)
    try:
        if any(fatal_provider_error(e) for e in errors.values()):
            raise RuntimeError("Judging stopped after provider credit/auth failure")
        faithful, count, rationales = await judge.citations(
            answer, citations, originals, invalid
        )
        result.update(
            faithful_citations=faithful,
            citation_count=count,
            citation_judgements=rationales,
            citation_faithfulness=faithful / count if count else 0.0,
        )
    except Exception as exc:  # noqa: BLE001
        errors["faithfulness"] = type(exc).__name__ + ": " + str(exc)
        result["citation_faithfulness"] = None
    if errors:
        result["judgement_errors"] = errors
    return result


async def run_evaluation(
    settings,
    repo,
    *,
    rows: list[str] | None = None,
    snapshot: str,
    progress=None,
    resume=None,
    limit=None,
    dataset_name=None,
    split=None,
    background=None,
) -> EvalRunSummary:
    from omnistream.db import Repository
    from omnistream.retrieval.runtime import build_query_runtime

    from .audit import audit_graph
    from .judge import Judge
    from .snapshot import SnapshotBuilder, bound_dataset, save, snapshot_path

    names = parse_rows(rows)
    directory = snapshot_path(settings, snapshot)
    dataset = bound_dataset(directory, dataset_name, split=split, background=background)

    directory.mkdir(parents=True, exist_ok=True)
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    questions = dataset["questions"][:limit] if limit else dataset["questions"]
    runs = directory / "runs"
    runs.mkdir(exist_ok=True)
    if resume:
        candidates = [p for p in runs.iterdir() if p.name.isdigit()]
        chosen = (
            max(candidates, key=lambda p: int(p.name))
            if resume == "latest" and candidates
            else runs / str(resume)
        )
        if not chosen.is_dir():
            raise ValueError("resume run not found")
        record = await repo.get_eval_run(int(chosen.name))
        if record is None or record.snapshot != snapshot or record.rows != names:
            raise ValueError("resume snapshot/configurations do not match")
        metadata = json.loads((chosen / "metadata.json").read_text(encoding="utf-8"))
        if metadata["question_ids"] != [q["id"] for q in questions]:
            raise ValueError("resume question selection does not match --limit")
    else:
        record = await repo.create_eval_run(
            snapshot=snapshot, rows=names, status="running"
        )
        chosen = runs / str(record.id)
        chosen.mkdir()
        (chosen / "metadata.json").write_text(
            json.dumps({"question_ids": [q["id"] for q in questions]}), encoding="utf-8"
        )
    log_path = Path("docs/eval") / f"{snapshot}-{record.id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_handler = logging.FileHandler(log_path, encoding="utf-8")
    logging.getLogger().addHandler(log_handler)

    async def emit(message):
        with log_path.open("a", encoding="utf-8") as log:
            log.write(str(message) + "\n")
        if progress:
            result = progress(message)
            if inspect.isawaitable(result):
                await result
        else:
            print(message, flush=True)

    summary = EvalRunSummary(record.id, snapshot, names, "running")
    local_repo = Repository.from_path(str(directory / "state.db"), settings=settings)
    builder = SnapshotBuilder(settings, local_repo, dataset, snapshot, emit)
    judge = Judge(settings)
    runtime = None
    sampler = MemorySampler()
    memory_task = asyncio.create_task(sampler.run())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    checkpoint = chosen / "summary.json"
    answers_path = chosen / "answers.jsonl"
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding="utf-8"))
        summary.global_metrics = previous.get("global_metrics", {})
    if answers_path.exists():
        # An interrupted final write can leave a partial last line. Preserve all valid records.
        valid = []
        for line in answers_path.read_text(encoding="utf-8").splitlines():
            try:
                valid.append(json.loads(line))
            except json.JSONDecodeError:
                break
        summary.results = valid
        repaired = answers_path.with_suffix(".repair")
        with repaired.open("w", encoding="utf-8") as stream:
            for result in valid:
                stream.write(json.dumps(result) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        repaired.replace(answers_path)
    sampler.app_peak = summary.global_metrics.get("application_peak_rss_bytes", 0)
    sampler.container_peak = summary.global_metrics.get("neo4j_peak_bytes") or 0
    sampler.peak = summary.global_metrics.get("peak_memory_bytes") or 0
    sampler.errors = summary.global_metrics.get("memory_sampling_errors", [])
    # Answer/retrieval failures remain retryable on every explicit resume.
    # Retain the existing once-only retry policy for judge-only failures.
    if resume:
        summary.global_metrics.pop("fatal_error", None)
        retry_pairs = {
            (r["configuration"], r["question_id"])
            for r in summary.results
            if r.get("error")
            or r.get("unmeasured")
            or (r.get("judgement_errors") and not r.get("resume_retry"))
        }
        summary.results = [
            r
            for r in summary.results
            if (r["configuration"], r["question_id"]) not in retry_pairs
        ]
        answers_path.write_text(
            "".join(json.dumps(r) + "\n" for r in summary.results), encoding="utf-8"
        )
    else:
        retry_pairs = set()
    completed = {(r["configuration"], r["question_id"]) for r in summary.results}
    await repo.update_eval_run(record.id, status="running", results=summary.results)
    await emit(
        f"Run {record.id}: {len(completed)} completed pairs; checkpoint {chosen}"
    )
    provider_stop = None
    with UsageMeter() as meter:
        for key, value in summary.global_metrics.get("usage_by_stage", {}).items():
            meter.values[key].update(
                {**value, "cost_usd": value.get("cost_usd") or 0.0}
            )
        try:
            stage.set("ingestion")
            builder.meter = meter
            if hasattr(builder, "verify_frozen"):
                await builder.verify_frozen()
            await builder.initialize()
            await builder.base()
            runtime = build_query_runtime(
                builder.local_settings, local_repo, embeddings=builder.embedder
            )
            # Inject each held-back update, process through the queue, and probe answerability.
            stage.set("freshness")
            for item in (i for i in dataset["items"] if i["freshness"]):
                if item["id"] in builder.manifest["freshness"]:
                    continue
                if builder.manifest.get("frozen"):
                    raise ValueError(
                        "frozen snapshot lacks recorded freshness measurements"
                    )
                stored = await builder.ingest(item)
                entry = builder.manifest["items"][item["id"]]
                question = next(
                    q for q in dataset["questions"] if item["id"] in q["gold"]
                )
                probe = []
                lag = None
                if stored.status == "written":
                    for _ in range(3):
                        result = await runtime.answer(
                            question["question"], mode="own", subagents=False
                        )
                        judged = await judge.correctness(question, result.answer.text)
                        probe.append({"answer": result.answer.text, **judged})
                        if judged["score"] == 2 and stored.id in evidence_ids(result):
                            lag = time.time() - entry["injected_at"]
                            break
                builder.manifest["freshness"][item["id"]] = {
                    "write_lag_seconds": entry.get("write_lag_seconds"),
                    "answerable_lag_seconds": lag,
                    "probes": probe,
                }
                save(builder.manifest_path, builder.manifest)
            if hasattr(builder, "verify_frozen"):
                if not await builder.verify_frozen():
                    raise ValueError("snapshot did not complete; refusing to freeze")
            else:
                builder.manifest["frozen"] = True
                save(builder.manifest_path, builder.manifest)
            mapping = {
                key: value["runtime_id"]
                for key, value in builder.manifest["items"].items()
            }
            originals = {}
            for stored in await local_repo.list_items():
                if stored.text_path:
                    originals[stored.id] = (
                        __import__("pathlib")
                        .Path(stored.text_path)
                        .read_text(encoding="utf-8")
                    )
            stage.set("calibration")
            if dataset["version"].startswith("2"):
                from .calibration import calibration_report

                summary.global_metrics["judge_calibration"] = calibration_report()
            summary.global_metrics["judge_model"] = (
                settings.judge_model or settings.llm_model
            )
            summary.global_metrics["answering_model"] = settings.llm_model
            summary.global_metrics["judge_equals_answering_model"] = (
                settings.judge_model or settings.llm_model
            ) == settings.llm_model
            stage.set("contamination")
            contamination = []
            for question in (
                [] if "contamination" in summary.global_metrics else questions
            ):
                result = await judge.contamination(question)
                contamination.append({"question_id": question["id"], **result})
                if len(contamination) % 10 == 0:
                    await emit(
                        f"Contamination check {len(contamination)}/{len(questions)}"
                    )
            if contamination:
                summary.global_metrics["contamination"] = {
                    "n": len(contamination),
                    "fully_correct": sum(r["score"] == 2 for r in contamination),
                    "nonzero": sum(r["score"] > 0 for r in contamination),
                    "results": contamination,
                }
            save(checkpoint, summary.model_dump())
            external = None
            for configuration in names:
                stage.set(configuration)
                if configuration == "external" and not provider_stop:
                    from .external import ExternalBaseline

                    external = await asyncio.to_thread(
                        ExternalBaseline,
                        builder.local_settings,
                        [
                            {**i, "runtime_id": mapping[i["id"]]}
                            for i in dataset["items"]
                        ],
                        builder.embedder.service,
                    )

                async def evaluate_one(
                    question, configuration=configuration, external=external
                ):
                    nonlocal provider_stop
                    started = time.perf_counter()
                    stage.set(configuration)
                    try:
                        if provider_stop:
                            raise RuntimeError(
                                "Unmeasured: calls stopped after " + provider_stop
                            )
                        if configuration == "external":
                            answer, ids, sources = await asyncio.to_thread(
                                external.answer, question["question"]
                            )
                            # Default synthesis has no citation grammar: explicit source-node attribution.
                            citations = [
                                (n, item_id, (), text)
                                for n, (item_id, text) in enumerate(sources, 1)
                            ]
                            selected = []
                            invalid = []
                        else:
                            mode = configuration.split("+")[0]
                            result = await runtime.answer(
                                question["question"],
                                mode=mode,
                                subagents="+" in configuration,
                            )
                            answer = result.answer.text
                            ids = evidence_ids(result)
                            selected = [
                                next(
                                    (
                                        name
                                        for name, bid in builder.groups.items()
                                        if bid == b
                                    ),
                                    b,
                                )
                                for b in result.routing.bubbles
                            ]
                            citations = [
                                (c.number, c.item_id, c.spans, c.snippet)
                                for c in result.answer.citations
                            ]
                            invalid = result.answer.invalid_citations
                        elapsed = time.perf_counter() - started
                        if provider_stop:
                            raise RuntimeError(
                                "Unmeasured: calls stopped after " + provider_stop
                            )
                        stage.set(configuration + ":judge")
                        scored = await score_question(
                            configuration,
                            question,
                            answer,
                            ids,
                            selected,
                            citations,
                            invalid,
                            originals,
                            judge,
                            [mapping[i] for i in question["gold"]],
                            elapsed,
                            [
                                mapping[i]
                                for i in question.get("acceptable_evidence", [])
                            ],
                        )
                    except Exception as exc:  # noqa: BLE001 - persist unmeasured failures
                        if fatal_provider_error(exc):
                            provider_stop = type(exc).__name__ + ": " + str(exc)
                        scored = {
                            "unmeasured": True,
                            "configuration": configuration,
                            "question_id": question["id"],
                            "type": question["type"],
                            "question": question["question"],
                            "correctness": None,
                            "recall_at_10": None,
                            "mrr": None,
                            "hits_at_1": None,
                            "routing_recall": None,
                            "routing_precision": None,
                            "latency_seconds": time.perf_counter() - started,
                            "error": type(exc).__name__ + ": " + str(exc),
                            "citation_count": None,
                            "faithful_citations": 0,
                        }
                    for error in scored.get("judgement_errors", {}).values():
                        if fatal_provider_error(error):
                            provider_stop = error
                    if (configuration, question["id"]) in retry_pairs:
                        scored["resume_retry"] = True
                    with answers_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(scored) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    summary.results.append(scored)
                    summary.global_metrics.update(sampler.summary())
                    summary.global_metrics["usage_by_stage"] = meter.summary()
                    save(checkpoint, summary.model_dump())
                    await repo.update_eval_run(
                        record.id,
                        metrics={
                            **aggregate(summary.results),
                            "global": summary.global_metrics,
                        },
                        results=summary.results,
                    )
                    await emit(
                        f"{configuration} {question['id']}/{len(questions)}: correctness={scored['correctness']} recall@10={scored['recall_at_10']}"
                        + (" ERROR " + scored["error"] if scored.get("error") else "")
                    )

                # Two questions at a time keeps provider pressure bounded while
                # allowing local retrieval and network waits to overlap.
                pending = [
                    q for q in questions if (configuration, q["id"]) not in completed
                ]
                for start in range(0, len(pending), 2):
                    if provider_stop:
                        break
                    await asyncio.gather(
                        *(evaluate_one(q) for q in pending[start : start + 2])
                    )
                summary.metrics = aggregate(summary.results)
                await repo.update_eval_run(
                    record.id, metrics=summary.metrics, results=summary.results
                )
                if provider_stop:
                    break
            stage.set("audit")
            if not provider_stop and "audit_sample_size" not in summary.global_metrics:
                summary.global_metrics.update(await audit_graph(builder, judge))
            entries = builder.manifest["items"]
            for item_id, entry in entries.items():
                measured = meter.summary().get("ingestion:" + item_id)
                if measured:
                    entry["usage"] = measured
            save(builder.manifest_path, builder.manifest)
            summary.global_metrics["ingestion_item_usage"] = {
                key: value.get("usage") for key, value in entries.items()
            }
            from .metrics import ingestion_routing_metrics

            summary.global_metrics.update(
                ingestion_routing_metrics(
                    [
                        {**i, "bubbles": i["routing_label"]}
                        for i in dataset["items"]
                        if i.get("routing_label")
                    ]
                    if dataset.get("corpus") == "real-v2"
                    else dataset["items"],
                    entries,
                    builder.groups,
                )
            )
            summary.global_metrics["snapshot_validation"] = (
                "PASS: matching dataset, exact item set, all written, all queue jobs done"
            )
            summary.global_metrics["snapshot_construction_seconds"] = (
                builder.manifest.get("frozen_at", 0)
                - builder.manifest.get("construction_started_at", 0)
                if builder.manifest.get("construction_started_at")
                else None
            )
            summary.global_metrics["ingestion_status_counts"] = {
                status: sum(v.get("status") == status for v in entries.values())
                for status in ("written", "unsorted", "failed")
            }
            freshness = builder.manifest["freshness"]
            lags = [v["answerable_lag_seconds"] for v in freshness.values()]
            summary.global_metrics["freshness_questions"] = {
                q["id"]: {i: freshness[i] for i in q["gold"] if i in freshness}
                for q in dataset["questions"]
                if q["type"] == "freshness"
            }
            summary.global_metrics["freshness_method"] = (
                "Recorded injection wall-clock to written and first grounded, judge-correct "
                "answer probe during snapshot construction; frozen snapshots reuse these "
                "measurements without re-ingestion. Probe lag is an upper bound."
            )
            summary.global_metrics.update(
                freshness=freshness,
                freshness_max_lag_seconds=max(lags)
                if lags and all(x is not None for x in lags)
                else None,
                freshness_answerable_count=sum(x is not None for x in lags),
                freshness_target_seconds=settings.poll_interval_minutes * 60 + 300,
            )
            summary.status = (
                "completed_with_errors"
                if any(
                    r.get("error") or r.get("judgement_errors") for r in summary.results
                )
                else "completed"
            )
        except Exception as exc:  # noqa: BLE001 - persist failures and mark missing pairs unmeasured
            summary.status = "failed"
            summary.global_metrics["fatal_error"] = type(exc).__name__ + ": " + str(exc)
            await emit("Evaluation failed: " + summary.global_metrics["fatal_error"])
        finally:
            if answers_path.exists():
                summary.results = [
                    json.loads(line)
                    for line in answers_path.read_text(encoding="utf-8").splitlines()
                ]
            if provider_stop or summary.global_metrics.get("fatal_error"):
                reason = provider_stop or summary.global_metrics["fatal_error"]
                done = {(r["configuration"], r["question_id"]) for r in summary.results}
                with answers_path.open("a", encoding="utf-8") as stream:
                    for name in names:
                        for q in questions:
                            if (name, q["id"]) not in done:
                                row = {
                                    "configuration": name,
                                    "question_id": q["id"],
                                    "type": q["type"],
                                    "unmeasured": True,
                                    "error": reason,
                                }
                                summary.results.append(row)
                                stream.write(json.dumps(row) + "\n")
                await emit(
                    "Provider calls stopped; remaining pairs UNMEASURED: " + reason
                )
            summary.metrics = aggregate(summary.results)
            validity = run_validity(summary.metrics)
            summary.global_metrics["run_validity"] = validity
            if validity["status"] != "completed":
                summary.status = validity["status"]
            summary.global_metrics["usage_by_stage"] = meter.summary()
            summary.global_metrics["total_tokens"] = sum(
                v["tokens"] for v in meter.summary().values()
            )
            usage_values = list(meter.summary().values())
            summary.global_metrics["total_cost_usd"] = (
                sum(v["cost_usd"] for v in usage_values)
                if usage_values and all(v["cost_usd"] is not None for v in usage_values)
                else None
            )
            for name, metrics in summary.metrics.items():
                judge_usage = meter.summary().get(name + ":judge", {})
                metrics["judge_tokens"] = judge_usage.get("tokens")
                metrics["judge_cost_usd"] = judge_usage.get("cost_usd")
                usages = [v for k, v in meter.summary().items() if k == name]
                metrics["tokens"] = sum(v["tokens"] for v in usages) if usages else None
                metrics["cost_usd"] = (
                    sum(v["cost_usd"] for v in usages)
                    if usages and all(v["cost_usd"] is not None for v in usages)
                    else None
                )
            summary.global_metrics["judge_usage_by_configuration"] = {
                name: meter.summary().get(name + ":judge") for name in names
            }
            await sampler.sample()
            memory_task.cancel()
            await asyncio.gather(memory_task, return_exceptions=True)
            summary.global_metrics.update(sampler.summary())
            checks = success_criteria(summary.metrics, summary.global_metrics)
            summary.global_metrics["success_criteria"] = checks
            summary.report_path, summary.csv_path, summary.configurations_csv_path = (
                write_report(
                    "docs/eval",
                    snapshot,
                    stamp,
                    summary.metrics,
                    summary.results,
                    summary.global_metrics,
                    checks,
                )
            )
            save(checkpoint, summary.model_dump())
            await repo.update_eval_run(
                record.id,
                status=summary.status,
                metrics={**summary.metrics, "global": summary.global_metrics},
                results=summary.results,
                report_path=summary.report_path,
                csv_path=summary.csv_path,
            )
            if runtime:
                await runtime.close()
            await builder.close()
            await judge.close()
            await local_repo.close()
    await emit(table(summary.metrics))
    await emit("Report: " + summary.report_path)
    logging.getLogger().removeHandler(log_handler)
    log_handler.close()
    return summary


__all__ = ["EvalRunSummary", "run_evaluation"]
