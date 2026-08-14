from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from llm_arbitrage_system.domain.contracts import (
    ExecutionStatus,
    FeatureSnapshot,
    InstrumentKind,
    MarketEvent,
    SignalKind,
    StrategyDecision,
    Venue,
)
from llm_arbitrage_system.simulation.approval import (
    PaperApprovalLimits,
    StatefulPaperApprover,
)
from llm_arbitrage_system.simulation.executor import DeterministicPaperExecutor
from llm_arbitrage_system.simulation.strategy_router import PaperStrategyRouter


def _features(*, zscore: float = 0.0, efficiency_ratio: float = 0.1) -> FeatureSnapshot:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return FeatureSnapshot(
        symbol="TEST",
        timestamp=now,
        efficiency_ratio=efficiency_ratio,
        kama=Decimal("100"),
        zscore=zscore,
        atr_pct=1.0,
        filtered_price=Decimal("100"),
        observation_count=25,
    )


def test_router_builds_quantity_balanced_funding_plan() -> None:
    event = MarketEvent(
        venue=Venue.PAPER,
        symbol="BTC",
        instrument=InstrumentKind.PERP,
        price=Decimal("100"),
        funding_rate_hourly=Decimal("0.00008"),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={
            "paper_hedge_symbol": "BTC-SPOT",
            "paper_hedge_price": "101",
        },
    )

    plan = PaperStrategyRouter().plan(event, _features())

    assert plan is not None
    assert plan.strategy is SignalKind.FUNDING_ARBITRAGE
    assert len(plan.legs) == 2
    assert plan.legs[0].quantity == plan.legs[1].quantity
    assert plan.context["simulation_only"] is True


def test_router_builds_crowding_and_lead_lag_plans() -> None:
    crowd_event = MarketEvent(
        venue=Venue.PAPER,
        symbol="CROWD",
        instrument=InstrumentKind.PERP,
        price=Decimal("100"),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    crowd_plan = PaperStrategyRouter().plan(
        crowd_event,
        _features(zscore=3.0, efficiency_ratio=0.1),
    )
    assert crowd_plan is not None
    assert crowd_plan.strategy is SignalKind.OVERCROWD_REVERSION

    lead_lag_event = MarketEvent(
        venue=Venue.PAPER,
        symbol="RWA",
        instrument=InstrumentKind.RWA_PERP,
        price=Decimal("103"),
        reference_price=Decimal("100"),
        reference_market_open=False,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    lead_lag_plan = PaperStrategyRouter().plan(lead_lag_event, _features())
    assert lead_lag_plan is not None
    assert lead_lag_plan.strategy is SignalKind.LEAD_LAG_RWA


def test_approver_reserves_and_reconciles_filled_plan() -> None:
    event = MarketEvent(
        venue=Venue.PAPER,
        symbol="BTC",
        instrument=InstrumentKind.PERP,
        price=Decimal("100"),
        funding_rate_hourly=Decimal("0.00008"),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={"paper_hedge_symbol": "BTC-SPOT"},
    )
    features = _features()
    plan = PaperStrategyRouter().plan(event, features)
    assert plan is not None
    decision = StrategyDecision(event=event, features=features, plan=plan)
    approver = StatefulPaperApprover()

    evaluation = approver.approve(decision)

    assert evaluation.accepted
    assert evaluation.approved is not None
    assert approver.gross_exposure_usd == plan.gross_notional_usd

    result = asyncio.run(
        DeterministicPaperExecutor().execute(evaluation.approved)
    )
    assert result.status is ExecutionStatus.FILLED
    approver.record_result(evaluation.approved, result)
    assert approver.gross_exposure_usd == Decimal("200")

    duplicate = approver.approve(decision)
    assert not duplicate.accepted
    assert "position key is already open" in duplicate.reasons


def test_approver_rejects_stale_event_outside_replay_mode() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = MarketEvent(
        venue=Venue.PAPER,
        symbol="STALE",
        instrument=InstrumentKind.PERP,
        price=Decimal("100"),
        timestamp=now - timedelta(seconds=30),
    )
    features = _features(zscore=3.0)
    plan = PaperStrategyRouter().plan(event, features)
    assert plan is not None
    decision = StrategyDecision(event=event, features=features, plan=plan)
    approver = StatefulPaperApprover(
        PaperApprovalLimits(maximum_event_age_seconds=5),
        replay_mode=False,
        clock=lambda: now,
    )

    evaluation = approver.approve(decision)

    assert not evaluation.accepted
    assert "market event is stale" in evaluation.reasons
