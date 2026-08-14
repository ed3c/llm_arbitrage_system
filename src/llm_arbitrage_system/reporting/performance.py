from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from statistics import fmean, pstdev
from typing import Any

from llm_arbitrage_system.domain.contracts import (
    ZERO,
    ApprovedTradePlan,
    ExecutionResult,
    ExecutionStatus,
    Fill,
    Side,
)

_BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class ResearchPerformanceMetrics:
    approved_plan_count: int
    execution_result_count: int
    filled_plan_count: int
    compensated_plan_count: int
    failed_plan_count: int
    partially_filled_plan_count: int
    rejected_plan_count: int
    skipped_plan_count: int
    unmatched_result_count: int
    fill_count: int
    gross_turnover_usd: Decimal
    fees_usd: Decimal
    net_settlement_cash_flow_usd: Decimal
    fill_success_rate: float
    compensation_rate: float
    failure_rate: float
    average_expected_edge_bps: Decimal | None
    average_execution_cost_bps: Decimal | None
    maximum_execution_cost_bps: Decimal | None
    average_edge_after_cost_bps: Decimal | None
    maximum_drawdown_pct: float | None
    annualized_sharpe_ratio: float | None
    alpha_decay_bps: Decimal | None


@dataclass(frozen=True, slots=True)
class ResearchPerformanceReport:
    metrics: ResearchPerformanceMetrics
    assumptions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        values = {
            name: _json_value(getattr(self.metrics, name))
            for name in self.metrics.__dataclass_fields__
        }
        return {"metrics": values, "assumptions": list(self.assumptions)}


def build_performance_report(
    approved_plans: Iterable[ApprovedTradePlan],
    results: Iterable[ExecutionResult],
    *,
    realized_pnl_usd: Iterable[Decimal] = (),
    initial_equity_usd: Decimal | None = None,
    periods_per_year: int | None = None,
) -> ResearchPerformanceReport:
    approved = tuple(approved_plans)
    execution_results = tuple(results)
    pnl_series = tuple(realized_pnl_usd)
    approved_by_plan_id = _approved_plan_index(approved)

    gross_turnover = ZERO
    fees = ZERO
    net_cash_flow = ZERO
    fill_count = 0
    execution_costs: list[Decimal] = []
    edge_after_costs: list[Decimal] = []
    unmatched = 0

    for result in execution_results:
        all_fills = (*result.fills, *result.compensated_fills)
        for fill in all_fills:
            fill_count += 1
            gross_turnover += fill.notional_usd
            fees += fill.fee_usd
            net_cash_flow += _signed_cash_flow(fill) - fill.fee_usd

        approved_plan = approved_by_plan_id.get(result.plan_id)
        if approved_plan is None:
            unmatched += 1
            continue
        if all_fills:
            cost_bps = _execution_cost_bps(approved_plan, result)
            execution_costs.append(cost_bps)
            edge_after_costs.append(
                approved_plan.plan.expected_edge_bps - cost_bps
            )

    expected_edges = [item.plan.expected_edge_bps for item in approved]
    result_count = len(execution_results)
    failed_count = _status_count(execution_results, ExecutionStatus.FAILED)
    partial_count = _status_count(
        execution_results,
        ExecutionStatus.PARTIALLY_FILLED,
    )
    rejected_count = _status_count(execution_results, ExecutionStatus.REJECTED)
    skipped_count = _status_count(execution_results, ExecutionStatus.SKIPPED)
    failure_count = failed_count + partial_count + rejected_count

    assumptions: list[str] = [
        "Execution cost is a replay estimate derived from reference prices, simulated fills, and fees.",
        "Net settlement cash flow is not realized profit and must not be interpreted as strategy PnL.",
    ]
    maximum_drawdown: float | None = None
    sharpe_ratio: float | None = None
    if pnl_series:
        if initial_equity_usd is None or initial_equity_usd <= 0:
            raise ValueError("positive initial_equity_usd is required with realized PnL")
        maximum_drawdown = _maximum_drawdown_pct(pnl_series, initial_equity_usd)
        if periods_per_year is not None:
            if periods_per_year <= 0:
                raise ValueError("periods_per_year must be positive")
            sharpe_ratio = _annualized_sharpe(
                pnl_series,
                initial_equity_usd,
                periods_per_year,
            )
        else:
            assumptions.append(
                "Sharpe ratio is omitted because the replay did not define an observation frequency."
            )
    else:
        assumptions.append(
            "Drawdown and Sharpe ratio are omitted because realized mark-to-market PnL was not supplied."
        )
    assumptions.append(
        "Alpha decay is omitted because it requires repeated out-of-sample windows, not one replay."
    )

    metrics = ResearchPerformanceMetrics(
        approved_plan_count=len(approved),
        execution_result_count=result_count,
        filled_plan_count=_status_count(execution_results, ExecutionStatus.FILLED),
        compensated_plan_count=_status_count(
            execution_results,
            ExecutionStatus.COMPENSATED,
        ),
        failed_plan_count=failed_count,
        partially_filled_plan_count=partial_count,
        rejected_plan_count=rejected_count,
        skipped_plan_count=skipped_count,
        unmatched_result_count=unmatched,
        fill_count=fill_count,
        gross_turnover_usd=gross_turnover,
        fees_usd=fees,
        net_settlement_cash_flow_usd=net_cash_flow,
        fill_success_rate=_rate(
            _status_count(execution_results, ExecutionStatus.FILLED),
            result_count,
        ),
        compensation_rate=_rate(
            _status_count(execution_results, ExecutionStatus.COMPENSATED),
            result_count,
        ),
        failure_rate=_rate(failure_count, result_count),
        average_expected_edge_bps=_average_decimal(expected_edges),
        average_execution_cost_bps=_average_decimal(execution_costs),
        maximum_execution_cost_bps=max(execution_costs, default=None),
        average_edge_after_cost_bps=_average_decimal(edge_after_costs),
        maximum_drawdown_pct=maximum_drawdown,
        annualized_sharpe_ratio=sharpe_ratio,
        alpha_decay_bps=None,
    )
    return ResearchPerformanceReport(metrics=metrics, assumptions=tuple(assumptions))


def _approved_plan_index(
    approved_plans: tuple[ApprovedTradePlan, ...],
) -> dict[str, ApprovedTradePlan]:
    result: dict[str, ApprovedTradePlan] = {}
    for approved in approved_plans:
        plan_id = approved.plan.plan_id
        if plan_id in result:
            raise ValueError(f"duplicate approved plan id: {plan_id}")
        result[plan_id] = approved
    return result


def _execution_cost_bps(
    approved: ApprovedTradePlan,
    result: ExecutionResult,
) -> Decimal:
    plan = approved.plan
    legs = {leg.client_order_id: leg for leg in plan.legs}
    impact_usd = ZERO
    fees_usd = ZERO
    for fill in (*result.fills, *result.compensated_fills):
        fees_usd += fill.fee_usd
        client_order_id = fill.client_order_id.removeprefix("reverse-")
        leg = legs.get(client_order_id)
        if leg is None:
            continue
        price_move = (fill.price - leg.reference_price) / leg.reference_price
        if fill.side is Side.BUY:
            impact_usd += price_move * leg.notional_usd
        else:
            impact_usd -= price_move * leg.notional_usd
    return (impact_usd + fees_usd) / plan.gross_notional_usd * _BPS


def _signed_cash_flow(fill: Fill) -> Decimal:
    return fill.notional_usd if fill.side is Side.SELL else -fill.notional_usd


def _status_count(
    results: tuple[ExecutionResult, ...],
    status: ExecutionStatus,
) -> int:
    return sum(result.status is status for result in results)


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _average_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / Decimal(len(values))


def _maximum_drawdown_pct(
    pnl_series: tuple[Decimal, ...],
    initial_equity: Decimal,
) -> float:
    equity = initial_equity
    peak = initial_equity
    maximum = ZERO
    for pnl in pnl_series:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = (peak - equity) / peak
            maximum = max(maximum, drawdown)
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


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value
