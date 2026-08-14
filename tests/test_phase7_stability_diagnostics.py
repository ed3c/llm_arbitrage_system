from __future__ import annotations

import json
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

from llm_arbitrage_system.experiments.oos_statistics import (
    CandidateOOSStatistics,
    OOSStatisticsReport,
    OOSValuationObservation,
)
from llm_arbitrage_system.experiments.stability_diagnostics import (
    build_stability_diagnostics_report,
    load_stability_policy,
)


def _policy_text(
    *,
    minimum_window_count: int = 3,
    zero_tolerance: str = "0",
    minimum_positive_fraction: str = "0.5",
    maximum_largest_share: str = "0.75",
    minimum_return_count: int = 2,
    maximum_drawdown: str | None = "10",
    maximum_alpha_decay: str | None = "5",
    candidate_family_threshold: int = 1,
    mode: str = "descriptive_only",
) -> str:
    drawdown = "null" if maximum_drawdown is None else f'"{maximum_drawdown}"'
    alpha_decay = (
        "null" if maximum_alpha_decay is None else f'"{maximum_alpha_decay}"'
    )
    return f"""schema_version: 1
mode: {mode}
diagnostics:
  minimum_window_count: {minimum_window_count}
  zero_pnl_tolerance_usd: "{zero_tolerance}"
  minimum_positive_window_fraction: "{minimum_positive_fraction}"
  maximum_largest_absolute_pnl_share: "{maximum_largest_share}"
  minimum_return_observation_count: {minimum_return_count}
  maximum_drawdown_pct: {drawdown}
  maximum_alpha_decay_bps_per_window: {alpha_decay}
  candidate_family_warning_threshold: {candidate_family_threshold}
"""


def _write_policy(path: Path, **kwargs: Any) -> Path:
    path.write_text(_policy_text(**kwargs), encoding="utf-8")
    return path


def _candidate(
    candidate_id: str,
    digest_character: str,
    *,
    pnls: tuple[str, ...] = ("3", "0", "-1", "2"),
    returns: tuple[str | None, ...] | None = None,
    drawdown: float = 2.0,
    alpha_decay: str | None = "1",
    total_override: str | None = None,
    reverse_observations: bool = False,
) -> CandidateOOSStatistics:
    if returns is None:
        returns = ("0.03", None, "-0.01", "0.02")
    if len(returns) != len(pnls):
        raise ValueError("returns and pnls must have the same length")
    initial_equity = Decimal("100")
    equity = initial_equity
    observations: list[OOSValuationObservation] = []
    for index, (pnl_text, return_text) in enumerate(zip(pnls, returns, strict=True)):
        pnl = Decimal(pnl_text)
        equity += pnl
        observations.append(
            OOSValuationObservation(
                evaluation_id=f"evaluation-{candidate_id}-{index}",
                experiment_id=f"experiment-{candidate_id}-{index}",
                valuation_id=f"valuation-{candidate_id}-{index}",
                candidate_id=candidate_id,
                candidate_config_sha256=digest_character * 64,
                window_index=index,
                test_start=index * 5,
                test_end=(index + 1) * 5,
                test_semantic_sha256=str(index + 1) * 64,
                mark_lag_microseconds=60_000_000,
                mark_to_market_pnl_usd=pnl,
                ending_equity_usd=equity,
                period_return=(
                    None if return_text is None else float(return_text)
                ),
            )
        )
    if reverse_observations:
        observations.reverse()
    total = sum((Decimal(value) for value in pnls), Decimal("0"))
    return CandidateOOSStatistics(
        candidate_id=candidate_id,
        candidate_config_sha256=digest_character * 64,
        expected_evaluation_count=len(observations),
        initial_equity_usd=initial_equity,
        ending_equity_usd=initial_equity + total,
        total_mark_to_market_pnl_usd=(
            Decimal(total_override) if total_override is not None else total
        ),
        maximum_drawdown_pct=drawdown,
        annualized_sharpe_ratio=0.5,
        oos_pnl_slope_bps_per_window=Decimal("-1"),
        alpha_decay_bps_per_window=(
            None if alpha_decay is None else Decimal(alpha_decay)
        ),
        mark_lag_microseconds=60_000_000,
        observations=tuple(observations),
    )


def _statistics(
    candidates: tuple[CandidateOOSStatistics, ...],
) -> OOSStatisticsReport:
    return OOSStatisticsReport(
        report_id="oos-report-" + "a" * 40,
        matrix_sha256="b" * 64,
        code_revision="phase7-stability-test",
        package_version="0.1.0",
        periods_per_year=252,
        candidates=candidates,
    )


def test_stability_policy_is_strict_content_addressed_and_normalized(
    tmp_path: Path,
) -> None:
    first = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    second = load_stability_policy(tmp_path / "policy.yaml")

    assert first.canonical_sha256 == second.canonical_sha256
    assert first.canonical_bytes == second.canonical_bytes
    payload = first.summary()["policy"]
    assert payload["mode"] == "descriptive_only"
    assert payload["diagnostics"]["maximum_drawdown_pct"] == "10"
    assert payload["diagnostics"]["minimum_positive_window_fraction"] == "0.5"

    changed = load_stability_policy(
        _write_policy(
            tmp_path / "changed.yaml",
            maximum_largest_share="0.6",
        )
    )
    assert changed.canonical_sha256 != first.canonical_sha256


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_policy_text() + "mode: descriptive_only\n", "duplicate"),
        (
            _policy_text().replace(
                "mode: descriptive_only\n",
                "mode: descriptive_only\nunknown: true\n",
            ),
            "unknown fields",
        ),
        (
            _policy_text().replace(
                '  maximum_drawdown_pct: "10"\n',
                "",
            ),
            "missing fields",
        ),
        (
            _policy_text().replace(
                '  maximum_largest_absolute_pnl_share: "0.75"\n',
                "  maximum_largest_absolute_pnl_share: 0.75\n",
            ),
            "decimal string",
        ),
        (
            _policy_text().replace(
                '  maximum_largest_absolute_pnl_share: "0.75"\n',
                '  maximum_largest_absolute_pnl_share: "NaN"\n',
            ),
            "finite",
        ),
        (
            _policy_text().replace(
                '  minimum_positive_window_fraction: "0.5"\n',
                '  minimum_positive_window_fraction: "1.1"\n',
            ),
            "at most 1",
        ),
        (
            _policy_text().replace(
                '  zero_pnl_tolerance_usd: "0"\n',
                '  zero_pnl_tolerance_usd: "-1"\n',
            ),
            "at least 0",
        ),
        (_policy_text(mode="selection"), "descriptive_only"),
        (
            _policy_text(candidate_family_threshold=0),
            "candidate_family_warning_threshold",
        ),
    ],
)
def test_stability_policy_rejects_invalid_contracts(
    tmp_path: Path,
    text: str,
    message: str,
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_stability_policy(path)


def test_diagnostics_are_deterministic_and_calculate_window_statistics(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    statistics = _statistics((_candidate("candidate-a", "c"),))

    first = build_stability_diagnostics_report(statistics, policy)
    second = build_stability_diagnostics_report(statistics, policy)

    assert first == second
    candidate = first.candidates[0]
    assert candidate.diagnostic_state == "within_declared_bounds"
    assert candidate.window_count == 4
    assert candidate.positive_window_count == 2
    assert candidate.negative_window_count == 1
    assert candidate.zero_window_count == 1
    assert candidate.positive_window_fraction == Decimal("0.5")
    assert candidate.negative_window_fraction == Decimal("0.25")
    assert candidate.zero_window_fraction == Decimal("0.25")
    assert candidate.sign_pattern == "mixed"
    assert candidate.median_window_pnl_usd == Decimal("1")
    with localcontext() as context:
        context.prec = 50
        expected_stddev = Decimal("2.5").sqrt()
    assert candidate.pnl_population_stddev_usd == expected_stddev
    assert candidate.best_window_pnl_usd == Decimal("3")
    assert candidate.worst_window_pnl_usd == Decimal("-1")
    assert candidate.largest_absolute_window_share == Decimal("0.5")
    assert candidate.worst_loss_share_of_total_absolute_pnl == (
        Decimal("1") / Decimal("6")
    )
    assert candidate.return_observation_count == 3
    assert candidate.median_period_return == Decimal("0.02")
    assert candidate.drawdown_threshold_status == "within_threshold"
    assert candidate.alpha_decay_threshold_status == "within_threshold"

    payload = first.as_dict()
    assert payload["selection"] is None
    assert payload["promotion"] is None
    assert payload["human_admit_required"] is True
    assert payload["verification"] == {
        "holdout_independence": "NOT_VERIFIED",
        "policy_preregistration_timing": "NOT_VERIFIED",
        "candidate_family_independence": "NOT_VERIFIED",
    }
    assert payload["statistical_significance"] == "NOT_EVALUATED"
    assert payload["multiple_testing_adjustment"] == "NOT_APPLIED"


def test_declared_boundaries_emit_deterministic_candidate_warnings(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(
        _write_policy(
            tmp_path / "policy.yaml",
            minimum_window_count=5,
            minimum_positive_fraction="0.75",
            maximum_largest_share="0.4",
            minimum_return_count=4,
            maximum_drawdown="1",
            maximum_alpha_decay="0.5",
        )
    )
    report = build_stability_diagnostics_report(
        _statistics((_candidate("candidate-warn", "d"),)),
        policy,
    )
    candidate = report.candidates[0]

    assert candidate.diagnostic_state == "warnings_present"
    assert candidate.drawdown_threshold_status == "exceeds_threshold"
    assert candidate.alpha_decay_threshold_status == "exceeds_threshold"
    assert len(candidate.warnings) == 6
    assert "Window count 4" in candidate.warnings[0]
    assert "Positive-window fraction 0.5" in candidate.warnings[1]
    assert "Largest absolute-window share 0.5" in candidate.warnings[2]
    assert "Return observation count 3" in candidate.warnings[3]
    assert "Maximum drawdown 2" in candidate.warnings[4]
    assert "Alpha decay 1" in candidate.warnings[5]


def test_alpha_decay_unavailability_is_explicit_when_threshold_is_required(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    report = build_stability_diagnostics_report(
        _statistics(
            (
                _candidate(
                    "candidate-no-alpha",
                    "e",
                    alpha_decay=None,
                ),
            )
        ),
        policy,
    )
    candidate = report.candidates[0]

    assert candidate.alpha_decay_bps_per_window is None
    assert candidate.alpha_decay_threshold_status == "unavailable"
    assert "Alpha-decay metric is unavailable" in candidate.warnings[-1]


def test_single_all_zero_window_has_zero_dispersion_and_concentration(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(
        _write_policy(
            tmp_path / "policy.yaml",
            minimum_window_count=1,
            minimum_positive_fraction="0",
            maximum_largest_share="1",
            minimum_return_count=0,
            maximum_drawdown=None,
            maximum_alpha_decay=None,
        )
    )
    report = build_stability_diagnostics_report(
        _statistics(
            (
                _candidate(
                    "candidate-zero",
                    "f",
                    pnls=("0",),
                    returns=(None,),
                    drawdown=0.0,
                    alpha_decay=None,
                ),
            )
        ),
        policy,
    )
    candidate = report.candidates[0]

    assert candidate.diagnostic_state == "within_declared_bounds"
    assert candidate.sign_pattern == "all_zero"
    assert candidate.median_window_pnl_usd == Decimal("0")
    assert candidate.pnl_population_stddev_usd == Decimal("0")
    assert candidate.largest_absolute_window_share == Decimal("0")
    assert candidate.worst_loss_share_of_total_absolute_pnl == Decimal("0")
    assert candidate.return_observation_count == 0
    assert candidate.median_period_return is None
    assert candidate.period_return_population_stddev is None
    assert candidate.drawdown_threshold_status == "not_configured"
    assert candidate.alpha_decay_threshold_status == "not_configured"


def test_candidate_family_breadth_warning_does_not_rank_or_select(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    report = build_stability_diagnostics_report(
        _statistics(
            (
                _candidate("candidate-b", "1"),
                _candidate("candidate-a", "2"),
            )
        ),
        policy,
    )

    assert [item.candidate_id for item in report.candidates] == [
        "candidate-a",
        "candidate-b",
    ]
    assert "contains 2 configurations" in report.warnings[0]
    rendered = json.dumps(report.as_dict(), sort_keys=True)
    for prohibited in (
        "winner",
        "rank",
        "score",
        "deployment",
        "p_value",
        "confidence_interval",
    ):
        assert f'"{prohibited}":' not in rendered


def test_diagnostics_reject_inconsistent_or_unordered_source_evidence(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    candidate = _candidate("candidate-a", "3")

    with pytest.raises(ValueError, match="duplicate candidate"):
        build_stability_diagnostics_report(
            _statistics((candidate, candidate)),
            policy,
        )

    with pytest.raises(ValueError, match="total PnL does not match"):
        build_stability_diagnostics_report(
            _statistics(
                (
                    _candidate(
                        "candidate-total",
                        "4",
                        total_override="999",
                    ),
                )
            ),
            policy,
        )

    with pytest.raises(ValueError, match="ordered by window index"):
        build_stability_diagnostics_report(
            _statistics(
                (
                    _candidate(
                        "candidate-order",
                        "5",
                        reverse_observations=True,
                    ),
                )
            ),
            policy,
        )


def test_diagnostics_reject_non_finite_period_return(
    tmp_path: Path,
) -> None:
    policy = load_stability_policy(_write_policy(tmp_path / "policy.yaml"))
    candidate = _candidate("candidate-nan", "6")
    first = candidate.observations[0]
    invalid_observation = OOSValuationObservation(
        evaluation_id=first.evaluation_id,
        experiment_id=first.experiment_id,
        valuation_id=first.valuation_id,
        candidate_id=first.candidate_id,
        candidate_config_sha256=first.candidate_config_sha256,
        window_index=first.window_index,
        test_start=first.test_start,
        test_end=first.test_end,
        test_semantic_sha256=first.test_semantic_sha256,
        mark_lag_microseconds=first.mark_lag_microseconds,
        mark_to_market_pnl_usd=first.mark_to_market_pnl_usd,
        ending_equity_usd=first.ending_equity_usd,
        period_return=float("nan"),
    )
    invalid_candidate = CandidateOOSStatistics(
        candidate_id=candidate.candidate_id,
        candidate_config_sha256=candidate.candidate_config_sha256,
        expected_evaluation_count=candidate.expected_evaluation_count,
        initial_equity_usd=candidate.initial_equity_usd,
        ending_equity_usd=candidate.ending_equity_usd,
        total_mark_to_market_pnl_usd=candidate.total_mark_to_market_pnl_usd,
        maximum_drawdown_pct=candidate.maximum_drawdown_pct,
        annualized_sharpe_ratio=candidate.annualized_sharpe_ratio,
        oos_pnl_slope_bps_per_window=candidate.oos_pnl_slope_bps_per_window,
        alpha_decay_bps_per_window=candidate.alpha_decay_bps_per_window,
        mark_lag_microseconds=candidate.mark_lag_microseconds,
        observations=(invalid_observation, *candidate.observations[1:]),
    )

    with pytest.raises(ValueError, match="period return must be finite"):
        build_stability_diagnostics_report(
            _statistics((invalid_candidate,)),
            policy,
        )
