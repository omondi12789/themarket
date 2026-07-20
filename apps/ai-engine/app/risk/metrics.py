"""
Risk & performance metrics on a return series. Convention: `returns` is a pandas
Series of periodic (e.g. daily) fractional returns, e.g. 0.01 for +1%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def annualization_factor(periods_per_year: int = 252) -> float:
    return np.sqrt(periods_per_year)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    if len(excess) == 0:
        return 0.0
    std = excess.std(ddof=0)
    if np.isnan(std) or std == 0:
        return 0.0
    if np.allclose(excess, excess.iloc[0]):
        return 0.0
    return float(excess.mean() / std * annualization_factor(periods_per_year))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    if len(excess) == 0:
        return 0.0
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    downside_std = downside.std(ddof=0)
    if np.isnan(downside_std) or downside_std == 0:
        return 0.0
    if np.allclose(excess, excess.iloc[0]):
        return 0.0
    return float(excess.mean() / downside_std * annualization_factor(periods_per_year))


def equity_curve(returns: pd.Series, starting_capital: float = 1.0) -> pd.Series:
    return starting_capital * (1 + returns).cumprod()


def max_drawdown(returns: pd.Series) -> float:
    curve = equity_curve(returns)
    running_max = curve.cummax()
    drawdown = (curve - running_max) / running_max
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    total_periods = len(returns)
    if total_periods == 0:
        return 0.0
    curve = equity_curve(returns)
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (periods_per_year / total_periods) - 1
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return 0.0
    return float(cagr / mdd)


def value_at_risk(returns: pd.Series, confidence: float = 0.95, method: str = "historical") -> float:
    """
    Returns VaR as a positive fractional loss (e.g. 0.02 = 2% loss at the given
    confidence level over one period).
    """
    if method == "historical":
        return float(-np.percentile(returns.dropna(), (1 - confidence) * 100))
    if method == "parametric":
        mu, sigma = returns.mean(), returns.std(ddof=0)
        from scipy.stats import norm

        z = norm.ppf(1 - confidence)
        return float(-(mu + z * sigma))
    raise ValueError(f"unknown VaR method: {method}")


def conditional_value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected shortfall: average loss in the tail beyond the VaR threshold."""
    var = value_at_risk(returns, confidence, method="historical")
    tail_losses = returns[returns <= -var]
    if len(tail_losses) == 0:
        return var
    return float(-tail_losses.mean())


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Classic Kelly fraction: f* = W - (1-W)/R, where R = avg_win / avg_loss (both positive).
    Returns the fraction of capital to risk per trade. Clipped to [0, 1] — negative
    edge means don't take the bet, and we never suggest >100% of capital.
    """
    if avg_loss <= 0:
        raise ValueError("avg_loss must be a positive number (magnitude of average losing trade)")
    r = avg_win / avg_loss
    f = win_rate - (1 - win_rate) / r
    return float(np.clip(f, 0.0, 1.0))


def fractional_kelly(win_rate: float, avg_win: float, avg_loss: float, fraction: float = 0.5) -> float:
    """
    Most practitioners use a fraction (commonly 1/4 to 1/2) of full Kelly to reduce
    variance, since full Kelly assumes perfectly known, stationary win/loss stats —
    an assumption that never quite holds in live markets.
    """
    return kelly_criterion(win_rate, avg_win, avg_loss) * fraction


def summarize_performance(returns: pd.Series, periods_per_year: int = 252, risk_free_rate: float = 0.0) -> dict:
    return {
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate, periods_per_year),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate, periods_per_year),
        "calmar_ratio": calmar_ratio(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "var_95": value_at_risk(returns, 0.95),
        "cvar_95": conditional_value_at_risk(returns, 0.95),
        "total_return": float(equity_curve(returns).iloc[-1] - 1) if len(returns) else 0.0,
        "volatility_annualized": float(returns.std(ddof=0) * annualization_factor(periods_per_year)),
    }
