#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=".phase6-runs"
KEY_ROOT="$RUN_ROOT/keys"
REGISTRY="$RUN_ROOT/experiments.registry.sqlite3"
DATASET="$RUN_ROOT/events.jsonl"
CONFIG="$RUN_ROOT/experiment.yaml"
SWEEP="$RUN_ROOT/sweep.yaml"
MATRIX="$RUN_ROOT/matrix.json"
INPUTS="$RUN_ROOT/statistics-inputs.json"
REPORT="$RUN_ROOT/oos-statistics.json"
REPORT_ATTESTATION="$RUN_ROOT/oos-statistics.attestation.json"
REVISION="${GITHUB_SHA:-phase6-smoke}"

cleanup() {
  rm -rf "$RUN_ROOT"
}
trap cleanup EXIT

rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT" "$KEY_ROOT" "$RUN_ROOT/marks" "$RUN_ROOT/attestations"

python - <<'PY'
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

root = Path('.phase6-runs')
start = datetime(2026, 2, 1, tzinfo=timezone.utc)
lines = []
for index in range(20):
    price = Decimal('100') + Decimal(index) / Decimal('10')
    hedge = price + Decimal('0.05')
    timestamp = (start + timedelta(minutes=index)).isoformat().replace('+00:00', 'Z')
    payload = {
        'schema_version': 1,
        'venue': 'paper',
        'symbol': 'BTC',
        'instrument': 'perp',
        'price': str(price),
        'timestamp': timestamp,
        'bid': str(price - Decimal('0.05')),
        'ask': str(price + Decimal('0.05')),
        'high': str(price + Decimal('0.1')),
        'low': str(price - Decimal('0.1')),
        'volume_24h': '1000000',
        'funding_rate_hourly': '0.0005',
        'sentiment_score': 0.0,
        'reference_price': None,
        'reference_market_open': None,
        'metadata': {
            'paper_hedge_symbol': 'BTC-SPOT',
            'paper_hedge_price': str(hedge),
        },
    }
    lines.append(json.dumps(payload, sort_keys=True, separators=(',', ':')))
(root / 'events.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY

cat > "$CONFIG" <<'YAML'
schema_version: 1
analytics:
  efficiency_period: 2
  kama_fast_period: 2
  kama_slow_period: 10
  zscore_window: 3
  kalman_process_variance: 0.00001
  kalman_measurement_variance: 0.01
strategy:
  scenario_notional_usd: "100"
  estimated_round_trip_cost_bps: "12"
  funding_entry_apy_pct: "50"
  funding_holding_hours: "24"
  crowd_entry_zscore: 99.0
  crowd_efficiency_ratio_maximum: 0.2
  crowd_requires_sentiment: false
  lead_lag_entry_premium_bps: "150"
approval:
  maximum_event_age_seconds: 5.0
  minimum_edge_bps: "1"
  maximum_leg_notional_usd: "1000"
  maximum_gross_exposure_usd: "10000"
  maximum_leg_imbalance_pct: "0.02"
  maximum_slippage_bps: "50"
execution:
  slippage_bps: "5"
  fee_bps: "1"
  fail_leg_indexes: []
runtime:
  queue_size: 16
YAML

cat > "$SWEEP" <<'YAML'
schema_version: 1
maximum_candidates: 2
parameters:
  strategy.funding_entry_apy_pct: ["50"]
walk_forward:
  train_size: 5
  purge_size: 0
  test_size: 5
  step_size: 5
  anchored: false
  minimum_windows: 3
YAML

llm-arbitrage validate-dataset "$DATASET"
llm-arbitrage validate-config "$CONFIG"
llm-arbitrage keygen \
  --private-key "$KEY_ROOT/provenance.pem" \
  --public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage registry-init "$REGISTRY"
llm-arbitrage registry-trust-key \
  "$REGISTRY" \
  "$KEY_ROOT/provenance.pub.pem" \
  --label phase6-smoke
llm-arbitrage plan-matrix \
  --dataset "$DATASET" \
  --config "$CONFIG" \
  --sweep "$SWEEP" \
  --output "$MATRIX"

mapfile -t EVALUATION_IDS < <(
  python - <<'PY'
import json
from pathlib import Path

matrix = json.loads(Path('.phase6-runs/matrix.json').read_text(encoding='utf-8'))
assert matrix['candidate_count'] == 1
assert matrix['window_count'] == 3
assert matrix['evaluation_count'] == 3
for item in matrix['evaluations']:
    print(item['evaluation_id'])
PY
)
test "${#EVALUATION_IDS[@]}" -eq 3

MARK_SPOT=("102" "101" "100")
MARK_PERP=("100" "100.5" "102")
BUNDLES=()
MARK_FILES=()

for index in "${!EVALUATION_IDS[@]}"; do
  evaluation_id="${EVALUATION_IDS[$index]}"
  evaluation_root="$RUN_ROOT/evaluations/$evaluation_id"
  llm-arbitrage run-evaluation \
    --dataset "$DATASET" \
    --config "$CONFIG" \
    --matrix "$MATRIX" \
    --evaluation-id "$evaluation_id" \
    --output "$evaluation_root" \
    --code-revision "$REVISION"
  bundle="$(
    find "$evaluation_root" \
      -mindepth 1 \
      -maxdepth 1 \
      -type d \
      -name 'exp-*' \
      -print \
      -quit
  )"
  test -n "$bundle"
  attestation="$RUN_ROOT/attestations/$evaluation_id.attestation.json"
  llm-arbitrage sign-bundle \
    --bundle "$bundle" \
    --private-key "$KEY_ROOT/provenance.pem" \
    --output "$attestation"
  llm-arbitrage registry-register-evaluation \
    "$REGISTRY" \
    --matrix "$MATRIX" \
    --evaluation-id "$evaluation_id" \
    --bundle "$bundle" \
    --attestation "$attestation"

  marks="$RUN_ROOT/marks/$evaluation_id.json"
  python - "$bundle" "$marks" "${MARK_SPOT[$index]}" "${MARK_PERP[$index]}" <<'PY'
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

bundle = Path(sys.argv[1])
marks_path = Path(sys.argv[2])
spot = sys.argv[3]
perp = sys.argv[4]
manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
last_event = str(manifest['dataset']['last_event_at'])
normalized = last_event[:-1] + '+00:00' if last_event.endswith('Z') else last_event
as_of = datetime.fromisoformat(normalized) + timedelta(seconds=60)
payload = {
    'schema_version': 1,
    'as_of': as_of.isoformat().replace('+00:00', 'Z'),
    'marks': [
        {'symbol': 'BTC-SPOT', 'price': spot},
        {'symbol': 'BTC:PERP', 'price': perp},
    ],
}
marks_path.write_text(
    json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
    encoding='utf-8',
)
PY
  llm-arbitrage validate-marks "$marks"
  BUNDLES+=("$bundle")
  MARK_FILES+=("$marks")
done

python - "$MATRIX" "$INPUTS" \
  "${EVALUATION_IDS[0]}" "${BUNDLES[0]}" "${MARK_FILES[0]}" \
  "${EVALUATION_IDS[1]}" "${BUNDLES[1]}" "${MARK_FILES[1]}" \
  "${EVALUATION_IDS[2]}" "${BUNDLES[2]}" "${MARK_FILES[2]}" <<'PY'
import json
import sys
from pathlib import Path

matrix_path = Path(sys.argv[1])
output = Path(sys.argv[2])
values = sys.argv[3:]
matrix = json.loads(matrix_path.read_text(encoding='utf-8'))
candidate_ids = sorted({item['candidate_id'] for item in matrix['evaluations']})
valuations = []
for offset in range(0, len(values), 3):
    valuations.append(
        {
            'evaluation_id': values[offset],
            'bundle': str(Path(values[offset + 1]).resolve()),
            'marks': str(Path(values[offset + 2]).resolve()),
        }
    )
payload = {
    'schema_version': 1,
    'candidate_ids': candidate_ids,
    'valuations': valuations,
}
output.write_text(
    json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
    encoding='utf-8',
)
PY

llm-arbitrage validate-statistics-inputs "$INPUTS"
llm-arbitrage value-bundle \
  --bundle "${BUNDLES[0]}" \
  --marks "${MARK_FILES[0]}" \
  --output "$RUN_ROOT/first-valuation.json" \
  --code-revision "$REVISION"
llm-arbitrage campaign-statistics \
  --registry "$REGISTRY" \
  --matrix "$MATRIX" \
  --inputs "$INPUTS" \
  --initial-equity "100000" \
  --periods-per-year 252 \
  --output "$REPORT" \
  --code-revision "$REVISION"
llm-arbitrage sign-statistics \
  --report "$REPORT" \
  --private-key "$KEY_ROOT/provenance.pem" \
  --output "$REPORT_ATTESTATION"
llm-arbitrage verify-statistics \
  --report "$REPORT" \
  --attestation "$REPORT_ATTESTATION" \
  --trusted-public-key "$KEY_ROOT/provenance.pub.pem"
llm-arbitrage registry-verify "$REGISTRY"

python - "$REPORT" <<'PY'
import json
import sys
from decimal import Decimal
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
assert report['selection'] is None
assert len(report['candidates']) == 1
candidate = report['candidates'][0]
assert candidate['coverage'] == 'complete'
assert candidate['expected_evaluation_count'] == 3
assert candidate['observed_evaluation_count'] == 3
assert candidate['mark_lag_microseconds'] == 60_000_000
assert candidate['maximum_drawdown_pct'] > 0
assert candidate['annualized_sharpe_ratio'] is not None
assert Decimal(candidate['oos_pnl_slope_bps_per_window']) < 0
assert Decimal(candidate['alpha_decay_bps_per_window']) > 0
assert report.get('winner') is None
PY
