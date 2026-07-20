"""
Technical indicators, implemented directly against pandas Series/DataFrame rather than
wrapping TA-Lib (which requires a compiled C library that's a pain in slim Docker
images). All formulas here are the standard textbook definitions.

Every function takes a DataFrame with at least columns: open, high, low, close, and
volume where relevant, indexed by timestamp (ascending).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing (the standard RSI definition), equivalent to an EMA with
    # alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_values = 100 - (100 / (1 + rs))

    rsi_values = rsi_values.where(~np.isnan(rsi_values), 100.0)
    return rsi_values.clip(0.0, 100.0)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    atr_smoothed = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr_smoothed
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr_smoothed

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx_line})


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP — resets per calendar day. df.index must be a tz-aware DatetimeIndex."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    day = df.index.normalize()
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {"upper": mid + num_std * std, "middle": mid, "lower": mid - num_std * std}
    )


def ichimoku(
    df: pd.DataFrame,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    displacement: int = 26,
) -> pd.DataFrame:
    high, low, close = df["high"], df["low"], df["close"]

    def _mid(period: int) -> pd.Series:
        return (high.rolling(period).max() + low.rolling(period).min()) / 2

    tenkan_sen = _mid(tenkan_period)
    kijun_sen = _mid(kijun_period)
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
    senkou_span_b = _mid(senkou_b_period).shift(displacement)
    chikou_span = close.shift(-displacement)

    return pd.DataFrame(
        {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_span_a": senkou_span_a,
            "senkou_span_b": senkou_span_b,
            "chikou_span": chikou_span,
        }
    )


def fibonacci_retracement(swing_high: float, swing_low: float) -> dict[str, float]:
    diff = swing_high - swing_low
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    return {f"{int(l * 1000) / 10}%": swing_high - diff * l for l in levels}


def fibonacci_extension(swing_high: float, swing_low: float, retracement_point: float) -> dict[str, float]:
    diff = swing_high - swing_low
    levels = [1.272, 1.414, 1.618, 2.0, 2.618]
    return {f"{l}": retracement_point + diff * l for l in levels}
