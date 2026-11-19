param([int]$IngestPid = 0)
# Remaining test QA, one QA process at a time (concurrent QA processes
# exhausted RAM). Rows: classic skipped for now; own+subagents before own.
# The HotpotQA ingest (3 resumable passes) runs alongside in its own process.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\mehme\omnistream-integrated"
$omni = "C:\Users\mehme\.omnistream\venv-gpu\Scripts\omni.exe"
$logDir = "$repo\docs\eval\bench"
$log = "$logDir\queue.log"
Set-Location $repo
$env:NEO4J_PASSWORD = (Get-Content "C:\Users\mehme\.omnistream\neo4j_pw.txt" -Raw).Trim()
$env:PYTHONUNBUFFERED = "1"
function Note($m) { "$(Get-Date -Format s) $m" | Add-Content $log }

if ($IngestPid) {
    $ingest = [pscustomobject]@{ Id = $IngestPid }
    Note "waiting on running hotpotqa ingest (PID $IngestPid)"
} else {
    $ingest = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
        "-NoProfile", "-Command",
        "Set-Location '$repo'; `$env:NEO4J_PASSWORD='$env:NEO4J_PASSWORD'; `$env:PYTHONUNBUFFERED='1'; " +
        "for (`$i=1; `$i -le 3; `$i++) { & '$omni' eval bench-ingest --dataset hotpotqa --n 200 --seed 0 " +
        "--corpus full --snapshot bench-hotpotqa-n200-full-oie --extractor openie --extract-concurrency 8 " +
        "*>> '$logDir\ingest-hotpotqa-n200-full-oie-retry.log' }")
    Note "hotpotqa ingest started (PID $($ingest.Id))"
}

$env:OMNI_OWN_SEED_MODE = "passage_specificity"
$env:OMNI_OWN_RERANK = "on"
$env:OMNI_OWN_PASSAGE_NODES = "on"
$rows = "closed_book,external,own+subagents,own"

Note "musique QA resume"
& $omni eval bench-qa --dataset musique --n 200 --seed 0 --snapshot bench-musique-n200-full-oie --rows $rows --exclude-sample 50:0 --resume *>> "$logDir\qa-musique-n200-full-oie.log"
Note "musique QA exit $LASTEXITCODE"

Note "2wiki QA resume"
& $omni eval bench-qa --dataset 2wiki --n 200 --seed 0 --snapshot bench-2wiki-n200-full-oie --rows $rows --resume *>> "$logDir\qa-2wiki-n200-full-oie.log"
Note "2wiki QA exit $LASTEXITCODE"

while (Get-Process -Id $ingest.Id -ErrorAction SilentlyContinue) { Start-Sleep 60 }
Note "hotpotqa ingest finished"
Note "hotpotqa QA start"
& $omni eval bench-qa --dataset hotpotqa --n 200 --seed 0 --snapshot bench-hotpotqa-n200-full-oie --rows $rows *>> "$logDir\qa-hotpotqa-n200-full-oie.log"
Note "hotpotqa QA exit $LASTEXITCODE"
