# Real-v1 recorded validation

Commands ran from the repository root with the project venv. No graph workers or LLM calls ran.

```text
.venv/Scripts/python.exe -m pytest -q
998 passed, 1 skipped, 21 deselected in 46.92s

.venv/Scripts/python.exe -m ruff check .
All checks passed!

.venv/Scripts/omni.exe realdata collect --name real-v1
Manifest unchanged: True
Accepted replay unchanged: True
recorded 228 items
```

All 228 clean originals passed SHA-256, dedup-ID and length validation. The accepted replay has the same 228 content IDs and source bubble hints. The manual NER audit is bound to manifest SHA-256 `edf451ad7b0d322f0474685433365fa0050a315564b0315a003e2a2c922dda03`.

Full raw test/collection output remains under ignored `data/real/real-v1/`. Scoped realdata/source tests also passed: `37 passed in 7.84s` (before the final redirect-policy regression was added; the full 998-test run includes it).

No commits were made. Protected eval-v1/eval-v2 snapshots and the other agent's diagnostics directories were not modified.
