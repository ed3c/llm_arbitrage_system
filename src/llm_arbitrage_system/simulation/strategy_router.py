from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from llm_arbitrage_system.domain.contracts import (
    FeatureSnapshot,
    InstrumentKind,
    MarketEvent,
    OrderLeg,
    Side,
    SignalKind,
    TradePlan,
    Venue,
)

_BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class ResearchThresholds:
    """Deterministic thresholds for offline scenario generation."""

    scenario_notional_usd: Decimal = Decimal("100")
    estimated_round_trip_cost_bps: Decimal = Decimal("12")
    funding_entry_apy_pct: Decimal = Decimal("50")
    funding_holding_hours: Decimal = Decimal("24")
    crowd_entry_zscore: float = 2.5
    crowd_efficiency_ratio_maximum: float = 0.2
    crowd_requires_sentiment: bool = False
    lead_lag_entry_premium_bps: Decimal = Decimal("150")

    def __post_init__(self) -> None:
        if self.scenario_notional_usd <= 0:
            raise ValueError("scenario_notional_usd must be positive")
        if self.estimated_round_trip_cost_bps < 0:
            raise ValueError("estimated cost cannot be negative")
        if self.funding_entry_apy_pct <= 0 or self.funding_holding_hours <= 0:
            raise ValueError("funding thresholds must be positive")
        if self.crowd_entry_zscore <= 0:
            raise ValueError("crowd_entry_zscore must be positive")
        if not 0 <= self.crowd_efficiency_ratio_maximum <= 1:
            raise ValueError("crowd efficiency threshold must be in [0, 1]")
        if self.lead_lag_entry_premium_bps <= 0:
            raise ValueError("lead-lag threshold must be positive")


class PaperStrategyRouter:
    """Generate paper-only plans for the three PDF-derived research scenarios."""

    def __init__(self, thresholds: ResearchThresholds | None = None) -> None:
        self.thresholds = thresholds or ResearchThresholds()

    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan | None:
        for builder in (self._funding, self._crowding, self._lead_lag):
            result = builder(event, features)
            if result is not None:
                return result
        return None

    def _funding(
        self,
        event: MarketEvent,
        features: FeatureSnapshot,
    ) -> TradePlan | None:
        del features
        if event.instrument not in {InstrumentKind.PERP, InstrumentKind.RWA_PERP}:
            return None
        if event.funding_apy_pct < self.thresholds.funding_entry_apy_pct:
            return None
        hedge_symbol = event.metadata.get("paper_hedge_symbol")
        if not isinstance(hedge_symbol, str) or not hedge_symbol:
            return None
        hedge_price = Decimal(str(event.metadata.get("paper_hedge_price", event.price)))
        quantity = self.thresholds.scenario_notional_usd / event.price
        hedge_notional = quantity * hedge_price
        expected_funding_bps = (
            event.funding_rate_hourly
            * self.thresholds.funding_holding_hours
            * _BPS
        )
        return TradePlan(
            strategy=SignalKind.FUNDING_ARBITRAGE,
            symbol=event.symbol,
            legs=(
                OrderLeg(
                    venue=Venue.PAPER,
                    symbol=f"{event.symbol}:PERP",
                    instrument=event.instrument,
                    side=Side.SELL,
                    notional_usd=self.thresholds.scenario_notional_usd,
                    reference_price=event.price,
                    metadata={"paper_role": "carry"},
                ),
                OrderLeg(
                    venue=Venue.PAPER,
                    symbol=hedge_symbol,
                    instrument=InstrumentKind.SPOT,
                    side=Side.BUY,
                    notional_usd=hedge_notional,
                    reference_price=hedge_price,
                    metadata={"paper_role": "hedge"},
                ),
            ),
            expected_edge_bps=(
                expected_funding_bps
                - self.thresholds.estimated_round_trip_cost_bps
            ),
            confidence=min(
                1.0,
                float(event.funding_apy_pct / self.thresholds.funding_entry_apy_pct),
            ),
            reason="offline funding-carry scenario crossed its research threshold",
            created_at=event.timestamp,
            context={
                "simulation_only": True,
                "position_key": f"funding:{event.symbol}",
                "transition": "open",
            },
        )

    def _crowding(
        self,
        event: MarketEvent,
        features: FeatureSnapshot,
    ) -> TradePlan | None:
        if abs(features.zscore) < self.thresholds.crowd_entry_zscore:
            return None
        if (
            features.efficiency_ratio
            > self.thresholds.crowd_efficiency_ratio_maximum
        ):
            return None
        if self.thresholds.crowd_requires_sentiment:
            if event.sentiment_score is None:
                return None
            if features.zscore > 0 and event.sentiment_score <= 0:
                return None
            if features.zscore < 0 and event.sentiment_score >= 0:
                return None
        side = Side.SELL if features.zscore > 0 else Side.BUY
        return TradePlan(
            strategy=SignalKind.OVERCROWD_REVERSION,
            symbol=event.symbol,
            legs=(
                OrderLeg(
                    venue=Venue.PAPER,
                    symbol=event.symbol,
                    instrument=event.instrument,
                    side=side,
                    notional_usd=self.thresholds.scenario_notional_usd,
                    reference_price=event.price,
                    metadata={"paper_role": "reversion_probe"},
                ),
            ),
            expected_edge_bps=(
                Decimal(str(abs(features.zscore) * 10))
                - self.thresholds.estimated_round_trip_cost_bps
            ),
            confidence=min(1.0, abs(features.zscore) / 4.0),
            reason="offline crowding scenario combined extreme deviation with low efficiency",
            created_at=event.timestamp,
            context={
                "simulation_only": True,
                "position_key": f"crowding:{event.symbol}",
                "transition": "open",
            },
        )

    def _lead_lag(
        self,
        event: MarketEvent,
        features: FeatureSnapshot,
    ) -> TradePlan | None:
        del features
        if event.instrument is not InstrumentKind.RWA_PERP:
            return None
        if event.reference_market_open is not False or event.reference_price is None:
            return None
        premium_bps = (event.price - event.reference_price) / event.reference_price * _BPS
        if abs(premium_bps) < self.thresholds.lead_lag_entry_premium_bps:
            return None
        side = Side.SELL if premium_bps > 0 else Side.BUY
        return TradePlan(
            strategy=SignalKind.LEAD_LAG_RWA,
            symbol=event.symbol,
            legs=(
                OrderLeg(
                    venue=Venue.PAPER,
                    symbol=event.symbol,
                    instrument=event.instrument,
                    side=side,
                    notional_usd=self.thresholds.scenario_notional_usd,
                    reference_price=event.price,
                    metadata={"paper_role": "convergence_probe"},
                ),
            ),
            expected_edge_bps=(
                abs(premium_bps)
                - self.thresholds.estimated_round_trip_cost_bps
            ),
            confidence=min(
                1.0,
                float(abs(premium_bps) / Decimal("500")),
            ),
            reason="offline lead-lag scenario observed a closed-reference deviation",
            created_at=event.timestamp,
            context={
                "simulation_only": True,
                "position_key": f"lead-lag:{event.symbol}",
                "transition": "open",
                "premium_bps": str(premium_bps),
            },
        )
