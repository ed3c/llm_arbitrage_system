from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from llm_arbitrage_system.analytics.engine import AnalyticsEngine
from llm_arbitrage_system.config.runtime import AnalyticsParameters
from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionStatus,
    FeatureSnapshot,
    InstrumentKind,
    MarketEvent,
    OrderLeg,
    PortfolioSnapshot,
    RiskEvaluation,
    Side,
    SignalKind,
    StrategyDecision,
    TradePlan,
    Venue,
)
from llm_arbitrage_system.simulation.executor import DeterministicPaperExecutor
from llm_arbitrage_system.simulation.pipeline import PaperReplayPipeline


class FixedPlanner:
    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan | None:
        if features.observation_count != 20:
            return None
        return TradePlan(
            strategy=SignalKind.OVERCROWD_REVERSION,
            symbol=event.symbol,
            legs=(
                OrderLeg(
                    venue=Venue.PAPER,
                    symbol=event.symbol,
                    instrument=event.instrument,
                    side=Side.SELL,
                    notional_usd=Decimal("100"),
                    reference_price=event.price,
                ),
            ),
            expected_edge_bps=Decimal("10"),
            confidence=0.8,
            reason="deterministic test plan",
            created_at=event.timestamp,
            context={"simulation_only": True},
        )


class AcceptAll:
    def approve(self, decision: StrategyDecision) -> RiskEvaluation:
        return RiskEvaluation(
            approved=ApprovedTradePlan(
                plan=decision.plan,
                approved_at=decision.event.timestamp,
                risk_checks=("test-fixture",),
                portfolio=PortfolioSnapshot(
                    equity_usd=Decimal("10000"),
                    available_balance_usd=Decimal("10000"),
                ),
            ),
            reasons=(),
        )


def _analytics() -> AnalyticsEngine:
    return AnalyticsEngine(
        AnalyticsParameters(
            efficiency_period=10,
            kama_fast_period=2,
            kama_slow_period=30,
            zscore_window=20,
            kalman_process_variance=1e-5,
            kalman_measurement_variance=1e-2,
        )
    )


def _events(count: int = 25) -> tuple[MarketEvent, ...]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        MarketEvent(
            venue=Venue.PAPER,
            symbol="TEST",
            instrument=InstrumentKind.PERP,
            price=Decimal("100") + Decimal(index) / Decimal("10"),
            timestamp=start + timedelta(seconds=index),
        )
        for index in range(count)
    )


@pytest.mark.asyncio
async def test_pipeline_processes_one_deterministic_plan() -> None:
    pipeline = PaperReplayPipeline(
        _analytics(),
        FixedPlanner(),
        AcceptAll(),
        DeterministicPaperExecutor(),
    )

    report = await pipeline.run(_events())

    assert report.events_received == 25
    assert report.feature_snapshots == 6
    assert report.plans_created == 1
    assert report.plans_approved == 1
    assert report.plans_rejected == 0
    assert report.filled == 1
    assert report.compensated == 0
    assert report.failed == 0


@pytest.mark.asyncio
async def test_executor_reverses_partial_outcome() -> None:
    event = _events(20)[-1]
    plan = TradePlan(
        strategy=SignalKind.FUNDING_ARBITRAGE,
        symbol=event.symbol,
        legs=(
            OrderLeg(
                venue=Venue.PAPER,
                symbol="LEG-A",
                instrument=InstrumentKind.PERP,
                side=Side.SELL,
                notional_usd=Decimal("100"),
                reference_price=Decimal("100"),
            ),
            OrderLeg(
                venue=Venue.PAPER,
                symbol="LEG-B",
                instrument=InstrumentKind.SPOT,
                side=Side.BUY,
                notional_usd=Decimal("100"),
                reference_price=Decimal("100"),
            ),
        ),
        expected_edge_bps=Decimal("10"),
        confidence=1.0,
        reason="deterministic compensation test",
        created_at=event.timestamp,
    )
    approved = ApprovedTradePlan(
        plan=plan,
        approved_at=event.timestamp,
        risk_checks=("test-fixture",),
        portfolio=PortfolioSnapshot(
            equity_usd=Decimal("10000"),
            available_balance_usd=Decimal("10000"),
        ),
    )

    result = await DeterministicPaperExecutor(
        fail_leg_indexes=frozenset({1})
    ).execute(approved)

    assert result.status is ExecutionStatus.COMPENSATED
    assert len(result.fills) == 1
    assert len(result.compensated_fills) == 1
    assert result.compensated_fills[0].side is result.fills[0].side.opposite
