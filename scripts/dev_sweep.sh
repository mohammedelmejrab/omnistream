#!/usr/bin/env bash
# Retrieval-only dev sweep. Each argument is TAG:VAR=VAL,VAR=VAL (env for
# that variant); every variant runs on the three datasets, sequentially (RAM).
cd "$(dirname "$0")/.."
export NEO4J_PASSWORD="$(tr -d '\r\n' < /c/Users/mehme/.omnistream/neo4j_pw.txt)"
export OMNI_OWN_SEED_MODE=passage_specificity OMNI_OWN_RERANK=on OMNI_OWN_PASSAGE_NODES=on PYTHONIOENCODING=utf-8
PY=/c/Users/mehme/.omnistream/venv-gpu/Scripts/python.exe
DATASETS="${DATASETS:-2wiki musique hotpotqa}"
for spec in "$@"; do
  tag="${spec%%:*}"; vars="${spec#*:}"
  for d in $DATASETS; do
    env $(echo "$vars" | tr ',' ' ') $PY scripts/dev_retrieval.py --dataset $d --n 100 --tag "$tag" 2>/dev/null | tail -1
  done
done
