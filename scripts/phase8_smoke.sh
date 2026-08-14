#!/usr/bin/env bash
set -euo pipefail

ROOT=".phase8-runs"
rm -rf "$ROOT"
mkdir -p "$ROOT"
cleanup() {
  rm -rf "$ROOT"
}
trap cleanup EXIT

python - <<'PY'
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.decision_request import (
    required_risk_acknowledgements,
)
from llm_arbitrage_system.experiments.review_evidence import (
    required_review_acknowledgements,
)
from llm_arbitrage_system.experiments.selection_diagnostics import (
    build_selection_diagnostics,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    build_selection_dossier,
    load_selection_dossier,
)

root = Path(".phase8-runs")
matrix_sha = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"
policy = root / "selection-policy.yaml"
policy.write_text(
    f"""schema_version: 1
matrix_sha256: {matrix_sha}
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
""",
    encoding="utf-8",
)


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
    values: tuple[int, ...],
) -> dict[str, Any]:
    config_sha = config_character * 64
    equity = 100000
    observations: list[dict[str, Any]] = []
    for index, pnl in enumerate(values):
        equity += pnl
        observations.append(
            observation(candidate_id, config_sha, index, pnl, equity)
        )
    total = sum(values)
    return {
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "coverage": "complete",
        "expected_evaluation_count": len(values),
        "observed_evaluation_count": len(values),
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


statistics = root / "statistics.json"
write_json(
    statistics,
    {
        "schema_version": 1,
        "report_id": "oos-report-" + "c" * 40,
        "matrix_sha256": matrix_sha,
        "code_revision": "phase8-smoke-statistics",
        "package_version": "0.1.0",
        "periods_per_year": 252,
        "candidates": [
            candidate("candidate-b", "b", (1, 2, 3)),
            candidate("candidate-a", "a", (10, 8, 6)),
        ],
        "selection": None,
        "assumptions": ["Synthetic deterministic Phase 8 smoke evidence."],
        "evidence_boundary": "Synthetic offline paper fixture only.",
    },
)
diagnostics = build_selection_diagnostics(
    policy_path=policy,
    statistics_report_path=statistics,
    code_revision="phase8-smoke-diagnostics",
    package_version="0.1.0",
)
diagnostics_path = root / "diagnostics.json"
write_json(diagnostics_path, diagnostics.as_dict())
dossier = build_selection_dossier(
    policy_path=policy,
    statistics_report_path=statistics,
    diagnostics_path=diagnostics_path,
    code_revision="phase8-smoke-dossier",
    package_version="0.1.0",
)
dossier_path = root / "dossier.json"
write_json(dossier_path, dossier.as_dict())
dossier_snapshot = load_selection_dossier(dossier_path)

request_acknowledgements = "\n".join(
    f"  - {value}" for value in required_risk_acknowledgements()
)
(root / "request.yaml").write_text(
    f"""schema_version: 1
dossier:
  dossier_id: {dossier_snapshot.dossier.dossier_id}
  sha256: {dossier_snapshot.source_sha256}
requested_candidate_id: candidate-a
requested_scope: research_review_only
requester:
  subject: phase8-smoke-proposer
  role: research_proposer
rationale: Request two independent research-only reviews of captured offline evidence.
requested_at: "2026-08-14T00:00:00Z"
expires_at: "2026-08-21T00:00:00Z"
risk_acknowledgements:
{request_acknowledgements}
decision: null
deployment_authorized: false
trading_authorized: false
""",
    encoding="utf-8",
)
review_acknowledgements = "\n".join(
    f"  - {value}" for value in required_review_acknowledgements()
)
(root / "review-acknowledgements.txt").write_text(
    review_acknowledgements,
    encoding="utf-8",
)
PY

for name in dossier requester reviewer-a reviewer-b quorum wrong; do
  llm-arbitrage keygen \
    --private-key "$ROOT/$name/private.pem" \
    --public-key "$ROOT/$name/public.pem" >/dev/null
done

llm-arbitrage sign-selection-dossier \
  --dossier "$ROOT/dossier.json" \
  --private-key "$ROOT/dossier/private.pem" \
  --output "$ROOT/dossier.attestation.json" >/dev/null
llm-arbitrage validate-decision-request "$ROOT/request.yaml" >/dev/null
llm-arbitrage sign-decision-request \
  --request "$ROOT/request.yaml" \
  --private-key "$ROOT/requester/private.pem" \
  --output "$ROOT/request.attestation.json" >/dev/null
llm-arbitrage verify-decision-request \
  --request "$ROOT/request.yaml" \
  --attestation "$ROOT/request.attestation.json" \
  --trusted-public-key "$ROOT/requester/public.pem" >/dev/null

python - <<'PY'
from pathlib import Path

from llm_arbitrage_system.experiments.decision_request import load_decision_request
from llm_arbitrage_system.experiments.selection_dossier import load_selection_dossier

root = Path(".phase8-runs")
request = load_decision_request(root / "request.yaml")
dossier = load_selection_dossier(root / "dossier.json")
acknowledgements = (root / "review-acknowledgements.txt").read_text(
    encoding="utf-8"
)
for index, subject in enumerate(("reviewer-alpha", "reviewer-beta")):
    (root / f"review-{index}.yaml").write_text(
        f"""schema_version: 1
request:
  request_id: {request.request_id}
  canonical_sha256: {request.canonical_sha256}
dossier:
  dossier_id: {dossier.dossier.dossier_id}
  sha256: {dossier.source_sha256}
requested_candidate_id: candidate-a
decision: approve_research_only
reviewer:
  subject: {subject}
  role: independent_reviewer
rationale: Approve additional offline research only; no release, deployment, or trading.
reviewed_at: "2026-08-{15 + index:02d}T00:00:00Z"
risk_acknowledgements:
{acknowledgements}
deployment_authorized: false
trading_authorized: false
""",
        encoding="utf-8",
    )
PY

for index in 0 1; do
  key="reviewer-a"
  if [ "$index" = "1" ]; then key="reviewer-b"; fi
  llm-arbitrage validate-review-record "$ROOT/review-$index.yaml" >/dev/null
  llm-arbitrage sign-review-record \
    --record "$ROOT/review-$index.yaml" \
    --request "$ROOT/request.yaml" \
    --request-attestation "$ROOT/request.attestation.json" \
    --trusted-requester-public-key "$ROOT/requester/public.pem" \
    --dossier "$ROOT/dossier.json" \
    --dossier-attestation "$ROOT/dossier.attestation.json" \
    --trusted-dossier-public-key "$ROOT/dossier/public.pem" \
    --reviewer-private-key "$ROOT/$key/private.pem" \
    --output "$ROOT/review-$index.attestation.json" >/dev/null
  llm-arbitrage verify-review-record \
    --record "$ROOT/review-$index.yaml" \
    --attestation "$ROOT/review-$index.attestation.json" \
    --trusted-reviewer-public-key "$ROOT/$key/public.pem" \
    --request "$ROOT/request.yaml" \
    --request-attestation "$ROOT/request.attestation.json" \
    --trusted-requester-public-key "$ROOT/requester/public.pem" \
    --dossier "$ROOT/dossier.json" \
    --dossier-attestation "$ROOT/dossier.attestation.json" \
    --trusted-dossier-public-key "$ROOT/dossier/public.pem" >/dev/null
done

cat >"$ROOT/quorum.yaml" <<EOF
schema_version: 1
scope: research_review_only
minimum_distinct_reviewers: 2
request:
  path: request.yaml
  attestation: request.attestation.json
  trusted_public_key: requester/public.pem
dossier:
  path: dossier.json
  attestation: dossier.attestation.json
  trusted_public_key: dossier/public.pem
reviews:
  - record: review-0.yaml
    attestation: review-0.attestation.json
    trusted_public_key: reviewer-a/public.pem
  - record: review-1.yaml
    attestation: review-1.attestation.json
    trusted_public_key: reviewer-b/public.pem
deployment_authorized: false
trading_authorized: false
release_authorized: false
EOF

llm-arbitrage validate-review-quorum-inputs "$ROOT/quorum.yaml" >/dev/null
llm-arbitrage build-review-quorum \
  --inputs "$ROOT/quorum.yaml" \
  --output "$ROOT/quorum.json" >/dev/null
llm-arbitrage validate-review-quorum "$ROOT/quorum.json" >/dev/null
llm-arbitrage sign-review-quorum \
  --envelope "$ROOT/quorum.json" \
  --private-key "$ROOT/quorum/private.pem" \
  --output "$ROOT/quorum.attestation.json" >/dev/null
llm-arbitrage verify-review-quorum \
  --envelope "$ROOT/quorum.json" \
  --attestation "$ROOT/quorum.attestation.json" \
  --trusted-public-key "$ROOT/quorum/public.pem" >/dev/null

python - <<'PY'
import json
from pathlib import Path

root = Path(".phase8-runs")
payload = json.loads((root / "quorum.json").read_text(encoding="utf-8"))
assert payload["status"] == "approved_for_research_only"
assert payload["review_count"] == 2
assert payload["distinct_reviewer_count"] == 2
assert payload["deployment_authorized"] is False
assert payload["trading_authorized"] is False
assert payload["release_authorized"] is False
assert "selected_candidate_id" not in payload
assert "promotion" not in payload
PY

if llm-arbitrage build-review-quorum \
  --inputs "$ROOT/quorum.yaml" \
  --output "$ROOT/quorum.json" >/dev/null 2>&1; then
  echo "expected quorum overwrite protection to fail" >&2
  exit 1
fi

if llm-arbitrage verify-review-quorum \
  --envelope "$ROOT/quorum.json" \
  --attestation "$ROOT/quorum.attestation.json" \
  --trusted-public-key "$ROOT/wrong/public.pem" >/dev/null 2>&1; then
  echo "expected wrong trusted quorum key to fail" >&2
  exit 1
fi

if llm-arbitrage sign-review-quorum \
  --envelope "$ROOT/quorum.json" \
  --private-key "$ROOT/requester/private.pem" \
  --output "$ROOT/participant.attestation.json" >/dev/null 2>&1; then
  echo "expected participant quorum signer to fail" >&2
  exit 1
fi

python - <<'PY'
import json
from pathlib import Path

from llm_arbitrage_system.experiments.bundle_io import write_json

root = Path(".phase8-runs")
payload = json.loads((root / "quorum.json").read_text(encoding="utf-8"))
payload["deployment_authorized"] = True
write_json(root / "tampered-quorum.json", payload)
PY

if llm-arbitrage verify-review-quorum \
  --envelope "$ROOT/tampered-quorum.json" \
  --attestation "$ROOT/quorum.attestation.json" \
  --trusted-public-key "$ROOT/quorum/public.pem" >/dev/null 2>&1; then
  echo "expected tampered quorum verification to fail" >&2
  exit 1
fi

echo "Phase 8 separation-of-duties quorum smoke passed"
