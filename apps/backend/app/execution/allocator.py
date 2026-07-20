"""
Multi-strategy capital allocator.

Core algorithm, deliberately pure-stdlib (statistics + math modules only, no numpy):
1. Compute each strategy's rolling Sharpe ratio over its recent realized trade returns.
2. Strategies with too little data (< min_trades) get a flat minimum allocation —
   never zero, since a strategy needs some capital to keep generating the trade
   history the allocator needs to evaluate it; never full weight either, since an
   unproven strategy shouldn't get outsized capital on a lucky first few trades.
3. Convert Sharpe ratios to weights via a temperature-scaled softmax over
   max(sharpe, floor) — softmax (not a linear proportion) means a strategy with a
   meaningfully higher Sharpe gets a disproportionately larger allocation, while
   still giving every active strategy some non-zero weight (unlike a hard top-N cut).
4. Clip each weight to [min_allocation_pct, max_allocation_pct] and renormalize so
   the clipped result still sums to 1.0 — bounds exist so no single strategy can be
   starved to zero or allowed to run away with the entire portfolio regardless of
   how good its recent Sharpe looks (recent performance is not a permanent contract).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyBounds:
    min_allocation_pct: float = 0.0
    max_allocation_pct: float = 1.0


def rolling_sharpe(returns: list[float], periods_per_year: int = 252) -> float:
    """Same formula as ai-engine's app.risk.metrics.sharpe_ratio, reimplemented with
    stdlib `statistics` so this module has zero numpy/pandas dependency."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.mean(returns)
    stdev = statistics.pstdev(returns)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(periods_per_year)


def compute_allocations(
    strategy_returns: dict[str, list[float]],
    bounds: dict[str, StrategyBounds] | None = None,
    lookback_trades: int = 50,
    min_trades_for_sharpe: int = 10,
    default_allocation_for_new_strategy: float = 0.05,
    softmax_temperature: float = 2.0,
    sharpe_floor: float = -1.0,
) -> dict[str, float]:
    """
    Returns {strategy_tag: allocation_pct}, summing to 1.0 across all input strategies
    (assuming at least one strategy is passed). `bounds` defaults to [0, 1] per
    strategy if not specified for a given tag.
    """
    bounds = bounds or {}
    tags = list(strategy_returns.keys())
    if not tags:
        return {}

    sharpes: dict[str, float] = {}
    needs_default: set[str] = set()

    for tag in tags:
        recent_returns = strategy_returns[tag][-lookback_trades:]
        if len(recent_returns) < min_trades_for_sharpe:
            needs_default.add(tag)
            sharpes[tag] = sharpe_floor  # placeholder; weight comes from the default path below
        else:
            sharpes[tag] = max(rolling_sharpe(recent_returns), sharpe_floor)

    # Softmax over the *established* strategies only (enough trade history) — new/
    # unproven strategies are carved out with a flat default allocation up front so
    # they don't distort the softmax comparison among strategies with real track records.
    established = [t for t in tags if t not in needs_default]
    raw_weights: dict[str, float] = {}

    if established:
        exp_values = {t: math.exp(sharpes[t] / softmax_temperature) for t in established}
        total_exp = sum(exp_values.values())
        remaining_pct = 1.0 - len(needs_default) * default_allocation_for_new_strategy
        remaining_pct = max(remaining_pct, 0.0)
        for t in established:
            raw_weights[t] = remaining_pct * (exp_values[t] / total_exp)

    for t in needs_default:
        raw_weights[t] = default_allocation_for_new_strategy

    for t in needs_default:
        raw_weights[t] = default_allocation_for_new_strategy

    return _apply_bounds_water_filling(raw_weights, tags, bounds)


def _apply_bounds_water_filling(
    raw_weights: dict[str, float], tags: list[str], bounds: dict[str, StrategyBounds]
) -> dict[str, float]:
    """
    A single clip-then-renormalize pass is NOT sufficient: renormalizing after
    clipping can push a value that was correctly clipped to its bound back past that
    same bound (e.g. two strategies both clipped toward 0.5 with one capped at 0.3 —
    renormalizing the remainder can inflate the capped one back above 0.3). This
    iteratively pins strategies at their bound and redistributes the remaining budget
    proportionally among the still-free strategies, standard "water-filling" — the
    same technique used for bandwidth/resource allocation under box constraints.
    """
    weights = dict(raw_weights)
    pinned: dict[str, float] = {}
    free = set(tags)

    for _iteration in range(len(tags) + 1):  # can pin at most one strategy per iteration
        if not free:
            break

        total_pinned = sum(pinned.values())
        remaining_budget = 1.0 - total_pinned
        total_free_raw = sum(weights[t] for t in free)

        if total_free_raw <= 0:
            # No signal among the remaining free strategies — split the remaining
            # budget evenly rather than dividing by zero.
            for t in free:
                weights[t] = remaining_budget / len(free)
        else:
            for t in free:
                weights[t] = remaining_budget * (weights[t] / total_free_raw)

        newly_pinned = []
        for t in list(free):
            b = bounds.get(t, StrategyBounds())
            if weights[t] > b.max_allocation_pct:
                newly_pinned.append((t, b.max_allocation_pct))
            elif weights[t] < b.min_allocation_pct:
                newly_pinned.append((t, b.min_allocation_pct))

        if not newly_pinned:
            break

        for t, bound_value in newly_pinned:
            pinned[t] = bound_value
            free.discard(t)

    result = {**{t: weights[t] for t in free}, **pinned}
    total = sum(result.values())
    if total <= 0:
        return {t: 1.0 / len(tags) for t in tags}
    # Final safety renormalization for floating-point drift only (should already sum
    # to ~1.0 after water-filling) — not a bound-violating renormalization like the
    # single-pass version this replaced, since by this point no value is being pushed
    # across a bound it was deliberately pinned at.
    return {t: v / total for t, v in result.items()}
