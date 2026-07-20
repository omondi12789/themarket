"""
Cross-asset / statistical arbitrage tools: correlation matrix, PCA factor
decomposition, cointegration testing (for pairs selection), and z-score mean
reversion signals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from statsmodels.tsa.stattools import coint


def correlation_matrix(price_df: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """price_df: columns are symbols, rows are aligned timestamps."""
    returns = price_df.pct_change().dropna()
    return returns.corr(method=method)


def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 60) -> pd.Series:
    return series_a.pct_change().rolling(window).corr(series_b.pct_change())


class PCAFactorModel:
    """
    Decomposes a basket of FX return series into principal components — the first
    component in a G10 FX basket is typically a broad "dollar factor". Useful for
    factor-neutral position sizing and for spotting when a symbol's return is
    unexplained by common factors (a potential idiosyncratic trade signal).
    """

    def __init__(self, n_components: int = 3):
        self.n_components = n_components
        self.pca = PCA(n_components=n_components)
        self._symbols: list[str] = []
        self._fitted = False

    def fit(self, price_df: pd.DataFrame) -> "PCAFactorModel":
        self._symbols = list(price_df.columns)
        returns = price_df.pct_change().dropna()
        self.pca.fit(returns.values)
        self._fitted = True
        return self

    def explained_variance_ratio(self) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("call fit() first")
        return pd.Series(
            self.pca.explained_variance_ratio_,
            index=[f"PC{i+1}" for i in range(self.n_components)],
        )

    def loadings(self) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("call fit() first")
        return pd.DataFrame(
            self.pca.components_.T,
            index=self._symbols,
            columns=[f"PC{i+1}" for i in range(self.n_components)],
        )

    def transform(self, price_df: pd.DataFrame) -> pd.DataFrame:
        returns = price_df[self._symbols].pct_change().dropna()
        factors = self.pca.transform(returns.values)
        return pd.DataFrame(
            factors, index=returns.index, columns=[f"PC{i+1}" for i in range(self.n_components)]
        )


def engle_granger_cointegration(series_a: pd.Series, series_b: pd.Series) -> dict:
    """
    Engle-Granger two-step cointegration test (statsmodels.tsa.stattools.coint).
    p-value < 0.05 is the conventional threshold for "cointegrated enough to pairs-trade".
    """
    aligned = pd.concat([series_a, series_b], axis=1).dropna()
    score, pvalue, crit_values = coint(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return {
        "test_statistic": float(score),
        "p_value": float(pvalue),
        "critical_values": {"1%": crit_values[0], "5%": crit_values[1], "10%": crit_values[2]},
        "is_cointegrated_5pct": bool(pvalue < 0.05),
    }


def zscore_signal(spread: pd.Series, window: int = 30, entry_z: float = 2.0, exit_z: float = 0.5) -> pd.DataFrame:
    """
    Classic mean-reversion z-score signal on a (typically cointegrated pair's) spread:
    enter short when z > entry_z, enter long when z < -entry_z, exit when |z| < exit_z.
    """
    rolling_mean = spread.rolling(window).mean()
    rolling_std = spread.rolling(window).std(ddof=0)
    z = (spread - rolling_mean) / rolling_std.replace(0, np.nan)

    signal = pd.Series(0, index=spread.index, dtype=int)
    signal[z > entry_z] = -1  # spread too high -> expect reversion down -> short
    signal[z < -entry_z] = 1  # spread too low -> expect reversion up -> long
    signal[z.abs() < exit_z] = 0

    return pd.DataFrame({"zscore": z, "signal": signal})
