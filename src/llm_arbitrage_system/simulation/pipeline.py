from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from llm_arbitrage_system.analytics.engine import AnalyticsEngine
from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    ExecutionStatus,
    MarketEvent,
    StrategyDecision,
)
from llm_arbitrage_system.simulation.protocols import Approver, PaperExecutor, Planner

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
    ) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.analytics = analytics
        self.planner = planner
        self.approver = approver
        self.executor = executor
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
        self._results: list[ExecutionResult] = []

    async def run(self, events: Iterable[MarketEvent]) -> ReplayReport:
        tasks = (
            asyncio.create_task(self._produce(events)),
            asyncio.create_task(self._analyze()),
            asyncio.create_task(self._approve()),
            asyncio.create_task(self._execute()),
        )
        await asyncio.gather(*tasks)
        return self.report()

    async def _produce(self, events: Iterable[MarketEvent]) -> None:
        for event in events:
            self._events_received += 1
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
                self._plans_created += 1
                await self.decision_queue.put(
                    StrategyDecision(event=item, features=features, plan=plan)
                )
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
                if evaluation.approved is None:
                    self._plans_rejected += 1
                    continue
                self._plans_approved += 1
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
                self._results.append(await self.executor.execute(item))
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
            failed=sum(result.status is ExecutionStatus.FAILED for result in self._results),
        )
