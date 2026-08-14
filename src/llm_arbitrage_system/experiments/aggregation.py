from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.evaluation import load_experiment_matrix
from llm_arbitrage_system.experiments.registry import ExperimentRegistry


def aggregate_registry_matrix(registry_path: Path, matrix_path: Path) -> dict[str, Any]:
    matrix = load_experiment_matrix(matrix_path)
    with ExperimentRegistry(registry_path) as registry:
        registered = registry.evaluation_rows(matrix.semantic_sha256)
    planned: dict[str, list[Any]] = defaultdict(list)
    for item in matrix.evaluations:
        planned[item.candidate_id].append(item)
    rows_by_id = {str(row["evaluation_id"]): row for row in registered}
    candidates: list[dict[str, Any]] = []
    for candidate_id in sorted(planned):
        expected = sorted(
            planned[candidate_id], key=lambda item: (item.window["index"], item.evaluation_id)
        )
        rows = [rows_by_id[item.evaluation_id] for item in expected if item.evaluation_id in rows_by_id]
        missing = [item.evaluation_id for item in expected if item.evaluation_id not in rows_by_id]
        coverage = "complete" if not missing else ("partial" if rows else "none")
        edges: list[Decimal] = []
        costs: list[Decimal] = []
        net_edges: list[Decimal] = []
        fill_rates: list[float] = []
        failure_rates: list[float] = []
        filled = compensated = failed = 0
        for row in rows:
            report = row["performance_report"]
            metrics = report.get("metrics") if isinstance(report, dict) else None
            if not isinstance(metrics, dict):
                continue
            _append_decimal(edges, metrics.get("average_expected_edge_bps"))
            _append_decimal(costs, metrics.get("average_execution_cost_bps"))
            _append_decimal(net_edges, metrics.get("average_edge_after_cost_bps"))
            _append_float(fill_rates, metrics.get("fill_success_rate"))
            _append_float(failure_rates, metrics.get("failure_rate"))
            filled += _integer(metrics.get("filled_plan_count"))
            compensated += _integer(metrics.get("compensated_plan_count"))
            failed += _integer(metrics.get("failed_plan_count")) + _integer(
                metrics.get("partially_filled_plan_count")
            )
        hashes = {item.candidate_config_sha256 for item in expected}
        if len(hashes) != 1:
            raise ValueError(f"candidate has inconsistent config hashes: {candidate_id}")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_config_sha256": next(iter(hashes)),
                "expected_evaluations": len(expected),
                "registered_evaluations": len(rows),
                "trusted_evaluations": sum(bool(row["trusted"]) for row in rows),
                "missing_evaluation_ids": missing,
                "coverage": coverage,
                "average_expected_edge_bps": _average_decimal(edges),
                "average_execution_cost_bps": _average_decimal(costs),
                "average_edge_after_cost_bps": _average_decimal(net_edges),
                "average_fill_success_rate": _average_float(fill_rates),
                "average_failure_rate": _average_float(failure_rates),
                "total_filled_plans": filled,
                "total_compensated_plans": compensated,
                "total_failed_plans": failed,
            }
        )
    return {
        "schema_version": 1,
        "matrix_sha256": matrix.semantic_sha256,
        "candidate_count": len(candidates),
        "complete_candidate_count": sum(item["coverage"] == "complete" for item in candidates),
        "partial_candidate_count": sum(item["coverage"] == "partial" for item in candidates),
        "missing_candidate_count": sum(item["coverage"] == "none" for item in candidates),
        "registered_evaluation_count": len(registered),
        "candidates": candidates,
        "selection": None,
        "realized_pnl": None,
        "sharpe_ratio": None,
        "alpha_decay": None,
        "evidence_boundary": (
            "This report aggregates registered test-window execution evidence. It does not "
            "select a winner, estimate realized PnL, or establish alpha decay."
        ),
    }


def _append_decimal(values: list[Decimal], value: Any) -> None:
    if value is None:
        return
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("performance metric is not a decimal") from error
    if not parsed.is_finite():
        raise ValueError("performance metric must be finite")
    values.append(parsed)


def _append_float(values: list[float], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("performance rate must be numeric")
    values.append(float(value))


def _integer(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("performance count must be an integer")
    return value


def _average_decimal(values: list[Decimal]) -> str | None:
    return None if not values else str(sum(values, Decimal("0")) / Decimal(len(values)))


def _average_float(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)
