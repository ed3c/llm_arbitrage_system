from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class AnalyticsParameters:
    efficiency_period: int = 10
    kama_fast_period: int = 2
    kama_slow_period: int = 30
    zscore_window: int = 20
    kalman_process_variance: float = 1e-5
    kalman_measurement_variance: float = 1e-2

    def __post_init__(self) -> None:
        if self.efficiency_period < 1 or self.zscore_window < 2:
            raise ValueError("analytics windows are too small")
        if not 1 <= self.kama_fast_period < self.kama_slow_period:
            raise ValueError("KAMA periods must satisfy 1 <= fast < slow")
        if self.kalman_process_variance <= 0 or self.kalman_measurement_variance <= 0:
            raise ValueError("Kalman variances must be positive")


def load_analytics_parameters(path: Path | None = None) -> AnalyticsParameters:
    if path is None or not path.exists():
        return AnalyticsParameters()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("configuration must contain a mapping")
    analytics = raw.get("analytics", raw)
    if not isinstance(analytics, dict):
        raise ValueError("analytics must be a mapping")
    return AnalyticsParameters(
        efficiency_period=int(analytics.get("efficiency_period", 10)),
        kama_fast_period=int(analytics.get("kama_fast_period", 2)),
        kama_slow_period=int(analytics.get("kama_slow_period", 30)),
        zscore_window=int(analytics.get("zscore_window", 20)),
        kalman_process_variance=float(analytics.get("kalman_process_variance", 1e-5)),
        kalman_measurement_variance=float(analytics.get("kalman_measurement_variance", 1e-2)),
    )
