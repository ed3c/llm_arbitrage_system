from __future__ import annotations

from decimal import Decimal
from itertools import pairwise


def kaufman_efficiency_ratio(prices: list[Decimal], period: int) -> float:
    if period < 1:
        raise ValueError("period must be positive")
    if len(prices) < period + 1:
        raise ValueError("not enough prices")
    window = prices[-(period + 1) :]
    change = abs(window[-1] - window[0])
    noise = sum(abs(current - previous) for previous, current in pairwise(window))
    return 0.0 if noise == 0 else float(change / noise)


def kaufman_adaptive_moving_average(
    prices: list[Decimal],
    *,
    efficiency_period: int,
    fast_period: int,
    slow_period: int,
) -> list[Decimal]:
    if not prices:
        return []
    if efficiency_period < 1 or not 1 <= fast_period < slow_period:
        raise ValueError("invalid KAMA periods")

    fast = Decimal(2) / Decimal(fast_period + 1)
    slow = Decimal(2) / Decimal(slow_period + 1)
    result = [prices[0]]
    for index in range(1, len(prices)):
        if index < efficiency_period:
            result.append(prices[index])
            continue
        window = prices[index - efficiency_period : index + 1]
        change = abs(window[-1] - window[0])
        noise = sum(abs(current - previous) for previous, current in pairwise(window))
        efficiency = Decimal("0") if noise == 0 else change / noise
        smoothing = (efficiency * (fast - slow) + slow) ** 2
        result.append(result[-1] + smoothing * (prices[index] - result[-1]))
    return result
