from __future__ import annotations

from decimal import Decimal
from math import sqrt
from statistics import fmean


def rolling_zscore(values: list[Decimal], window: int) -> float:
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(values) < window:
        raise ValueError("not enough values")
    sample = [float(value) for value in values[-window:]]
    mean = fmean(sample)
    variance = fmean((value - mean) ** 2 for value in sample)
    return 0.0 if variance == 0 else (sample[-1] - mean) / sqrt(variance)
