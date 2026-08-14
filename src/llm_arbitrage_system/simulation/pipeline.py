from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass

from llm_arbitrage_system.analytics.engine import AnalyticsEngine
from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    ExecutionStatus,
    MarketEvent,
    StrategyDecision,
)
from llm_arbitrage_system.reporting.performance import (
    ResearchPerformanceReport,
    build_performance_report,
)
from llm_arbitrage_system.simulation.protocols import (
    Approver,
    PaperExecutor,
    Planner,
    ReplayJournal,
    ResultReconciler,
)

_SENTINEL = object()


@dataclass(frozen=True, slots=True)
class ReplayReport:
    events_received: int
    feature_snapshots: int
    plans_created: int
    plans_approved: int
    plans_rejected: int
    filled: int
    compensated: int
    failed: int

    def as_dict(self) -> dict[str, int]:
        return {
            "events_received": self.events_received,
            "feature_snapshots": self.feature_snapshots,
            "plans_created": self.plans_created,
            "plans_approved": self.plans_approved,
            "plans_rejected": self.plans_rejected,
            "filled": self.filled,
            "compensated": self.compensated,
            "failed": self.failed,
        }


class PaperReplayPipeline:
    """Bounded queue pipeline for deterministic, offline research replays."""

    def __init__(
        self,
        analytics: AnalyticsEngine,
        planner: Planner,
        approver: Approver,
        executor: PaperExecutor,
        *,
        queue_size: int = 128,
        journal: ReplayJournal | None = None,
    ) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.analytics = analytics
        self.planner = planner
        self.approver = approver
        self.executor = executor
        self.journal = journal
        self.data_queue: asyncio.Queue[MarketEvent | object] = asyncio.Queue(queue_size)
        self.decision_queue: asyncio.Queue[StrategyDecision | object] = asyncio.Queue(
            queue_size
        )
        self.approved_queue: asyncio.Queue[ApprovedTradePlan | object] = asyncio.Queue(
            queue_size
        )
        self._events_received = 0
        self._feature_snapshots = 0
        self._plans_created = 0
        self._plans_approved = 0
        self._plans_rejected = 0
        self._approved_plans: list[ApprovedTradePlan] = []
        self._results: list[ExecutionResult] = []
        self._performance_report: ResearchPerformanceReport | None = None
        self._started = False

    async def run(self, events: Iterable[MarketEvent]) -> ReplayReport:
        if self._started:
            raise RuntimeError("PaperReplayPipeline is single-use")
        self._started = True
        if self.journal is not None:
            await self.journal.start_run()

        tasks = [
            asyncio.create_task(self._produce(events), name="paper-replay-producer"),
            asyncio.create_task(self._analyze(), name="paper-replay-analytics"),
            asyncio.create_task(self._approve(), name="paper-replay-approval"),
            asyncio.create_task(self._execute(), name="paper-replay-execution"),
        ]
        try:
            await asyncio.gather(*tasks)
        except BaseException as error:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.journal is not None:
                await asyncio.shield(
                    self.journal.abort_run(f"{type(error).__name__}: {error}")
                )
            raise

        replay_report = self.report()
        self._performance_report = build_performance_report(
            self._approved_plans,
            self._results,
        )
        if self.journal is not None:
            await self.journal.complete_run(
                replay_report.as_dict(),
                self._performance_report.as_dict(),
            )
        return replay_report

    async def _produce(self, events: Iterable[MarketEvent]) -> None:
        for event in events:
            self._events_received += 1
            if self.journal is not None:
                await self.journal.record_market_event(event)
            await self.data_queue.put(event)
        await self.data_queue.put(_SENTINEL)

    async def _analyze(self) -> None:
        while True:
            item = await self.data_queue.get()
            try:
                if item is _SENTINEL:
                    await self.decision_queue.put(_SENTINEL)
                    return
                if not isinstance(item, MarketEvent):
                    raise TypeError("data queue contained an invalid item")
                features = self.analytics.process(item)
                if features is None:
                    continue
                self._feature_snapshots += 1
                plan = self.planner.plan(item, features)
                if plan is None:
                    continue
                decision = StrategyDecision(event=item, features=features, plan=plan)
                self._plans_created += 1
                if self.journal is not None:
                    await self.journal.record_decision(decision)
                await self.decision_queue.put(decision)
            finally:
                self.data_queue.task_done()

    async def _approve(self) -> None:
        while True:
            item = await self.decision_queue.get()
            try:
                if item is _SENTINEL:
                    await self.approved_queue.put(_SENTINEL)
                    return
                if not isinstance(item, StrategyDecision):
                    raise TypeError("decision queue contained an invalid item")
                evaluation = self.approver.approve(item)
                if self.journal is not None:
                    await self.journal.record_risk_evaluation(item, evaluation)
                if evaluation.approved is None:
                    self._plans_rejected += 1
                    continue
                self._plans_approved += 1
                self._approved_plans.append(evaluation.approved)
                await self.approved_queue.put(evaluation.approved)
            finally:
                self.decision_queue.task_done()

    async def _execute(self) -> None:
        while True:
            item = await self.approved_queue.get()
            try:
                if item is _SENTINEL:
                    return
                if not isinstance(item, ApprovedTradePlan):
                    raise TypeError("approval queue contained an invalid item")
                result = await self.executor.execute(item)
                self._results.append(result)
                if self.journal is not None:
                    await self.journal.record_execution_result(item, result)
                if isinstance(self.approver, ResultReconciler):
                    self.approver.record_result(item, result)
            finally:
                self.approved_queue.task_done()

    def report(self) -> ReplayReport:
        return ReplayReport(
            events_received=self._events_received,
            feature_snapshots=self._feature_snapshots,
            plans_created=self._plans_created,
            plans_approved=self._plans_approved,
            plans_rejected=self._plans_rejected,
            filled=sum(result.status is ExecutionStatus.FILLED for result in self._results),
            compensated=sum(
                result.status is ExecutionStatus.COMPENSATED for result in self._results
            ),
            failed=sum(
                result.status
                in {ExecutionStatus.FAILED, ExecutionStatus.PARTIALLY_FILLED}
                for result in self._results
            ),
        )

    @property
    def approved_plans(self) -> tuple[ApprovedTradePlan, ...]:
        return tuple(self._approved_plans)

    @property
    def results(self) -> tuple[ExecutionResult, ...]:
        return tuple(self._results)

    @property
    def performance_report(self) -> ResearchPerformanceReport | None:
        return self._performance_report
