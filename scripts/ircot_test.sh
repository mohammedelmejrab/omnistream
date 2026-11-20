#!/usr/bin/env bash
# After the final QA run: IRCoT multi-step retrieval on the 200 test questions.
cd "$(dirname "$0")/.."
until grep -q "hotpotqa QA exit" docs/eval/bench/final.log 2>/dev/null; do sleep 60; done
export NEO4J_PASSWORD="$(tr -d '\r\n' < /c/Users/mehme/.omnistream/neo4j_pw.txt)"
export OMNI_OWN_SEED_MODE=passage_specificity OMNI_OWN_RERANK=on OMNI_OWN_PASSAGE_NODES=on \
  OMNI_OWN_PASSAGE_RERANK=rrf OMNI_OWN_RESEED=on OMNI_OWN_FACT_SEEDS=3 OMNI_OWN_RRF_PPR_WEIGHT=2 \
  OMNI_OWN_IRCOT=on PYTHONIOENCODING=utf-8
for d in 2wiki musique hotpotqa; do
  /c/Users/mehme/.omnistream/venv-gpu/Scripts/python.exe scripts/dev_retrieval.py --dataset $d --split test --tag ircot 2>/dev/null | tail -1 >> docs/eval/bench/test-retrieval/ircot.log
done
echo done >> docs/eval/bench/test-retrieval/ircot.log
