from __future__ import annotations

from decimal import Decimal


def average_true_range_pct(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    *,
    period: int,
) -> float:
    if period < 1 or len(closes) < period + 1:
        raise ValueError("not enough values for ATR")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high, low, and close series must align")
    start = len(closes) - period
    ranges: list[Decimal] = []
    for index in range(start, len(closes)):
        previous_close = closes[index - 1]
        ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - previous_close),
                abs(lows[index] - previous_close),
            )
        )
    atr = sum(ranges, Decimal("0")) / Decimal(period)
    return float(atr / closes[-1] * Decimal(100))
