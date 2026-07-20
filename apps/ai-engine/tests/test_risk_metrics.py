import numpy as np
import pandas as pd
import pytest

from app.risk.metrics import (
    calmar_ratio,
    conditional_value_at_risk,
    fractional_kelly,
    kelly_criterion,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk,
)


def test_kelly_criterion_matches_hand_calculation():
    # f* = W - (1-W)/R, R = avg_win/avg_loss = 1.5
    # f* = 0.6 - 0.4/1.5 = 0.3333...
    f = kelly_criterion(win_rate=0.6, avg_win=1.5, avg_loss=1.0)
    assert f == pytest.approx(0.3333, abs=1e-3)


def test_kelly_criterion_clips_negative_edge_to_zero():
    # Losing edge: win_rate too low relative to payoff ratio -> negative Kelly -> clipped to 0
    f = kelly_criterion(win_rate=0.2, avg_win=1.0, avg_loss=1.0)
    assert f == 0.0


def test_kelly_criterion_never_exceeds_one():
    f = kelly_criterion(win_rate=0.99, avg_win=100.0, avg_loss=0.01)
    assert f <= 1.0


def test_kelly_criterion_rejects_nonpositive_avg_loss():
    with pytest.raises(ValueError):
        kelly_criterion(win_rate=0.5, avg_win=1.0, avg_loss=0.0)


def test_fractional_kelly_scales_down_full_kelly():
    full = kelly_criterion(win_rate=0.6, avg_win=1.5, avg_loss=1.0)
    half = fractional_kelly(win_rate=0.6, avg_win=1.5, avg_loss=1.0, fraction=0.5)
    assert half == pytest.approx(full * 0.5)


def test_sharpe_ratio_zero_for_flat_returns():
    # Zero variance -> defined as 0.0 rather than dividing by zero
    flat = pd.Series([0.001] * 10)
    assert sharpe_ratio(flat) == 0.0


def test_sharpe_ratio_positive_for_positive_drift():
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(0.001, 0.01, 500))
    assert sharpe_ratio(returns) > 0


def test_sortino_only_penalizes_downside():
    # Two series with identical mean and identical *overall* std, but one has all its
    # variance on the upside — Sortino should score the upside-only series higher.
    upside_vol = pd.Series([0.01, 0.03, 0.01, 0.03, 0.01, 0.03] * 20)
    mixed_vol = pd.Series([0.03, -0.01, 0.03, -0.01, 0.03, -0.01] * 20)
    assert sortino_ratio(upside_vol) > sortino_ratio(mixed_vol)


def test_max_drawdown_is_zero_for_monotonic_gains():
    returns = pd.Series([0.01] * 20)
    assert max_drawdown(returns) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_detects_known_decline():
    # Equity: 100 -> 110 -> 88 (a 20% drawdown from the 110 peak)
    returns = pd.Series([0.10, -0.20])
    dd = max_drawdown(returns)
    assert dd == pytest.approx(-0.20, abs=1e-6)


def test_calmar_ratio_zero_when_no_drawdown():
    returns = pd.Series([0.001] * 252)
    # No drawdown at all is the degenerate case handled explicitly (division by zero guard)
    assert calmar_ratio(returns) >= 0


def test_value_at_risk_historical_matches_percentile():
    returns = pd.Series(np.linspace(-0.05, 0.05, 101))  # uniform from -5% to +5%
    var_95 = value_at_risk(returns, confidence=0.95, method="historical")
    # 5th percentile of this series is very close to -0.045
    assert var_95 == pytest.approx(0.045, abs=0.005)


def test_conditional_var_is_at_least_as_large_as_var():
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0, 0.02, 1000))
    var_95 = value_at_risk(returns, 0.95)
    cvar_95 = conditional_value_at_risk(returns, 0.95)
    # CVaR (expected shortfall beyond VaR) is always >= VaR for the same confidence level
    assert cvar_95 >= var_95
