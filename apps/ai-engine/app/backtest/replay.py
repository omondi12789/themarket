"""
Historical replay backtester. Bar-by-bar simulation (not vectorized) deliberately —
a vectorized backtest can accidentally use future information (look-ahead bias); a
replay loop that only ever sees bars up to the current index structurally can't.

Strategy interface: any callable `(history_df, position) -> Signal | None`, where
`history_df` is every bar up to and including the current one (never beyond), and
`position` is the currently open position for this symbol, if any.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

import pandas as pd


class SignalAction(str, Enum):
    open_long = "open_long"
    open_short = "open_short"
    close = "close"
    hold = "hold"


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    stop_loss: float | None = None
    take_profit: float | None = None
    volume: float = 1.0


@dataclass
class SimPosition:
    side: str  # "long" | "short"
    entry_price: float
    volume: float
    entry_index: int
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class Trade:
    side: str
    entry_price: float
    exit_price: float
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    volume: float
    pnl: float
    return_pct: float
    exit_reason: str


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)

    @property
    def trade_returns(self) -> pd.Series:
        return pd.Series([t.return_pct for t in self.trades])

    def summary(self) -> dict:
        if not self.trades:
            return {"total_trades": 0}
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        return {
            "total_trades": len(self.trades),
            "win_rate": len(wins) / len(self.trades),
            "avg_win_pct": sum(t.return_pct for t in wins) / len(wins) if wins else 0.0,
            "avg_loss_pct": sum(t.return_pct for t in losses) / len(losses) if losses else 0.0,
            "total_pnl": sum(t.pnl for t in self.trades),
            "final_equity": float(self.equity_curve.iloc[-1]) if len(self.equity_curve) else None,
        }


class Backtester:
    def __init__(
        self,
        starting_capital: float = 10_000.0,
        spread_pips: float = 1.0,
        slippage_pips: float = 0.3,
        pip_value_per_lot: float = 10.0,
        pip_size: float = 0.0001,
    ):
        self.starting_capital = starting_capital
        self.spread_cost = spread_pips * pip_size
        self.slippage_cost = slippage_pips * pip_size
        self.pip_value_per_lot = pip_value_per_lot
        self.pip_size = pip_size

    def run(self, df: pd.DataFrame, strategy, warmup_bars: int = 60) -> BacktestResult:
        """
        df: OHLCV DataFrame indexed by timestamp ascending.
        strategy: callable(history_df, position) -> Signal
        """
        equity = self.starting_capital
        position: SimPosition | None = None
        trades: list[Trade] = []
        equity_points: dict = {}

        for i in range(warmup_bars, len(df)):
            history = df.iloc[: i + 1]
            bar = df.iloc[i]

            # Check stop/TP hits first, using this bar's high/low (intrabar, before
            # the strategy sees this bar's close — avoids a subtle look-ahead bug
            # where a stop that would have triggered mid-bar is instead evaluated
            # against the close).
            if position is not None:
                exit_price, exit_reason = self._check_stop_tp(position, bar)
                if exit_price is not None:
                    trade, equity = self._close_position(position, exit_price, bar.name, equity, exit_reason)
                    trades.append(trade)
                    position = None

            signal = strategy(history, position)

            if signal.action == SignalAction.close and position is not None:
                exit_price = self._apply_cost(bar["close"], position.side, closing=True)
                trade, equity = self._close_position(position, exit_price, bar.name, equity, "signal")
                trades.append(trade)
                position = None

            elif signal.action in (SignalAction.open_long, SignalAction.open_short) and position is None:
                side = "long" if signal.action == SignalAction.open_long else "short"
                entry_price = self._apply_cost(bar["close"], side, closing=False)
                position = SimPosition(
                    side=side,
                    entry_price=entry_price,
                    volume=signal.volume,
                    entry_index=i,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

            # Mark-to-market equity for the curve, even with an open position.
            unrealized = 0.0
            if position is not None:
                direction = 1 if position.side == "long" else -1
                unrealized = (
                    (bar["close"] - position.entry_price) * direction / self.pip_size
                ) * self.pip_value_per_lot * position.volume
            equity_points[bar.name] = equity + unrealized

        return BacktestResult(trades=trades, equity_curve=pd.Series(equity_points))

    def _apply_cost(self, price: float, side: str, closing: bool) -> float:
        cost = self.spread_cost / 2 + self.slippage_cost
        # Buying (or closing a short) crosses the spread upward; selling crosses downward.
        crosses_up = (side == "long" and not closing) or (side == "short" and closing)
        return price + cost if crosses_up else price - cost

    def _check_stop_tp(self, position: SimPosition, bar: pd.Series) -> tuple[float | None, str]:
        if position.side == "long":
            if position.stop_loss is not None and bar["low"] <= position.stop_loss:
                return position.stop_loss, "stop_loss"
            if position.take_profit is not None and bar["high"] >= position.take_profit:
                return position.take_profit, "take_profit"
        else:
            if position.stop_loss is not None and bar["high"] >= position.stop_loss:
                return position.stop_loss, "stop_loss"
            if position.take_profit is not None and bar["low"] <= position.take_profit:
                return position.take_profit, "take_profit"
        return None, ""

    def _close_position(
        self, position: SimPosition, exit_price: float, exit_time, equity: float, reason: str
    ) -> tuple[Trade, float]:
        direction = 1 if position.side == "long" else -1
        pips = (exit_price - position.entry_price) * direction / self.pip_size
        pnl = pips * self.pip_value_per_lot * position.volume
        return_pct = pnl / equity if equity > 0 else 0.0

        trade = Trade(
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=None,  # populated by caller if needed; kept minimal here
            exit_time=exit_time,
            volume=position.volume,
            pnl=pnl,
            return_pct=return_pct,
            exit_reason=reason,
        )
        return trade, equity + pnl
