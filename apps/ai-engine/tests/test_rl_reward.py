import pytest

from app.rl.reward import drawdown_penalty, position_pnl_return, step_reward, transaction_cost


def test_position_pnl_return_long_winning():
    # Full size (1.0), long (1), market up 2% -> full 2% gain
    assert position_pnl_return(1.0, 1, 0.02) == pytest.approx(0.02)


def test_position_pnl_return_short_winning():
    # Full size, short (-1), market down 2% -> +2% gain for the short
    assert position_pnl_return(1.0, -1, -0.02) == pytest.approx(0.02)


def test_position_pnl_return_scales_with_size():
    assert position_pnl_return(0.5, 1, 0.02) == pytest.approx(0.01)
    assert position_pnl_return(0.0, 1, 0.02) == pytest.approx(0.0)


def test_position_pnl_return_rejects_invalid_size():
    with pytest.raises(ValueError):
        position_pnl_return(1.5, 1, 0.01)
    with pytest.raises(ValueError):
        position_pnl_return(-0.1, 1, 0.01)


def test_position_pnl_return_rejects_invalid_direction():
    with pytest.raises(ValueError):
        position_pnl_return(0.5, 0, 0.01)


def test_transaction_cost_zero_when_size_unchanged():
    assert transaction_cost(0.5, 0.5, cost_rate=0.0002) == 0.0


def test_transaction_cost_scales_with_size_change():
    cost_small = transaction_cost(0.5, 0.4, cost_rate=0.0002)
    cost_large = transaction_cost(1.0, 0.0, cost_rate=0.0002)
    assert cost_large > cost_small
    assert cost_large == pytest.approx(1.0 * 0.0002)


def test_drawdown_penalty_zero_at_peak():
    assert drawdown_penalty(equity=100.0, peak_equity=100.0, penalty_coef=0.5) == 0.0


def test_drawdown_penalty_positive_below_peak():
    # 10% below peak -> penalty = 0.5 * 0.10 = 0.05
    penalty = drawdown_penalty(equity=90.0, peak_equity=100.0, penalty_coef=0.5)
    assert penalty == pytest.approx(0.05)


def test_drawdown_penalty_zero_when_peak_is_zero():
    # Degenerate guard — shouldn't happen in practice but must not divide by zero
    assert drawdown_penalty(equity=0.0, peak_equity=0.0, penalty_coef=0.5) == 0.0


def test_step_reward_full_breakdown_winning_trade():
    result = step_reward(
        size=1.0, prev_size=1.0, direction=1, next_bar_return=0.02,
        equity_before=1000.0, peak_equity_before=1000.0,
        cost_rate=0.0, drawdown_penalty_coef=0.5,
    )
    assert result["pnl_return"] == pytest.approx(0.02)
    assert result["transaction_cost"] == 0.0
    assert result["drawdown_penalty"] == 0.0  # new equity is above peak, no drawdown
    assert result["reward"] == pytest.approx(0.02)
    assert result["equity_after"] == pytest.approx(1020.0)
    assert result["peak_equity_after"] == pytest.approx(1020.0)


def test_step_reward_penalizes_size_churn():
    no_churn = step_reward(
        size=0.5, prev_size=0.5, direction=1, next_bar_return=0.01,
        equity_before=1000.0, peak_equity_before=1000.0, cost_rate=0.001,
    )
    with_churn = step_reward(
        size=1.0, prev_size=0.0, direction=1, next_bar_return=0.01,
        equity_before=1000.0, peak_equity_before=1000.0, cost_rate=0.001,
    )
    # Same directional bet in aggregate terms, but the churned version paid more
    # transaction cost for changing size by a full unit instead of zero.
    assert with_churn["transaction_cost"] > no_churn["transaction_cost"]


def test_step_reward_penalizes_new_drawdown():
    result = step_reward(
        size=1.0, prev_size=1.0, direction=1, next_bar_return=-0.05,
        equity_before=1000.0, peak_equity_before=1000.0,
        cost_rate=0.0, drawdown_penalty_coef=1.0,
    )
    assert result["equity_after"] == pytest.approx(950.0)
    assert result["drawdown_penalty"] > 0
    # Reward should be worse than the raw pnl due to the drawdown penalty stacking on top
    assert result["reward"] < result["pnl_return"]


def test_step_reward_flat_size_has_zero_pnl_and_zero_cost_if_unchanged():
    result = step_reward(
        size=0.0, prev_size=0.0, direction=1, next_bar_return=0.05,
        equity_before=1000.0, peak_equity_before=1000.0,
    )
    assert result["pnl_return"] == 0.0
    assert result["transaction_cost"] == 0.0
    assert result["equity_after"] == pytest.approx(1000.0)
