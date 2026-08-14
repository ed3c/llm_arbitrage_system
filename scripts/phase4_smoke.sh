#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=".phase4-runs"
KEY_ROOT=".phase4-keys"
REGISTRY="$RUN_ROOT/experiments.registry.sqlite3"
REVISION="${GITHUB_SHA:-phase4-smoke}"

rm -rf "$RUN_ROOT" "$KEY_ROOT"
mkdir -p "$RUN_ROOT" "$KEY_ROOT"

llm-arbitrage keygen --private-key "$KEY_ROOT/provenance.pem" --public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage validate-lineage examples/phase4/lineage.yaml
llm-arbitrage registry-init "$REGISTRY"
llm-arbitrage registry-trust-key "$REGISTRY" "$KEY_ROOT/provenance.pub.pem" --label phase4-smoke
llm-arbitrage registry-import-lineage "$REGISTRY" examples/phase4/lineage.yaml

llm-arbitrage run \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --output "$RUN_ROOT/base" \
  --code-revision "$REVISION"
BASE_BUNDLE="$(find "$RUN_ROOT/base" -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit)"
test -n "$BASE_BUNDLE"
llm-arbitrage sign-bundle \
  --bundle "$BASE_BUNDLE" \
  --private-key "$KEY_ROOT/provenance.pem" \
  --lineage examples/phase4/lineage.yaml \
  --output "$RUN_ROOT/base.attestation.json"
llm-arbitrage verify-attestation \
  --bundle "$BASE_BUNDLE" \
  --attestation "$RUN_ROOT/base.attestation.json" \
  --trusted-public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage registry-import-bundle "$REGISTRY" "$BASE_BUNDLE" "$RUN_ROOT/base.attestation.json"

llm-arbitrage plan-matrix \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --sweep examples/phase3/sweep.yaml \
  --output "$RUN_ROOT/matrix.json"
EVALUATION_ID="$(python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('.phase4-runs/matrix.json').read_text(encoding='utf-8'))
print(payload['evaluations'][0]['evaluation_id'])
PY
)"
llm-arbitrage run-evaluation \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --matrix "$RUN_ROOT/matrix.json" \
  --evaluation-id "$EVALUATION_ID" \
  --output "$RUN_ROOT/evaluations" \
  --code-revision "$REVISION"
EVALUATION_BUNDLE="$(find "$RUN_ROOT/evaluations" -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit)"
test -n "$EVALUATION_BUNDLE"
llm-arbitrage sign-bundle \
  --bundle "$EVALUATION_BUNDLE" \
  --private-key "$KEY_ROOT/provenance.pem" \
  --output "$RUN_ROOT/evaluation.attestation.json"
llm-arbitrage verify-attestation \
  --bundle "$EVALUATION_BUNDLE" \
  --attestation "$RUN_ROOT/evaluation.attestation.json" \
  --trusted-public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage registry-register-evaluation \
  "$REGISTRY" \
  --matrix "$RUN_ROOT/matrix.json" \
  --evaluation-id "$EVALUATION_ID" \
  --bundle "$EVALUATION_BUNDLE" \
  --attestation "$RUN_ROOT/evaluation.attestation.json"
llm-arbitrage registry-aggregate "$REGISTRY" --matrix "$RUN_ROOT/matrix.json" --output "$RUN_ROOT/aggregate.json"
llm-arbitrage registry-verify "$REGISTRY"
