from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from llm_arbitrage_system.analytics.kalman import KalmanFilter1D
from llm_arbitrage_system.analytics.kaufman import (
    kaufman_adaptive_moving_average,
    kaufman_efficiency_ratio,
)
from llm_arbitrage_system.analytics.volatility import average_true_range_pct
from llm_arbitrage_system.analytics.zscore import rolling_zscore
from llm_arbitrage_system.config.runtime import AnalyticsParameters
from llm_arbitrage_system.domain.contracts import FeatureSnapshot, MarketEvent


@dataclass(slots=True)
class _SeriesState:
    prices: deque[Decimal]
    highs: deque[Decimal]
    lows: deque[Decimal]
    kalman: KalmanFilter1D


class AnalyticsEngine:
    def __init__(self, parameters: AnalyticsParameters) -> None:
        self.parameters = parameters
        minimum = max(parameters.efficiency_period + 1, parameters.zscore_window)
        self._capacity = max(128, minimum * 4)
        self._states: dict[str, _SeriesState] = {}

    def _state(self, event: MarketEvent) -> _SeriesState:
        key = f"{event.venue.value}:{event.symbol}"
        state = self._states.get(key)
        if state is None:
            state = _SeriesState(
                prices=deque(maxlen=self._capacity),
                highs=deque(maxlen=self._capacity),
                lows=deque(maxlen=self._capacity),
                kalman=KalmanFilter1D(
                    self.parameters.kalman_process_variance,
                    self.parameters.kalman_measurement_variance,
                ),
            )
            self._states[key] = state
        return state

    def process(self, event: MarketEvent) -> FeatureSnapshot | None:
        state = self._state(event)
        state.prices.append(event.price)
        state.highs.append(event.high if event.high is not None else event.price)
        state.lows.append(event.low if event.low is not None else event.price)
        filtered = state.kalman.update(float(event.price))

        required = max(self.parameters.efficiency_period + 1, self.parameters.zscore_window)
        if len(state.prices) < required:
            return None

        prices = list(state.prices)
        kama = kaufman_adaptive_moving_average(
            prices,
            efficiency_period=self.parameters.efficiency_period,
            fast_period=self.parameters.kama_fast_period,
            slow_period=self.parameters.kama_slow_period,
        )[-1]
        atr_period = min(14, len(prices) - 1)
        return FeatureSnapshot(
            symbol=event.symbol,
            timestamp=event.timestamp,
            efficiency_ratio=kaufman_efficiency_ratio(prices, self.parameters.efficiency_period),
            kama=kama,
            zscore=rolling_zscore(prices, self.parameters.zscore_window),
            atr_pct=average_true_range_pct(
                list(state.highs), list(state.lows), prices, period=atr_period
            ),
            filtered_price=Decimal(str(filtered)),
            observation_count=len(prices),
        )
