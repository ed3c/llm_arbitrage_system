from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.cli import main
from llm_arbitrage_system.experiments.selection_diagnostics import (
    build_selection_diagnostics,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    build_selection_dossier,
    load_selection_dossier,
)
from llm_arbitrage_system.experiments.selection_signing import (
    sign_selection_dossier,
    verify_selection_dossier_attestation,
)
from llm_arbitrage_system.experiments.signing import generate_signing_keypair

_MATRIX_SHA = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"


def _write_policy(path: Path) -> Path:
    path.write_text(
        f"""schema_version: 1
matrix_sha256: {_MATRIX_SHA}
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
    return path


def _observation(
    candidate_id: str,
    config_sha: str,
    window_index: int,
    pnl: int,
    ending_equity: int,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"evaluation-{candidate_id}-{window_index}",
        "experiment_id": f"experiment-{candidate_id}-{window_index}",
        "valuation_id": f"valuation-{candidate_id}-{window_index}",
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "window_index": window_index,
        "test_start": window_index * 10,
        "test_end": window_index * 10 + 5,
        "test_semantic_sha256": f"{window_index + 1:064x}",
        "mark_lag_microseconds": 60_000_000,
        "mark_to_market_pnl_usd": str(pnl),
        "ending_equity_usd": str(ending_equity),
        "period_return": pnl / 100000.0,
    }


def _candidate(
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
            _observation(candidate_id, config_sha, index, pnl, equity)
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


def _write_statistics(path: Path) -> Path:
    write_json(
        path,
        {
            "schema_version": 1,
            "report_id": "oos-report-" + "c" * 40,
            "matrix_sha256": _MATRIX_SHA,
            "code_revision": "phase7-statistics-fixture",
            "package_version": "0.1.0",
            "periods_per_year": 252,
            "candidates": [
                _candidate("candidate-b", "b", (1, 2, 3)),
                _candidate("candidate-a", "a", (10, 8, 6)),
            ],
            "selection": None,
            "assumptions": ["Synthetic Phase 7 CLI fixture."],
            "evidence_boundary": "Synthetic offline paper fixture only.",
        },
    )
    return path


def _build_phase7_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    policy = _write_policy(tmp_path / "selection-policy.yaml")
    statistics = _write_statistics(tmp_path / "statistics.json")
    diagnostics_path = tmp_path / "diagnostics.json"
    diagnostics = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=statistics,
        code_revision="phase7-test-diagnostics",
        package_version="0.1.0",
    )
    write_json(diagnostics_path, diagnostics.as_dict())
    dossier_path = tmp_path / "dossier.json"
    dossier = build_selection_dossier(
        policy_path=policy,
        statistics_report_path=statistics,
        diagnostics_path=diagnostics_path,
        code_revision="phase7-test-dossier",
        package_version="0.1.0",
    )
    write_json(dossier_path, dossier.as_dict())
    return policy, statistics, diagnostics_path, dossier_path


def test_phase7_cli_builds_and_signs_human_review_dossier(
    tmp_path: Path,
) -> None:
    policy = _write_policy(tmp_path / "policy.yaml")
    statistics = _write_statistics(tmp_path / "statistics.json")
    diagnostics = tmp_path / "diagnostics.json"
    dossier = tmp_path / "dossier.json"

    assert main(["validate-selection-policy", str(policy)]) == 0
    assert (
        main(
            [
                "selection-diagnostics",
                "--policy",
                str(policy),
                "--statistics",
                str(statistics),
                "--output",
                str(diagnostics),
                "--code-revision",
                "phase7-cli-diagnostics",
            ]
        )
        == 0
    )
    diagnostic_payload = json.loads(diagnostics.read_text(encoding="utf-8"))
    assert diagnostic_payload["selection"] is None
    assert diagnostic_payload["ranking"] is None
    assert diagnostic_payload["promotion"] is None
    assert [item["candidate_id"] for item in diagnostic_payload["candidates"]] == [
        "candidate-a",
        "candidate-b",
    ]

    assert (
        main(
            [
                "build-selection-dossier",
                "--policy",
                str(policy),
                "--statistics",
                str(statistics),
                "--diagnostics",
                str(diagnostics),
                "--output",
                str(dossier),
                "--code-revision",
                "phase7-cli-dossier",
            ]
        )
        == 0
    )
    dossier_payload = json.loads(dossier.read_text(encoding="utf-8"))
    assert dossier_payload["human_decision"] is None
    assert dossier_payload["selected_candidate_id"] is None
    assert dossier_payload["promotion"] is None
    assert dossier_payload["eligible_candidate_ids"] == [
        "candidate-a",
        "candidate-b",
    ]

    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(private_key),
                "--public-key",
                str(public_key),
            ]
        )
        == 0
    )
    attestation = tmp_path / "dossier.attestation.json"
    assert (
        main(
            [
                "sign-selection-dossier",
                "--dossier",
                str(dossier),
                "--private-key",
                str(private_key),
                "--output",
                str(attestation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-selection-dossier",
                "--dossier",
                str(dossier),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(public_key),
            ]
        )
        == 0
    )

    assert (
        main(
            [
                "selection-diagnostics",
                "--policy",
                str(policy),
                "--statistics",
                str(statistics),
                "--output",
                str(diagnostics),
                "--code-revision",
                "phase7-cli-diagnostics",
            ]
        )
        == 2
    )


def test_selection_dossier_signing_rejects_wrong_key_and_tampering(
    tmp_path: Path,
) -> None:
    _, _, _, dossier = _build_phase7_files(tmp_path)
    first_private = tmp_path / "first/private.pem"
    first_public = tmp_path / "first/public.pem"
    second_private = tmp_path / "second/private.pem"
    second_public = tmp_path / "second/public.pem"
    generate_signing_keypair(first_private, first_public)
    generate_signing_keypair(second_private, second_public)
    attestation = tmp_path / "dossier.attestation.json"
    sign_selection_dossier(dossier, first_private, attestation)

    with pytest.raises(ValueError, match="trusted public key"):
        verify_selection_dossier_attestation(
            dossier,
            attestation,
            trusted_public_key_path=second_public,
        )

    payload = json.loads(dossier.read_text(encoding="utf-8"))
    payload["family_state"] = "blocked"
    write_json(dossier, payload)
    with pytest.raises(ValueError, match="dossier_id"):
        verify_selection_dossier_attestation(
            dossier,
            attestation,
            trusted_public_key_path=first_public,
        )


def test_selection_dossier_requires_canonical_and_matching_evidence(
    tmp_path: Path,
) -> None:
    policy, statistics, diagnostics, dossier = _build_phase7_files(tmp_path)
    payload = json.loads(dossier.read_text(encoding="utf-8"))
    dossier.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        load_selection_dossier(dossier)

    changed_statistics = json.loads(statistics.read_text(encoding="utf-8"))
    changed_statistics["package_version"] = "0.1.1"
    write_json(statistics, changed_statistics)
    with pytest.raises(ValueError, match="report hash"):
        build_selection_dossier(
            policy_path=policy,
            statistics_report_path=statistics,
            diagnostics_path=diagnostics,
            code_revision="phase7-evidence-drift",
        )
