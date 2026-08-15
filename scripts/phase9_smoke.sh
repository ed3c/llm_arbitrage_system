#!/usr/bin/env bash
set -euo pipefail

ROOT=".phase9-runs"
rm -rf "$ROOT"
mkdir -p "$ROOT"
cleanup() {
  rm -rf "$ROOT"
}
trap cleanup EXIT

python - <<'PY'
from __future__ import annotations

from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.review_quorum import (
    QuorumReviewEvidence,
    ReviewQuorumEnvelope,
)
from llm_arbitrage_system.experiments.review_quorum_signing import (
    sign_review_quorum_envelope,
)
from llm_arbitrage_system.experiments.selection_dossier import SelectionDossier
from llm_arbitrage_system.experiments.selection_signing import sign_selection_dossier
from llm_arbitrage_system.experiments.signing import generate_signing_keypair
from llm_arbitrage_system.experiments.statistics_signing import (
    load_statistics_report,
    sign_statistics_report,
)

root = Path(".phase9-runs")
candidate_id = "candidate-a0c8f92d194d01b5ecaf5dbf"
candidate_config_sha = (
    "a0c8f92d194d01b5ecaf5dbfa089b2ce230fd3366918a3918943ce005e0c4adc"
)
code_revision = "phase9-smoke-comparable-revision"
package_version = "0.1.0"
periods_per_year = 252
mark_lag_microseconds = 60_000_000


def digest(value: int) -> str:
    return f"{value:064x}"


def keypair(name: str) -> tuple[Path, Path, str]:
    private_key = root / "keys" / name / "private.pem"
    public_key = root / "keys" / name / "public.pem"
    identity = generate_signing_keypair(private_key, public_key)
    return private_key, public_key, identity.key_id


keys = {
    "statistics-a": keypair("statistics-a"),
    "statistics-b": keypair("statistics-b"),
    "dossier-a": keypair("dossier-a"),
    "dossier-b": keypair("dossier-b"),
    "quorum-a": keypair("quorum-a"),
    "quorum-b": keypair("quorum-b"),
    "replication": keypair("replication"),
    "wrong": keypair("wrong"),
}
for cohort_index in range(1, 4):
    keys[f"requester-{cohort_index}"] = keypair(f"requester-{cohort_index}")
    keys[f"reviewer-{cohort_index}-a"] = keypair(
        f"reviewer-{cohort_index}-a"
    )
    keys[f"reviewer-{cohort_index}-b"] = keypair(
        f"reviewer-{cohort_index}-b"
    )


def observation(
    cohort_index: int,
    window_index: int,
    pnl: int,
    ending_equity: int,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"evaluation-{cohort_index:02x}{window_index:030x}",
        "experiment_id": f"exp-{cohort_index:02x}{window_index:038x}",
        "valuation_id": f"valuation-{cohort_index:02x}{window_index:038x}",
        "candidate_id": candidate_id,
        "candidate_config_sha256": candidate_config_sha,
        "window_index": window_index,
        "test_start": window_index * 5,
        "test_end": (window_index + 1) * 5,
        "test_semantic_sha256": digest(cohort_index * 100 + window_index),
        "mark_lag_microseconds": mark_lag_microseconds,
        "mark_to_market_pnl_usd": str(pnl),
        "ending_equity_usd": str(ending_equity),
        "period_return": pnl / 100000.0,
    }


def candidate_payload(cohort_index: int, window_pnl: int) -> dict[str, Any]:
    equity = 100000
    observations: list[dict[str, Any]] = []
    for window_index in range(3):
        equity += window_pnl
        observations.append(
            observation(cohort_index, window_index, window_pnl, equity)
        )
    total = window_pnl * 3
    return {
        "candidate_id": candidate_id,
        "candidate_config_sha256": candidate_config_sha,
        "coverage": "complete",
        "expected_evaluation_count": 3,
        "observed_evaluation_count": 3,
        "initial_equity_usd": "100000",
        "ending_equity_usd": str(100000 + total),
        "total_mark_to_market_pnl_usd": str(total),
        "maximum_drawdown_pct": 0.0,
        "annualized_sharpe_ratio": 1.0,
        "alpha_decay_method": "ols_terminal_pnl_bps_per_window",
        "oos_pnl_slope_bps_per_window": "0",
        "alpha_decay_bps_per_window": "0",
        "mark_lag_microseconds": mark_lag_microseconds,
        "observations": observations,
    }


input_cohorts: list[dict[str, Any]] = []
for cohort_index, window_pnl in enumerate((4, 6, 8), start=1):
    cohort_root = root / f"cohort-{cohort_index}"
    cohort_root.mkdir(parents=True, exist_ok=True)
    matrix_sha = digest(1000 + cohort_index)
    statistics_path = cohort_root / "statistics.json"
    write_json(
        statistics_path,
        {
            "schema_version": 1,
            "report_id": f"oos-report-{cohort_index:040x}",
            "matrix_sha256": matrix_sha,
            "code_revision": code_revision,
            "package_version": package_version,
            "periods_per_year": periods_per_year,
            "candidates": [candidate_payload(cohort_index, window_pnl)],
            "selection": None,
            "assumptions": [
                "Synthetic deterministic Phase 9 smoke statistics evidence."
            ],
            "evidence_boundary": "Synthetic offline paper fixture only.",
        },
    )
    statistics_snapshot = load_statistics_report(statistics_path)
    statistics_key_name = "statistics-a" if cohort_index != 2 else "statistics-b"
    statistics_attestation = cohort_root / "statistics.attestation.json"
    sign_statistics_report(
        statistics_path,
        keys[statistics_key_name][0],
        statistics_attestation,
    )

    dossier_key_name = "dossier-a" if cohort_index != 2 else "dossier-b"
    dossier_identity = {
        "schema_version": 1,
        "matrix_sha256": matrix_sha,
        "policy": {
            "policy_id": f"selection-policy-{100 + cohort_index:040x}",
            "sha256": digest(2000 + cohort_index),
        },
        "statistics": {
            "report_id": statistics_snapshot.report_id,
            "sha256": statistics_snapshot.source_sha256,
        },
        "diagnostics": {
            "diagnostics_id": (
                f"selection-diagnostics-{200 + cohort_index:040x}"
            ),
            "sha256": digest(3000 + cohort_index),
        },
        "family_state": "eligible_for_human_review",
        "global_blockers": [],
        "eligible_candidate_ids": [candidate_id],
        "blocked_candidate_ids": [],
        "code_revision": code_revision,
        "package_version": package_version,
    }
    dossier = SelectionDossier(
        dossier_id="selection-dossier-"
        + sha256_hex(canonical_json_bytes(dossier_identity))[:40],
        matrix_sha256=matrix_sha,
        policy=dossier_identity["policy"],
        statistics=dossier_identity["statistics"],
        diagnostics=dossier_identity["diagnostics"],
        family_state="eligible_for_human_review",
        global_blockers=(),
        eligible_candidate_ids=(candidate_id,),
        blocked_candidate_ids=(),
        code_revision=code_revision,
        package_version=package_version,
    )
    dossier_path = cohort_root / "dossier.json"
    write_json(dossier_path, dossier.as_dict())
    dossier_attestation = cohort_root / "dossier.attestation.json"
    sign_selection_dossier(
        dossier_path,
        keys[dossier_key_name][0],
        dossier_attestation,
    )

    requester_key = keys[f"requester-{cohort_index}"][2]
    review_key_names = (
        f"reviewer-{cohort_index}-a",
        f"reviewer-{cohort_index}-b",
    )
    reviews = tuple(
        sorted(
            (
                QuorumReviewEvidence(
                    record_id=f"review-record-{cohort_index * 10 + index:040x}",
                    record_sha256=digest(4000 + cohort_index * 10 + index),
                    reviewer_subject=f"phase9-smoke-reviewer-{cohort_index}-{index}",
                    reviewer_key_id=keys[key_name][2],
                    decision="approve_research_only",
                    reviewed_at=(
                        f"2026-08-{15 + cohort_index:02d}T0{index}:00:00.000000Z"
                    ),
                )
                for index, key_name in enumerate(review_key_names)
            ),
            key=lambda review: (review.reviewer_key_id, review.record_id),
        )
    )
    quorum_identity = {
        "schema_version": 1,
        "scope": "research_review_only",
        "request": {
            "request_id": f"decision-request-{300 + cohort_index:040x}",
            "canonical_sha256": digest(5000 + cohort_index),
            "requester_key_id": requester_key,
        },
        "dossier": {
            "dossier_id": dossier.dossier_id,
            "sha256": sha256_hex(dossier_path.read_bytes()),
            "dossier_key_id": keys[dossier_key_name][2],
        },
        "requested_candidate_id": candidate_id,
        "minimum_distinct_reviewers": 2,
        "status": "approved_for_research_only",
        "reviews": [review.as_dict() for review in reviews],
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }
    quorum = ReviewQuorumEnvelope(
        envelope_id="review-quorum-"
        + sha256_hex(canonical_json_bytes(quorum_identity))[:40],
        request_id=quorum_identity["request"]["request_id"],
        request_sha256=quorum_identity["request"]["canonical_sha256"],
        requester_key_id=requester_key,
        dossier_id=dossier.dossier_id,
        dossier_sha256=quorum_identity["dossier"]["sha256"],
        dossier_key_id=keys[dossier_key_name][2],
        requested_candidate_id=candidate_id,
        minimum_distinct_reviewers=2,
        status="approved_for_research_only",
        reviews=reviews,
    )
    quorum_path = cohort_root / "quorum.json"
    write_json(quorum_path, quorum.as_dict())
    quorum_key_name = "quorum-a" if cohort_index != 2 else "quorum-b"
    quorum_attestation = cohort_root / "quorum.attestation.json"
    sign_review_quorum_envelope(
        quorum_path,
        keys[quorum_key_name][0],
        quorum_attestation,
    )

    input_cohorts.append(
        {
            "cohort_id": f"cohort-{cohort_index:024x}",
            "statistics": {
                "evidence": f"cohort-{cohort_index}/statistics.json",
                "attestation": (
                    f"cohort-{cohort_index}/statistics.attestation.json"
                ),
                "trusted_public_key": (
                    f"keys/{statistics_key_name}/public.pem"
                ),
            },
            "dossier": {
                "evidence": f"cohort-{cohort_index}/dossier.json",
                "attestation": f"cohort-{cohort_index}/dossier.attestation.json",
                "trusted_public_key": f"keys/{dossier_key_name}/public.pem",
            },
            "quorum": {
                "evidence": f"cohort-{cohort_index}/quorum.json",
                "attestation": f"cohort-{cohort_index}/quorum.attestation.json",
                "trusted_public_key": f"keys/{quorum_key_name}/public.pem",
            },
        }
    )

(root / "replication-plan.yaml").write_text(
    f"""schema_version: 1
scope: independent_offline_replication
candidate:
  candidate_id: {candidate_id}
  candidate_config_sha256: {candidate_config_sha}
independence:
  minimum_replications: 3
  minimum_distinct_quorum_signers: 2
  minimum_distinct_dossier_signers: 2
  minimum_distinct_statistics_signers: 2
  require_disjoint_test_semantic_sha256: true
  require_distinct_matrix_sha256: true
  require_distinct_dossier_sha256: true
  require_distinct_quorum_envelope_sha256: true
  prohibit_statistics_report_reuse: true
comparability:
  require_equal_code_revision: true
  require_equal_package_version: true
  require_equal_periods_per_year: true
  require_equal_terminal_mark_lag: true
acceptance:
  minimum_research_approved_fraction: "0.67"
  minimum_positive_replication_fraction: "0.67"
  minimum_windows_per_replication: 3
  maximum_failed_replications: 1
  maximum_insufficient_replications: 0
  minimum_worst_case_total_pnl_usd: "0"
  minimum_median_total_pnl_usd: "0"
authority:
  human_admit_required: true
  automatic_promotion: false
  release_authorized: false
  deployment_authorized: false
  trading_authorized: false
""",
    encoding="utf-8",
)
write_json(
    root / "replication-inputs.json",
    {"schema_version": 1, "cohorts": input_cohorts},
)
PY

llm-arbitrage validate-replication-plan \
  "$ROOT/replication-plan.yaml" >/dev/null
llm-arbitrage validate-replication-inputs \
  "$ROOT/replication-inputs.json" >/dev/null
llm-arbitrage replication-report \
  --plan "$ROOT/replication-plan.yaml" \
  --inputs "$ROOT/replication-inputs.json" \
  --output "$ROOT/replication-report.json" >/dev/null
llm-arbitrage validate-replication-report \
  "$ROOT/replication-report.json" >/dev/null
llm-arbitrage sign-replication-report \
  --report "$ROOT/replication-report.json" \
  --private-key "$ROOT/keys/replication/private.pem" \
  --output "$ROOT/replication-report.attestation.json" >/dev/null
llm-arbitrage verify-replication-report \
  --report "$ROOT/replication-report.json" \
  --attestation "$ROOT/replication-report.attestation.json" \
  --trusted-public-key "$ROOT/keys/replication/public.pem" >/dev/null

python - <<'PY'
import json
from pathlib import Path

root = Path(".phase9-runs")
payload = json.loads((root / "replication-report.json").read_text(encoding="utf-8"))
assert payload["status"] == "replication_consistent"
assert payload["cohort_count"] == 3
assert payload["research_approved_count"] == 3
assert payload["positive_replication_count"] == 3
assert payload["failed_replication_count"] == 0
assert payload["insufficient_replication_count"] == 0
assert all(payload["independence_checks"].values())
assert all(payload["comparability_checks"].values())
assert all(payload["acceptance_checks"].values())
assert payload["selection"] is None
assert payload["promotion"] is None
assert payload["human_admit_required"] is True
assert payload["automatic_promotion"] is False
assert payload["release_authorized"] is False
assert payload["deployment_authorized"] is False
assert payload["trading_authorized"] is False
PY

if llm-arbitrage replication-report \
  --plan "$ROOT/replication-plan.yaml" \
  --inputs "$ROOT/replication-inputs.json" \
  --output "$ROOT/replication-report.json" >/dev/null 2>&1; then
  echo "expected replication-report overwrite protection to fail" >&2
  exit 1
fi

if llm-arbitrage verify-replication-report \
  --report "$ROOT/replication-report.json" \
  --attestation "$ROOT/replication-report.attestation.json" \
  --trusted-public-key "$ROOT/keys/wrong/public.pem" >/dev/null 2>&1; then
  echo "expected wrong trusted replication key to fail" >&2
  exit 1
fi

if llm-arbitrage sign-replication-report \
  --report "$ROOT/replication-report.json" \
  --private-key "$ROOT/keys/statistics-a/private.pem" \
  --output "$ROOT/participant.attestation.json" >/dev/null 2>&1; then
  echo "expected participant replication signer to fail" >&2
  exit 1
fi

python - <<'PY'
import json
from pathlib import Path

from llm_arbitrage_system.experiments.bundle_io import write_json

root = Path(".phase9-runs")
payload = json.loads((root / "replication-report.json").read_text(encoding="utf-8"))
payload["deployment_authorized"] = True
write_json(root / "tampered-replication-report.json", payload)
PY

if llm-arbitrage verify-replication-report \
  --report "$ROOT/tampered-replication-report.json" \
  --attestation "$ROOT/replication-report.attestation.json" \
  --trusted-public-key "$ROOT/keys/replication/public.pem" >/dev/null 2>&1; then
  echo "expected tampered replication report verification to fail" >&2
  exit 1
fi

echo "Phase 9 signed independent-replication smoke passed"
