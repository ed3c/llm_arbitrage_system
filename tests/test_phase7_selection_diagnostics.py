from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.selection_diagnostics import (
    build_selection_diagnostics,
)

_MATRIX_SHA = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"
_CONFIG_A = "a" * 64
_CONFIG_B = "b" * 64


def _policy(
    path: Path,
    *,
    require_adjusted: bool = False,
    maximum_drawdown: str = "25",
) -> Path:
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
  maximum_drawdown_pct: "{maximum_drawdown}"
  minimum_positive_window_fraction: "0.5"
  maximum_alpha_decay_bps_per_window: "100"
multiple_testing:
  method: holm_sign_test
  family_alpha: "0.05"
  minimum_non_tied_pairwise_windows: 3
  require_adjusted_pairwise_evidence: {str(require_adjusted).lower()}
""",
        encoding="utf-8",
    )
    return path


def _observation(
    candidate_id: str,
    config_sha: str,
    window_index: int,
    pnl: str,
    *,
    mark_lag: int,
    ending_equity: str,
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
        "mark_lag_microseconds": mark_lag,
        "mark_to_market_pnl_usd": pnl,
        "ending_equity_usd": ending_equity,
        "period_return": float(pnl) / 100000.0,
    }


def _candidate(
    candidate_id: str,
    config_sha: str,
    pnl_values: tuple[str, ...],
    *,
    mark_lag: int = 60_000_000,
    maximum_drawdown: float = 5.0,
    alpha_decay: str | None = "10",
) -> dict[str, Any]:
    equity = 100000.0
    observations: list[dict[str, Any]] = []
    for index, pnl in enumerate(pnl_values):
        equity += float(pnl)
        observations.append(
            _observation(
                candidate_id,
                config_sha,
                index,
                pnl,
                mark_lag=mark_lag,
                ending_equity=str(equity),
            )
        )
    total = sum(float(value) for value in pnl_values)
    total_text = str(int(total)) if total.is_integer() else str(total)
    ending_text = str(int(100000 + total)) if total.is_integer() else str(100000 + total)
    return {
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "coverage": "complete",
        "expected_evaluation_count": len(pnl_values),
        "observed_evaluation_count": len(pnl_values),
        "initial_equity_usd": "100000",
        "ending_equity_usd": ending_text,
        "total_mark_to_market_pnl_usd": total_text,
        "maximum_drawdown_pct": maximum_drawdown,
        "annualized_sharpe_ratio": 1.25,
        "alpha_decay_method": "ols_terminal_pnl_bps_per_window",
        "oos_pnl_slope_bps_per_window": "-1",
        "alpha_decay_bps_per_window": alpha_decay,
        "mark_lag_microseconds": mark_lag,
        "observations": observations,
    }


def _report(
    path: Path,
    candidates: list[dict[str, Any]],
    *,
    matrix_sha: str = _MATRIX_SHA,
) -> Path:
    write_json(
        path,
        {
            "schema_version": 1,
            "report_id": "oos-report-" + "c" * 40,
            "matrix_sha256": matrix_sha,
            "code_revision": "phase7-fixture",
            "package_version": "0.1.0",
            "periods_per_year": 252,
            "candidates": candidates,
            "selection": None,
            "assumptions": ["Synthetic Phase 7 diagnostic fixture."],
            "evidence_boundary": "Synthetic offline fixture only.",
        },
    )
    return path


def test_selection_diagnostics_are_deterministic_and_never_rank(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path / "policy.yaml")
    report = _report(
        tmp_path / "statistics.json",
        [
            _candidate("candidate-b", _CONFIG_B, ("1", "2", "3")),
            _candidate("candidate-a", _CONFIG_A, ("10", "8", "6")),
        ],
    )

    first = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=report,
        code_revision="phase7-diagnostics",
        package_version="0.1.0",
    )
    second = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=report,
        code_revision="phase7-diagnostics",
        package_version="0.1.0",
    )

    assert first == second
    payload = first.as_dict()
    assert payload["family_state"] == "eligible_for_human_review"
    assert [item["candidate_id"] for item in payload["candidates"]] == [
        "candidate-a",
        "candidate-b",
    ]
    assert payload["selection"] is None
    assert payload["ranking"] is None
    assert payload["promotion"] is None
    assert len(payload["pairwise"]) == 1
    comparison = payload["pairwise"][0]
    assert comparison["left_wins"] == 3
    assert comparison["right_wins"] == 0
    assert comparison["raw_two_sided_sign_p_value"] == "0.25"
    assert comparison["holm_adjusted_p_value"] == "0.25"
    assert comparison["adjusted_significant"] is False


def test_selection_diagnostics_report_policy_blockers(tmp_path: Path) -> None:
    policy = _policy(tmp_path / "policy.yaml", maximum_drawdown="10")
    report = _report(
        tmp_path / "statistics.json",
        [
            _candidate("candidate-a", _CONFIG_A, ("10", "8", "6")),
            _candidate(
                "candidate-b",
                _CONFIG_B,
                ("-5", "-4", "-3"),
                maximum_drawdown=20.0,
            ),
        ],
    )
    diagnostics = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=report,
        code_revision="phase7-blockers",
    )
    candidates = {
        item.candidate_id: item for item in diagnostics.candidates
    }
    assert candidates["candidate-a"].status == "eligible_for_human_review"
    assert candidates["candidate-b"].status == "blocked"
    assert "maximum_drawdown_exceeded" in candidates["candidate-b"].blockers
    assert (
        "positive_window_fraction_below_policy"
        in candidates["candidate-b"].blockers
    )


def test_selection_diagnostics_block_unequal_lag_and_skip_pairwise(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path / "policy.yaml")
    report = _report(
        tmp_path / "statistics.json",
        [
            _candidate("candidate-a", _CONFIG_A, ("3", "2", "1")),
            _candidate(
                "candidate-b",
                _CONFIG_B,
                ("2", "1", "0"),
                mark_lag=120_000_000,
            ),
        ],
    )
    diagnostics = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=report,
        code_revision="phase7-lag",
    )
    assert diagnostics.family_state == "blocked"
    assert diagnostics.global_blockers == ("unequal_mark_lag",)
    assert diagnostics.pairwise == ()


def test_selection_diagnostics_can_require_adjusted_pairwise_evidence(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path / "policy.yaml", require_adjusted=True)
    report = _report(
        tmp_path / "statistics.json",
        [
            _candidate("candidate-a", _CONFIG_A, ("10", "8", "6")),
            _candidate("candidate-b", _CONFIG_B, ("1", "2", "3")),
        ],
    )
    diagnostics = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=report,
        code_revision="phase7-adjusted",
    )
    assert diagnostics.family_state == "blocked"
    assert all(
        "adjusted_pairwise_evidence_unavailable" in candidate.blockers
        for candidate in diagnostics.candidates
    )


def test_selection_diagnostics_reject_identity_and_accounting_drift(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path / "policy.yaml")
    wrong_matrix = _report(
        tmp_path / "wrong-matrix.json",
        [
            _candidate("candidate-a", _CONFIG_A, ("1", "2", "3")),
            _candidate("candidate-b", _CONFIG_B, ("1", "2", "3")),
        ],
        matrix_sha="d" * 64,
    )
    with pytest.raises(ValueError, match="matrix does not match"):
        build_selection_diagnostics(
            policy_path=policy,
            statistics_report_path=wrong_matrix,
            code_revision="phase7-matrix",
        )

    first = _candidate("candidate-a", _CONFIG_A, ("1", "2", "3"))
    first["total_mark_to_market_pnl_usd"] = "999"
    drift = _report(
        tmp_path / "drift.json",
        [first, _candidate("candidate-b", _CONFIG_B, ("1", "2", "3"))],
    )
    with pytest.raises(ValueError, match="total PnL does not match windows"):
        build_selection_diagnostics(
            policy_path=policy,
            statistics_report_path=drift,
            code_revision="phase7-drift",
        )
