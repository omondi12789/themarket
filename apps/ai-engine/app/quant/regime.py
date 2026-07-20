"""
Market regime detection (Hidden Markov Model) and volatility forecasting (GARCH).

Both use well-established libraries rather than hand-rolled implementations, since
correctness/numerical stability here genuinely matters:
- hmmlearn for the HMM (Gaussian emissions on returns)
- arch for GARCH(1,1)-family volatility models
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM


class RegimeDetector:
    """
    Fits an n-state Gaussian HMM on return + realized-volatility features to label
    market regimes (e.g. trending-low-vol, trending-high-vol, mean-reverting/choppy).
    States are unlabeled by the model itself — `describe_states()` ranks them by mean
    return and volatility so callers can map state indices to human labels.
    """

    def __init__(self, n_states: int = 3, random_state: int = 42):
        self.n_states = n_states
        self.model = GaussianHMM(
            n_components=n_states, covariance_type="full", n_iter=1000, random_state=random_state
        )
        self._fitted = False

    @staticmethod
    def _build_features(close: pd.Series, vol_window: int = 10) -> pd.DataFrame:
        returns = close.pct_change()
        realized_vol = returns.rolling(vol_window).std()
        features = pd.DataFrame({"returns": returns, "volatility": realized_vol}).dropna()
        return features

    def fit(self, close: pd.Series) -> "RegimeDetector":
        features = self._build_features(close)
        self.model.fit(features.values)
        self._fitted = True
        return self

    def predict_states(self, close: pd.Series) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("call fit() before predict_states()")
        features = self._build_features(close)
        states = self.model.predict(features.values)
        return pd.Series(states, index=features.index, name="regime")

    def describe_states(self) -> pd.DataFrame:
        """Ranks each state by its fitted mean return and volatility for interpretation."""
        if not self._fitted:
            raise RuntimeError("call fit() before describe_states()")
        means = self.model.means_  # shape (n_states, 2) -> [return, volatility]
        return pd.DataFrame(
            means, columns=["mean_return", "mean_volatility"]
        ).sort_values("mean_return")


class GarchVolatilityForecaster:
    """
    GARCH(1,1) via the `arch` package — the standard baseline for forex volatility
    forecasting. Returns are expected in percent (e.g. 0.5 for +0.5%) since arch's
    optimizer is numerically better-behaved on that scale than raw fractional returns.
    """

    def __init__(self, p: int = 1, q: int = 1):
        self.p = p
        self.q = q
        self._fitted_result = None

    def fit(self, returns_pct: pd.Series):
        from arch import arch_model

        model = arch_model(returns_pct.dropna(), vol="Garch", p=self.p, q=self.q, dist="t")
        self._fitted_result = model.fit(disp="off")
        return self

    def forecast_volatility(self, horizon: int = 5) -> pd.Series:
        if self._fitted_result is None:
            raise RuntimeError("call fit() before forecast_volatility()")
        forecast = self._fitted_result.forecast(horizon=horizon, reindex=False)
        variances = forecast.variance.iloc[-1]
        return np.sqrt(variances)  # returns forecasted std dev (volatility), per-step

    def conditional_volatility(self) -> pd.Series:
        """In-sample fitted conditional volatility, useful for feature engineering."""
        if self._fitted_result is None:
            raise RuntimeError("call fit() before conditional_volatility()")
        return self._fitted_result.conditional_volatility
