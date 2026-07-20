from decimal import Decimal

from app.execution.sizing import atr_based_stops, correlation_adjusted_size, kelly_adjusted_size, volatility_scaled_size


def test_volatility_scaled_size_basic():
    result = volatility_scaled_size(
        account_equity=Decimal("10000"),
        risk_per_trade_pct=Decimal("0.01"),
        atr=Decimal("0.0010"),
        atr_stop_multiple=Decimal("1.5"),
        pip_value_per_lot=Decimal("10"),
    )
    # risk_amount = 100; stop_distance_pips = 15; volume = 100 / (15*10) = 0.6667
    assert result.risk_amount == Decimal("100.00")
    assert abs(result.volume - Decimal("0.67")) <= Decimal("0.01")


def test_volatility_scaled_size_caps_at_max_volume():
    result = volatility_scaled_size(
        account_equity=Decimal("1000000"),
        risk_per_trade_pct=Decimal("0.05"),
        atr=Decimal("0.0001"),
        atr_stop_multiple=Decimal("1.0"),
        pip_value_per_lot=Decimal("1"),
        max_volume=Decimal("10"),
    )
    assert result.volume == Decimal("10")


def test_volatility_scaled_size_rejects_invalid_inputs():
    result = volatility_scaled_size(
        account_equity=Decimal("10000"),
        risk_per_trade_pct=Decimal("0.01"),
        atr=Decimal("0"),
        atr_stop_multiple=Decimal("1.5"),
        pip_value_per_lot=Decimal("10"),
    )
    assert result.volume == Decimal("0")


def test_atr_based_stops_buy_side():
    stops = atr_based_stops(
        entry_price=Decimal("1.1000"),
        atr=Decimal("0.0010"),
        side="buy",
        stop_multiple=Decimal("1.5"),
        reward_risk_ratio=Decimal("2.0"),
    )
    # stop_distance = 0.0015; SL = 1.1000 - 0.0015 = 1.0985; TP = 1.1000 + 0.0030 = 1.1030
    assert stops.stop_loss == Decimal("1.0985")
    assert stops.take_profit == Decimal("1.1030")


def test_atr_based_stops_sell_side_mirrors_buy():
    stops = atr_based_stops(
        entry_price=Decimal("1.1000"),
        atr=Decimal("0.0010"),
        side="sell",
        stop_multiple=Decimal("1.5"),
        reward_risk_ratio=Decimal("2.0"),
    )
    assert stops.stop_loss == Decimal("1.1015")
    assert stops.take_profit == Decimal("1.0970")


def test_kelly_adjusted_size_scales_base_volume():
    base = volatility_scaled_size(
        account_equity=Decimal("10000"),
        risk_per_trade_pct=Decimal("0.01"),
        atr=Decimal("0.0010"),
        atr_stop_multiple=Decimal("1.5"),
        pip_value_per_lot=Decimal("10"),
    )
    adjusted = kelly_adjusted_size(base, kelly_fraction=0.5, confidence=0.8)
    # multiplier = min(max(0.5*0.8*2, 0.1), 1.5) = min(0.8, 1.5) = 0.8
    assert adjusted.volume == (base.volume * Decimal("0.8")).quantize(Decimal("0.01"))


def _base_size():
    return volatility_scaled_size(
        account_equity=Decimal("10000"),
        risk_per_trade_pct=Decimal("0.01"),
        atr=Decimal("0.0010"),
        atr_stop_multiple=Decimal("1.5"),
        pip_value_per_lot=Decimal("10"),
    )


def test_correlation_adjusted_size_unaffected_with_no_existing_positions():
    base = _base_size()
    adjusted = correlation_adjusted_size(base, "EURUSD", "buy", existing_positions=[])
    assert adjusted.volume == base.volume


def test_correlation_adjusted_size_reduces_for_correlated_same_direction():
    base = _base_size()
    # Already long GBPUSD, correlation to EURUSD is 0.85 (highly correlated), same direction (buy/buy)
    adjusted = correlation_adjusted_size(
        base, "EURUSD", "buy", existing_positions=[("GBPUSD", "buy", Decimal("0.85"))]
    )
    assert adjusted.volume < base.volume
    assert adjusted.volume == (base.volume * Decimal("0.75")).quantize(Decimal("0.01"))


def test_correlation_adjusted_size_ignores_opposite_direction_hedge():
    base = _base_size()
    # Already short GBPUSD, correlation 0.85, but new trade is a buy -> opposite direction -> hedging, not compounding risk
    adjusted = correlation_adjusted_size(
        base, "EURUSD", "buy", existing_positions=[("GBPUSD", "sell", Decimal("0.85"))]
    )
    assert adjusted.volume == base.volume


def test_correlation_adjusted_size_ignores_low_correlation():
    base = _base_size()
    adjusted = correlation_adjusted_size(
        base, "EURUSD", "buy", existing_positions=[("USDJPY", "buy", Decimal("0.1"))]
    )
    assert adjusted.volume == base.volume


def test_correlation_adjusted_size_caps_at_max_reduction():
    base = _base_size()
    # 5 correlated same-direction positions at 25% reduction each would be 125% -> capped at 75%
    positions = [(f"SYM{i}", "buy", Decimal("0.9")) for i in range(5)]
    adjusted = correlation_adjusted_size(base, "EURUSD", "buy", existing_positions=positions)
    assert adjusted.volume == (base.volume * Decimal("0.25")).quantize(Decimal("0.01"))
