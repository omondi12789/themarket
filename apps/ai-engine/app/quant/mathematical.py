"""
Remaining mathematical toolkit: Monte Carlo simulation, Fourier/wavelet analysis,
entropy, and fractal dimension estimation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pywt
from scipy.fft import rfft, rfftfreq
from scipy.stats import entropy as scipy_entropy


def monte_carlo_gbm(
    initial_price: float,
    mu: float,
    sigma: float,
    horizon_days: int,
    n_simulations: int = 10_000,
    seed: int | None = None,
) -> np.ndarray:
    """
    Geometric Brownian Motion Monte Carlo price simulation. mu/sigma are daily
    drift/volatility (e.g. estimated from historical log returns). Returns an array
    of shape (n_simulations, horizon_days+1), each row a simulated price path.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0
    shocks = rng.normal(
        loc=(mu - 0.5 * sigma**2) * dt, scale=sigma * np.sqrt(dt), size=(n_simulations, horizon_days)
    )
    log_paths = np.cumsum(shocks, axis=1)
    paths = initial_price * np.exp(log_paths)
    return np.hstack([np.full((n_simulations, 1), initial_price), paths])


def monte_carlo_var(
    initial_price: float, mu: float, sigma: float, horizon_days: int, confidence: float = 0.95,
    n_simulations: int = 10_000, seed: int | None = None,
) -> float:
    """Monte-Carlo-estimated VaR (fractional loss) at the given horizon/confidence."""
    paths = monte_carlo_gbm(initial_price, mu, sigma, horizon_days, n_simulations, seed)
    terminal_returns = paths[:, -1] / initial_price - 1
    return float(-np.percentile(terminal_returns, (1 - confidence) * 100))


def strategy_bootstrap_robustness(
    trade_returns: pd.Series, n_resamples: int = 5000, seed: int | None = None
) -> dict:
    """
    Monte Carlo robustness test for a backtested strategy: bootstrap-resample the
    realized trade returns (with replacement) to build a distribution of possible
    equity curves, and report the spread of final-return / max-drawdown outcomes.
    This is the standard way to sanity-check whether a backtest's result depends on
    trade *ordering* rather than genuine edge.
    """
    rng = np.random.default_rng(seed)
    returns = trade_returns.dropna().values
    n = len(returns)
    final_returns = np.empty(n_resamples)
    max_drawdowns = np.empty(n_resamples)

    for i in range(n_resamples):
        sample = rng.choice(returns, size=n, replace=True)
        curve = np.cumprod(1 + sample)
        final_returns[i] = curve[-1] - 1
        running_max = np.maximum.accumulate(curve)
        max_drawdowns[i] = np.min((curve - running_max) / running_max)

    return {
        "final_return_p5": float(np.percentile(final_returns, 5)),
        "final_return_median": float(np.percentile(final_returns, 50)),
        "final_return_p95": float(np.percentile(final_returns, 95)),
        "max_drawdown_p5": float(np.percentile(max_drawdowns, 5)),
        "max_drawdown_median": float(np.percentile(max_drawdowns, 50)),
        "probability_of_loss": float(np.mean(final_returns < 0)),
    }


def dominant_cycle_fft(close: pd.Series, sample_spacing: float = 1.0) -> pd.DataFrame:
    """
    FFT-based dominant cycle detection on detrended price — surfaces periodic
    components (e.g. a recurring N-bar oscillation) that pure time-domain indicators
    can miss.
    """
    detrended = (close - close.rolling(20, min_periods=1).mean()).dropna().values
    n = len(detrended)
    yf = rfft(detrended)
    xf = rfftfreq(n, d=sample_spacing)
    power = np.abs(yf) ** 2

    with np.errstate(divide="ignore"):
        periods = np.where(xf > 0, 1 / xf, np.inf)

    df = pd.DataFrame({"frequency": xf, "period_bars": periods, "power": power})
    return df[df["frequency"] > 0].sort_values("power", ascending=False)


def wavelet_denoise(close: pd.Series, wavelet: str = "db4", level: int = 4) -> pd.Series:
    """
    Wavelet-based denoising: decompose into detail/approximation coefficients,
    soft-threshold the detail coefficients (removing high-frequency noise), and
    reconstruct. Preserves trend/structure better than a simple moving average.
    """
    values = close.values
    coeffs = pywt.wavedec(values, wavelet, level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745  # robust noise estimate (MAD)
    threshold = sigma * np.sqrt(2 * np.log(len(values)))
    denoised_coeffs = [coeffs[0]] + [pywt.threshold(c, threshold, mode="soft") for c in coeffs[1:]]
    reconstructed = pywt.waverec(denoised_coeffs, wavelet)[: len(values)]
    return pd.Series(reconstructed, index=close.index)


def shannon_entropy(returns: pd.Series, bins: int = 20) -> float:
    """Higher entropy = more unpredictable/random-walk-like returns distribution."""
    hist, _ = np.histogram(returns.dropna(), bins=bins, density=True)
    hist = hist[hist > 0]
    return float(scipy_entropy(hist))


def hurst_exponent(close: pd.Series, max_lag: int = 100) -> float:
    """
    Hurst exponent via rescaled-range-style variance scaling:
    H < 0.5 -> mean-reverting, H = 0.5 -> random walk, H > 0.5 -> trending/persistent.
    """
    prices = close.dropna().values
    lags = range(2, min(max_lag, len(prices) // 2))
    tau = [np.std(np.subtract(prices[lag:], prices[:-lag])) for lag in lags]
    tau = [t if t > 0 else 1e-10 for t in tau]
    poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(poly[0] * 2.0)
