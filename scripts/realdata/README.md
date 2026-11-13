# Real corpus tooling

Run from the repository root. The implementation is in `src/omnistream/eval/real/` and the `omni realdata` CLI; source bodies and HTTP caches stay in ignored `data/`.

```powershell
.venv/Scripts/omni.exe realdata collect --name real-v1 --since 2026-09-18 --until 2026-11-13
.venv/Scripts/omni.exe realdata verify --name real-v1
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
```

Install dependencies from `pyproject.toml` and the pinned local NER model as documented in the quality report. These commands deliberately construct settings with `_env_file=None`. Round 1 collection and verification do not use the LLM; neither round uses the production database/graph. Only an isolated C2 intake database is populated.

`record_manual_audit.py` materialises annotations recorded by directly reading the fixed-seed sample. It is not an automatic judge and cannot replace manual review for a changed manifest. The audit is bound to the manifest SHA-256. The raw review prefixes are kept only in `data/real/real-v1/audit-input.json`; the committed audit has entity-name metadata and quality notes, no article excerpts.

The committed manifest is authoritative for corpus membership; local storage also retains intermediate discovery/collection payloads. Do not ingest or write questions until the owner approves a corpus version. The accepted replay snapshot carries source bubble hints as overrides; those hints are provisional and must be reviewed. A later C3 routing experiment should use a separate replay copy with overrides cleared, leaving the frozen corpus untouched.


## Round 2

```powershell
.venv/Scripts/omni.exe realdata collect --name real-v2
.venv/Scripts/python.exe -m omnistream.eval.real.entities_v2 --name real-v2
.venv/Scripts/omni.exe realdata verify --name real-v2
```

V2 settings always disable dotenv. Supply OpenRouter credentials through the process
or the extraction command's `--secret-file` private path, never by reading `.env`.
The entity pass uses `omnistream.llm.LLMClient` with JSON mode and the specified
DeepSeek model; it caches validated observed surface forms and provider usage per
item under `data/real/real-v2/llm-entities/`. Verification is offline and reads this
cache; missing entries cause HOLD, with no local-NER fallback. Token-priced cost is
reported separately from provider-reported cost.

V2 replay snapshots are under `data/real/real-v2/snapshots/`, never the shared
`data/snapshots/`. Each collection creates a fresh isolated intake database so an
interrupted run cannot make later collection silently discard accepted documents.
HTTP responses are reused. Bubble targets use deterministic seeded round-robin
selection across source IDs; publisher groups still determine concentration gates.

Documented API access requires both an exact terms URL and a code-allowlisted HTTPS
endpoint. Redirects outside that scope are robots checked. Requests remain sequential
with a minimum three-second per-host delay and stricter robots crawl delays.
EX-99 documents are discovered from the official filing index's document type and
kept as separate items linked by accession. ArXiv query provenance is in each row.
Displayed leading body dates and conservative URL date/month upper bounds supply
`event_date_hint`; historical dates within prose do not establish article age.

The changed-fact validator checks metadata references, chronological dates and short
verbatim evidence against local originals. It does not prove semantic supersession.
Only records actually reviewed against both documents may carry `verified: true`.
The 30-item audit must be bound to the current manifest SHA-256.
