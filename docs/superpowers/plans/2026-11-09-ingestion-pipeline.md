# OmniStream RAG: Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow TDD strictly: write the test, watch it fail, implement, watch it pass, commit.

**Goal:** Build the ingestion half of OmniStream RAG. It takes items from RSS feeds, JSON APIs and uploaded documents, deduplicates them, extracts grounded triples with an LLM, resolves entities against one global entity table and writes time-aware, provenance-carrying facts into one or more bubbles.

**Architecture:** A linear async pipeline (`dedup → route → extract → ground → resolve → write → mark seen`). Every stage is a small class with one public method. Stages talk to storage only through a `GraphStore` protocol, which has two implementations: `InMemoryStore` for fast unit tests and `Neo4jStore` for production. One shared contract test suite runs against both. The LLM and the embedder sit behind thin interfaces so tests can use deterministic fakes.

**Tech Stack:** Python 3.12, `uv`, FastAPI, Neo4j 5.26 (with its built-in vector index), official `neo4j` async driver, `anthropic` Python SDK (`messages.parse` structured outputs), `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim), `rapidfuzz`, `feedparser`, `httpx`, `beautifulsoup4`, `pypdf`, APScheduler 3.x. For tests: `pytest`, `pytest-asyncio`, `testcontainers[neo4j]`, `respx`, `fpdf2`. For dev: `ruff`, `mypy`.

**Spec:** `omnistream-rag.md` (project root). Executors read both documents. This plan covers spec §3 "Ingestion flow", §4 decisions 3, 4, 5, 8 and 10, the ingestion items in §5, the §7 data model, and MVP step 1 plus the ingestion half of step 2.

**Out of scope (separate plans):** query flow / orchestrator / subagents, web UI, auto-refreshing bubble descriptions (§4.2), and read-time decay ranking (§4.9). This plan does store `description_embedding` on bubble creation and does store `valid_from`, `credibility` and `source_count`, because the query side needs them.

---

## Decisions this plan makes (not fixed by the spec)

| Decision | Choice | Why |
|---|---|---|
| Graphiti vs custom pipeline | **Custom pipeline on Neo4j**, no Graphiti | Graphiti runs its own extraction and resolves entities *per group*. That conflicts with the spec's grounding check (§3.4) and with the *global* entity table shared across bubbles (§4.4). The data stays in Neo4j, so adopting Graphiti later is still possible. |
| Graph DB | Neo4j 5.26 | Graph traversal for later subagents plus a built-in vector index means one store (§5 "skipped: three stores"). |
| Bubble namespace | `bubble_id` property on every `FACT` relationship; entities are global nodes | Implements §4.4 and §4.5 directly. |
| Extraction / routing model | `claude-haiku-5-5` (configurable) | Spec §6: use a cheaper, faster model for extraction. |
| Embedding match threshold | cosine ≥ **0.88**, same entity `type` | Avoids merging "Apple" (ORG) with "apple" (PRODUCT). |
| Fuzzy fallback | `rapidfuzz.fuzz.token_sort_ratio` ≥ **90** against canonical name + aliases of the top-20 embedding candidates of the same type | Bounded cost, no full table scan. |
| Grounding | `rapidfuzz.fuzz.partial_ratio(mention, text) ≥ 85` (casefolded). Mentions of ≤ 3 characters need an exact word-boundary match. | Implements "fuzzy partial match, not strict substring". The short-mention rule stops "AI" or "US" from matching anywhere. |
| Retry idempotency | Facts store `evidence_hashes: list[str]`. `source_count` only grows when a *new* item hash corroborates the fact. | Retrying a failed item must not inflate `source_count`. |
| Supersession | Only for triples the LLM marks `exclusive=True` (single-valued relations such as `CEO_OF`) | A company can have many `ACQUIRED` facts, but only one CEO at a time. |

---

## Global Constraints

- Python ≥ 3.12. All I/O code is `async`.
- Content hash = `sha256(normalize_url(url) + "\n" + normalize_text(text))`, as lowercase hex (§3.2, §5).
- Every fact carries `source_id`, `source_url`, `credibility`, `valid_from`, `ingested_at` (§3.6, §4.10).
- `status ∈ {"VERIFIED", "HISTORICAL"}`. Superseded facts get `valid_to` set and `status="HISTORICAL"`. They are never deleted (§4.8).
- `credibility` is a float in `[0.0, 1.0]`, default `0.5`. `poll_interval` is in seconds, minimum `60`, default `900`.
- One Neo4j database. Bubbles are namespaces, never separate databases (§4.5).
- Neo4j vector index similarity = `cosine`. **Neo4j returns cosine scores as `(1 + cos) / 2`, so the store must convert back with `cos = 2*score − 1`** (this plays the same role as the ChromaDB gotcha in §5).
- An item is marked seen **only after** all its facts are written. Items that fail or can't be routed get retried on the next poll.
- LLM calls go through one `LLMClient`: an `asyncio.Semaphore` (default 4) plus the SDK's built-in exponential backoff (`max_retries=5`) (§5 "rate-limit queue with backoff").
- Test markers: `integration` (needs Docker/Neo4j) and `live` (needs `ANTHROPIC_API_KEY`, costs money). The default run excludes both.

## Review Focus

These are the failure modes most likely to hurt a real user, most likely first. Each one is pinned by a named test in the task that owns the code:

1. **The same story arriving twice, from one feed or from two concurrent polls**, must produce facts once and `source_count` must not double. → Task 11 `test_concurrent_duplicate_items_processed_once`, Task 10 `test_retry_same_hash_does_not_increment_source_count`.
2. **An LLM-hallucinated entity** (a name that isn't in the article) must never reach the graph, and short mentions like "US" must not match "status". → Task 7 `test_short_mention_requires_word_boundary`, `test_hallucinated_entity_dropped`.
3. **Old news processed after newer news** (out-of-order `published_at`) must not mark the *current* fact as HISTORICAL. → Task 10 `test_late_arriving_older_fact_is_stored_as_historical`.
4. **One broken source** (404, malformed XML, invalid JSON path, LLM refusal) must not stop other sources or crash the scheduler. → Task 12 `test_failing_source_does_not_block_others`, Task 11 `test_llm_failure_returns_failed_and_does_not_mark_seen`.
5. **Neo4j cosine score scale.** Without the conversion, unrelated entities score about 0.5 and the resolver's threshold behaves wrongly. → Task 3 contract test `test_vector_search_returns_raw_cosine`.

---

## File Structure

```text
pyproject.toml
docker-compose.yml                    # neo4j:5.26 for local dev
src/omnistream/
  config.py                           # Settings (pydantic-settings, env prefix OMNI_)
  models.py                           # all pydantic domain models
  embed.py                            # Embedder protocol + SentenceTransformerEmbedder
  llm.py                              # LLMClient, LLMError
  store/
    base.py                           # GraphStore protocol
    memory.py                         # InMemoryStore
    neo4j_store.py                    # Neo4jStore
    schema.cypher                     # constraints + indexes
  ingest/
    normalize.py                      # normalize_text/url, content_hash, normalize_relation
    sources/rss.py                    # fetch_rss
    sources/api.py                    # fetch_api
    sources/documents.py              # load_document, chunk_text
    extract.py                        # Extractor
    grounding.py                      # ground_extraction, is_grounded
    resolve.py                        # EntityResolver
    route.py                          # Router
    write.py                          # FactWriter
    pipeline.py                       # IngestPipeline
    scheduler.py                      # IngestScheduler
  api/app.py                          # FastAPI app factory + ingestion routes
tests/
  conftest.py                         # fakes: FakeLLM, FakeEmbedder; store fixtures
  fixtures/feeds/{news.xml,finance.xml,broken.xml}
  fixtures/api/items.json
  fixtures/golden/articles.jsonl      # live eval set
  unit/...  store/test_store_contract.py  integration/...  live/...
```

---

## Task 0: Scaffold, config and domain models

**Files:** Create `pyproject.toml`, `docker-compose.yml`, `src/omnistream/config.py`, `src/omnistream/models.py`, `tests/conftest.py`, `tests/unit/test_models.py`.

**Interfaces, Produces:**
- `Settings` fields: `neo4j_uri="bolt://localhost:7687"`, `neo4j_user="neo4j"`, `neo4j_password="password"`, `anthropic_model_extract="claude-haiku-5-5"`, `anthropic_model_route="claude-haiku-5-5"`, `llm_max_concurrency=4`, `llm_max_retries=5`, `embed_model="all-MiniLM-L6-v2"`, `embed_dim=384`, `embed_match_threshold=0.88`, `fuzzy_match_threshold=90`, `grounding_threshold=85`, `chunk_size=2000`, `chunk_overlap=200`, `max_upload_bytes=20_000_000`.
- Models (all pydantic v2):
  - `Bubble(id: str, name: str, description: str, description_embedding: list[float] | None = None, auto_summary: str | None = None, updated_at: datetime)`
  - `ApiFeedConfig(items_path: str, text_field: str, url_field: str, title_field: str | None = None, published_field: str | None = None, headers: dict[str, str] = {})`
  - `Source(id: str, type: Literal["rss","api","document"], url: str | None, credibility: float = 0.5 [0..1], poll_interval: int = 900 [>=60], bubble_ids: list[str] = [], auto_route: bool = True, api_config: ApiFeedConfig | None = None, last_polled_at: datetime | None = None, last_error: str | None = None)`. The validator requires `api_config` when `type=="api"`.
  - `RawItem(source_id: str, url: str, title: str = "", text: str, published_at: datetime | None = None, bubble_ids_override: list[str] | None = None)`
  - `ExtractedTriple(subject: str, subject_type: str, relation: str, object: str, object_type: str, exclusive: bool = False, valid_from: datetime | None = None)`
  - `Extraction(triples: list[ExtractedTriple])`
  - `Entity(id: str, canonical_name: str, type: str, aliases: list[str] = [], embedding: list[float])`
  - `Fact(id: str, subject_id: str, relation: str, object_id: str, bubble_id: str, source_id: str, source_url: str, credibility: float, source_count: int = 1, evidence_hashes: list[str], valid_from: datetime, valid_to: datetime | None = None, status: Literal["VERIFIED","HISTORICAL"] = "VERIFIED", ingested_at: datetime)`
  - `IngestResult(status: Literal["ingested","duplicate","unrouted","empty","failed"], item_hash: str, bubble_ids: list[str] = [], facts_created: int = 0, facts_merged: int = 0, facts_superseded: int = 0, dropped_ungrounded: int = 0, error: str | None = None)`

- [ ] **Step 1: Set up the project.** Run `git init`. Create `pyproject.toml` with the deps listed in the Tech Stack, `[tool.pytest.ini_options] asyncio_mode="auto"`, `markers=["integration","live"]` and `addopts='-m "not integration and not live"'`. In `docker-compose.yml` use `neo4j:5.26` with `NEO4J_AUTH=neo4j/password` on ports 7474/7687.
- [ ] **Step 2: Write failing tests** in `tests/unit/test_models.py`:
  - `test_source_rejects_credibility_out_of_range`: `Source(..., credibility=1.5)` raises `ValidationError`, and so does `-0.1`.
  - `test_source_rejects_poll_interval_below_60`: `poll_interval=59` raises.
  - `test_api_source_requires_api_config`: `Source(type="api", api_config=None, ...)` raises.
  - `test_settings_defaults`: `Settings().embed_match_threshold == 0.88` and `Settings().anthropic_model_extract == "claude-haiku-5-5"`.
- [ ] **Step 3: Run** `uv run pytest tests/unit/test_models.py -v`. Expected: FAIL (import error).
- [ ] **Step 4: Implement** `config.py` and `models.py` as specified above.
- [ ] **Step 5: Run** the same command. Expected: 4 passed.
- [ ] **Step 6: Commit** with `chore: scaffold project, settings and domain models`.

---

## Task 1: Normalization and content hashing

**Files:** Create `src/omnistream/ingest/normalize.py`, `tests/unit/test_normalize.py`.

**Interfaces, Produces:** `normalize_text(text: str) -> str`, `normalize_url(url: str) -> str`, `content_hash(url: str, text: str) -> str`, `normalize_relation(rel: str) -> str`.

Rules:
- `normalize_text`: Unicode NFKC, then casefold, then collapse all whitespace runs to one space, then strip.
- `normalize_url`: lowercase the scheme and host, drop the fragment, drop query params starting with `utm_` plus `fbclid` and `gclid`, sort the remaining params, strip a trailing `/` from the path (except root), and drop default ports (`:80` for http, `:443` for https). Non-http schemes (`doc://`, `rss://`) only get their fragment rule skipped and are otherwise returned unchanged.
- `normalize_relation`: uppercase snake case of alphanumeric words, e.g. `"is CEO of"` → `"IS_CEO_OF"` and `"acquired-by"` → `"ACQUIRED_BY"`.

- [ ] **Step 1: Write failing tests:**
  - `test_hash_ignores_whitespace_and_case`: `content_hash("https://a.com/x", "Hello  World\n") == content_hash("https://a.com/x", "hello world")`.
  - `test_hash_ignores_tracking_params_and_fragment`: `content_hash("https://A.com/x/?utm_source=t#top", t) == content_hash("https://a.com/x", t)`.
  - `test_hash_differs_for_different_text`: changing one word changes the hash.
  - `test_hash_is_sha256_hex`: `len(h) == 64` and `int(h, 16)` doesn't raise.
  - `test_nfkc_normalization`: `normalize_text("ﬁnance") == "finance"`.
  - `test_doc_scheme_keeps_fragment`: `normalize_url("doc://abc#chunk-2") == "doc://abc#chunk-2"`, because chunk identity lives in the fragment.
  - `test_normalize_relation` with the two examples above, plus `"  works for "` → `"WORKS_FOR"`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_normalize.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** using `unicodedata` and `urllib.parse` (no new deps).
- [ ] **Step 4: Run** the same command. Expected: all pass.
- [ ] **Step 5: Commit** with `feat(ingest): text/url normalization and sha256 content hash`.

---

## Task 2: GraphStore protocol, InMemoryStore and contract suite

**Files:** Create `src/omnistream/store/base.py`, `src/omnistream/store/memory.py`, `tests/store/test_store_contract.py`, and add store fixtures to `tests/conftest.py`.

**Interfaces, Produces** (all `async`, on `GraphStore`):
- Seen items: `has_seen(item_hash: str) -> bool`, `mark_seen(item_hash: str, source_id: str) -> None` (idempotent).
- Bubbles: `create_bubble(b: Bubble) -> Bubble`, `get_bubble(id) -> Bubble | None`, `list_bubbles() -> list[Bubble]`.
- Sources: `upsert_source(s: Source) -> Source`, `get_source(id) -> Source | None`, `list_sources() -> list[Source]`.
- Entities: `create_entity(e: Entity) -> Entity`, `add_alias(entity_id: str, alias: str) -> None` (no duplicates, case-insensitive), `get_entity(id) -> Entity | None`, `search_entities(embedding: list[float], type: str, k: int) -> list[tuple[Entity, float]]` (**raw cosine in [-1, 1]**, sorted descending, filtered to the same `type`).
- Facts: `create_fact(f: Fact) -> Fact`, `update_fact(f: Fact) -> Fact`, `find_active_facts(bubble_id: str, subject_id: str, relation: str) -> list[Fact]` (status VERIFIED only), `list_facts(bubble_id: str) -> list[Fact]`.

- [ ] **Step 1: Write the contract suite.** It is parametrized over a `store` fixture. In this task the fixture yields only `InMemoryStore()`; Task 3 adds the Neo4j param. Tests:
  - `test_mark_seen_then_has_seen`, `test_mark_seen_idempotent` (calling it twice doesn't raise).
  - `test_vector_search_returns_raw_cosine`: entity A with embedding `[1,0,0,…]`. Querying with the same vector gives score ≈ 1.0 (±1e-3). Querying with an orthogonal vector gives ≈ 0.0, **not 0.5**.
  - `test_vector_search_filters_by_type`: an ORG and a PRODUCT with identical embeddings. Searching with `type="ORG"` returns only the ORG.
  - `test_add_alias_deduplicates_case_insensitive`: adding "apple" twice to an entity that already has alias "Apple" leaves one alias.
  - `test_find_active_facts_excludes_historical`.
  - `test_facts_are_namespaced_by_bubble`: a fact in bubble `news` is absent from `list_facts("finance")`.
  - `test_entities_shared_across_bubbles`: facts in two bubbles can reference the same `subject_id`, and `get_entity` returns one entity.
- [ ] **Step 2: Run** `uv run pytest tests/store -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `GraphStore` as a `typing.Protocol` and `InMemoryStore` with dicts. Compute cosine with plain Python math, so numpy isn't needed in the store.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(store): GraphStore protocol, in-memory store, contract tests`.

---

## Task 3: Neo4jStore

**Files:** Create `src/omnistream/store/neo4j_store.py`, `src/omnistream/store/schema.cypher`. Modify `tests/conftest.py` (add the `neo4j` param, marked `integration`, using `testcontainers.neo4j.Neo4jContainer("neo4j:5.26")` with session scope, and clear all nodes between tests).

**Interfaces:**
- Consumes the `GraphStore` protocol from Task 2.
- Produces `Neo4jStore(uri, user, password, embed_dim)`, plus `async init_schema()` and `async close()`.

Schema (`schema.cypher`, applied idempotently with `IF NOT EXISTS`):
- Uniqueness constraints on `SeenItem.hash`, `Bubble.id`, `Source.id` and `Entity.id`.
- `CREATE VECTOR INDEX entity_embedding IF NOT EXISTS FOR (e:Entity) ON e.embedding OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}`.
- A relationship property index on `FACT(bubble_id, relation)`.
- Facts are stored as `(:Entity)-[:FACT {id, relation, bubble_id, source_id, source_url, credibility, source_count, evidence_hashes, valid_from, valid_to, status, ingested_at}]->(:Entity)`.
- `search_entities` calls `db.index.vector.queryNodes('entity_embedding', $k_oversample, $emb)` with `k_oversample = k*5`, filters `node.type = $type`, takes `k`, and returns `2*score - 1`.
- `Source.api_config` and `bubble_ids` are stored as a JSON string and a list property respectively.

- [ ] **Step 1: Add the param.** Add the Neo4j fixture param so the whole Task 2 contract suite also runs against `Neo4jStore`.
- [ ] **Step 2: Run** `uv run pytest tests/store -m integration -v`. Expected: FAIL (no module).
- [ ] **Step 3: Implement** `Neo4jStore`. Use the async driver with one session per call and `execute_write`/`execute_read`. Store datetimes as Neo4j `DateTime` and convert back to tz-aware `datetime`.
- [ ] **Step 4: Run** `uv run pytest tests/store -m integration -v`. Expected: every contract test passes for `neo4j`. Also run `uv run pytest tests/store -v`. Expected: the memory params still pass.
- [ ] **Step 5: Add** `test_init_schema_is_idempotent` (calling `init_schema()` twice doesn't raise) and run it.
- [ ] **Step 6: Commit** with `feat(store): Neo4j store with vector index and cosine conversion`.

---

## Task 4: Embedder and LLM client

**Files:** Create `src/omnistream/embed.py`, `src/omnistream/llm.py`, `tests/unit/test_llm.py`, `tests/unit/test_embed.py`. Add `FakeEmbedder` and `FakeLLM` to `tests/conftest.py`.

**Interfaces, Produces:**
- `Embedder` protocol: `async embed(texts: list[str]) -> list[list[float]]`. Vectors are L2-normalized.
- `SentenceTransformerEmbedder(model_name: str)` runs `model.encode(..., normalize_embeddings=True)` in `asyncio.to_thread`.
- `FakeEmbedder(table: dict[str, list[float]] | None = None, dim: int = 8)`. Lookup is casefolded. Unknown text gets a deterministic unit vector seeded from `sha256(text)`.
- `class LLMError(Exception)`.
- `LLMClient(client: anthropic.AsyncAnthropic, max_concurrency: int)` with `async parse(model: str, system: str, user: str, schema: type[T], max_tokens: int = 4096) -> T`. It calls `client.messages.parse(model=..., max_tokens=..., system=..., messages=[{"role":"user","content":user}], output_format=schema)` inside the semaphore. It raises `LLMError` when `stop_reason in {"refusal","max_tokens"}` or `parsed_output is None`. The `AsyncAnthropic` is built with `max_retries=settings.llm_max_retries`. Don't write a custom retry loop; the SDK already backs off on 429/5xx.
- `FakeLLM(responses: dict[type, Callable[[str], BaseModel] | BaseModel])` has the same `parse` signature and records `calls: list[(model, user)]`.

- [ ] **Step 1: Write failing tests** (use a stub object in place of `AsyncAnthropic` whose `messages.parse` is an async function you control):
  - `test_parse_returns_parsed_output`.
  - `test_refusal_raises_llm_error`: the stub returns `stop_reason="refusal"`.
  - `test_max_tokens_raises_llm_error`.
  - `test_concurrency_is_capped`: fire 10 calls with `max_concurrency=3`. The stub sleeps 50 ms and tracks peak concurrent calls. Assert `peak == 3`.
  - `test_fake_embedder_is_deterministic_and_normalized`: same text gives the same vector, and the norm ≈ 1.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_llm.py tests/unit/test_embed.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as specified above.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat: embedder and rate-limited LLM client with structured outputs`.

---

## Task 5: Source adapters (RSS, JSON API, documents)

**Files:** Create `src/omnistream/ingest/sources/{rss,api,documents}.py`, fixtures under `tests/fixtures/`, and `tests/unit/test_sources.py`.

**Interfaces, Produces:**
- `async fetch_rss(source: Source, http: httpx.AsyncClient) -> list[RawItem]`. It GETs `source.url` with a 20 s timeout, then calls `feedparser.parse(response.content)`. If `bozo` is set and there are zero entries, it raises `SourceFetchError`. Per entry: `url = entry.link`, falling back to `f"rss://{source.id}/{entry.get('id') or sha256(title)[:16]}"`. `text` is the HTML-stripped (BeautifulSoup `get_text(" ")`) `content[0].value`, falling back to `summary`. `published_at` comes from `published_parsed` or `updated_parsed` (UTC). Entries with empty text are skipped.
- `async fetch_api(source: Source, http: httpx.AsyncClient) -> list[RawItem]`. It GETs with `api_config.headers` and resolves `items_path` as a dotted path (`"data.articles"`; empty string means root list). Fields are dotted paths into each item. A missing `text_field` or `url_field` on an item skips that item. A non-list at `items_path` raises `SourceFetchError`.
- `chunk_text(text: str, size: int, overlap: int) -> list[str]`. Splits at paragraph (`\n\n`) boundaries when possible, otherwise at whitespace. Each chunk is ≤ `size` characters and consecutive chunks share about `overlap` characters.
- `load_document(source_id: str, filename: str, data: bytes, size: int, overlap: int, bubble_ids: list[str] | None) -> list[RawItem]`. Supports `.pdf` (`pypdf`, pages joined by `\n\n`), `.txt` and `.md` (UTF-8, `errors="replace"`). Anything else raises `UnsupportedDocumentError`. `url = f"doc://{sha256(data)[:16]}#chunk-{i}"`, `title = f"{filename} (part {i+1}/{n})"`, `bubble_ids_override = bubble_ids`.
- `class SourceFetchError(Exception)`, `class UnsupportedDocumentError(Exception)`.

Fixtures:
- `news.xml`: 3 entries, one with HTML in its content and one without `<link>`.
- `broken.xml`: truncated XML.
- `items.json`: `{"data": {"articles": [3 items, one missing "body"]}}`.
- PDF: generated in a fixture with `fpdf2` (2 pages of known text).

- [ ] **Step 1: Write failing tests** (mock HTTP with `respx`):
  - `test_rss_parses_entries_and_strips_html`: 3 items, and no `<p>` remains in the text.
  - `test_rss_entry_without_link_gets_synthetic_url`: `url.startswith("rss://")`.
  - `test_rss_published_at_is_utc`.
  - `test_rss_broken_feed_raises_source_fetch_error`.
  - `test_rss_http_404_raises_source_fetch_error`.
  - `test_api_extracts_dotted_paths_and_skips_incomplete_items`: 2 items.
  - `test_api_non_list_items_path_raises`.
  - `test_chunk_text_respects_size_and_overlap`: for a 5,000-char text with size 2000 and overlap 200, every chunk is ≤ 2000, there are 3 chunks, and `chunks[1]` starts with text contained in the end of `chunks[0]`.
  - `test_chunk_text_short_text_single_chunk`.
  - `test_load_pdf_extracts_text`: the known sentence from page 2 is present.
  - `test_same_file_bytes_same_urls_regardless_of_filename`: the dedup basis for re-uploads.
  - `test_unsupported_extension_raises`: `.docx`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_sources.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): RSS, JSON API and document source adapters`.

---

## Task 6: Extractor

**Files:** Create `src/omnistream/ingest/extract.py`, `tests/unit/test_extract.py`.

**Interfaces:**
- Consumes `LLMClient.parse` (Task 4) and `normalize_relation` (Task 1).
- Produces `Extractor(llm: LLMClient, model: str)` with `async extract(item: RawItem) -> Extraction`.

Prompt requirements (system prompt, fixed string constant `EXTRACTION_SYSTEM`):
- Extract factual (subject, relation, object) triples **only** for statements made in the text.
- `subject` and `object` must be copied **verbatim as they appear in the text** (surface form, not a canonicalized name). This is what makes grounding work.
- Types come from `PERSON | ORG | LOCATION | PRODUCT | EVENT | CONCEPT | MONEY | OTHER`.
- Set `exclusive=true` only when the subject can have exactly one object for that relation at a time (CEO_OF, HEADQUARTERED_IN, PRICE_IS).
- `valid_from` is the date the fact became true if the text states it, else null.
- The user message carries `Title`, `Published` (ISO or "unknown") and `Text`.

Post-processing in `extract()`: apply `normalize_relation` to every relation, drop triples where subject equals object (casefolded), drop triples with an empty field, and replace an unknown type with `OTHER`.

- [ ] **Step 1: Write failing tests** with `FakeLLM`:
  - `test_extract_normalizes_relations`: the fake returns `"is CEO of"` and the result is `"IS_CEO_OF"`.
  - `test_extract_drops_self_loops_and_empty_fields`.
  - `test_extract_unknown_type_becomes_other`.
  - `test_extract_prompt_contains_title_published_text`: inspect `fake.calls[0]`.
  - `test_extract_uses_configured_model`.
  - `test_extract_propagates_llm_error`: the fake raises `LLMError` and `extract` re-raises it.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_extract.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): LLM triple extractor with structured output`.

---

## Task 7: Grounding check

**Files:** Create `src/omnistream/ingest/grounding.py`, `tests/unit/test_grounding.py`.

**Interfaces, Produces:**
- `is_grounded(mention: str, text: str, threshold: int) -> bool`.
- `ground_extraction(extraction: Extraction, text: str, threshold: int) -> tuple[Extraction, int]`. Returns the kept triples and the number of triples dropped. A triple is dropped if **either** subject or object is ungrounded.

Rule: casefold both sides and collapse whitespace. If `len(mention) <= 3`, require `re.search(rf"\b{re.escape(mention)}\b", text)`. Otherwise use `rapidfuzz.fuzz.partial_ratio(mention, text) >= threshold`.

- [ ] **Step 1: Write failing tests** (threshold 85):
  - `test_exact_mention_grounded`.
  - `test_minor_variation_grounded`: mention `"Apple Inc"` against text `"Apple Inc. said..."`, and `"Federal Reserve"` against `"federal  reserve"`.
  - `test_hallucinated_entity_dropped`: mention `"Microsoft"` in text that only mentions Apple. The triple is removed and `dropped == 1`.
  - `test_short_mention_requires_word_boundary`: `"US"` is not grounded in `"the status quo"` but is grounded in `"the US economy"`.
  - `test_triple_dropped_if_object_ungrounded`: the subject is fine but the object is invented.
  - `test_empty_extraction_returns_zero_dropped`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_grounding.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): fuzzy grounding check for extracted mentions`.

---

## Task 8: Entity resolver (global entity table)

**Files:** Create `src/omnistream/ingest/resolve.py`, `tests/unit/test_resolve.py`.

**Interfaces:**
- Consumes `GraphStore.search_entities / create_entity / add_alias` and `Embedder.embed`.
- Produces `EntityResolver(store: GraphStore, embedder: Embedder, embed_threshold: float, fuzzy_threshold: int, candidate_k: int = 20)` with `async resolve(mention: str, type: str) -> Entity`, plus `new_batch()`, which clears the per-item cache.

Algorithm:
1. Check the cache, keyed by `(casefold(mention), type)`.
2. Embed the mention and call `search_entities(emb, type, k=candidate_k)`.
3. If the best candidate's cosine is ≥ `embed_threshold`, it's a match.
4. Otherwise, for each candidate, compute `max(token_sort_ratio(mention, n) for n in [canonical_name, *aliases])`. If the best score is ≥ `fuzzy_threshold`, it's a match.
5. On a match, `add_alias(entity.id, mention)` when the mention differs (casefolded) from the canonical name and all aliases.
6. With no match, `create_entity(Entity(id=uuid4().hex, canonical_name=mention, type=type, aliases=[], embedding=emb))`.
7. Store the result in the cache.

- [ ] **Step 1: Write failing tests** with `InMemoryStore` and a `FakeEmbedder` table that gives controlled similarities:
  - `test_embedding_match_reuses_entity_and_adds_alias`: "Apple Inc." exists. "Apple" has cosine 0.95, so it resolves to the same id and the aliases contain "Apple".
  - `test_fuzzy_fallback_when_embedding_below_threshold`: "Timothy D. Cook" vs "Timothy Cook" at cosine 0.80 with token_sort_ratio ≥ 90 resolve to the same id.
  - `test_creates_new_entity_when_no_match`.
  - `test_type_mismatch_creates_new_entity`: "Apple" ORG vs "Apple" PRODUCT give different ids.
  - `test_same_mention_twice_in_batch_creates_one_entity`: two `resolve("NewCo","ORG")` calls in one batch leave `store` with exactly one entity.
  - `test_cross_bubble_entity_shared`: this is resolver-level. Resolving the same mention for two different items (with `new_batch()` between) returns the same id.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_resolve.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): global entity resolution (embedding → fuzzy → new)`.

---

## Task 9: Bubble router (auto-route with manual override)

**Files:** Create `src/omnistream/ingest/route.py`, `tests/unit/test_route.py`.

**Interfaces:**
- Consumes `LLMClient.parse` and `GraphStore.list_bubbles`.
- Produces `Router(llm: LLMClient, model: str)` with `async route(item: RawItem, source: Source, bubbles: list[Bubble]) -> list[str]`, and `class BubbleChoice(BaseModel): bubble_ids: list[str]`.

Precedence (first non-empty wins, always filtered to ids present in `bubbles`, de-duplicated with order preserved):
1. `item.bubble_ids_override`.
2. `source.bubble_ids` when `source.auto_route is False`.
3. The LLM classifier. The prompt lists each bubble as `id | name | description` plus the item title and the first 1,500 chars of text. It may choose several bubbles or none.
4. `source.bubble_ids` as a fallback.
5. `[]`, which the pipeline reports as "unrouted".

If `bubbles` is empty, return `[]` without calling the LLM. If the classifier raises `LLMError`, fall through to step 4.

- [ ] **Step 1: Write failing tests:**
  - `test_item_override_wins_and_skips_llm`: `fake.calls == []`.
  - `test_manual_source_skips_llm`.
  - `test_classifier_can_pick_multiple_bubbles`: a bank-collapse item gives `["news","finance"]`.
  - `test_classifier_unknown_ids_filtered`.
  - `test_classifier_empty_falls_back_to_source_bubbles`.
  - `test_classifier_error_falls_back_to_source_bubbles`.
  - `test_no_bubbles_returns_empty_without_llm_call`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_route.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): bubble router with override precedence`.

---

## Task 10: Fact writer (provenance, corroboration, supersession)

**Files:** Create `src/omnistream/ingest/write.py`, `tests/unit/test_write.py`.

**Interfaces:**
- Consumes the `GraphStore` fact methods.
- Produces `FactWriter(store: GraphStore, clock: Callable[[], datetime] = utcnow)` with `async write(subject_id: str, relation: str, object_id: str, exclusive: bool, valid_from: datetime | None, bubble_id: str, item: RawItem, item_hash: str, source: Source) -> Literal["created","merged","superseded"]`. The return value is `"superseded"` when the call created a fact *and* historicized ≥ 1 other fact.

Algorithm:
- `vf = valid_from or item.published_at or clock()`.
- `active = find_active_facts(bubble_id, subject_id, relation)`.
- **Same object already active:** if `item_hash not in evidence_hashes`, append it, `source_count += 1` and `credibility = max(old, source.credibility)`, then `update_fact`. Return `"merged"`.
- **Exclusive with different active objects:**
  - For each active fact `a` with `a.valid_from <= vf`, set `valid_to=vf` and `status="HISTORICAL"`.
  - If any active `a.valid_from > vf`, the incoming fact is older news. Create it with `status="HISTORICAL"` and `valid_to=min(a.valid_from for those)`, and leave those `a` untouched.
- **Otherwise** create a VERIFIED fact with `source_count=1`, `evidence_hashes=[item_hash]`, `source_url=item.url`, `credibility=source.credibility` and `ingested_at=clock()`.

- [ ] **Step 1: Write failing tests:**
  - `test_new_fact_has_full_provenance`: every §7 field is set, and `valid_from == item.published_at`.
  - `test_corroboration_increments_source_count_and_max_credibility`: a second item with a new hash and credibility 0.9 vs 0.5 gives count 2 and credibility 0.9.
  - `test_retry_same_hash_does_not_increment_source_count`.
  - `test_exclusive_fact_supersedes_previous`: "Apple CEO_OF? Cook" at t1, then "X" at t2. The Cook fact becomes HISTORICAL with `valid_to == t2`, X is VERIFIED, and the return is `"superseded"`.
  - `test_late_arriving_older_fact_is_stored_as_historical`: X at t2 is stored first, then Cook at t1 arrives. X stays VERIFIED, and Cook is HISTORICAL with `valid_to == t2`.
  - `test_non_exclusive_relation_keeps_both_active`: ACQUIRED A then ACQUIRED B leaves both VERIFIED.
  - `test_supersession_is_per_bubble`: an exclusive fact in `finance` does not historicize the same subject/relation in `news`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_write.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): fact writer with provenance, corroboration and HISTORICAL supersession`.

---

## Task 11: Ingest pipeline orchestration

**Files:** Create `src/omnistream/ingest/pipeline.py`, `tests/unit/test_pipeline.py`.

**Interfaces:**
- Consumes everything from Tasks 1 and 6–10.
- Produces `IngestPipeline(store, router: Router, extractor: Extractor, resolver: EntityResolver, writer: FactWriter, grounding_threshold: int)` with `async process(item: RawItem, source: Source) -> IngestResult` and `async process_many(items: list[RawItem], source: Source) -> list[IngestResult]` (sequential, in order).

Order (must match):
1. `h = content_hash(item.url, item.text)`. If `normalize_text(item.text) == ""`, return `empty`.
2. If `h` is in `self._inflight` or `await store.has_seen(h)`, return `duplicate`. Otherwise add `h` to `_inflight`, and remove it in `finally`.
3. `bubbles = await router.route(item, source, await store.list_bubbles())`. If empty, return `unrouted` (not marked seen).
4. `extraction = await extractor.extract(item)`.
5. `kept, dropped = ground_extraction(extraction, f"{item.title}\n{item.text}", threshold)`.
6. `resolver.new_batch()`. Resolve subject and object for each kept triple.
7. For each triple and each bubble, call `writer.write(...)` and tally the counters.
8. `await store.mark_seen(h, source.id)`, then return `ingested` (even if 0 facts, so the item isn't re-extracted forever).

Any exception in steps 3–7 returns `failed` with `error=repr(exc)`, is logged with `logger.exception`, and does **not** mark the item seen.

- [ ] **Step 1: Write failing tests** with `InMemoryStore`, `FakeLLM` and `FakeEmbedder`:
  - `test_happy_path_writes_facts_to_all_routed_bubbles`: routed to news and finance, 1 grounded triple gives 2 facts with the same subject_id, and `status=="ingested"`.
  - `test_duplicate_item_skipped_before_llm`: process twice. The second is `duplicate` and `len(fake.calls)` doesn't grow.
  - `test_concurrent_duplicate_items_processed_once`: `asyncio.gather(process(i), process(i))` gives one `ingested` and one `duplicate`. The FakeLLM must `await asyncio.sleep(0.01)` so the calls overlap.
  - `test_ungrounded_triples_counted_and_not_written`.
  - `test_unrouted_item_not_marked_seen`.
  - `test_llm_failure_returns_failed_and_does_not_mark_seen`: then fix the fake and re-process, which gives `ingested`.
  - `test_empty_text_returns_empty`.
  - `test_item_with_no_triples_is_marked_seen`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_pipeline.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): end-to-end ingest pipeline with dedup and failure isolation`.

---

## Task 12: Polling scheduler

**Files:** Create `src/omnistream/ingest/scheduler.py`, `tests/unit/test_scheduler.py`.

**Interfaces:**
- Consumes `fetch_rss` and `fetch_api` (Task 5), `IngestPipeline.process_many` (Task 11), and `GraphStore.list_sources / upsert_source`.
- Produces `IngestScheduler(store, pipeline, http: httpx.AsyncClient, scheduler: AsyncIOScheduler | None = None)` with these methods:
  - `async start()`: schedules every non-document source.
  - `schedule_source(source: Source) -> None`: an `IntervalTrigger(seconds=source.poll_interval)` job with id `f"poll:{source.id}"`, using `replace_existing=True`, `max_instances=1` and `coalesce=True`.
  - `async poll_source(source_id: str) -> list[IngestResult]`.
  - `async shutdown()`.

`poll_source` dispatches on `source.type` (rss → `fetch_rss`, api → `fetch_api`, document → `[]`). On `SourceFetchError` or `httpx.HTTPError` it sets `source.last_error`, upserts and returns `[]`. On success it sets `last_polled_at=now` and `last_error=None`. It never raises.

- [ ] **Step 1: Write failing tests** (use `respx` for HTTP):
  - `test_poll_rss_source_ingests_items`: uses the `news.xml` fixture, so `len(results)==3` and the statuses are `ingested`.
  - `test_second_poll_reports_duplicates`.
  - `test_failing_source_does_not_block_others`: source A returns 500 and source B is fine. Poll both: A gives `[]` with `last_error` set, and B ingests.
  - `test_schedule_source_registers_interval_job`: the job `poll:{id}` exists and its trigger interval equals `poll_interval`.
  - `test_rescheduling_replaces_job`: scheduling twice leaves one job.
  - `test_document_sources_not_scheduled`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_scheduler.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(ingest): APScheduler-based source polling with error isolation`.

---

## Task 13: Ingestion HTTP API

**Files:** Create `src/omnistream/api/app.py`, `tests/unit/test_api.py`.

**Interfaces:**
- Consumes all of the above.
- Produces `create_app(store, pipeline, scheduler, embedder) -> FastAPI`. Wiring with real components lives in `omnistream.api.app:main_app()`, which reads `Settings` and runs `init_schema` and `scheduler.start()` in the lifespan.

Routes:

| Method / path | Body | Success | Errors |
|---|---|---|---|
| `POST /bubbles` | `{name, description}` | 201 `Bubble`, with `description_embedding` computed | 422 empty name/description; 409 duplicate name (case-insensitive) |
| `GET /bubbles` | none | 200 `list[Bubble]` | none |
| `POST /sources` | `{type: rss\|api, url, credibility?, poll_interval?, bubble_ids?, auto_route?, api_config?}` | 201 `Source`, and the source is scheduled | 422 validation or unknown bubble id |
| `GET /sources` | none | 200 `list[Source]` | none |
| `POST /sources/{id}/poll` | none | 200 `list[IngestResult]` | 404 unknown id |
| `POST /documents` | multipart `file`, form `bubble_ids` (comma-separated, optional), `credibility` (optional) | 200 `list[IngestResult]`. A `document` source is created per upload. | 413 over `max_upload_bytes`; 415 unsupported type; 422 unknown bubble id |

- [ ] **Step 1: Write failing tests** with `httpx.AsyncClient(transport=ASGITransport(app))` and fakes:
  - One test per success row.
  - `test_create_source_unknown_bubble_422`, `test_poll_unknown_source_404`, `test_upload_too_large_413`, `test_upload_unsupported_415`, `test_duplicate_bubble_name_409`.
  - `test_upload_same_document_twice_second_all_duplicate`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** with `feat(api): ingestion endpoints for bubbles, sources, polling and uploads`.

---

## Task 14: Integration and live acceptance tests

**Files:** Create `tests/integration/test_ingest_e2e.py`, `tests/live/test_extraction_golden.py`, `tests/fixtures/golden/articles.jsonl`, `tests/fixtures/feeds/finance.xml`.

**Interfaces:** Consumes `main_app`-style wiring with `Neo4jStore`, the real `SentenceTransformerEmbedder` and `FakeLLM` (integration) or the real `LLMClient` (live).

`articles.jsonl` holds 6 short (≤ 1,500 chars) **self-written** articles. Write fictional companies and people, not copied news. Each record is `{id, title, text, published_at, expected_bubbles: [...], expected_entities: [{name, type}], expected_facts: [{subject, relation_contains, object}]}`. Cover:

1. a single-bubble news item;
2. a single-bubble finance item;
3. a bank collapse (news + finance);
4. a CEO change (`exclusive`, supersedes article 5's fact);
5. the older CEO fact (published earlier, ingested after 4);
6. an article that mentions "Apple Inc." where 1 said "Apple" (entity merge).

- [ ] **Step 1: Write the integration tests** (`@pytest.mark.integration`, Neo4j container, real embedder, FakeLLM returning scripted extractions):
  - `test_e2e_feed_to_neo4j`: create bubbles `news` and `finance`, add a source pointing at `news.xml` (served via respx), then poll. Neo4j holds the expected facts, every `FACT` has non-null `source_id`, `source_url`, `credibility`, `valid_from` and `ingested_at`, and the `SeenItem` count equals the ingested count.
  - `test_e2e_cross_bubble_entity_shared`: the same entity id appears in facts from both bubbles (Cypher: `MATCH (e:Entity)-[f:FACT]-() RETURN e.id, collect(DISTINCT f.bubble_id)`).
  - `test_e2e_real_embedder_merges_aliases`: "Apple" and "Apple Inc." (ORG) resolve to one Entity node with the real MiniLM model.
  - `test_e2e_restart_preserves_dedup`: build a fresh `Neo4jStore` on the same container and re-poll. Everything is `duplicate`.
- [ ] **Step 2: Run** `docker compose up -d` (optional; testcontainers starts its own), then `uv run pytest -m integration -v`. Expected: all pass. Fix forward by adding a failing unit test first for any bug found.
- [ ] **Step 3: Write the live golden test** (`@pytest.mark.live`, real `claude-haiku-5-5`). Ingest the 6 articles in file order through `IngestPipeline` with `InMemoryStore` and the real embedder. Assert:
  - entity recall ≥ 0.8 (an expected entity counts as found if some Entity has a canonical name or alias with `token_sort_ratio ≥ 90` and the same type);
  - **0** stored entity names that fail `is_grounded` against their source article;
  - routing exact-match on ≥ 5 of 6 articles;
  - after article 5, the Acme CEO fact from article 4 is still VERIFIED and article 5's is HISTORICAL;
  - article 6 created no second "Apple" ORG entity.

  The test also prints a per-article table (entities found or missed, routing, tokens used) so a human can inspect quality.
- [ ] **Step 4: Run** `ANTHROPIC_API_KEY=... uv run pytest -m live -v -s`. Expected: pass. If recall < 0.8, tune `EXTRACTION_SYSTEM`, never the thresholds in the test, and re-run.
- [ ] **Step 5: Commit** with `test: e2e Neo4j integration and live golden extraction eval`.

---

## Final acceptance checklist (an agent runs all of these before claiming done)

```bash
uv run pytest -v                              # unit + contract (memory): all pass, < 30 s
uv run pytest -m integration -v               # Neo4j contract + e2e: all pass
ANTHROPIC_API_KEY=$KEY uv run pytest -m live -v -s   # golden eval thresholds met
uv run ruff check src tests && uv run mypy src       # clean
```

Then a manual smoke test against the running app:

```bash
docker compose up -d
uv run uvicorn omnistream.api.app:main_app --factory --port 8000 &
curl -s -X POST localhost:8000/bubbles -H 'content-type: application/json' \
  -d '{"name":"News","description":"General world and business news"}'
curl -s -X POST localhost:8000/sources -H 'content-type: application/json' \
  -d '{"type":"rss","url":"https://feeds.bbci.co.uk/news/business/rss.xml","credibility":0.8}'
curl -s -X POST localhost:8000/sources/<id>/poll | jq '[.[].status] | group_by(.) | map({(.[0]): length}) | add'
curl -s -X POST localhost:8000/sources/<id>/poll | jq '[.[].status] | unique'   # expect ["duplicate"]
```

Check in Neo4j Browser (`http://localhost:7474`):

```cypher
MATCH ()-[f:FACT]->() WHERE f.source_url IS NULL OR f.valid_from IS NULL RETURN count(f);  // expect 0
MATCH (e:Entity) WITH toLower(e.canonical_name) AS n, e.type AS t, count(*) AS c WHERE c > 1 RETURN n, t, c;  // review duplicates
```

| Spec requirement | Covered by |
|---|---|
| §3.1 poll / receive (RSS, API, documents) | Tasks 5, 12, 13 |
| §3.2 SHA-256 dedup of normalized text + URL | Tasks 1, 11 |
| §3.3 LLM extraction (triples + timestamp) | Task 6 |
| §3.4 fuzzy grounding check | Task 7 |
| §3.5 global entity resolution (embedding → fuzzy → new) | Task 8 |
| §3.6 write with source ID, URL, credibility, validity | Task 10 |
| §4.3 auto-route with manual override, multi-bubble | Task 9 |
| §4.4 / §4.5 global entities, one DB with namespaces | Tasks 2, 3 |
| §4.8 valid_from / valid_to / HISTORICAL | Task 10 |
| §5 rate-limit queue with backoff | Task 4 |
| §5 per-feed credibility | Tasks 0, 10, 13 |
| §7 data model | Tasks 0, 3 |
