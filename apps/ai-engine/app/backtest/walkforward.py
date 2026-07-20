"""
Walk-forward optimization: the standard defense against curve-fitting a strategy's
parameters to one lucky backtest window. Splits history into rolling
(in-sample train, out-of-sample test) windows, re-optimizes parameters on each
train window, and evaluates *only* on the following unseen test window — then rolls
forward. The final reported performance is the concatenation of out-of-sample
segments only, which is what you'd have actually earned running this process live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from app.backtest.replay import Backtester, BacktestResult


@dataclass
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict
    train_score: float
    test_result: BacktestResult


@dataclass
class WalkForwardReport:
    windows: list[WalkForwardWindow]

    @property
    def out_of_sample_trades(self) -> list:
        trades = []
        for w in self.windows:
            trades.extend(w.test_result.trades)
        return trades

    def summary(self) -> dict:
        all_trades = self.out_of_sample_trades
        if not all_trades:
            return {"total_windows": len(self.windows), "total_oos_trades": 0}
        wins = [t for t in all_trades if t.pnl > 0]
        return {
            "total_windows": len(self.windows),
            "total_oos_trades": len(all_trades),
            "oos_win_rate": len(wins) / len(all_trades),
            "oos_total_pnl": sum(t.pnl for t in all_trades),
            "params_by_window": [w.best_params for w in self.windows],
        }


def generate_windows(
    df: pd.DataFrame, train_bars: int, test_bars: int, step_bars: int | None = None
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    step = step_bars or test_bars
    windows = []
    start = 0
    while start + train_bars + test_bars <= len(df):
        train = df.iloc[start : start + train_bars]
        test = df.iloc[start + train_bars : start + train_bars + test_bars]
        windows.append((train, test))
        start += step
    return windows


def run_walk_forward(
    df: pd.DataFrame,
    param_grid: list[dict],
    strategy_factory: Callable[[dict], Callable],
    train_bars: int = 2000,
    test_bars: int = 500,
    step_bars: int | None = None,
    optimization_metric: Callable[[BacktestResult], float] | None = None,
    backtester_kwargs: dict | None = None,
) -> WalkForwardReport:
    """
    param_grid: list of parameter dicts to try, e.g. [{"rsi_period": 14, "atr_mult": 1.5}, ...].
    strategy_factory: params -> strategy callable, matching Backtester.run()'s expected signature.
    optimization_metric: BacktestResult -> float, higher is better (default: total PnL).
    """
    optimization_metric = optimization_metric or (lambda r: r.summary().get("total_pnl", 0.0) or 0.0)
    backtester = Backtester(**(backtester_kwargs or {}))

    windows_data = generate_windows(df, train_bars, test_bars, step_bars)
    results: list[WalkForwardWindow] = []

    for train_df, test_df in windows_data:
        best_params, best_score, best_result = None, float("-inf"), None

        for params in param_grid:
            strategy = strategy_factory(params)
            train_result = backtester.run(train_df, strategy)
            score = optimization_metric(train_result)
            if score > best_score:
                best_params, best_score = params, score

        # Re-run the winning params' strategy on the untouched test window.
        test_strategy = strategy_factory(best_params)
        test_result = backtester.run(test_df, test_strategy)

        results.append(
            WalkForwardWindow(
                train_start=train_df.index[0],
                train_end=train_df.index[-1],
                test_start=test_df.index[0],
                test_end=test_df.index[-1],
                best_params=best_params,
                train_score=best_score,
                test_result=test_result,
            )
        )

    return WalkForwardReport(windows=results)
