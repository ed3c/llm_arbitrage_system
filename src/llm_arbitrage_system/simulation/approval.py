from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    ExecutionStatus,
    PortfolioSnapshot,
    RiskEvaluation,
    StrategyDecision,
    TradePlan,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PaperApprovalLimits:
    """Offline approval limits with no account or venue integration."""

    maximum_event_age_seconds: float = 5.0
    minimum_edge_bps: Decimal = Decimal("1")
    maximum_leg_notional_usd: Decimal = Decimal("1000")
    maximum_gross_exposure_usd: Decimal = Decimal("10000")
    maximum_leg_imbalance_pct: Decimal = Decimal("0.02")
    maximum_slippage_bps: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        if self.maximum_event_age_seconds <= 0:
            raise ValueError("maximum event age must be positive")
        if self.minimum_edge_bps < 0 or self.maximum_slippage_bps < 0:
            raise ValueError("edge and slippage limits cannot be negative")
        if self.maximum_leg_notional_usd <= 0 or self.maximum_gross_exposure_usd <= 0:
            raise ValueError("notional limits must be positive")
        if not 0 <= self.maximum_leg_imbalance_pct < 1:
            raise ValueError("leg imbalance must be in [0, 1)")


class StatefulPaperApprover:
    """Reserve paper capacity before simulation and reconcile terminal results."""

    def __init__(
        self,
        limits: PaperApprovalLimits | None = None,
        *,
        replay_mode: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.limits = limits or PaperApprovalLimits()
        self.replay_mode = replay_mode
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._reservations: dict[str, tuple[str, Decimal]] = {}
        self._open_exposure: dict[str, Decimal] = {}
        self._halt_reason: str | None = None

    def approve(self, decision: StrategyDecision) -> RiskEvaluation:
        plan = decision.plan
        position_key = str(plan.context.get("position_key", plan.plan_id))
        now = decision.event.timestamp if self.replay_mode else self.clock()
        reasons: list[str] = []

        if self._halt_reason is not None:
            reasons.append(f"paper runtime halted: {self._halt_reason}")
        age = (now - decision.event.timestamp).total_seconds()
        if age > self.limits.maximum_event_age_seconds:
            reasons.append("market event is stale")
        if age < -1:
            reasons.append("market event timestamp is in the future")
        if plan.expected_edge_bps < self.limits.minimum_edge_bps:
            reasons.append("expected edge is below the paper threshold")
        if plan.max_leg_notional_usd > self.limits.maximum_leg_notional_usd:
            reasons.append("a leg exceeds the paper notional limit")
        if position_key in self._open_exposure:
            reasons.append("position key is already open")
        if any(key == position_key for key, _ in self._reservations.values()):
            reasons.append("position key already has a reservation")
        projected = self.gross_exposure_usd + plan.gross_notional_usd
        if projected > self.limits.maximum_gross_exposure_usd:
            reasons.append("paper gross-exposure budget would be exceeded")
        if self._quantity_imbalance(plan) > self.limits.maximum_leg_imbalance_pct:
            reasons.append("multi-leg quantity imbalance exceeds tolerance")
        if reasons:
            return RiskEvaluation(approved=None, reasons=tuple(reasons))

        approved_plan = plan.with_slippage_cap(self.limits.maximum_slippage_bps)
        snapshot = PortfolioSnapshot(
            equity_usd=self.limits.maximum_gross_exposure_usd,
            available_balance_usd=max(
                ZERO,
                self.limits.maximum_gross_exposure_usd - self.gross_exposure_usd,
            ),
            gross_exposure_usd=self.gross_exposure_usd,
            open_plan_count=len(self._open_exposure) + len(self._reservations),
        )
        approved = ApprovedTradePlan(
            plan=approved_plan,
            approved_at=now,
            risk_checks=(
                "freshness",
                "edge",
                "notional",
                "gross_exposure",
                "position_reservation",
                "leg_balance",
                "slippage_cap",
            ),
            portfolio=snapshot,
        )
        self._reservations[plan.plan_id] = (position_key, plan.gross_notional_usd)
        return RiskEvaluation(approved=approved, reasons=())

    def record_result(
        self,
        approved: ApprovedTradePlan,
        result: ExecutionResult,
    ) -> None:
        reservation = self._reservations.pop(approved.plan.plan_id, None)
        if reservation is None:
            return
        position_key, _ = reservation
        if result.status is ExecutionStatus.FILLED:
            self._open_exposure[position_key] = sum(
                (fill.notional_usd for fill in result.fills),
                ZERO,
            )
            return
        if result.status is ExecutionStatus.COMPENSATED:
            return
        residual = self._residual_notional(result)
        if residual > 0:
            self._open_exposure[f"residual:{approved.plan.plan_id}"] = residual
            self._halt_reason = (
                f"unreconciled simulated residual of {residual} USD"
            )

    def release_reservation(self, plan_id: str) -> None:
        self._reservations.pop(plan_id, None)

    def acknowledge_reconciliation(self) -> None:
        residual_keys = [
            key for key in self._open_exposure if key.startswith("residual:")
        ]
        for key in residual_keys:
            del self._open_exposure[key]
        self._halt_reason = None

    @staticmethod
    def _quantity_imbalance(plan: TradePlan) -> Decimal:
        if len(plan.legs) < 2:
            return ZERO
        quantities = [leg.quantity for leg in plan.legs]
        largest = max(quantities)
        if largest == 0:
            return ZERO
        return (largest - min(quantities)) / largest

    @staticmethod
    def _residual_notional(result: ExecutionResult) -> Decimal:
        net: dict[tuple[str, str], Decimal] = {}
        prices: dict[tuple[str, str], Decimal] = {}
        for fill in (*result.fills, *result.compensated_fills):
            key = (fill.venue.value, fill.symbol)
            signed = fill.quantity if fill.side.value == "buy" else -fill.quantity
            net[key] = net.get(key, ZERO) + signed
            prices[key] = fill.price
        return sum(
            (abs(quantity) * prices[key] for key, quantity in net.items()),
            ZERO,
        )

    @property
    def gross_exposure_usd(self) -> Decimal:
        return sum(self._open_exposure.values(), ZERO) + sum(
            reservation[1] for reservation in self._reservations.values()
        )

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason
