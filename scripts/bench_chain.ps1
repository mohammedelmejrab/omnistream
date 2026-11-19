param(
    [Parameter(Mandatory)][string]$Dataset,
    [Parameter(Mandatory)][int]$WaitPid,
    [string]$Exclude = ""
)
# Waits for a running bench ingest, retries failed extractions (up to 2 reruns),
# then runs the pre-declared 200-question test QA on the full-corpus snapshot.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\mehme\omnistream-integrated"
$omni = "C:\Users\mehme\.omnistream\venv-gpu\Scripts\omni.exe"
$snap = "bench-$Dataset-n200-full-oie"
$logDir = "$repo\docs\eval\bench"
Set-Location $repo
$env:NEO4J_PASSWORD = (Get-Content "C:\Users\mehme\.omnistream\neo4j_pw.txt" -Raw).Trim()
$env:PYTHONUNBUFFERED = "1"

while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 60 }
"$(Get-Date -Format s) ingest PID $WaitPid finished" | Add-Content "$logDir\chain-$Dataset.log"

$ingestArgs = @("eval", "bench-ingest", "--dataset", $Dataset, "--n", "200", "--seed", "0",
    "--corpus", "full", "--snapshot", $snap, "--extractor", "openie", "--extract-concurrency", "8")
for ($i = 1; $i -le 2; $i++) {
    "$(Get-Date -Format s) retry ingest $i" | Add-Content "$logDir\chain-$Dataset.log"
    & $omni @ingestArgs *>> "$logDir\ingest-$Dataset-n200-full-oie-retry.log"
}

$env:OMNI_OWN_SEED_MODE = "passage_specificity"
$env:OMNI_OWN_RERANK = "on"
$env:OMNI_OWN_PASSAGE_NODES = "on"
$qaArgs = @("eval", "bench-qa", "--dataset", $Dataset, "--n", "200", "--seed", "0",
    "--snapshot", $snap, "--rows", "closed_book,external,classic,own,own+subagents")
if ($Exclude) { $qaArgs += @("--exclude-sample", $Exclude) }
"$(Get-Date -Format s) start QA" | Add-Content "$logDir\chain-$Dataset.log"
& $omni @qaArgs *>> "$logDir\qa-$Dataset-n200-full-oie.log"
"$(Get-Date -Format s) QA exit $LASTEXITCODE" | Add-Content "$logDir\chain-$Dataset.log"
