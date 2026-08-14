from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from llm_arbitrage_system.experiments.oos_statistics import (
    CandidateOOSStatistics,
    OOSStatisticsReport,
    OOSValuationObservation,
)
from llm_arbitrage_system.experiments.selection_policy import (
    build_selection_governance_report,
    load_selection_policy,
)


def _policy_text(
    *,
    multiple_testing_mode: str = "warn_only",
    maximum_candidates_without_warning: int = 1,
    minimum_sharpe: str | None = "0",
    maximum_alpha_decay: str | None = "2",
    minimum_positive_fraction: str | None = "0.5",
) -> str:
    sharpe = "null" if minimum_sharpe is None else f'"{minimum_sharpe}"'
    alpha_decay = (
        "null" if maximum_alpha_decay is None else f'"{maximum_alpha_decay}"'
    )
    positive_fraction = (
        "null"
        if minimum_positive_fraction is None
        else f'"{minimum_positive_fraction}"'
    )
    return f"""schema_version: 1
mode: human_review_only
admission:
  require_complete_coverage: true
  minimum_evaluation_count: 3
  maximum_drawdown_pct: "10.0"
  minimum_annualized_sharpe_ratio: {sharpe}
  maximum_alpha_decay_bps_per_window: {alpha_decay}
  minimum_oos_pnl_slope_bps_per_window: "-2"
  minimum_total_mark_to_market_pnl_usd: "0"
  minimum_positive_window_fraction: {positive_fraction}
multiple_testing:
  mode: {multiple_testing_mode}
  maximum_candidates_without_warning: {maximum_candidates_without_warning}
"""


def _write_policy(path: Path, **kwargs: Any) -> Path:
    path.write_text(_policy_text(**kwargs), encoding="utf-8")
    return path


def _candidate(
    candidate_id: str,
    digest_character: str,
    *,
    pnls: tuple[str, ...] = ("2", "1", "-0.5"),
    sharpe: float | None = 0.5,
    drawdown: float = 1.0,
    slope: str | None = "-1",
    alpha_decay: str | None = "1",
) -> CandidateOOSStatistics:
    equity = Decimal("100000")
    observations: list[OOSValuationObservation] = []
    for index, pnl_text in enumerate(pnls):
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
                period_return=float(pnl / (equity - pnl)),
            )
        )
    return CandidateOOSStatistics(
        candidate_id=candidate_id,
        candidate_config_sha256=digest_character * 64,
        expected_evaluation_count=len(observations),
        initial_equity_usd=Decimal("100000"),
        ending_equity_usd=equity,
        total_mark_to_market_pnl_usd=sum(
            (item.mark_to_market_pnl_usd for item in observations),
            Decimal("0"),
        ),
        maximum_drawdown_pct=drawdown,
        annualized_sharpe_ratio=sharpe,
        oos_pnl_slope_bps_per_window=(
            None if slope is None else Decimal(slope)
        ),
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
        code_revision="phase7-test",
        package_version="0.1.0",
        periods_per_year=252,
        candidates=candidates,
    )


def _criterion(
    payload: dict[str, Any],
    candidate_index: int,
    name: str,
) -> dict[str, Any]:
    criteria = payload["candidates"][candidate_index]["criteria"]
    return next(item for item in criteria if item["name"] == name)


def test_selection_policy_is_strict_content_addressed_and_normalized(
    tmp_path: Path,
) -> None:
    first = load_selection_policy(_write_policy(tmp_path / "policy.yaml"))
    second = load_selection_policy(tmp_path / "policy.yaml")

    assert first.canonical_sha256 == second.canonical_sha256
    assert first.canonical_bytes == second.canonical_bytes
    payload = first.summary()["policy"]
    assert payload["mode"] == "human_review_only"
    assert payload["admission"]["maximum_drawdown_pct"] == "10"
    assert payload["admission"]["minimum_positive_window_fraction"] == "0.5"

    changed_path = _write_policy(
        tmp_path / "changed.yaml",
        minimum_positive_fraction="0.6",
    )
    changed = load_selection_policy(changed_path)
    assert changed.canonical_sha256 != first.canonical_sha256


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            _policy_text() + "mode: human_review_only\n",
            "duplicate",
        ),
        (
            _policy_text().replace(
                "mode: human_review_only\n",
                "mode: human_review_only\nunknown: true\n",
            ),
            "unknown fields",
        ),
        (
            _policy_text().replace(
                '  maximum_drawdown_pct: "10.0"\n',
                "",
            ),
            "missing fields",
        ),
        (
            _policy_text().replace(
                '  maximum_drawdown_pct: "10.0"\n',
                "  maximum_drawdown_pct: 10.0\n",
            ),
            "decimal string or null",
        ),
        (
            _policy_text().replace(
                '  maximum_drawdown_pct: "10.0"\n',
                '  maximum_drawdown_pct: "NaN"\n',
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
    ],
)
def test_selection_policy_rejects_invalid_contracts(
    tmp_path: Path,
    text: str,
    message: str,
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_selection_policy(path)


def test_governance_report_is_deterministic_and_never_selects(
    tmp_path: Path,
) -> None:
    policy = load_selection_policy(_write_policy(tmp_path / "policy.yaml"))
    statistics = _statistics(
        (
            _candidate("candidate-b", "c", pnls=("1", "1", "1")),
            _candidate("candidate-a", "d"),
        )
    )

    first = build_selection_governance_report(statistics, policy)
    second = build_selection_governance_report(statistics, policy)

    assert first == second
    assert [item.candidate_id for item in first.candidates] == [
        "candidate-a",
        "candidate-b",
    ]
    assert first.admissible_candidate_ids == ("candidate-a", "candidate-b")
    assert first.blocked_candidate_ids == ()
    assert any("no multiple-testing adjustment" in item for item in first.warnings)

    payload = first.as_dict()
    assert payload["selection"] is None
    assert payload["promotion"] is None
    assert payload["human_admit_required"] is True
    rendered = json.dumps(payload, sort_keys=True)
    for prohibited in ("winner", "rank", "score", "deployment"):
        assert f'"{prohibited}":' not in rendered


def test_unavailable_required_metrics_and_window_fraction_block_candidate(
    tmp_path: Path,
) -> None:
    policy = load_selection_policy(_write_policy(tmp_path / "policy.yaml"))
    candidate = _candidate(
        "candidate-blocked",
        "e",
        pnls=("1", "-1", "-1"),
        sharpe=None,
        alpha_decay=None,
    )

    report = build_selection_governance_report(
        _statistics((candidate,)),
        policy,
    )
    payload = report.as_dict()

    assert report.admissible_candidate_ids == ()
    assert report.blocked_candidate_ids == ("candidate-blocked",)
    assert _criterion(
        payload,
        0,
        "minimum_annualized_sharpe_ratio",
    )["reason"] == "required metric is unavailable"
    assert _criterion(
        payload,
        0,
        "maximum_alpha_decay_bps_per_window",
    )["reason"] == "required metric is unavailable"
    assert _criterion(
        payload,
        0,
        "minimum_positive_window_fraction",
    )["status"] == "fail"


def test_single_candidate_policy_blocks_multi_candidate_report(
    tmp_path: Path,
) -> None:
    policy = load_selection_policy(
        _write_policy(
            tmp_path / "policy.yaml",
            multiple_testing_mode="require_single_candidate",
        )
    )
    statistics = _statistics(
        (
            _candidate("candidate-a", "1"),
            _candidate("candidate-b", "2"),
        )
    )

    report = build_selection_governance_report(statistics, policy)
    payload = report.as_dict()

    assert report.admissible_candidate_ids == ()
    assert report.blocked_candidate_ids == ("candidate-a", "candidate-b")
    assert any("all candidates are blocked" in item for item in report.warnings)
    for index in range(2):
        criterion = _criterion(payload, index, "multiple_testing_gate")
        assert criterion["status"] == "fail"
        assert criterion["threshold"] == 1


def test_governance_report_rejects_incomplete_and_duplicate_candidates(
    tmp_path: Path,
) -> None:
    policy = load_selection_policy(_write_policy(tmp_path / "policy.yaml"))
    complete = _candidate("candidate-a", "3")
    incomplete = CandidateOOSStatistics(
        candidate_id=complete.candidate_id,
        candidate_config_sha256=complete.candidate_config_sha256,
        expected_evaluation_count=4,
        initial_equity_usd=complete.initial_equity_usd,
        ending_equity_usd=complete.ending_equity_usd,
        total_mark_to_market_pnl_usd=complete.total_mark_to_market_pnl_usd,
        maximum_drawdown_pct=complete.maximum_drawdown_pct,
        annualized_sharpe_ratio=complete.annualized_sharpe_ratio,
        oos_pnl_slope_bps_per_window=complete.oos_pnl_slope_bps_per_window,
        alpha_decay_bps_per_window=complete.alpha_decay_bps_per_window,
        mark_lag_microseconds=complete.mark_lag_microseconds,
        observations=complete.observations,
    )
    with pytest.raises(ValueError, match="not complete"):
        build_selection_governance_report(_statistics((incomplete,)), policy)

    with pytest.raises(ValueError, match="duplicate candidate"):
        build_selection_governance_report(
            _statistics((complete, complete)),
            policy,
        )
