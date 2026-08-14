#!/usr/bin/env bash
set -euo pipefail

ROOT=".phase7-runs"
rm -rf "$ROOT"
mkdir -p "$ROOT/keys" "$ROOT/second-keys"
cleanup() {
  rm -rf "$ROOT"
}
trap cleanup EXIT

MATRIX_SHA="b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"

cat >"$ROOT/selection-policy.yaml" <<EOF
schema_version: 1
matrix_sha256: ${MATRIX_SHA}
decision_mode: human_review_only
objective:
  metric: total_mark_to_market_pnl_usd
  direction: maximize
  tie_breakers:
    - maximum_drawdown_pct
admission:
  minimum_candidates: 2
  minimum_windows_per_candidate: 3
  require_complete_coverage: true
  require_equal_window_indexes: true
  require_equal_test_intervals: true
  require_equal_mark_lag: true
  maximum_drawdown_pct: "25"
  minimum_positive_window_fraction: "0.5"
  maximum_alpha_decay_bps_per_window: "100"
multiple_testing:
  method: holm_sign_test
  family_alpha: "0.05"
  minimum_non_tied_pairwise_windows: 3
  require_adjusted_pairwise_evidence: false
EOF

python - <<'PY'
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import write_json

root = Path(".phase7-runs")
matrix_sha = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"


def observation(
    candidate_id: str,
    config_sha: str,
    index: int,
    pnl: int,
    ending_equity: int,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"evaluation-{candidate_id}-{index}",
        "experiment_id": f"experiment-{candidate_id}-{index}",
        "valuation_id": f"valuation-{candidate_id}-{index}",
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "window_index": index,
        "test_start": index * 10,
        "test_end": index * 10 + 5,
        "test_semantic_sha256": f"{index + 1:064x}",
        "mark_lag_microseconds": 60_000_000,
        "mark_to_market_pnl_usd": str(pnl),
        "ending_equity_usd": str(ending_equity),
        "period_return": pnl / 100000.0,
    }


def candidate(
    candidate_id: str,
    config_character: str,
    pnl_values: tuple[int, ...],
) -> dict[str, Any]:
    config_sha = config_character * 64
    equity = 100000
    observations: list[dict[str, Any]] = []
    for index, pnl in enumerate(pnl_values):
        equity += pnl
        observations.append(
            observation(candidate_id, config_sha, index, pnl, equity)
        )
    total = sum(pnl_values)
    return {
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "coverage": "complete",
        "expected_evaluation_count": len(pnl_values),
        "observed_evaluation_count": len(pnl_values),
        "initial_equity_usd": "100000",
        "ending_equity_usd": str(100000 + total),
        "total_mark_to_market_pnl_usd": str(total),
        "maximum_drawdown_pct": 5.0,
        "annualized_sharpe_ratio": 1.25,
        "alpha_decay_method": "ols_terminal_pnl_bps_per_window",
        "oos_pnl_slope_bps_per_window": "-1",
        "alpha_decay_bps_per_window": "10",
        "mark_lag_microseconds": 60_000_000,
        "observations": observations,
    }


write_json(
    root / "statistics.json",
    {
        "schema_version": 1,
        "report_id": "oos-report-" + "c" * 40,
        "matrix_sha256": matrix_sha,
        "code_revision": "phase7-smoke-statistics",
        "package_version": "0.1.0",
        "periods_per_year": 252,
        "candidates": [
            candidate("candidate-b", "b", (1, 2, 3)),
            candidate("candidate-a", "a", (10, 8, 6)),
        ],
        "selection": None,
        "assumptions": ["Synthetic deterministic Phase 7 smoke evidence."],
        "evidence_boundary": "Synthetic offline paper fixture only.",
    },
)
PY

llm-arbitrage validate-selection-policy "$ROOT/selection-policy.yaml" >/dev/null
llm-arbitrage selection-diagnostics \
  --policy "$ROOT/selection-policy.yaml" \
  --statistics "$ROOT/statistics.json" \
  --output "$ROOT/diagnostics.json" \
  --code-revision phase7-smoke-diagnostics >/dev/null
llm-arbitrage build-selection-dossier \
  --policy "$ROOT/selection-policy.yaml" \
  --statistics "$ROOT/statistics.json" \
  --diagnostics "$ROOT/diagnostics.json" \
  --output "$ROOT/dossier.json" \
  --code-revision phase7-smoke-dossier >/dev/null
llm-arbitrage keygen \
  --private-key "$ROOT/keys/private.pem" \
  --public-key "$ROOT/keys/public.pem" >/dev/null
llm-arbitrage sign-selection-dossier \
  --dossier "$ROOT/dossier.json" \
  --private-key "$ROOT/keys/private.pem" \
  --output "$ROOT/dossier.attestation.json" >/dev/null
llm-arbitrage verify-selection-dossier \
  --dossier "$ROOT/dossier.json" \
  --attestation "$ROOT/dossier.attestation.json" \
  --trusted-public-key "$ROOT/keys/public.pem" >/dev/null

python - <<'PY'
import json
from pathlib import Path

root = Path(".phase7-runs")
diagnostics = json.loads((root / "diagnostics.json").read_text(encoding="utf-8"))
dossier = json.loads((root / "dossier.json").read_text(encoding="utf-8"))

assert diagnostics["family_state"] == "eligible_for_human_review"
assert diagnostics["selection"] is None
assert diagnostics["ranking"] is None
assert diagnostics["promotion"] is None
assert [item["candidate_id"] for item in diagnostics["candidates"]] == [
    "candidate-a",
    "candidate-b",
]
assert dossier["human_decision"] is None
assert dossier["selected_candidate_id"] is None
assert dossier["promotion"] is None
assert dossier["eligible_candidate_ids"] == ["candidate-a", "candidate-b"]
assert dossier["blocked_candidate_ids"] == []
PY

if llm-arbitrage build-selection-dossier \
  --policy "$ROOT/selection-policy.yaml" \
  --statistics "$ROOT/statistics.json" \
  --diagnostics "$ROOT/diagnostics.json" \
  --output "$ROOT/dossier.json" \
  --code-revision phase7-smoke-dossier >/dev/null 2>&1; then
  echo "expected dossier overwrite protection to fail" >&2
  exit 1
fi

llm-arbitrage keygen \
  --private-key "$ROOT/second-keys/private.pem" \
  --public-key "$ROOT/second-keys/public.pem" >/dev/null
if llm-arbitrage verify-selection-dossier \
  --dossier "$ROOT/dossier.json" \
  --attestation "$ROOT/dossier.attestation.json" \
  --trusted-public-key "$ROOT/second-keys/public.pem" >/dev/null 2>&1; then
  echo "expected wrong trusted key verification to fail" >&2
  exit 1
fi

python - <<'PY'
import json
from pathlib import Path

from llm_arbitrage_system.experiments.bundle_io import write_json

root = Path(".phase7-runs")
payload = json.loads((root / "dossier.json").read_text(encoding="utf-8"))
payload["family_state"] = "blocked"
write_json(root / "tampered-dossier.json", payload)
PY

if llm-arbitrage verify-selection-dossier \
  --dossier "$ROOT/tampered-dossier.json" \
  --attestation "$ROOT/dossier.attestation.json" \
  --trusted-public-key "$ROOT/keys/public.pem" >/dev/null 2>&1; then
  echo "expected tampered dossier verification to fail" >&2
  exit 1
fi

echo "Phase 7 selection-governance smoke passed"
