import numpy as np
import pandas as pd
import pytest

from app.indicators.technical import (
    atr,
    bollinger_bands,
    ema,
    fibonacci_retracement,
    macd,
    rsi,
    sma,
)


def test_sma_matches_manual_average():
    series = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(series, period=3)
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[3] == pytest.approx((2 + 3 + 4) / 3)
    assert pd.isna(result.iloc[0])


def test_ema_converges_toward_constant_series():
    series = pd.Series([5.0] * 30)
    result = ema(series, period=10)
    assert result.iloc[-1] == pytest.approx(5.0, abs=1e-6)


def test_rsi_is_100_for_strictly_increasing_series():
    series = pd.Series(np.arange(1, 30, dtype=float))
    result = rsi(series, period=14)
    assert result.iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_rsi_is_0_for_strictly_decreasing_series():
    series = pd.Series(np.arange(30, 1, -1, dtype=float))
    result = rsi(series, period=14)
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_is_bounded_0_to_100():
    rng = np.random.default_rng(0)
    series = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    result = rsi(series, period=14).dropna()
    assert (result >= 0).all() and (result <= 100).all()


def test_macd_histogram_equals_macd_minus_signal():
    series = pd.Series(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 100)))
    result = macd(series)
    diff = result["macd"] - result["signal"]
    pd.testing.assert_series_equal(result["histogram"], diff, check_names=False)


def test_atr_is_nonnegative():
    df = pd.DataFrame(
        {
            "high": [1.10, 1.12, 1.11, 1.13, 1.15] * 5,
            "low": [1.08, 1.09, 1.09, 1.10, 1.12] * 5,
            "close": [1.09, 1.11, 1.10, 1.12, 1.14] * 5,
        }
    )
    result = atr(df, period=14).dropna()
    assert (result >= 0).all()


def test_bollinger_bands_ordering():
    series = pd.Series(100 + np.cumsum(np.random.default_rng(2).normal(0, 1, 60)))
    bands = bollinger_bands(series, period=20, num_std=2.0).dropna()
    assert (bands["upper"] >= bands["middle"]).all()
    assert (bands["middle"] >= bands["lower"]).all()


def test_fibonacci_retracement_levels_are_between_high_and_low():
    levels = fibonacci_retracement(swing_high=1.2000, swing_low=1.1000)
    for price in levels.values():
        assert 1.0999 <= price <= 1.2001
    assert levels["0.0%"] == pytest.approx(1.2000)
    assert levels["100.0%"] == pytest.approx(1.1000)
