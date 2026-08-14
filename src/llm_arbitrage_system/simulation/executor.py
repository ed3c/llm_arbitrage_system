from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    ExecutionStatus,
    Fill,
    OrderLeg,
    Side,
)


class DeterministicPaperExecutor:
    """Produce reproducible simulated fills and reverse partial outcomes.

    No credentials, network endpoints, SDKs, or live-mode branches exist here.
    """

    def __init__(
        self,
        *,
        slippage_bps: Decimal = Decimal("5"),
        fee_bps: Decimal = Decimal("1"),
        fail_leg_indexes: frozenset[int] = frozenset(),
    ) -> None:
        if slippage_bps < 0 or fee_bps < 0:
            raise ValueError("simulation costs cannot be negative")
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.fail_leg_indexes = fail_leg_indexes

    async def execute(self, approved: ApprovedTradePlan) -> ExecutionResult:
        tasks = [
            asyncio.create_task(self._simulate_leg(index, leg))
            for index, leg in enumerate(approved.plan.legs)
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        fills = tuple(outcome for outcome in outcomes if isinstance(outcome, Fill))
        errors = tuple(
            outcome for outcome in outcomes if isinstance(outcome, Exception)
        )

        if not errors:
            return ExecutionResult(
                plan_id=approved.plan.plan_id,
                status=ExecutionStatus.FILLED,
                fills=fills,
            )
        if not fills:
            return ExecutionResult(
                plan_id=approved.plan.plan_id,
                status=ExecutionStatus.FAILED,
                error="; ".join(str(error) for error in errors),
            )

        reversed_fills = tuple(self._reverse(fill) for fill in fills)
        return ExecutionResult(
            plan_id=approved.plan.plan_id,
            status=ExecutionStatus.COMPENSATED,
            fills=fills,
            compensated_fills=reversed_fills,
            error="simulated partial outcome was reversed",
        )

    async def _simulate_leg(self, index: int, leg: OrderLeg) -> Fill:
        await asyncio.sleep(0)
        if index in self.fail_leg_indexes:
            raise RuntimeError(f"simulated failure for leg {index}")

        direction = Decimal("1") if leg.side is Side.BUY else Decimal("-1")
        price = leg.reference_price * (
            Decimal("1") + direction * self.slippage_bps / Decimal("10000")
        )
        quantity = leg.notional_usd / price
        return Fill(
            venue=leg.venue,
            symbol=leg.symbol,
            side=leg.side,
            quantity=quantity,
            price=price,
            status=ExecutionStatus.FILLED,
            order_id=f"paper-{uuid4().hex}",
            client_order_id=leg.client_order_id,
            fee_usd=leg.notional_usd * self.fee_bps / Decimal("10000"),
        )

    @staticmethod
    def _reverse(fill: Fill) -> Fill:
        return Fill(
            venue=fill.venue,
            symbol=fill.symbol,
            side=fill.side.opposite,
            quantity=fill.quantity,
            price=fill.price,
            status=ExecutionStatus.FILLED,
            order_id=f"paper-reverse-{uuid4().hex}",
            client_order_id=f"reverse-{fill.client_order_id}",
            fee_usd=fill.fee_usd,
        )
