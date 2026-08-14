from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from math import sqrt
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.evaluation import (
    ExperimentMatrixSnapshot,
    MatrixEvaluation,
    load_evaluation_record,
    load_experiment_matrix,
)
from llm_arbitrage_system.experiments.manifest import installed_package_version
from llm_arbitrage_system.experiments.valuation import (
    BundleValuationReport,
    value_bundle,
)

_STATISTICS_SCHEMA_VERSION = 1
_ALPHA_DECAY_METHOD = "ols_terminal_pnl_bps_per_window"
_BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class EvaluationValuationInput:
    evaluation_id: str
    bundle_path: Path
    marks_path: Path

    def __post_init__(self) -> None:
        if not self.evaluation_id:
            raise ValueError("evaluation_id cannot be empty")


@dataclass(frozen=True, slots=True)
class OOSValuationObservation:
    evaluation_id: str
    experiment_id: str
    valuation_id: str
    candidate_id: str
    candidate_config_sha256: str
    window_index: int
    test_start: int
    test_end: int
    test_semantic_sha256: str
    mark_lag_microseconds: int
    mark_to_market_pnl_usd: Decimal
    ending_equity_usd: Decimal
    period_return: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "experiment_id": self.experiment_id,
            "valuation_id": self.valuation_id,
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "window_index": self.window_index,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "test_semantic_sha256": self.test_semantic_sha256,
            "mark_lag_microseconds": self.mark_lag_microseconds,
            "mark_to_market_pnl_usd": str(self.mark_to_market_pnl_usd),
            "ending_equity_usd": str(self.ending_equity_usd),
            "period_return": self.period_return,
        }


@dataclass(frozen=True, slots=True)
class CandidateOOSStatistics:
    candidate_id: str
    candidate_config_sha256: str
    expected_evaluation_count: int
    initial_equity_usd: Decimal
    ending_equity_usd: Decimal
    total_mark_to_market_pnl_usd: Decimal
    maximum_drawdown_pct: float
    annualized_sharpe_ratio: float | None
    oos_pnl_slope_bps_per_window: Decimal | None
    alpha_decay_bps_per_window: Decimal | None
    mark_lag_microseconds: int
    observations: tuple[OOSValuationObservation, ...]

    @property
    def coverage(self) -> str:
        return "complete"

    @property
    def observed_evaluation_count(self) -> int:
        return len(self.observations)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "coverage": self.coverage,
            "expected_evaluation_count": self.expected_evaluation_count,
            "observed_evaluation_count": self.observed_evaluation_count,
            "initial_equity_usd": str(self.initial_equity_usd),
            "ending_equity_usd": str(self.ending_equity_usd),
            "total_mark_to_market_pnl_usd": str(
                self.total_mark_to_market_pnl_usd
            ),
            "maximum_drawdown_pct": self.maximum_drawdown_pct,
            "annualized_sharpe_ratio": self.annualized_sharpe_ratio,
            "alpha_decay_method": _ALPHA_DECAY_METHOD,
            "oos_pnl_slope_bps_per_window": _optional_decimal_text(
                self.oos_pnl_slope_bps_per_window
            ),
            "alpha_decay_bps_per_window": _optional_decimal_text(
                self.alpha_decay_bps_per_window
            ),
            "mark_lag_microseconds": self.mark_lag_microseconds,
            "observations": [item.as_dict() for item in self.observations],
        }


@dataclass(frozen=True, slots=True)
class OOSStatisticsReport:
    report_id: str
    matrix_sha256: str
    code_revision: str
    package_version: str
    periods_per_year: int
    candidates: tuple[CandidateOOSStatistics, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _STATISTICS_SCHEMA_VERSION,
            "report_id": self.report_id,
            "matrix_sha256": self.matrix_sha256,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "periods_per_year": self.periods_per_year,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "selection": None,
            "assumptions": [
                (
                    "Each candidate is evaluated as an independent equity path from "
                    "the declared initial equity."
                ),
                (
                    "Terminal marks must use one comparable lag after every test "
                    "window; mark-source authenticity is not proven."
                ),
                (
                    "Annualized Sharpe uses terminal-window returns and the explicit "
                    "periods_per_year value."
                ),
                (
                    "Alpha decay is the non-negative magnitude of a negative ordinary-"
                    "least-squares slope in terminal PnL basis points per window."
                ),
                (
                    "No candidate is selected or promoted. Multiple-testing and model-"
                    "selection risk remain outside this report."
                ),
            ],
            "evidence_boundary": (
                "The report is conditional on trusted registered paper evaluations and "
                "caller-supplied terminal marks. It does not establish source-market "
                "truth, live realized profit, causal alpha, future returns, or release "
                "readiness."
            ),
        }


def build_oos_statistics(
    *,
    registry_path: Path,
    matrix_path: Path,
    candidate_ids: Sequence[str],
    valuation_inputs: Sequence[EvaluationValuationInput],
    initial_equity_usd: Decimal,
    periods_per_year: int,
    code_revision: str,
    package_version: str | None = None,
) -> OOSStatisticsReport:
    _validate_statistics_parameters(
        initial_equity_usd,
        periods_per_year,
        code_revision,
    )
    normalized_revision = code_revision.strip()
    selected_candidates = _unique_non_empty(candidate_ids, "candidate_ids")
    inputs_by_id = _valuation_input_index(valuation_inputs)
    matrix = load_experiment_matrix(matrix_path)
    registry = _load_registry_rows(registry_path, matrix.semantic_sha256)
    resolved_version = package_version or installed_package_version()

    candidate_reports: list[CandidateOOSStatistics] = []
    expected_all: set[str] = set()
    for candidate_id in selected_candidates:
        planned = _candidate_plan(matrix, candidate_id)
        expected_ids = {item.evaluation_id for item in planned}
        expected_all.update(expected_ids)
        missing = sorted(expected_ids - set(inputs_by_id))
        if missing:
            raise ValueError(
                f"candidate {candidate_id} is missing valuation evidence: "
                + ", ".join(missing)
            )
        candidate_reports.append(
            _build_candidate_statistics(
                matrix=matrix,
                planned=planned,
                inputs_by_id=inputs_by_id,
                registry=registry,
                initial_equity_usd=initial_equity_usd,
                periods_per_year=periods_per_year,
                code_revision=normalized_revision,
                package_version=resolved_version,
            )
        )

    unexpected = sorted(set(inputs_by_id) - expected_all)
    if unexpected:
        raise ValueError(
            "valuation inputs contain evaluations outside selected candidates: "
            + ", ".join(unexpected)
        )
    identity = {
        "schema_version": _STATISTICS_SCHEMA_VERSION,
        "matrix_sha256": matrix.semantic_sha256,
        "candidate_reports": [
            {
                "candidate_id": report.candidate_id,
                "candidate_config_sha256": report.candidate_config_sha256,
                "valuation_ids": [
                    observation.valuation_id for observation in report.observations
                ],
            }
            for report in candidate_reports
        ],
        "initial_equity_usd": str(initial_equity_usd),
        "periods_per_year": periods_per_year,
        "alpha_decay_method": _ALPHA_DECAY_METHOD,
        "code_revision": normalized_revision,
        "package_version": resolved_version,
    }
    return OOSStatisticsReport(
        report_id=(
            "oos-report-" + sha256_hex(canonical_json_bytes(identity))[:40]
        ),
        matrix_sha256=matrix.semantic_sha256,
        code_revision=normalized_revision,
        package_version=resolved_version,
        periods_per_year=periods_per_year,
        candidates=tuple(candidate_reports),
    )


def _candidate_plan(
    matrix: ExperimentMatrixSnapshot,
    candidate_id: str,
) -> tuple[MatrixEvaluation, ...]:
    planned = tuple(
        sorted(
            (
                item
                for item in matrix.evaluations
                if item.candidate_id == candidate_id
            ),
            key=lambda item: item.window["index"],
        )
    )
    if not planned:
        raise ValueError(f"matrix does not contain candidate: {candidate_id}")
    indexes = tuple(item.window["index"] for item in planned)
    if len(set(indexes)) != len(indexes):
        raise ValueError(f"candidate {candidate_id} contains duplicate window indexes")
    for previous, current in pairwise(planned):
        if previous.window["test_end"] > current.window["test_start"]:
            raise ValueError(
                f"candidate {candidate_id} contains overlapping test windows"
            )
    return planned


def _build_candidate_statistics(
    *,
    matrix: ExperimentMatrixSnapshot,
    planned: tuple[MatrixEvaluation, ...],
    inputs_by_id: Mapping[str, EvaluationValuationInput],
    registry: Mapping[str, dict[str, Any]],
    initial_equity_usd: Decimal,
    periods_per_year: int,
    code_revision: str,
    package_version: str,
) -> CandidateOOSStatistics:
    candidate_id = planned[0].candidate_id
    candidate_hash = planned[0].candidate_config_sha256
    if any(item.candidate_config_sha256 != candidate_hash for item in planned):
        raise ValueError(f"candidate {candidate_id} uses multiple configuration hashes")

    valuations: list[tuple[MatrixEvaluation, BundleValuationReport, int]] = []
    for item in planned:
        row = registry.get(item.evaluation_id)
        if row is None:
            raise ValueError(
                f"trusted registry is missing evaluation: {item.evaluation_id}"
            )
        _verify_registry_binding(matrix, item, row)
        input_value = inputs_by_id[item.evaluation_id]
        record = load_evaluation_record(input_value.bundle_path)
        if record.get("evaluation_id") != item.evaluation_id:
            raise ValueError("valuation bundle is not the planned evaluation")
        valuation = value_bundle(
            input_value.bundle_path,
            input_value.marks_path,
            code_revision=code_revision,
            package_version=package_version,
        )
        if valuation.experiment_id != row["experiment_id"]:
            raise ValueError(
                "valuation experiment does not match trusted registry evidence: "
                + item.evaluation_id
            )
        if valuation.bundle_root_sha256 != row["bundle_root_sha256"]:
            raise ValueError(
                "valuation bundle root does not match trusted registry evidence: "
                + item.evaluation_id
            )
        valuations.append(
            (
                item,
                valuation,
                _mark_lag_microseconds(
                    valuation.as_of,
                    valuation.last_dataset_event_at,
                ),
            )
        )

    lags = {lag for _, _, lag in valuations}
    if len(lags) != 1:
        raise ValueError(
            f"candidate {candidate_id} contains mixed terminal-mark lags"
        )
    mark_lag = next(iter(lags))
    pnl_series = tuple(
        valuation.mark_to_market_pnl_usd for _, valuation, _ in valuations
    )
    slope = _pnl_slope_bps_per_window(pnl_series, initial_equity_usd)
    observations, ending_equity = _observations(
        valuations,
        initial_equity_usd,
    )
    return CandidateOOSStatistics(
        candidate_id=candidate_id,
        candidate_config_sha256=candidate_hash,
        expected_evaluation_count=len(planned),
        initial_equity_usd=initial_equity_usd,
        ending_equity_usd=ending_equity,
        total_mark_to_market_pnl_usd=sum(pnl_series, Decimal("0")),
        maximum_drawdown_pct=_maximum_drawdown_pct(
            pnl_series,
            initial_equity_usd,
        ),
        annualized_sharpe_ratio=_annualized_sharpe(
            pnl_series,
            initial_equity_usd,
            periods_per_year,
        ),
        oos_pnl_slope_bps_per_window=slope,
        alpha_decay_bps_per_window=(
            None if slope is None else max(Decimal("0"), -slope)
        ),
        mark_lag_microseconds=mark_lag,
        observations=observations,
    )


def _observations(
    valuations: list[tuple[MatrixEvaluation, BundleValuationReport, int]],
    initial_equity: Decimal,
) -> tuple[tuple[OOSValuationObservation, ...], Decimal]:
    result: list[OOSValuationObservation] = []
    equity = initial_equity
    for item, valuation, lag in valuations:
        period_return = (
            None
            if equity <= 0
            else float(valuation.mark_to_market_pnl_usd / equity)
        )
        equity += valuation.mark_to_market_pnl_usd
        result.append(
            OOSValuationObservation(
                evaluation_id=item.evaluation_id,
                experiment_id=valuation.experiment_id,
                valuation_id=valuation.valuation_id,
                candidate_id=item.candidate_id,
                candidate_config_sha256=item.candidate_config_sha256,
                window_index=item.window["index"],
                test_start=item.window["test_start"],
                test_end=item.window["test_end"],
                test_semantic_sha256=item.test_semantic_sha256,
                mark_lag_microseconds=lag,
                mark_to_market_pnl_usd=valuation.mark_to_market_pnl_usd,
                ending_equity_usd=equity,
                period_return=period_return,
            )
        )
    return tuple(result), equity


def _load_registry_rows(
    path: Path,
    matrix_sha256: str,
) -> dict[str, dict[str, Any]]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"trusted experiment registry does not exist: {resolved}")
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]) != "ok":
            raise RuntimeError("trusted experiment registry integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("trusted experiment registry foreign-key check failed")
        rows = connection.execute(
            """
            SELECT e.evaluation_id, e.experiment_id, e.matrix_sha256,
                   e.candidate_id, e.candidate_config_sha256,
                   e.test_semantic_sha256, e.train_semantic_sha256,
                   e.window_index, x.bundle_root_sha256, x.trusted
            FROM evaluations AS e
            JOIN experiments AS x USING (experiment_id)
            WHERE e.matrix_sha256 = ?
            ORDER BY e.candidate_id, e.window_index
            """,
            (matrix_sha256,),
        ).fetchall()
    finally:
        connection.close()

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        evaluation_id = str(row["evaluation_id"])
        if evaluation_id in result:
            raise RuntimeError(f"duplicate registry evaluation: {evaluation_id}")
        if not bool(row["trusted"]):
            raise PermissionError(
                f"OOS statistics require trusted evaluation evidence: {evaluation_id}"
            )
        result[evaluation_id] = {
            "experiment_id": str(row["experiment_id"]),
            "matrix_sha256": str(row["matrix_sha256"]),
            "candidate_id": str(row["candidate_id"]),
            "candidate_config_sha256": str(row["candidate_config_sha256"]),
            "test_semantic_sha256": str(row["test_semantic_sha256"]),
            "train_semantic_sha256": str(row["train_semantic_sha256"]),
            "window_index": int(row["window_index"]),
            "bundle_root_sha256": str(row["bundle_root_sha256"]),
        }
    return result


def _verify_registry_binding(
    matrix: ExperimentMatrixSnapshot,
    planned: MatrixEvaluation,
    row: Mapping[str, Any],
) -> None:
    expected: dict[str, Any] = {
        "matrix_sha256": matrix.semantic_sha256,
        "candidate_id": planned.candidate_id,
        "candidate_config_sha256": planned.candidate_config_sha256,
        "test_semantic_sha256": planned.test_semantic_sha256,
        "train_semantic_sha256": planned.train_semantic_sha256,
        "window_index": planned.window["index"],
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise ValueError(
                f"trusted registry {key} does not match matrix evaluation: "
                + planned.evaluation_id
            )


def _valuation_input_index(
    values: Sequence[EvaluationValuationInput],
) -> dict[str, EvaluationValuationInput]:
    result: dict[str, EvaluationValuationInput] = {}
    for item in values:
        if item.evaluation_id in result:
            raise ValueError(
                f"duplicate valuation input evaluation_id: {item.evaluation_id}"
            )
        result[item.evaluation_id] = item
    if not result:
        raise ValueError("valuation_inputs cannot be empty")
    return result


def _unique_non_empty(values: Sequence[str], name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or any(not value for value in result):
        raise ValueError(f"{name} must contain non-empty values")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} cannot contain duplicates")
    return tuple(sorted(result))


def _validate_statistics_parameters(
    initial_equity: Decimal,
    periods_per_year: int,
    code_revision: str,
) -> None:
    if not initial_equity.is_finite() or initial_equity <= 0:
        raise ValueError("initial_equity_usd must be positive and finite")
    if isinstance(periods_per_year, bool) or not 1 <= periods_per_year <= 1_000_000:
        raise ValueError("periods_per_year must be in [1, 1000000]")
    if not code_revision.strip():
        raise ValueError("code_revision cannot be empty")
    if len(code_revision.strip()) > 160:
        raise ValueError("code_revision is too long")


def _mark_lag_microseconds(as_of: str, last_event_at: str) -> int:
    delta = _timestamp(as_of) - _timestamp(last_event_at)
    result = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    if result < 0:
        raise ValueError("terminal mark lag cannot be negative")
    return result


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is None:
        raise ValueError("OOS timestamp must include a timezone")
    return timestamp


def _maximum_drawdown_pct(
    pnl_series: tuple[Decimal, ...],
    initial_equity: Decimal,
) -> float:
    equity = initial_equity
    peak = initial_equity
    maximum = Decimal("0")
    for pnl in pnl_series:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak)
    return float(maximum * Decimal("100"))


def _annualized_sharpe(
    pnl_series: tuple[Decimal, ...],
    initial_equity: Decimal,
    periods_per_year: int,
) -> float | None:
    equity = initial_equity
    returns: list[float] = []
    for pnl in pnl_series:
        if equity <= 0:
            return None
        returns.append(float(pnl / equity))
        equity += pnl
    if len(returns) < 2:
        return None
    deviation = pstdev(returns)
    if deviation == 0:
        return None
    return fmean(returns) / deviation * sqrt(periods_per_year)


def _pnl_slope_bps_per_window(
    pnl_series: tuple[Decimal, ...],
    initial_equity: Decimal,
) -> Decimal | None:
    if len(pnl_series) < 3:
        return None
    values = tuple(pnl / initial_equity * _BPS for pnl in pnl_series)
    x_mean = Decimal(len(values) - 1) / Decimal("2")
    y_mean = sum(values, Decimal("0")) / Decimal(len(values))
    numerator = Decimal("0")
    denominator = Decimal("0")
    for index, value in enumerate(values):
        x_delta = Decimal(index) - x_mean
        numerator += x_delta * (value - y_mean)
        denominator += x_delta * x_delta
    return None if denominator == 0 else numerator / denominator


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
