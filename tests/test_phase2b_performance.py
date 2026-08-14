from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    InstrumentKind,
    OrderLeg,
    PortfolioSnapshot,
    Side,
    SignalKind,
    TradePlan,
    Venue,
)
from llm_arbitrage_system.reporting.performance import build_performance_report
from llm_arbitrage_system.simulation.executor import DeterministicPaperExecutor


def _approved(plan_id: str = "quality-plan") -> ApprovedTradePlan:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    plan = TradePlan(
        strategy=SignalKind.FUNDING_ARBITRAGE,
        symbol="PAIR",
        legs=(
            OrderLeg(
                venue=Venue.PAPER,
                symbol="PAIR-PERP",
                instrument=InstrumentKind.PERP,
                side=Side.SELL,
                notional_usd=Decimal("100"),
                reference_price=Decimal("100"),
                client_order_id=f"{plan_id}-perp",
            ),
            OrderLeg(
                venue=Venue.PAPER,
                symbol="PAIR-SPOT",
                instrument=InstrumentKind.SPOT,
                side=Side.BUY,
                notional_usd=Decimal("100"),
                reference_price=Decimal("100"),
                client_order_id=f"{plan_id}-spot",
            ),
        ),
        expected_edge_bps=Decimal("20"),
        confidence=0.9,
        reason="execution quality fixture",
        created_at=timestamp,
        plan_id=plan_id,
    )
    return ApprovedTradePlan(
        plan=plan,
        approved_at=timestamp,
        risk_checks=("fixture",),
        portfolio=PortfolioSnapshot(
            equity_usd=Decimal("1000"),
            available_balance_usd=Decimal("1000"),
        ),
    )


@pytest.mark.asyncio
async def test_report_separates_execution_quality_from_realized_pnl() -> None:
    approved = _approved()
    result = await DeterministicPaperExecutor(
        slippage_bps=Decimal("5"),
        fee_bps=Decimal("1"),
    ).execute(approved)

    report = build_performance_report((approved,), (result,))

    assert report.metrics.filled_plan_count == 1
    assert report.metrics.fill_count == 2
    assert report.metrics.gross_turnover_usd == Decimal("200")
    assert report.metrics.fees_usd == Decimal("0.02")
    assert report.metrics.average_expected_edge_bps == Decimal("20")
    assert report.metrics.average_execution_cost_bps == Decimal("6")
    assert report.metrics.average_edge_after_cost_bps == Decimal("14")
    assert report.metrics.maximum_drawdown_pct is None
    assert report.metrics.annualized_sharpe_ratio is None
    assert report.metrics.alpha_decay_bps is None
    assert any("not realized profit" in item for item in report.assumptions)


@pytest.mark.asyncio
async def test_report_handles_compensation_and_realized_pnl_series() -> None:
    approved = _approved("compensated")
    result = await DeterministicPaperExecutor(
        slippage_bps=Decimal("5"),
        fee_bps=Decimal("1"),
        fail_leg_indexes=frozenset({1}),
    ).execute(approved)

    report = build_performance_report(
        (approved,),
        (result,),
        realized_pnl_usd=(Decimal("10"), Decimal("-20"), Decimal("15")),
        initial_equity_usd=Decimal("1000"),
        periods_per_year=252,
    )

    assert report.metrics.compensated_plan_count == 1
    assert report.metrics.compensation_rate == 1.0
    assert report.metrics.average_execution_cost_bps == Decimal("1")
    assert report.metrics.maximum_drawdown_pct is not None
    assert report.metrics.maximum_drawdown_pct > 0
    assert report.metrics.annualized_sharpe_ratio is not None


def test_report_rejects_duplicate_plan_ids() -> None:
    approved = _approved("duplicate")

    with pytest.raises(ValueError, match="duplicate approved plan id"):
        build_performance_report((approved, approved), ())


def test_report_requires_equity_for_realized_pnl() -> None:
    with pytest.raises(ValueError, match="initial_equity_usd"):
        build_performance_report((), (), realized_pnl_usd=(Decimal("1"),))
