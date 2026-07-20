"""
Pure position-sizing math for copy trading — zero dependencies (no sqlalchemy,
no broker adapters), separated from app/execution/copytrading.py's I/O orchestration
specifically so this math is testable without a database or any installed ML/web
framework, the same pattern as app/execution/sizing.py and app/execution/allocator.py.
"""
from __future__ import annotations

import enum
from decimal import Decimal


class ScalingMode(str, enum.Enum):
    fixed_ratio = "fixed_ratio"
    equity_proportional = "equity_proportional"


def compute_follower_volume(
    source_volume: Decimal,
    scaling_mode: ScalingMode,
    scaling_value: Decimal,
    source_equity: Decimal | None = None,
    follower_equity: Decimal | None = None,
    max_follower_volume: Decimal | None = None,
    min_volume: Decimal = Decimal("0.01"),
) -> Decimal:
    """
    fixed_ratio: follower_volume = source_volume * scaling_value — e.g. scaling_value=0.5
        means "always trade half the leader's size", regardless of either account's equity.
    equity_proportional: additionally scales by (follower_equity / source_equity) —
        e.g. a follower with 1/4 the leader's equity trading at scaling_value=1.0 gets
        1/4 the leader's size, keeping *relative* risk comparable across differently
        capitalized accounts rather than mirroring absolute lot size.
    """
    if scaling_mode == ScalingMode.fixed_ratio:
        volume = source_volume * scaling_value
    elif scaling_mode == ScalingMode.equity_proportional:
        if not source_equity or source_equity <= 0:
            raise ValueError("source_equity must be positive for equity_proportional scaling")
        if follower_equity is None or follower_equity < 0:
            raise ValueError("follower_equity must be provided and non-negative for equity_proportional scaling")
        equity_ratio = follower_equity / source_equity
        volume = source_volume * scaling_value * equity_ratio
    else:
        raise ValueError(f"unknown scaling mode: {scaling_mode}")

    if max_follower_volume is not None:
        volume = min(volume, max_follower_volume)

    # Round to standard lot-size precision; below the broker's minimum tradeable
    # size, the mirrored trade is skipped rather than sent as a near-zero order.
    volume = volume.quantize(Decimal("0.01"))
    return volume if volume >= min_volume else Decimal("0")
