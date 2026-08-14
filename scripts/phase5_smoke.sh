#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=".phase5-runs"
KEY_ROOT="$RUN_ROOT/keys"
REGISTRY="$RUN_ROOT/experiments.registry.sqlite3"
MATRIX="$RUN_ROOT/matrix.json"
CAMPAIGN="$RUN_ROOT/campaign.yaml"
REVISION="${GITHUB_SHA:-phase5-smoke}"

cleanup() {
  rm -rf "$RUN_ROOT"
}
trap cleanup EXIT

rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT" "$KEY_ROOT"

llm-arbitrage keygen \
  --private-key "$KEY_ROOT/provenance.pem" \
  --public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage registry-init "$REGISTRY"
llm-arbitrage registry-trust-key \
  "$REGISTRY" \
  "$KEY_ROOT/provenance.pub.pem" \
  --label phase5-smoke
llm-arbitrage plan-matrix \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --sweep examples/phase3/sweep.yaml \
  --output "$MATRIX"

python - <<'PY'
import json
from pathlib import Path

matrix = json.loads(Path('.phase5-runs/matrix.json').read_text(encoding='utf-8'))
evaluation_ids = [item['evaluation_id'] for item in matrix['evaluations'][:2]]
lines = [
    'schema_version: 1',
    'execution:',
    '  maximum_parallel_evaluations: 2',
    '  maximum_failures: 1',
    '  stop_on_failure: true',
    'selection:',
    '  include_evaluation_ids:',
]
lines.extend(f'    - {evaluation_id}' for evaluation_id in evaluation_ids)
lines.extend(['  exclude_evaluation_ids: []', ''])
Path('.phase5-runs/campaign.yaml').write_text('\n'.join(lines), encoding='utf-8')
PY

llm-arbitrage validate-campaign "$CAMPAIGN"
llm-arbitrage run-campaign \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --matrix "$MATRIX" \
  --campaign "$CAMPAIGN" \
  --registry "$REGISTRY" \
  --private-key "$KEY_ROOT/provenance.pem" \
  --output "$RUN_ROOT/campaigns" \
  --code-revision "$REVISION"

WORKSPACE="$(
  find "$RUN_ROOT/campaigns" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name 'campaign-*' \
    -print \
    -quit
)"
test -n "$WORKSPACE"
llm-arbitrage campaign-status "$WORKSPACE"
llm-arbitrage registry-verify "$REGISTRY"

python - "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
report = json.loads((workspace / 'report.json').read_text(encoding='utf-8'))
summary = report['summary']
assert summary['status'] == 'completed'
assert summary['registered'] == 2
assert summary['failed'] == 0
assert report['selection'] is None
assert report['realized_pnl'] is None
assert report['sharpe_ratio'] is None
assert report['alpha_decay'] is None
assert (workspace / 'aggregate.json').is_file()
assert len(list((workspace / 'attestations').glob('*.json'))) == 2
PY
