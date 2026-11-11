# Spec Alignment Plan: Ingestion (Phases 1–2)

**Spec (binding authority):** `omnistream-rag-specification.md` (v1.0). Sections C1–C4, §4, §5, §7, §13.

**Goal:** make the existing ingestion pipeline match the spec exactly, except where the spec would make the system worse (listed under "Deliberate exceptions"). Query path (C5), UI pages other than Sources/Unsorted, and evaluation (C7) are out of scope.

**Baseline:** branch `feat/ingestion-pipeline`, 154 unit tests pass (`uv run pytest -q`). Integration tests: `uv run pytest -m integration` (Docker is running). Live tests: `-m live`.

## Global Constraints

- Python 3.12, `uv`, `ruff check` and `ruff format --check` clean, `uv run pytest -q` green after every task. Never call a real LLM or network in default (unmarked) tests; use recorded fixtures/stubs. Integration tests needing Neo4j get `@pytest.mark.integration`; real-LLM tests get `@pytest.mark.live`.
- Repository layout (spec §13.1): `src/omnistream/{sources,ingest,router,graph,retrieval,agents,api,ui,eval}`. Persistence code may live in `src/omnistream/db/`. Empty packages `retrieval/ agents/ eval/` get only `__init__.py`.
- Configuration env vars exactly as spec §13.2, no prefix: `LLM_BASE_URL` (default `https://api.deepseek.com/v1`), `LLM_API_KEY`, `LLM_MODEL`, `JUDGE_MODEL`, `NEO4J_URI` (default `bolt://localhost:7687`), `NEO4J_USER` (default `neo4j`), `NEO4J_PASSWORD`. Additional app settings may use `OMNI_` prefix. The API key is read from the environment only, never stored in SQLite or returned by the API (D20).
- LLM: `openai` Python client (`AsyncOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)`), any OpenAI-compatible endpoint. Structured output via JSON mode (`response_format={"type":"json_object"}`) + Pydantic validation, retry on parse error (max 2 re-asks). Token-bucket rate limiting and exponential backoff on HTTP 429/5xx.
- Embeddings: local `BAAI/bge-small-en-v1.5`, 384 dims, `sentence-transformers`, always local regardless of LLM provider.
- Defaults (spec values, all tunable in settings): credibility 0.5; poll_interval 15 min; max_items_per_hour 30; store_full_text true; pre-filter min 200 chars; 2 queue workers; router threshold 0.5; router top-3 candidates; grounding `partial_ratio` ≥ 85; global link cosine ≥ 0.88 same type, else fuzzy ≥ 90; document episodes ≈1,500 tokens; chunks ≈300 tokens; auto-summary refresh every 200 episodes; half-lives News 3, Finance 30, Research 365 days.
- Entity types (one shared set, spec C4): Person, Organization, Location, Product, Event, Concept, Financial Instrument, Publication.
- Every fact, episode and chunk carries `item_id`; every item references `raw_path` and `text_path` (spec §4.2). No fact without `item_id`.
- Corroboration: `source_count` increments when another source asserts the same fact; `confidence = 1 − Π(1 − credibility_i)` over distinct sources.
- Commit after each task with conventional-commit messages.

## Deliberate exceptions (where following the spec literally is a negative)

1. **Pre-filter "under 200 characters or without a date"** applies to feed items (rss/api) only. Uploaded documents use upload time as their date and are never length-filtered per part (a short final section of a PDF is still content).
2. **Existing tuned logic is reused, not discarded**: the legal-suffix-aware fuzzy matching and short-mention word-bounded grounding stay; they implement the spec's thresholds more accurately.
3. **In-memory/fake implementations** remain for tests.

## Tasks

### Task 1: Config, LLM client, embedder, layout, compose

- Replace `config.py` with Settings reading the spec env vars (Global Constraints) plus `OMNI_`-prefixed app settings for every default above, plus `data_dir` (default `data`), `llm_tokens_per_minute` (token bucket, default 60 requests/min), `llm_max_retries` 5.
- Replace `llm.py`: `LLMClient` over `openai.AsyncOpenAI`, same `parse(model, system, user, schema, max_tokens)` signature returning a validated Pydantic object; JSON-mode + schema in system prompt; re-ask on validation failure (2 times) then raise `LLMError`; token bucket; backoff on 429/5xx (use client `max_retries` plus own handling of `openai.RateLimitError`/`APIStatusError` ≥500). `connection_test()` returns `{"json_mode": bool, "function_calling": bool}`.
- Remove `anthropic` dependency; add `openai`, `graphiti-core`, `chromadb`, `sqlmodel`, `python-docx`, `networkx`, `jsonpath-ng`.
- `embed.py`: bge-small-en-v1.5, normalized embeddings.
- Move packages to spec layout: `ingest/sources/*` → `sources/`, `ingest/route.py` → `router/`, `ingest/{extract,grounding,resolve,write}.py` → `graph/`. Update imports and tests. Create empty `retrieval/ agents/ ui/ eval/` packages.
- `docker-compose.yml`: `neo4j:5.26-community`, `NEO4J_server_memory_heap_max__size=1G`, `NEO4J_server_memory_heap_initial__size=1G`, `NEO4J_server_memory_pagecache_size=512M`, password from `${NEO4J_PASSWORD}`.
- `.env.example` exactly spec §13.2. `pyproject.toml`: markers say `live: needs LLM_API_KEY`; add console script `omni = "omnistream.cli:main"` (cli stub with `seed`, `replay`, `serve` subcommands filled in later tasks).
- Tests: settings defaults/env names; LLM client JSON parse, re-ask, LLMError, 429 retry (stub transport, e.g. `respx` on the OpenAI base URL); bucket.

### Task 2: SQLite application state (SQLModel)

Spec §7 tables in `db/`: `bubbles` (id, name, description, description_embedding, auto_summary, half_life_days, created_at, updated_at, plus `episodes_since_summary` counter), `sources` (id, type ∈ rss/api/document/log, url, credibility, poll_interval, bubble_ids, api_mapping, max_items_per_hour, store_full_text, enabled, last_polled_at, status, last_error), `seen_items` (hash, source_id, url, first_seen_at), `items` (id, source_id, bubble_ids, url, title, published_at, raw_path, text_path, status ∈ queued/routed/unsorted/extracted/written/failed/filtered, route_confidence, stage timestamps polled_at, deduplicated_at, routed_at, extracted_at, written_at, error), `jobs` (id, item_id, state, attempts, available_at, created_at), `settings` (key, value), `query_log`, `eval_runs` (columns per spec §7). JSON columns for lists/dicts. A `Repository` class with async-friendly methods (run sync SQLModel in `asyncio.to_thread` or use aiosqlite) used by everything else. `api_mapping` replaces `ApiFeedConfig`: JSONPath strings for `items`, `title`, `body`, `date`, `url` plus optional `headers`. Bubbles and sources leave Neo4j entirely. Tests: CRUD, JSON round-trip, seen-hash uniqueness, settings override.

### Task 3: Sources, original store, dedup, pre-filter

- `sources/rss.py`, `sources/api.py` (JSONPath via `jsonpath-ng`), `sources/documents.py` (PDF, DOCX, TXT, MD; split into episodes of ≈1,500 tokens at heading then paragraph boundaries; token count ≈ words×1.3 or a tokenizer—document the choice).
- `ingest/originals.py`: store raw file at `data/raw/<source_id>/<sha256>.<ext>` (sha256 of raw bytes; ext html/json/pdf/docx/txt/md) and clean text alongside as `<sha256>.txt`. When `store_full_text` is false keep only the clean title+first 500 chars and record that. Originals are never deleted by the app.
- Dedup key per spec C2: SHA-256 of normalized text (lowercase, whitespace collapsed, tracking params removed) plus canonical URL — keep `normalize.py`, extend tracking-param list (utm_*, fbclid, gclid, mc_cid, mc_eid, ref, ref_src). Pre-filter per Deliberate exception 1. Per-source `max_items_per_hour` cap (items beyond cap are left unseen so the next poll picks them up). Disabled sources are never polled.
- Each accepted item: `items` row with `polled_at`, `deduplicated_at`, raw/text paths, status `queued`, and a `jobs` row.
- Replay: `sources/replay.py` records every polled RawItem to `data/snapshots/<name>.jsonl` when recording is on, and `omni replay <name>` re-injects them with original `published_at` and polled order.
- Tests: re-polling a feed adds zero items; cap; pre-filter; original files exist and clean text readable; DOCX parsing; episode splitting at headings; replay round-trip.

### Task 4: Queue and workers

`ingest/queue.py`: SQLite-backed job table claimed atomically, N workers (default 2) as asyncio tasks; failures retry with exponential backoff up to 5 attempts then item `failed` with error; HTTP 429 from the LLM causes retry without losing the item. Workers call a `process_item(item_id)` callable (wired in Task 7). Scheduler (`ingest/scheduler.py`) now only polls and enqueues; failed polls back off (double interval up to 4× after consecutive failures) and record `status`/`last_error`. Tests: claim exclusivity, retry on 429-like error, backoff, item never lost.

### Task 5: Ingestion router (C3)

`router/router.py`: if item/upload or source has explicit `bubble_ids` (source `bubble_ids` non-empty means fixed), bypass router with confidence 1.0. Else embed item (title + first 2,000 chars), cosine against each bubble's `description_embedding` (computed on bubble create/update from the user description), take top 3, one LLM call with candidates (id, name, description primary, auto_summary as "secondary hint") returning `{"bubble_ids": [...], "confidence": 0..1}`; may choose several; ids filtered to candidates. Confidence < threshold (0.5) or empty → item status `unsorted`, no graph write. Manual assignment of an unsorted item re-enqueues it with explicit bubbles. Tests with stub LLM; record route_confidence and routed_at.

### Task 6: Graph writer on Graphiti (C4)

`graph/graphiti_client.py`: build `Graphiti(uri,user,password, llm_client=OpenAIGenericClient(LLMConfig(api_key, model, base_url)), embedder=<EmbedderClient wrapping our bge embedder>, cross_encoder=<local implementation, no remote calls>)`; `build_indices_and_constraints()` once at startup. Inspect the installed `graphiti_core` source for exact signatures.

`graph/writer.py`, per item and bubble:
1. `add_episode(name=item title, episode_body=clean text, source=EpisodeType.text, source_description=JSON {"item_id","url","credibility","source_id"}, reference_time=item date, group_id=bubble_id, entity_types=<8 Pydantic types>)`. Set `item_id`, `source_url`, `credibility` as properties on the resulting Episodic node and on each returned/updated entity edge (append item_id to an `item_ids` list on edges).
2. Grounding: for each newly created entity node (not ones resolved to existing), check name or any alias against episode text with existing `is_grounded` (threshold 85). Failures: node and its edges from this episode get `grounded=false`; others `grounded=true`. Never delete (D15).
3. Global linking: each new entity gets `(:Entity)-[:SAME_AS]->(:GlobalEntity {uuid,name,type,name_embedding,aliases})`: cosine ≥ 0.88 with same type via a Neo4j vector index on `GlobalEntity.name_embedding`, else fuzzy ≥ 90 (reuse resolver fuzzy logic incl. legal suffixes for Organization), else create new GlobalEntity.
4. Temporal: edges with `invalid_at` or `expired_at` set get `status='HISTORICAL'`, else `status='VERIFIED'` (re-check edges Graphiti invalidated during this episode).
5. Corroboration: for each returned edge, maintain `source_ids` list and `credibilities` per distinct source; `source_count = len(source_ids)`; `confidence = 1 − Π(1 − c_i)`.
6. Chunking: clean text split into ≈300-token chunks into Chroma `PersistentClient(path=data/chroma)`, one collection per bubble named `bubble_<id>` with `{"hnsw:space":"cosine"}`, embeddings from our embedder, metadata item_id, source_url, published_at.
7. After success: item `extracted_at`/`written_at`, status `written`; bubble `episodes_since_summary` += 1; at 200 regenerate `auto_summary` with one LLM call (never touch `description`).
Remove the old custom `extract.py`, `write.py`, Neo4j fact store and `store/` protocol once replaced; keep `grounding.py` and the fuzzy helpers from `resolve.py`. Unit tests with a fake Graphiti object; integration test (`-m integration`) against testcontainers Neo4j using recorded LLM fixture responses for one episode, asserting: episode node has item_id, every edge has item_id(s), SAME_AS links exist, grounded flag set, confidence formula.

### Task 7: Pipeline wiring, bubble lifecycle, API, seed

- `ingest/pipeline.py`: `process_item(item_id)` = route → (unsorted | for each bubble: graph writer) with stage timestamps; plugged into workers.
- Bubble create: name, description, half_life_days, `backfill_days` (None = new items only; N = re-route stored items from the last N days through the router, enqueueing those routed to the new bubble). Bubble delete (after the caller confirms counts — `GET /bubbles/{id}` returns counts of episodes, entities, facts, chunks, sources): remove the Graphiti group (`remove_episode`/Cypher delete by group_id), Chroma collection, SAME_AS edges from that group's entities, orphaned GlobalEntity nodes, catalog row; sources bound only to this bubble get `enabled=false` with seen_items kept; originals kept.
- REST (spec C6, ingestion subset): `POST/GET/DELETE /bubbles` (`DELETE /bubbles/{id}`), `GET /bubbles/{id}`, `POST/GET /sources`, `PATCH /sources/{id}` (enable/disable etc.), `POST /sources/{id}/poll`, `POST /documents` (multipart, optional bubble_ids; empty = automatic routing), `GET /items?status=unsorted`, `POST /items/{id}/assign`, `GET /items/{id}/text`.
- `omni seed`: creates bubbles News, Finance, Research (descriptions written for routing, half-lives 3/30/365) and sources: BBC World RSS `https://feeds.bbci.co.uk/news/world/rss.xml`, Guardian World `https://www.theguardian.com/world/rss`, CNBC Markets `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258`, Finnhub company news API (`https://finnhub.io/api/v1/news?category=general&token=${FINNHUB_API_KEY}` with matching api_mapping; skipped with a warning if the env var is missing), arXiv `https://rss.arxiv.org/rss/cs.CL`, each bound to its bubble. `omni serve` runs uvicorn.
- Tests: API tests with fakes; delete removes all derived data (integration); backfill.

### Task 8: Sources and Unsorted pages

Server-rendered HTML with HTMX (spec §5, Phase 1 gate). `ui/` with Jinja2 templates served by FastAPI: `/ui/sources` (list with status, last polled, last error, enable/disable toggle, poll-now button, add-source form including api_mapping fields) and `/ui/unsorted` (list unsorted items with title, snippet, route confidence, bubble multi-select and assign button). HTMX loaded from a vendored static file, no build step. Tests with TestClient: pages render, assign action works.
