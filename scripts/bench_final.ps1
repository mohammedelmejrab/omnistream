# Final test QA with the development-chosen retrieval settings, one QA process at
# a time. New run directories (not a resume of the earlier test run).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\mehme\omnistream-integrated"
$omni = "C:\Users\mehme\.omnistream\venv-gpu\Scripts\omni.exe"
$logDir = "$repo\docs\eval\bench"
$log = "$logDir\final.log"
Set-Location $repo
$env:NEO4J_PASSWORD = (Get-Content "C:\Users\mehme\.omnistream\neo4j_pw.txt" -Raw).Trim()
$env:PYTHONUNBUFFERED = "1"
$env:OMNI_OWN_SEED_MODE = "passage_specificity"
$env:OMNI_OWN_RERANK = "on"
$env:OMNI_OWN_PASSAGE_NODES = "on"
$env:OMNI_OWN_PASSAGE_RERANK = "rrf"
$env:OMNI_OWN_RESEED = "on"
$env:OMNI_OWN_FACT_SEEDS = "3"
$env:OMNI_OWN_RRF_PPR_WEIGHT = "2"
function Note($m) { "$(Get-Date -Format s) $m" | Add-Content $log }
$rows = "closed_book,external,own,own+subagents"
foreach ($d in @("2wiki", "musique", "hotpotqa")) {
    $extra = @()
    if ($d -eq "musique") { $extra = @("--exclude-sample", "50:0") }
    Note "$d QA start"
    & $omni eval bench-qa --dataset $d --n 200 --seed 0 --snapshot "bench-$d-n200-full-oie" --rows $rows @extra *>> "$logDir\qa-$d-final.log"
    Note "$d QA exit $LASTEXITCODE"
}
