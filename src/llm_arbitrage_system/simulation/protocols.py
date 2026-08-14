from __future__ import annotations

from typing import Protocol

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


class PaperExecutor(Protocol):
    """Asynchronous simulator interface with no external connectivity."""

    async def execute(self, approved: ApprovedTradePlan) -> ExecutionResult: ...
