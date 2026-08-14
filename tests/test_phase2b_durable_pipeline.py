from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from llm_arbitrage_system.analytics.engine import AnalyticsEngine
from llm_arbitrage_system.config.runtime import AnalyticsParameters
from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
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
from llm_arbitrage_system.storage.sqlite_journal import SQLiteReplayJournal


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
                    client_order_id="fixed-leg",
                ),
            ),
            expected_edge_bps=Decimal("10"),
            confidence=0.8,
            reason="durable replay test",
            created_at=event.timestamp,
            plan_id="fixed-plan",
            context={"simulation_only": True},
        )


class AcceptAndReconcile:
    def __init__(self) -> None:
        self.result_count = 0

    def approve(self, decision: StrategyDecision) -> RiskEvaluation:
        return RiskEvaluation(
            approved=ApprovedTradePlan(
                plan=decision.plan,
                approved_at=decision.event.timestamp,
                risk_checks=("test",),
                portfolio=PortfolioSnapshot(
                    equity_usd=Decimal("10000"),
                    available_balance_usd=Decimal("10000"),
                ),
            ),
            reasons=(),
        )

    def record_result(self, approved: ApprovedTradePlan, result: object) -> None:
        del approved, result
        self.result_count += 1


class ExplodingPlanner:
    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan | None:
        del event, features
        raise RuntimeError("planned failure")


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
            metadata={"sequence": index},
        )
        for index in range(count)
    )


@pytest.mark.asyncio
async def test_pipeline_persists_complete_replay_evidence(tmp_path) -> None:
    journal_path = tmp_path / "replay.sqlite3"
    journal = SQLiteReplayJournal(journal_path, run_id="run-complete")
    approver = AcceptAndReconcile()
    pipeline = PaperReplayPipeline(
        _analytics(),
        FixedPlanner(),
        approver,
        DeterministicPaperExecutor(),
        queue_size=4,
        journal=journal,
    )

    report = await pipeline.run(_events())

    assert report.events_received == 25
    assert report.plans_created == 1
    assert report.plans_approved == 1
    assert report.filled == 1
    assert approver.result_count == 1
    assert pipeline.results[0].fills[0].order_id == "paper-fixed-plan-0"
    assert await journal.run_status() == "completed"
    assert await journal.load_report() == report.as_dict()
    performance = await journal.load_performance_report()
    assert performance is not None
    assert performance["metrics"]["filled_plan_count"] == 1
    assert len(await journal.load_market_event_payloads()) == 25
    assert await journal.integrity_check() == "ok"
    counts = await journal.counts()
    assert counts.market_events == 25
    assert counts.strategy_decisions == 1
    assert counts.risk_evaluations == 1
    assert counts.execution_results == 1
    assert counts.replay_runs == 1
    payloads = await journal.load_execution_payloads()
    assert payloads[0]["result"]["status"] == "filled"
    await journal.close()

    reopened = SQLiteReplayJournal(journal_path, run_id="run-complete")
    assert await reopened.run_status() == "completed"
    assert (await reopened.counts()).execution_results == 1
    await reopened.close()


@pytest.mark.asyncio
async def test_pipeline_marks_journal_aborted_when_a_stage_fails(tmp_path) -> None:
    journal = SQLiteReplayJournal(tmp_path / "failed.sqlite3", run_id="run-failed")
    pipeline = PaperReplayPipeline(
        _analytics(),
        ExplodingPlanner(),
        AcceptAndReconcile(),
        DeterministicPaperExecutor(),
        journal=journal,
    )

    with pytest.raises(RuntimeError, match="planned failure"):
        await pipeline.run(_events(20))

    assert await journal.run_status() == "aborted"
    assert (await journal.counts()).market_events == 20
    await journal.close()


@pytest.mark.asyncio
async def test_executor_identifiers_are_reproducible() -> None:
    event = _events(20)[-1]
    plan = FixedPlanner().plan(
        event,
        FeatureSnapshot(
            symbol=event.symbol,
            timestamp=event.timestamp,
            efficiency_ratio=0.1,
            kama=event.price,
            zscore=3.0,
            atr_pct=1.0,
            filtered_price=event.price,
            observation_count=20,
        ),
    )
    assert plan is not None
    approved = ApprovedTradePlan(
        plan=plan,
        approved_at=event.timestamp,
        risk_checks=("test",),
        portfolio=PortfolioSnapshot(
            equity_usd=Decimal("10000"),
            available_balance_usd=Decimal("10000"),
        ),
    )
    executor = DeterministicPaperExecutor()

    first = await executor.execute(approved)
    second = await executor.execute(approved)

    assert first.fills[0].order_id == second.fills[0].order_id
    assert first.fills[0].quantity == second.fills[0].quantity


@pytest.mark.asyncio
async def test_pipeline_is_explicitly_single_use(tmp_path) -> None:
    journal = SQLiteReplayJournal(tmp_path / "single.sqlite3", run_id="single")
    pipeline = PaperReplayPipeline(
        _analytics(),
        FixedPlanner(),
        AcceptAndReconcile(),
        DeterministicPaperExecutor(),
        journal=journal,
    )
    await pipeline.run(_events())

    with pytest.raises(RuntimeError, match="single-use"):
        await pipeline.run(_events())

    await journal.close()
