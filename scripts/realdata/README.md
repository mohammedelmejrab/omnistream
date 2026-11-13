# Real corpus tooling

Run from the repository root. The implementation is in `src/omnistream/eval/real/` and the `omni realdata` CLI; source bodies and HTTP caches stay in ignored `data/`.

```powershell
.venv/Scripts/omni.exe realdata collect --name real-v1 --since 2026-09-18 --until 2026-11-13
.venv/Scripts/omni.exe realdata verify --name real-v1
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
```

Install dependencies from `pyproject.toml` and the pinned local NER model as documented in the quality report. These commands deliberately construct settings with `_env_file=None`. Neither collection nor verification uses the LLM or production database/graph. Only an isolated C2 intake database is populated.

`record_manual_audit.py` materialises annotations recorded by directly reading the fixed-seed sample. It is not an automatic judge and cannot replace manual review for a changed manifest. The audit is bound to the manifest SHA-256. The raw review prefixes are kept only in `data/real/real-v1/audit-input.json`; the committed audit has entity-name metadata and quality notes, no article excerpts.

The committed manifest is authoritative for corpus membership; local storage also retains intermediate discovery/collection payloads. Do not ingest or write questions until the owner approves a corpus version. The accepted replay snapshot carries source bubble hints as overrides; those hints are provisional and must be reviewed. A later C3 routing experiment should use a separate replay copy with overrides cleared, leaving the frozen corpus untouched.
