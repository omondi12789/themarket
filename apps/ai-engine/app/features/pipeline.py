"""
Feature engineering pipeline: turns raw OHLCV bars into the feature matrix consumed
by forecasting models and the AI decision system. Combines technical indicators,
statistical/regime features, and price-action structure into one aligned DataFrame.
"""
from __future__ import annotations

import pandas as pd

from app.indicators.technical import adx, atr, bollinger_bands, ema, macd, rsi, sma
from app.quant.mathematical import hurst_exponent, shannon_entropy
from app.quant.regime import RegimeDetector


def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    features = pd.DataFrame(index=df.index)

    features["sma_20"] = sma(close, 20)
    features["sma_50"] = sma(close, 50)
    features["ema_12"] = ema(close, 12)
    features["ema_26"] = ema(close, 26)
    features["price_vs_sma20"] = close / features["sma_20"] - 1
    features["price_vs_sma50"] = close / features["sma_50"] - 1

    features["rsi_14"] = rsi(close, 14)

    macd_df = macd(close)
    features["macd"] = macd_df["macd"]
    features["macd_signal"] = macd_df["signal"]
    features["macd_histogram"] = macd_df["histogram"]

    features["atr_14"] = atr(df, 14)
    features["atr_pct"] = features["atr_14"] / close

    adx_df = adx(df, 14)
    features["adx"] = adx_df["adx"]
    features["di_diff"] = adx_df["plus_di"] - adx_df["minus_di"]

    bb = bollinger_bands(close, 20, 2.0)
    features["bb_width"] = (bb["upper"] - bb["lower"]) / bb["middle"]
    features["bb_position"] = (close - bb["lower"]) / (bb["upper"] - bb["lower"])

    return features


def build_price_action_features(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """
    Structural price-action features: recent swing high/low distance, higher-highs /
    lower-lows counts, and simple support/resistance proximity. These are cheap
    proxies for order-block/liquidity/BOS concepts — full SMC pattern detection
    (order blocks, fair value gaps, CHOCH) lives in app/quant/smart_money.py
    (next file), this module stays to summary-statistic-style features that feed a
    model rather than discrete pattern labels.
    """
    high, low, close = df["high"], df["low"], df["close"]
    features = pd.DataFrame(index=df.index)

    rolling_high = high.rolling(lookback).max()
    rolling_low = low.rolling(lookback).min()

    features["dist_to_swing_high"] = (rolling_high - close) / close
    features["dist_to_swing_low"] = (close - rolling_low) / close
    features["range_position"] = (close - rolling_low) / (rolling_high - rolling_low)

    higher_high = (high > high.shift(1)).rolling(lookback).sum()
    lower_low = (low < low.shift(1)).rolling(lookback).sum()
    features["trend_structure_score"] = (higher_high - lower_low) / lookback

    return features


def build_regime_features(df: pd.DataFrame, regime_detector: RegimeDetector | None = None) -> pd.DataFrame:
    close = df["close"]
    features = pd.DataFrame(index=df.index)

    returns = close.pct_change()
    features["rolling_volatility_10"] = returns.rolling(10).std()
    features["rolling_volatility_30"] = returns.rolling(30).std()

    # Rolling Hurst/entropy are expensive (O(window) per row) — computed on a coarser
    # stride and forward-filled, which is standard practice for these regime features
    # since they change slowly relative to price.
    stride = 10
    hurst_vals, entropy_vals = {}, {}
    for i in range(60, len(close), stride):
        window = close.iloc[max(0, i - 100): i]
        idx = close.index[i]
        hurst_vals[idx] = hurst_exponent(window)
        entropy_vals[idx] = shannon_entropy(window.pct_change())

    features["hurst_exponent"] = pd.Series(hurst_vals).reindex(df.index).ffill()
    features["return_entropy"] = pd.Series(entropy_vals).reindex(df.index).ffill()

    if regime_detector is not None:
        try:
            states = regime_detector.predict_states(close)
            features["regime_state"] = states.reindex(df.index)
        except RuntimeError:
            pass  # detector not fitted yet — caller fits it separately during training

    return features


def build_feature_matrix(
    df: pd.DataFrame, regime_detector: RegimeDetector | None = None, dropna: bool = True
) -> pd.DataFrame:
    """
    df must have columns: open, high, low, close, volume, indexed by timestamp ascending.
    Returns the full aligned feature matrix ready for model training/inference.
    """
    technical = build_technical_features(df)
    price_action = build_price_action_features(df)
    regime = build_regime_features(df, regime_detector)

    matrix = pd.concat([technical, price_action, regime], axis=1)
    return matrix.dropna() if dropna else matrix
