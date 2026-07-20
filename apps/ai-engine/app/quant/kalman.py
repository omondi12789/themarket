"""
Kalman filter implementations.

Two concrete uses in a forex quant stack:
1. `KalmanTrendFilter` — smooths a noisy price series into a denoised level + trend
   estimate, adaptively (unlike a fixed-window moving average).
2. `KalmanHedgeRatio` — tracks a time-varying hedge ratio between two correlated pairs
   (e.g. EURUSD vs GBPUSD) for statistical arbitrage / pairs trading, updating the
   ratio bar-by-bar instead of a rolling OLS regression recomputed from scratch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class KalmanTrendFilter:
    """
    A local linear trend model: state = [level, trend], observation = level + noise.
    Standard 2D Kalman filter, tuned via process/observation noise variances.
    """

    def __init__(self, process_variance: float = 1e-5, observation_variance: float = 1e-2):
        self.process_variance = process_variance
        self.observation_variance = observation_variance

        # State: [level, trend]
        self.state = np.array([0.0, 0.0])
        self.covariance = np.eye(2)
        self._initialized = False

        self.transition = np.array([[1.0, 1.0], [0.0, 1.0]])  # level += trend
        self.observation_matrix = np.array([[1.0, 0.0]])  # we observe level only
        self.process_noise = np.eye(2) * process_variance
        self.observation_noise = np.array([[observation_variance]])

    def update(self, observation: float) -> tuple[float, float]:
        if not self._initialized:
            self.state = np.array([observation, 0.0])
            self._initialized = True
            return self.state[0], self.state[1]

        # Predict
        predicted_state = self.transition @ self.state
        predicted_cov = self.transition @ self.covariance @ self.transition.T + self.process_noise

        # Update
        innovation = observation - (self.observation_matrix @ predicted_state)[0]
        innovation_cov = (
            self.observation_matrix @ predicted_cov @ self.observation_matrix.T + self.observation_noise
        )[0, 0]
        kalman_gain = (predicted_cov @ self.observation_matrix.T).flatten() / innovation_cov

        self.state = predicted_state + kalman_gain * innovation
        self.covariance = predicted_cov - np.outer(kalman_gain, self.observation_matrix @ predicted_cov)

        return float(self.state[0]), float(self.state[1])

    def filter_series(self, series: pd.Series) -> pd.DataFrame:
        levels, trends = [], []
        for value in series:
            level, trend = self.update(float(value))
            levels.append(level)
            trends.append(trend)
        return pd.DataFrame({"level": levels, "trend": trends}, index=series.index)


class KalmanHedgeRatio:
    """
    Tracks beta_t in: y_t = beta_t * x_t + intercept_t + noise, where beta evolves as
    a random walk. This is the standard Kalman-filter approach to dynamic pairs-trading
    hedge ratios (see Ernest Chan's "Algorithmic Trading" for the reference formulation).
    """

    def __init__(self, delta: float = 1e-4, observation_variance: float = 1e-3):
        # delta controls how fast beta/intercept are allowed to drift.
        self.delta = delta
        self.observation_variance = observation_variance
        self.state = np.array([0.0, 0.0])  # [beta, intercept]
        self.covariance = np.eye(2)
        self.process_noise = np.eye(2) * (delta / (1 - delta))
        self._initialized = False

    def update(self, y: float, x: float) -> tuple[float, float]:
        obs_matrix = np.array([[x, 1.0]])

        if not self._initialized:
            self.state = np.array([0.0, y])
            self._initialized = True
            return float(self.state[0]), float(self.state[1])

        predicted_state = self.state
        predicted_cov = self.covariance + self.process_noise

        innovation = y - (obs_matrix @ predicted_state)[0]
        innovation_cov = (obs_matrix @ predicted_cov @ obs_matrix.T)[0, 0] + self.observation_variance
        kalman_gain = (predicted_cov @ obs_matrix.T).flatten() / innovation_cov

        self.state = predicted_state + kalman_gain * innovation
        self.covariance = predicted_cov - np.outer(kalman_gain, obs_matrix @ predicted_cov)

        return float(self.state[0]), float(self.state[1])

    def track_pair(self, y_series: pd.Series, x_series: pd.Series) -> pd.DataFrame:
        betas, intercepts, spreads = [], [], []
        for y, x in zip(y_series, x_series):
            beta, intercept = self.update(float(y), float(x))
            betas.append(beta)
            intercepts.append(intercept)
            spreads.append(y - (beta * x + intercept))
        return pd.DataFrame(
            {"beta": betas, "intercept": intercepts, "spread": spreads}, index=y_series.index
        )
