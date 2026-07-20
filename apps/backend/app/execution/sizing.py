"""
Position sizing and dynamic stop-loss/take-profit calculation.

Two sizing methods, combinable:
1. Volatility scaling — size inversely to ATR, so every trade risks a consistent
   dollar amount regardless of the instrument's current volatility.
2. Fractional Kelly — scales further by a confidence-adjusted edge estimate. Kept as
   a multiplier on top of vol-scaled size, not a replacement, since raw Kelly sizing
   from noisy live-trade statistics is notoriously unstable on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PositionSizeResult:
    volume: Decimal
    risk_amount: Decimal
    stop_loss_distance: Decimal
    reasoning: str


def volatility_scaled_size(
    account_equity: Decimal,
    risk_per_trade_pct: Decimal,
    atr: Decimal,
    atr_stop_multiple: Decimal,
    pip_value_per_lot: Decimal,
    max_volume: Decimal = Decimal("10"),
) -> PositionSizeResult:
    """
    risk_per_trade_pct: fraction of equity to risk (e.g. 0.01 = 1%).
    pip_value_per_lot: broker/instrument-specific $ value of a 1-pip move per 1.0 lot
        (varies by symbol and account currency — fetch from the broker adapter's
        symbol info in production rather than hardcoding).
    """
    risk_amount = account_equity * risk_per_trade_pct
    stop_distance = atr * atr_stop_multiple

    if stop_distance <= 0 or pip_value_per_lot <= 0:
        return PositionSizeResult(
            volume=Decimal("0"),
            risk_amount=risk_amount,
            stop_loss_distance=stop_distance,
            reasoning="invalid ATR or pip value — refusing to size a trade",
        )

    # risk_amount = volume_lots * stop_distance_in_pips * pip_value_per_lot
    stop_distance_pips = stop_distance * 10_000  # assumes 4/5-decimal FX quoting
    volume = risk_amount / (stop_distance_pips * pip_value_per_lot)
    volume = min(volume, max_volume)

    return PositionSizeResult(
        volume=volume.quantize(Decimal("0.01")),
        risk_amount=risk_amount,
        stop_loss_distance=stop_distance,
        reasoning=(
            f"risking {risk_per_trade_pct:.2%} of equity ({risk_amount}) over a "
            f"{atr_stop_multiple}x-ATR stop ({stop_distance_pips:.1f} pips)"
        ),
    )


def kelly_adjusted_size(
    base_size: PositionSizeResult, kelly_fraction: float, confidence: float, max_multiplier: Decimal = Decimal("1.5")
) -> PositionSizeResult:
    """
    Scales the volatility-based size by a confidence-weighted Kelly fraction.
    confidence in [0, 1] comes from the AI decision system's probability estimate;
    kelly_fraction from app.risk.metrics.fractional_kelly (ai-engine service) applied
    to that strategy's live/backtested win-rate stats.
    """
    multiplier = Decimal(str(min(max(kelly_fraction * confidence * 2, 0.1), float(max_multiplier))))
    adjusted_volume = (base_size.volume * multiplier).quantize(Decimal("0.01"))
    return PositionSizeResult(
        volume=adjusted_volume,
        risk_amount=base_size.risk_amount * multiplier,
        stop_loss_distance=base_size.stop_loss_distance,
        reasoning=base_size.reasoning + f"; Kelly/confidence multiplier {multiplier}",
    )


@dataclass(frozen=True)
class StopLevels:
    stop_loss: Decimal
    take_profit: Decimal


def atr_based_stops(
    entry_price: Decimal,
    atr: Decimal,
    side: str,  # "buy" or "sell"
    stop_multiple: Decimal = Decimal("1.5"),
    reward_risk_ratio: Decimal = Decimal("2.0"),
) -> StopLevels:
    stop_distance = atr * stop_multiple
    tp_distance = stop_distance * reward_risk_ratio

    if side == "buy":
        return StopLevels(stop_loss=entry_price - stop_distance, take_profit=entry_price + tp_distance)
    return StopLevels(stop_loss=entry_price + stop_distance, take_profit=entry_price - tp_distance)


def correlation_adjusted_size(
    base_size: PositionSizeResult,
    new_symbol: str,
    new_side: str,
    existing_positions: list[tuple[str, str, Decimal]],  # (symbol, side, correlation_to_new_symbol)
    correlation_threshold: float = 0.7,
    reduction_per_correlated_exposure: Decimal = Decimal("0.25"),
    max_reduction: Decimal = Decimal("0.75"),
) -> PositionSizeResult:
    """
    Reduces position size when the account already holds exposure highly correlated
    with the new trade — e.g. already long GBPUSD and about to go long EURUSD, both
    of which move together on broad USD strength/weakness. `existing_positions`
    should be pre-computed by the caller (correlation values come from
    app.quant.statarb.correlation_matrix on the ai-engine, over recent daily returns)
    since this module deliberately stays free of the ai-engine's numpy/pandas
    dependency — it's a pure-Decimal function the execution engine can call cheaply.

    Same-direction correlated exposure compounds risk (both positions lose together
    in the correlated scenario) and gets reduced. Opposite-direction correlated
    exposure is partially hedging and is left alone.
    """
    correlated_same_direction = 0
    for symbol, side, correlation in existing_positions:
        if symbol == new_symbol:
            continue
        if abs(correlation) >= correlation_threshold:
            same_direction = (side == new_side) == (correlation > 0)
            if same_direction:
                correlated_same_direction += 1

    if correlated_same_direction == 0:
        return base_size

    reduction = min(
        Decimal(str(correlated_same_direction)) * reduction_per_correlated_exposure, max_reduction
    )
    multiplier = Decimal("1") - reduction
    adjusted_volume = (base_size.volume * multiplier).quantize(Decimal("0.01"))

    return PositionSizeResult(
        volume=adjusted_volume,
        risk_amount=base_size.risk_amount * multiplier,
        stop_loss_distance=base_size.stop_loss_distance,
        reasoning=(
            base_size.reasoning
            + f"; reduced {reduction:.0%} for {correlated_same_direction} correlated same-direction "
            f"exposure(s) (correlation >= {correlation_threshold})"
        ),
    )
