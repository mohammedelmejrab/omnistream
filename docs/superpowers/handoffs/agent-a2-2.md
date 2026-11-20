# Agent A2 (backend) handoff, round 2

Status: DONE. Backend changes for the app's round-2 needs are in place and tested against the real FastAPI app.
Not committed or pushed.

## Done

1. **Step summary keys** match `web/src/trace/types.ts`:
   - `route.bubbles`, `retrieve.count`, `subagent.count` / `subagent.relevance`, `join.count`, `answer.citation_count`, `any.source_text` (on retrieve and subagent steps, capped at 600 characters).
   - `score.relevance` is now emitted (see ruling 1).
   - **Seed and score steps added.** Both are zero-length children of the retrieve step, recorded when retrieval returns. Normal runs now store: route, retrieve, seed, score, answer. Agentic runs gain seed and score under each subagent's retrieve.
   - **Merge is folded**, not emitted. In Agentic, merge work sits in `join`. In Normal, the merge is inside `answer`. Equivalent for the four-stage view (ruling 2).
2. **410 for expired traces.** A run older than 30 days returns `410 "Trace no longer available"` from `GET /api/runs/{id}`, `/steps` and `/events`. Unknown runs return `404 "Unknown run"`. Retention now deletes steps only and keeps the run row, so expiry can be told apart from unknown (ruling 3).
3. **Duplicate source URL on `POST /api/sources` returns 409** with `{"detail": "Already added", "source_id": <existing id>}`. Matching ignores surrounding whitespace and a trailing slash. The plain `POST /sources` route is unchanged.
4. **`backfill_days`** is accepted on `SourceIn` (1 to 3650, 0 is 422), stored on `Source` and `SourceRow`, and returned by GET. Existing SQLite files get the column through the existing `_add_missing_columns` migration. It applies on the first successful poll (ruling 4).
5. **`POST /api/sources/test`** fetches once, applies the backfill rule, returns up to 5 items `{items: [{title, url}]}` and stores nothing. Fetch errors return 422 with a readable message.
6. **Endpoint contract** (checked by `tests/unit/test_ui_contract.py` against the real app):
   - `GET /api/bubbles` added (alias).
   - `POST /api/documents` added (multipart alias of `/documents`). The JSON content-type guard in `c6.py` now exempts it, as it already did `/documents`.
   - `GET /api/chats/{id}` now returns `{chat, messages}`. Previously the chat fields were flat. This matches `web/src/api/types.ts` `ChatDetail`.
   - `POST /api/chats/{id}/messages` returns `run_id` (already true, now tested).
   - `POST /api/settings/provider/test` returns `{ok, message}` (tested by stubbing the probe, since there is no real provider).

## Files touched

Source:
- `src/omnistream/api/ui_trace.py`: summary keys, `relevance_of`, `source_text_of`, `record_retrieval_children`, join count.
- `src/omnistream/api/ui_api.py`: `trace_expired` and `_known_run` (410), step-only purge, `citation_count`, `ChatDetail` shape.
- `src/omnistream/api/app.py`: `SourceIn.backfill_days`, `/api/sources` duplicate check, `POST /api/sources/test`, `/api/bubbles`, `/api/documents`.
- `src/omnistream/api/c6.py`: JSON guard exempts `/api/documents`.
- `src/omnistream/db/ui_store.py`: `purge_steps_started_before` replaces `purge_runs_started_before`.
- `src/omnistream/db/repository.py`: `backfill_days` column migration.
- `src/omnistream/db/tables.py`: `SourceRow.backfill_days`.
- `src/omnistream/models.py`: `Source.backfill_days`.
- `src/omnistream/sources/rss.py`: `apply_backfill`.
- `src/omnistream/ingest/scheduler.py`: first-poll backfill filter.

Tests:
- `tests/unit/test_ui_trace.py`: 3 new tests (seed and score children, retrieve and subagent summary keys); the normal-mode unpacking test was made kind-based.
- `tests/unit/test_ui_api.py`: step-kind expectations updated for seed and score; chat assertions read `["chat"]`; 410 expiry test.
- `tests/unit/test_ui_store.py`: retention test now checks step-only purge.
- `tests/unit/test_ui_contract.py`: new, 13 tests.
- `tests/unit/ui_support.py`: `FakeRetriever(score=...)`.

## How to test

From the repo root:

```
.venv/bin/python -m pytest tests/unit/test_ui_contract.py tests/unit/test_ui_api.py tests/unit/test_ui_trace.py tests/unit/test_ui_store.py -q -p no:cacheprovider
.venv/bin/ruff check src/omnistream tests/unit/test_ui_*.py tests/unit/ui_support.py
```

Results at handoff:
- UI set: 60 pass (contract 13, api, trace and store the rest).
- Full suite (`.venv/bin/python -m pytest tests -q`): 1255 passed, 5 failed, 22 deselected. Output saved to `/private/tmp/claude-501/-Users-hf-Desktop-Semester-7-Capstone-Project-Capstone-omnistream/54d98192-c200-4bb8-86fc-6992d3f5a211/scratchpad/agent-a2-full.txt`.
- The 5 failures are `tests/unit/test_real_question_repairs.py`. They read `data/real/...`, which is gitignored and missing here (`FileNotFoundError`). Same 5 as round 1. Not caused by this work; left as is.
- Ruff: `All checks passed!` on the touched source and test files.

## Rulings (where the spec or brief was silent)

1. **Relevance (0..1).** Own-pipeline fact scores are RRF-fused. `relevance = clamp01(best_score / (3/(k+1)))` with k = 60. A fact ranked first by all three signals scores 1.0. Graphiti scores (1/rank) clamp to 1.0, so Graphiti relevance is coarse. Relevance is omitted when there are no facts.
2. **Merge step folded**, not recorded. Agentic: merge work is inside `join`. Normal: it is inside `answer`. Seed and score are recorded because the Searched and Gathered stages read them.
3. **Expiry.** Expired means `started_at` is older than 30 days, computed on read. Purge deletes steps only, so an expired run still has a row and returns 410 (not 404). Unknown ids return 404 `"Unknown run"`. This changes round-1 ruling 11, which said purged runs return 404.
4. **Backfill.** `backfill_days` keeps items published within N days on the first successful poll and in the test preview. Undated items are kept. Later polls are not filtered. This is a per-feed setting, not a bubble-level re-route like the bubble backfill.
5. **Duplicate check** applies only to `/api/sources` (the UI route), not `/sources`, so the admin pages are unchanged.
6. **Test button** returns at most 5 items and uses its own HTTP client (not the scheduler's).
7. **Chat detail shape** is `{chat, messages}`. Anything reading the old flat fields breaks. Only round-1 tests used the flat shape, and they are updated.

## Concerns

- No live provider, Neo4j or browser run. The provider test is covered by stubbing the probe.
- The 5 pre-existing failures need `data/` restored to pass. They are not part of this work.
- Migration is additive and tested only on a fresh database and by the code path. An existing `data/` SQLite file has not been opened by this build.
- Web side: `web/src/trace` still depends on the step kinds and the 410 status. Agent C's summary-key assumptions are now met. The Searched stage now gets real seed steps.

Status line: DONE. Files touched: 15 (10 source, 5 test; one new test file). Tests: UI set 60 pass; full suite 1255 pass, 5 pre-existing `data/` failures. Concerns: see above.
