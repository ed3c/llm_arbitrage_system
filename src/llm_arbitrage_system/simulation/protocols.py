from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    FeatureSnapshot,
    MarketEvent,
    RiskEvaluation,
    StrategyDecision,
    TradePlan,
)


class Planner(Protocol):
    """Pure planning interface used by deterministic replays."""

    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan | None: ...


class Approver(Protocol):
    """Pure approval interface; implementations must not perform network I/O."""

    def approve(self, decision: StrategyDecision) -> RiskEvaluation: ...


@runtime_checkable
class ResultReconciler(Protocol):
    """Optional state reconciliation hook after a terminal paper result."""

    def record_result(
        self,
        approved: ApprovedTradePlan,
        result: ExecutionResult,
    ) -> None: ...


class PaperExecutor(Protocol):
    """Asynchronous simulator interface with no external connectivity."""

    async def execute(self, approved: ApprovedTradePlan) -> ExecutionResult: ...


class ReplayJournal(Protocol):
    """Durable local evidence sink used by the replay pipeline."""

    async def start_run(self) -> None: ...

    async def record_market_event(self, event: MarketEvent) -> None: ...

    async def record_decision(self, decision: StrategyDecision) -> None: ...

    async def record_risk_evaluation(
        self,
        decision: StrategyDecision,
        evaluation: RiskEvaluation,
    ) -> None: ...

    async def record_execution_result(
        self,
        approved: ApprovedTradePlan,
        result: ExecutionResult,
    ) -> None: ...

    async def complete_run(
        self,
        report: Mapping[str, int],
        performance_report: Mapping[str, Any] | None = None,
    ) -> None: ...

    async def abort_run(self, error: str) -> None: ...
