from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from llm_arbitrage_system.domain.contracts import (
    FeatureSnapshot,
    MarketEvent,
    OrderLeg,
    TradePlan,
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    normalized = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return normalized.replace("+00:00", "Z")


def canonical_jsonable(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return canonical_datetime(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            result[key] = canonical_jsonable(item)
        return result
    if isinstance(value, (tuple, list)):
        return [canonical_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical JSON values")
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    payload = canonical_jsonable(value)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def market_event_payload(event: MarketEvent) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "venue": event.venue.value,
        "symbol": event.symbol,
        "instrument": event.instrument.value,
        "price": canonical_decimal(event.price),
        "timestamp": canonical_datetime(event.timestamp),
        "bid": None if event.bid is None else canonical_decimal(event.bid),
        "ask": None if event.ask is None else canonical_decimal(event.ask),
        "high": None if event.high is None else canonical_decimal(event.high),
        "low": None if event.low is None else canonical_decimal(event.low),
        "volume_24h": canonical_decimal(event.volume_24h),
        "funding_rate_hourly": canonical_decimal(event.funding_rate_hourly),
        "sentiment_score": event.sentiment_score,
        "reference_price": (
            None
            if event.reference_price is None
            else canonical_decimal(event.reference_price)
        ),
        "reference_market_open": event.reference_market_open,
        "metadata": canonical_jsonable(event.metadata),
    }


def feature_payload(features: FeatureSnapshot) -> dict[str, Any]:
    return {
        "symbol": features.symbol,
        "timestamp": canonical_datetime(features.timestamp),
        "efficiency_ratio": format(features.efficiency_ratio, ".17g"),
        "kama": canonical_decimal(features.kama),
        "zscore": format(features.zscore, ".17g"),
        "atr_pct": format(features.atr_pct, ".17g"),
        "filtered_price": canonical_decimal(features.filtered_price),
        "observation_count": features.observation_count,
    }


def order_leg_semantic_payload(leg: OrderLeg) -> dict[str, Any]:
    return {
        "venue": leg.venue.value,
        "symbol": leg.symbol,
        "instrument": leg.instrument.value,
        "side": leg.side.value,
        "notional_usd": canonical_decimal(leg.notional_usd),
        "reference_price": canonical_decimal(leg.reference_price),
        "max_slippage_bps": canonical_decimal(leg.max_slippage_bps),
        "reduce_only": leg.reduce_only,
        "metadata": canonical_jsonable(leg.metadata),
    }


def trade_plan_semantic_payload(plan: TradePlan) -> dict[str, Any]:
    return {
        "strategy": plan.strategy.value,
        "symbol": plan.symbol,
        "legs": [order_leg_semantic_payload(leg) for leg in plan.legs],
        "expected_edge_bps": canonical_decimal(plan.expected_edge_bps),
        "confidence": format(plan.confidence, ".17g"),
        "reason": plan.reason,
        "created_at": canonical_datetime(plan.created_at),
        "context": canonical_jsonable(plan.context),
    }
