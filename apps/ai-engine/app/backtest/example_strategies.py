"""
Example strategies compatible with Backtester.run()'s `strategy(history_df, position)
-> Signal` interface. SMA crossover is a deliberately simple, well-understood baseline
— useful for exercising the backtest engine and report generator end-to-end, not
presented as a strategy anyone should expect to be profitable out of the box.
"""
from __future__ import annotations

from app.backtest.replay import Signal, SignalAction, SimPosition
from app.indicators.technical import atr as atr_fn
from app.indicators.technical import sma


def sma_crossover_strategy(fast_period: int = 10, slow_period: int = 30, atr_stop_multiple: float = 2.0):
    """
    Returns a strategy callable: goes long when the fast SMA crosses above the slow
    SMA, short on the opposite cross, with an ATR-based stop. Closes on an opposing
    crossover signal.
    """

    def strategy(history_df, position: SimPosition | None) -> Signal:
        if len(history_df) < slow_period + 2:
            return Signal(action=SignalAction.hold)

        close = history_df["close"]
        fast = sma(close, fast_period)
        slow = sma(close, slow_period)

        if fast.iloc[-1] is None or slow.iloc[-1] is None or fast.isna().iloc[-1] or slow.isna().iloc[-1]:
            return Signal(action=SignalAction.hold)

        crossed_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        crossed_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

        current_atr = atr_fn(history_df, 14).iloc[-1]
        price = close.iloc[-1]

        if position is None:
            if crossed_up:
                return Signal(
                    action=SignalAction.open_long,
                    stop_loss=price - current_atr * atr_stop_multiple,
                    take_profit=price + current_atr * atr_stop_multiple * 2,
                )
            if crossed_down:
                return Signal(
                    action=SignalAction.open_short,
                    stop_loss=price + current_atr * atr_stop_multiple,
                    take_profit=price - current_atr * atr_stop_multiple * 2,
                )
            return Signal(action=SignalAction.hold)

        if position.side == "long" and crossed_down:
            return Signal(action=SignalAction.close)
        if position.side == "short" and crossed_up:
            return Signal(action=SignalAction.close)
        return Signal(action=SignalAction.hold)

    return strategy
