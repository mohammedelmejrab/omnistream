# Agent A (backend) handoff, run 1

Status: DONE for spec sections 10.1, 10.4, 10.6, 9 (storage, masking, test connection), 12, 13 and 14 (unit and API tests).
Frontend-independent: the React app (Agents B and C) can build against the API below now.

## Done

- Tables `chats`, `messages`, `runs`, `run_steps` (30-day retention). `query_log` untouched.
- Persistence mixin `UIStoreMixin` (chats, messages, runs, steps, stale-run sweep, retention purge). `Repository` now inherits it.
- Step recorder around the own pipeline:
  - Normal: `answer_question(mode="own", subagents=False)` runs once. Steps: route, retrieve, answer.
  - Agentic: `answer_question(subagents=True)` calls the real orchestrator. Steps: route, subagent (one per bubble, nested retrieve steps), join, answer.
  - `answer_question`, `run_subagents` and `Subagent` are called unchanged. The behaviour is observed through proxies (router, dispatcher, async retriever, sync LLM). Each subagent step is tied to its own asyncio task, so it is recorded as it finishes.
- SSE `GET /api/runs/{id}/events` (step on start and finish, run on status change, done at end). Snapshot first, then live, deduplicated.
- Cancel (`POST /api/runs/{id}/cancel`), delete-chat-during-run (cancels, keeps the trace), stale-run sweep at startup, retention at startup and hourly.
- Provider settings in the existing `settings` table. The key is stored under `provider.api_key` and is write-only. `LLM_API_KEY` is the fallback. Saving a key or changing the base URL or model rebuilds the query runtime (the old one closes after its in-flight runs finish).
- `GET /api/graph` (bubble filter, limit up to 1000, offset).
- `web/dist` served at `/app` with SPA fallback. Path traversal blocked. 503 with a hint when the build is missing.
- `/api/sources` GET, POST, PATCH aliases of the existing handlers. `DELETE /api/sources/{id}` is new.
- Live check: ran the app under uvicorn with a 2-second retrieval. The `running` step arrived at 05:17:08 and its `ok` at 05:17:10 over real HTTP.

## Files touched

New:
- `src/omnistream/api/ui_api.py` (router, `UIServices`, run lifecycle, provider, graph, `/app`)
- `src/omnistream/api/ui_trace.py` (`RunRecorder`, `RunBus`, `PipelineTrace` proxies, digests)
- `src/omnistream/db/ui_store.py` (persistence mixin)
- `tests/unit/ui_support.py` (fakes: router, dispatcher, retriever, sync and async LLM, runtime, graph ops)
- `tests/unit/test_ui_store.py` (6 tests)
- `tests/unit/test_ui_trace.py` (12 tests)
- `tests/unit/test_ui_api.py` (26 tests)
- `docs/superpowers/handoffs/agent-a-1.md` (this file)

Edited (minimal):
- `src/omnistream/db/tables.py` (4 table classes appended)
- `src/omnistream/db/repository.py` (import, and `class Repository(UIStoreMixin)`)
- `src/omnistream/api/app.py` (`web_dist` parameter; `UIServices` built; `ui.startup()` after `services.load()`; `ui.shutdown()` before `services.close()` in both branches; `/api/sources` aliases; router and `/app` mounts)

## API as built (additive fields are marked +)

- `POST /api/chats` (201), `GET /api/chats`, `GET /api/chats/{id}` (with `messages`), `PATCH /api/chats/{id}`, `DELETE /api/chats/{id}` (204)
- `POST /api/chats/{id}/messages` (202) body `{content, mode, bubble_ids}`. Returns `{run_id, run, user_message, assistant_message}`. Errors: 404 unknown chat; 409 no key; 409 no bubbles; 422 unknown bubble, blank or over 20,000 characters.
- `GET /api/runs/{id}`, `GET /api/runs/{id}/steps`, `POST /api/runs/{id}/cancel`, `GET /api/runs/{id}/events` (SSE). Unknown or expired run: 404 "Trace no longer available".
- `GET /api/settings/provider` returns `{key_set, key_hint, key_source, base_url, model}`.
- `PUT /api/settings/provider` takes `{api_key?, base_url, model}`. Omitting `api_key` keeps the saved key.
- `DELETE /api/settings/provider/key`, `POST /api/settings/provider/test` returns `{ok, message}`.
- `GET /api/graph?bubble=&limit=300&offset=` returns `{nodes, edges, total}`.
- `DELETE /api/sources/{id}` (204)
- `GET /app`, `GET /app/{path}`

Run: `{id, chat_id, mode, status, answer, error, started_at, finished_at, +question}`.
Step: `{id, run_id, parent_step_id, kind, bubble, started_at, duration_ms (null while running), status, summary, node_ids, edge_ids, citations, error, +seq}`.
Citation entries: `{item_id, url, title, +number}`.
Message: `{id, chat_id, role, content, run_id, mode, created_at}`.

Node and edge ids for the trace graph: `node_ids` are entity ids (seeds, and fact subject and object ids). `edge_ids` are fact ids. `route` has no node ids (bubbles are in `summary.bubbles`).

Step kinds emitted: `route`, `retrieve`, `subagent`, `join`, `answer`. Not emitted: `seed`, `score`, `merge` (seed and score counts are in the retrieve summary; merge work falls inside join or answer).

## How to run tests

From the repo root, with the project venv:

```
.venv/bin/python -m pytest tests/unit/test_ui_store.py tests/unit/test_ui_trace.py tests/unit/test_ui_api.py -q -p no:cacheprovider
```

Result: 44 passed.

Full unit and DB suites: 1239 passed, 5 failed. The 5 failures are all in `tests/unit/test_real_question_repairs.py`. They read files under the gitignored `data/` folder, which is missing in this checkout. They are not caused by this work.

Lint: `.venv/bin/ruff check` on the new and edited files: clean.

Manual live check: `serve_fake.py` in the scratchpad (uvicorn with a fake runtime) plus curl against `/api/runs/{id}/events`.

## Rulings (spec was silent or left a choice)

1. Steps are persisted only when they finish. Running steps live in memory and appear in `/steps` and in the SSE snapshot while running. Stored `seq` is the start order.
2. Answer step: in Normal it starts when retrieval finishes. In Agentic the join and answer boundaries are taken at the first chat call of answer generation. The join step is backdated to the last subagent finish.
3. A subagent step starts at its first retrieve call, not at task start. A subagent that never searches is recorded after the orchestrator returns (duration about 0).
4. Stopped steps: a step open at cancel is stored as `cancelled`. A stored step can never change after that.
5. Cancelled run: assistant message content becomes "Stopped". Failed run: "This answer failed: <reason>". Empty answer: "The model returned no answer." Interrupted run (startup sweep or server shutdown): "Interrupted when OmniStream restarted".
6. Cancel and delete-during-run wait up to 10 s for the run to finish before responding.
7. Provider test uses the saved settings. It does not take unsaved values. Errors map to fixed messages, so no provider text reaches the browser.
8. Redaction: any occurrence of the UI key or the env key in a run error is replaced with `[redacted]`.
9. A key that is `""` is rejected with 422 (omit the field to keep the saved key).
10. Graph: `total` counts the nodes fetched, capped at 1000 per bubble. Edges are returned only when both ends are on the returned page.
11. Trace retention: runs and their steps older than 30 days by `started_at` are purged at startup and hourly. The assistant message keeps its `run_id`, and the run then returns 404.
12. SSE keep-alive comment every 15 s. No `Last-Event-ID` support (not required by the brief).
13. `DEFAULT_WEB_DIST` is `<repo>/web/dist`. It is not packaged in the wheel.
14. A run started while no bubble exists returns 409.

## Concerns and gaps

- Duplicate source URLs: the server does not return "Already added". `POST /api/sources` (the existing handler) still creates a duplicate. The frontend can check `GET /api/sources` first, or the backend can add a 409 with `source_id`. Not done, to keep the existing handler unchanged.
- Documents: `POST /documents` is unchanged, as the spec says. There is no `/api/documents` alias. `POST /documents` already bypasses the JSON content-type check.
- The UI-saved key applies to queries and Agentic runs immediately. Ingestion and the graph writer keep the key from process start until restart, which matches how the existing `/settings` behaves.
- Changing the model does not update `judge_model`.
- `GET /api/settings/provider` returns `base_url` and `model` read from the in-memory settings. Those values are written to the same `llm_base_url` and `llm_model` keys that `PUT /settings` uses, so the two stay in sync.
- The "background effects" toggle is not handled by the backend. It is presumably a client-side setting (for example localStorage).
- `join` and `answer` boundaries are approximate, as described in ruling 2.
- No live Neo4j or real-model test was run. The own pipeline ran with fakes around the real `answer_question` and the real subagent loop.
