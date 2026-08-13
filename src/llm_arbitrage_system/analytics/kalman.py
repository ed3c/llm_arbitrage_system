from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KalmanFilter1D:
    process_variance: float
    measurement_variance: float
    estimate: float | None = None
    error_estimate: float = 1.0

    def update(self, measurement: float) -> float:
        if self.process_variance <= 0 or self.measurement_variance <= 0:
            raise ValueError("Kalman variances must be positive")
        if self.estimate is None:
            self.estimate = measurement
            return measurement
        self.error_estimate += self.process_variance
        gain = self.error_estimate / (self.error_estimate + self.measurement_variance)
        self.estimate += gain * (measurement - self.estimate)
        self.error_estimate *= 1 - gain
        return self.estimate
