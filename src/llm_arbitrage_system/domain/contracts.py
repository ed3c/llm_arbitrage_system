from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

ZERO = Decimal("0")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Venue(str, Enum):
    PERP = "perp_venue"
    SPOT = "spot_venue"
    EQUITY = "equity_venue"
    PAPER = "paper"


class InstrumentKind(str, Enum):
    PERP = "perp"
    SPOT = "spot"
    EQUITY = "equity"
    RWA_PERP = "rwa_perp"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class SignalKind(str, Enum):
    FUNDING_ARBITRAGE = "funding_arbitrage"
    OVERCROWD_REVERSION = "overcrowd_reversion"
    LEAD_LAG_RWA = "lead_lag_rwa"


class ExecutionStatus(str, Enum):
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    FAILED = "failed"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class MarketEvent:
    venue: Venue
    symbol: str
    instrument: InstrumentKind
    price: Decimal
    timestamp: datetime = field(default_factory=utc_now)
    bid: Decimal | None = None
    ask: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume_24h: Decimal = ZERO
    funding_rate_hourly: Decimal = ZERO
    sentiment_score: float | None = None
    reference_price: Decimal | None = None
    reference_market_open: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.volume_24h < 0:
            raise ValueError("volume_24h cannot be negative")
        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive")
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask cannot be below bid")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high cannot be below low")
        if self.reference_price is not None and self.reference_price <= 0:
            raise ValueError("reference_price must be positive")
        if self.sentiment_score is not None and not -1 <= self.sentiment_score <= 1:
            raise ValueError("sentiment_score must be in [-1, 1]")

    @property
    def funding_apy_pct(self) -> Decimal:
        return self.funding_rate_hourly * Decimal(24 * 365 * 100)


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    symbol: str
    timestamp: datetime
    efficiency_ratio: float
    kama: Decimal
    zscore: float
    atr_pct: float
    filtered_price: Decimal
    observation_count: int


@dataclass(frozen=True, slots=True)
class OrderLeg:
    venue: Venue
    symbol: str
    instrument: InstrumentKind
    side: Side
    notional_usd: Decimal
    reference_price: Decimal
    max_slippage_bps: Decimal = Decimal("25")
    reduce_only: bool = False
    client_order_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.notional_usd <= 0:
            raise ValueError("notional_usd must be positive")
        if self.reference_price <= 0:
            raise ValueError("reference_price must be positive")
        if self.max_slippage_bps < 0:
            raise ValueError("max_slippage_bps cannot be negative")

    @property
    def quantity(self) -> Decimal:
        return self.notional_usd / self.reference_price

    def scaled(self, factor: Decimal) -> OrderLeg:
        if factor <= 0:
            raise ValueError("scale factor must be positive")
        return replace(self, notional_usd=self.notional_usd * factor)


@dataclass(frozen=True, slots=True)
class TradePlan:
    strategy: SignalKind
    symbol: str
    legs: tuple[OrderLeg, ...]
    expected_edge_bps: Decimal
    confidence: float
    reason: str
    created_at: datetime = field(default_factory=utc_now)
    plan_id: str = field(default_factory=lambda: uuid4().hex)
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.legs:
            raise ValueError("trade plan requires at least one leg")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    @property
    def gross_notional_usd(self) -> Decimal:
        return sum((leg.notional_usd for leg in self.legs), ZERO)

    @property
    def max_leg_notional_usd(self) -> Decimal:
        return max(leg.notional_usd for leg in self.legs)

    def scaled(self, factor: Decimal) -> TradePlan:
        return replace(self, legs=tuple(leg.scaled(factor) for leg in self.legs))

    def with_slippage_cap(self, cap_bps: Decimal) -> TradePlan:
        return replace(
            self,
            legs=tuple(
                replace(
                    leg,
                    max_slippage_bps=min(leg.max_slippage_bps, cap_bps),
                )
                for leg in self.legs
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    event: MarketEvent
    features: FeatureSnapshot
    plan: TradePlan


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    equity_usd: Decimal
    available_balance_usd: Decimal
    gross_exposure_usd: Decimal = ZERO
    daily_pnl_usd: Decimal = ZERO
    open_plan_count: int = 0


@dataclass(frozen=True, slots=True)
class ApprovedTradePlan:
    plan: TradePlan
    approved_at: datetime
    risk_checks: tuple[str, ...]
    portfolio: PortfolioSnapshot


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    approved: ApprovedTradePlan | None
    reasons: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.approved is not None


@dataclass(frozen=True, slots=True)
class Fill:
    venue: Venue
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    status: ExecutionStatus
    order_id: str
    client_order_id: str
    fee_usd: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative")
        if self.status in {ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED} and self.quantity <= 0:
            raise ValueError("filled quantity must be positive")
        if self.price <= 0:
            raise ValueError("fill price must be positive")
        if self.fee_usd < 0:
            raise ValueError("fee_usd cannot be negative")

    @property
    def notional_usd(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    plan_id: str
    status: ExecutionStatus
    fills: tuple[Fill, ...] = ()
    compensated_fills: tuple[Fill, ...] = ()
    error: str | None = None
