from decimal import Decimal

import pytest

from app.execution.copytrading_sizing import ScalingMode, compute_follower_volume


def test_fixed_ratio_halves_size():
    assert compute_follower_volume(Decimal("1.0"), ScalingMode.fixed_ratio, Decimal("0.5")) == Decimal("0.50")


def test_fixed_ratio_full_size():
    assert compute_follower_volume(Decimal("2.0"), ScalingMode.fixed_ratio, Decimal("1.0")) == Decimal("2.00")


def test_equity_proportional_scales_by_equity_ratio():
    volume = compute_follower_volume(
        Decimal("1.0"), ScalingMode.equity_proportional, Decimal("1.0"),
        source_equity=Decimal("10000"), follower_equity=Decimal("2500"),
    )
    assert volume == Decimal("0.25")


def test_equity_proportional_requires_source_equity():
    with pytest.raises(ValueError):
        compute_follower_volume(Decimal("1.0"), ScalingMode.equity_proportional, Decimal("1.0"))


def test_equity_proportional_requires_follower_equity():
    with pytest.raises(ValueError):
        compute_follower_volume(
            Decimal("1.0"), ScalingMode.equity_proportional, Decimal("1.0"), source_equity=Decimal("10000")
        )


def test_max_follower_volume_caps_result():
    volume = compute_follower_volume(
        Decimal("10.0"), ScalingMode.fixed_ratio, Decimal("1.0"), max_follower_volume=Decimal("2.0")
    )
    assert volume == Decimal("2.00")


def test_below_min_volume_returns_zero():
    volume = compute_follower_volume(Decimal("0.01"), ScalingMode.fixed_ratio, Decimal("0.1"))
    assert volume == Decimal("0")


def test_zero_source_equity_raises():
    with pytest.raises(ValueError):
        compute_follower_volume(
            Decimal("1.0"), ScalingMode.equity_proportional, Decimal("1.0"),
            source_equity=Decimal("0"), follower_equity=Decimal("1000"),
        )
