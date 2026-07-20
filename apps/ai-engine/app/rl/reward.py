"""
Reward computation for the position-sizing RL environment, factored out as plain
float functions with zero dependencies (no numpy/pandas/torch). This is deliberate:
it's the one piece of the RL stack that can actually be unit-tested in any Python
environment, including this build sandbox with no network access to install ML
libraries — everything downstream (environment.py, agent.py) depends on this module
being correct, so it's worth keeping trivially verifiable.

Reward design, per step:
    reward = pnl_return - transaction_cost - drawdown_penalty

- pnl_return: size * direction * next_bar_return — the actual P&L this step, scaled
  by how much size the agent chose to allocate.
- transaction_cost: penalizes churning size up/down every bar (real trading has
  spread/slippage cost on every size change) — without this term, a DQN agent will
  happily oscillate size wildly if it ever helps squeeze out marginal reward.
- drawdown_penalty: penalizes new equity lows beyond the prior peak, scaled by
  penalty_coef — this is what pushes the agent toward smaller size in choppy/losing
  stretches rather than a reward function that only cares about raw P&L (which would
  learn to just always bet max size, ignoring risk of ruin).
"""
from __future__ import annotations


def position_pnl_return(size: float, direction: int, next_bar_return: float) -> float:
    """size in [0, 1]; direction in {-1, 1}. Returns the fractional P&L for this step."""
    if not (0.0 <= size <= 1.0):
        raise ValueError(f"size must be in [0, 1], got {size}")
    if direction not in (-1, 1):
        raise ValueError(f"direction must be -1 or 1, got {direction}")
    return size * direction * next_bar_return


def transaction_cost(size: float, prev_size: float, cost_rate: float) -> float:
    """cost_rate is the fractional cost per unit of size changed (spread+slippage proxy)."""
    return abs(size - prev_size) * cost_rate


def drawdown_penalty(equity: float, peak_equity: float, penalty_coef: float) -> float:
    """Penalizes being below the running peak; zero at or above the peak."""
    if peak_equity <= 0:
        return 0.0
    current_drawdown = max(0.0, (peak_equity - equity) / peak_equity)
    return penalty_coef * current_drawdown


def step_reward(
    size: float,
    prev_size: float,
    direction: int,
    next_bar_return: float,
    equity_before: float,
    peak_equity_before: float,
    cost_rate: float = 0.0002,
    drawdown_penalty_coef: float = 0.5,
) -> dict:
    """
    Computes one full environment step's reward and the resulting equity/peak state.
    Returns a dict rather than a bare float so callers (and tests) can inspect each
    component — reward = pnl - cost - dd_penalty is the actual scalar RL reward.
    """
    pnl = position_pnl_return(size, direction, next_bar_return)
    cost = transaction_cost(size, prev_size, cost_rate)
    equity_after = equity_before * (1 + pnl - cost)
    peak_equity_after = max(peak_equity_before, equity_after)
    dd_penalty = drawdown_penalty(equity_after, peak_equity_after, drawdown_penalty_coef)

    reward = pnl - cost - dd_penalty

    return {
        "reward": reward,
        "pnl_return": pnl,
        "transaction_cost": cost,
        "drawdown_penalty": dd_penalty,
        "equity_after": equity_after,
        "peak_equity_after": peak_equity_after,
    }
