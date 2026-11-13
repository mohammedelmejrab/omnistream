# real-v2 recorded validation

Commands run from the repository root with the supplied venv. These are copied outputs.

```text
> .venv\Scripts\python.exe -m pytest -q
........................................................................ [  7%]
........................................................................ [ 14%]
........................................................................ [ 21%]
........................................................................ [ 28%]
........................................................................ [ 35%]
........................................................................ [ 42%]
........................................................................ [ 49%]
........................................................................ [ 57%]
........................................................................ [ 64%]
................s....................................................... [ 71%]
........................................................................ [ 78%]
........................................................................ [ 85%]
........................................................................ [ 92%]
........................................................................ [ 99%]
..                                                                       [100%]
1009 passed, 1 skipped, 21 deselected in 48.65s

> .venv\Scripts\ruff.exe check .
All checks passed!

> .venv\Scripts\omni.exe realdata verify --name real-v2
QA: 350 originals checked; cached LLM statistics read; computing local BGE
HOLD: 350 items

> git diff --check
(no output; exit 0)

> git diff --name-only -- src/omnistream/eval/real/real-v1* src/omnistream/eval/real/sources-real-v1.json docs/realdata/real-v1*
(no output; v1 artefacts unchanged)
```

Additional real checks passed: current source-file SHA-256 matches collection record;
accepted replay snapshot under data/real/real-v2/snapshots has 350 records; all accepted
raw/text paths are under data/real/; 25 fact records have valid accepted references,
chronological publication dates and verbatim evidence quotes of at most 15 words.
No production graph or database was used. No .env file was opened; no git commits made.
No writes were made to data/snapshots/ or the diagnostics agent's directories.

The first embedding run completed local BGE computation but PowerShell treated its
stderr progress/warning stream as a NativeCommandError during redirection. An explicit
subsequent CLI invocation completed with exit code 0, as pasted above. Model weights
and computed vectors are cached locally; the final verification reused these vectors.

The private OpenRouter credential request timed out. LLM calls and actual cost are zero;
entity extraction, the 30-item entity precision check, cross-bubble counts, top 40 and
alias statistics are incomplete. Empty entity exports explicitly say extraction_status=missing.
