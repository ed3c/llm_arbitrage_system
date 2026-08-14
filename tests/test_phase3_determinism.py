from __future__ import annotations

from datetime import datetime, timezone
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
from llm_arbitrage_system.experiments.determinism import ContentAddressedPlanner


class _Planner:
    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan:
        del features
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
                ),
            ),
            expected_edge_bps=Decimal("20"),
            confidence=0.75,
            reason="deterministic test",
            created_at=event.timestamp,
            context={"simulation_only": True},
        )


def _inputs() -> tuple[MarketEvent, FeatureSnapshot]:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = MarketEvent(
        venue=Venue.PAPER,
        symbol="BTC",
        instrument=InstrumentKind.PERP,
        price=Decimal("100"),
        timestamp=timestamp,
    )
    features = FeatureSnapshot(
        symbol="BTC",
        timestamp=timestamp,
        efficiency_ratio=0.1,
        kama=Decimal("99"),
        zscore=3.0,
        atr_pct=1.0,
        filtered_price=Decimal("100"),
        observation_count=20,
    )
    return event, features


def test_content_addressed_planner_replaces_random_defaults() -> None:
    event, features = _inputs()
    left = ContentAddressedPlanner(_Planner(), dataset_semantic_sha256="a" * 64)
    right = ContentAddressedPlanner(_Planner(), dataset_semantic_sha256="a" * 64)

    left_first = left.plan(event, features)
    right_first = right.plan(event, features)
    left_second = left.plan(event, features)
    right_second = right.plan(event, features)

    assert left_first is not None and right_first is not None
    assert left_second is not None and right_second is not None
    assert left_first.plan_id == right_first.plan_id
    assert left_first.legs[0].client_order_id == right_first.legs[0].client_order_id
    assert left_second.plan_id == right_second.plan_id
    assert left_first.plan_id != left_second.plan_id
    assert left_first.context["feature_sequence"] == 0
    assert left_second.context["feature_sequence"] == 1
