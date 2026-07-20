"""
Smart Money Concepts (SMC) / ICT-style structural pattern detection.

These are discrete, rule-based pattern detectors (unlike features/pipeline.py's
continuous summary statistics) — each function returns explicit event rows
(timestamp, type, price levels), the way a discretionary SMC trader would mark them
on a chart. There is no single universally agreed-upon algorithmic definition for
"order block" or "CHOCH" — different traders draw the lines slightly differently.
The definitions below are the common, widely-taught versions; treat them as one
reasonable implementation, not the only valid one.
"""
from __future__ import annotations

import pandas as pd


def detect_swing_points(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """
    A swing high/low is a bar whose high/low is the max/min within `lookback` bars on
    both sides — the standard fractal definition.
    """
    high, low = df["high"], df["low"]
    is_swing_high = pd.Series(True, index=df.index)
    is_swing_low = pd.Series(True, index=df.index)

    for shift in range(1, lookback + 1):
        is_swing_high &= (high > high.shift(shift)) & (high > high.shift(-shift))
        is_swing_low &= (low < low.shift(shift)) & (low < low.shift(-shift))

    return pd.DataFrame({"swing_high": is_swing_high, "swing_low": is_swing_low})


def detect_break_of_structure(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """
    Break of Structure (BOS): price closes beyond the most recent confirmed swing
    high (bullish BOS, trend continuation) or swing low (bearish BOS).
    Change of Character (CHOCH): the first BOS in the *opposite* direction of the
    prevailing trend — the earliest structural signal that a trend may be reversing.
    """
    swings = detect_swing_points(df, lookback)
    close = df["close"]

    last_swing_high = df["high"].where(swings["swing_high"]).ffill().shift(1)
    last_swing_low = df["low"].where(swings["swing_low"]).ffill().shift(1)

    bullish_bos = close > last_swing_high
    bearish_bos = close < last_swing_low

    # Track prevailing trend as the direction of the most recent BOS; CHOCH is a BOS
    # opposite to that prevailing trend.
    trend = pd.Series(0, index=df.index)  # 1 = bullish, -1 = bearish, 0 = undetermined
    choch = pd.Series(False, index=df.index)

    current_trend = 0
    for i, ts in enumerate(df.index):
        if bullish_bos.iloc[i]:
            if current_trend == -1:
                choch.iloc[i] = True
            current_trend = 1
        elif bearish_bos.iloc[i]:
            if current_trend == 1:
                choch.iloc[i] = True
            current_trend = -1
        trend.iloc[i] = current_trend

    return pd.DataFrame(
        {
            "bullish_bos": bullish_bos,
            "bearish_bos": bearish_bos,
            "choch": choch,
            "trend": trend,
        }
    )


def detect_fair_value_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    A Fair Value Gap (FVG) / imbalance: a 3-candle pattern where candle 1's high is
    below candle 3's low (bullish FVG, price likely to fill the gap down later) or
    candle 1's low is above candle 3's high (bearish FVG).
    """
    high, low = df["high"], df["low"]

    bullish_fvg = low.shift(-1) > high.shift(1)  # centered on the middle candle
    bearish_fvg = high.shift(-1) < low.shift(1)

    return pd.DataFrame(
        {
            "bullish_fvg": bullish_fvg.fillna(False),
            "bearish_fvg": bearish_fvg.fillna(False),
            "fvg_top": low.shift(-1).where(bullish_fvg, high.shift(-1).where(bearish_fvg)),
            "fvg_bottom": high.shift(1).where(bullish_fvg, low.shift(1).where(bearish_fvg)),
        }
    )


def detect_order_blocks(df: pd.DataFrame, min_move_atr_multiple: float = 1.5) -> pd.DataFrame:
    """
    A bullish order block: the last down-candle before a strong up-move (the
    "smart money" accumulation candle before markup). A bearish order block is the
    mirror. "Strong move" is defined here as a subsequent candle range exceeding
    `min_move_atr_multiple` * ATR(14) — a common, if not universal, filter to avoid
    flagging every minor swing as an order block.
    """
    from app.indicators.technical import atr as atr_fn

    atr_series = atr_fn(df, 14)
    close, open_ = df["close"], df["open"]
    is_down_candle = close < open_
    is_up_candle = close > open_

    next_move_size = (close.shift(-1) - open_.shift(-1)).abs()
    strong_up_move = is_up_candle.shift(-1) & (next_move_size > min_move_atr_multiple * atr_series)
    strong_down_move = is_down_candle.shift(-1) & (next_move_size > min_move_atr_multiple * atr_series)

    bullish_ob = is_down_candle & strong_up_move
    bearish_ob = is_up_candle & strong_down_move

    return pd.DataFrame(
        {
            "bullish_order_block": bullish_ob.fillna(False),
            "bearish_order_block": bearish_ob.fillna(False),
            "ob_high": df["high"].where(bullish_ob | bearish_ob),
            "ob_low": df["low"].where(bullish_ob | bearish_ob),
        }
    )


def detect_liquidity_zones(df: pd.DataFrame, lookback: int = 3, equal_level_tolerance_pct: float = 0.0005) -> pd.DataFrame:
    """
    Liquidity zones: clusters of equal (or near-equal) swing highs/lows, where
    resting stop-loss/breakout orders are assumed to concentrate — classic
    "buy-side liquidity above equal highs, sell-side liquidity below equal lows".
    """
    swings = detect_swing_points(df, lookback)
    swing_highs = df["high"].where(swings["swing_high"]).dropna()
    swing_lows = df["low"].where(swings["swing_low"]).dropna()

    def _find_equal_levels(levels: pd.Series) -> pd.Series:
        flagged = pd.Series(False, index=levels.index)
        values = levels.values
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                if abs(values[i] - values[j]) / values[i] <= equal_level_tolerance_pct:
                    flagged.iloc[i] = True
                    flagged.iloc[j] = True
        return flagged

    equal_highs = _find_equal_levels(swing_highs)
    equal_lows = _find_equal_levels(swing_lows)

    return pd.DataFrame(
        {
            "buy_side_liquidity": equal_highs.reindex(df.index).fillna(False),
            "sell_side_liquidity": equal_lows.reindex(df.index).fillna(False),
        }
    )
