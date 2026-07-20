from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.execution.risk_guard import (
    DailyTradeState,
    NewsEvent,
    RejectionReason,
    RiskGuard,
    RiskGuardConfig,
    TradingSession,
)

LONDON_NOON = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _guard(**overrides) -> RiskGuard:
    config = RiskGuardConfig(**overrides)
    return RiskGuard(config)


def _base_check(guard: RiskGuard, **overrides):
    kwargs = dict(
        state=DailyTradeState(),
        starting_equity=Decimal("10000"),
        current_spread_pips=Decimal("1.0"),
        now=LONDON_NOON,
        upcoming_news=[],
        symbol_currencies=("EUR", "USD"),
    )
    kwargs.update(overrides)
    return guard.check(**kwargs)


def test_approves_a_clean_trade():
    guard = _guard()
    result = _base_check(guard)
    assert result.approved is True
    assert result.reason is None


def test_rejects_when_daily_loss_limit_hit():
    guard = _guard(max_daily_loss_pct=Decimal("0.03"))
    state = DailyTradeState(realized_pnl=Decimal("-350"))  # -3.5% > -3% limit
    result = _base_check(guard, state=state)
    assert result.approved is False
    assert result.reason == RejectionReason.daily_loss_limit_hit


def test_allows_trade_exactly_at_loss_boundary_but_not_beyond():
    guard = _guard(max_daily_loss_pct=Decimal("0.03"))
    # exactly -3% (== -300) should NOT yet block (guard uses <=, boundary is a loss stop)
    state_at_limit = DailyTradeState(realized_pnl=Decimal("-300"))
    result = _base_check(guard, state=state_at_limit)
    assert result.approved is False  # <= triggers at the exact limit, by design

    state_within = DailyTradeState(realized_pnl=Decimal("-299"))
    result_within = _base_check(guard, state=state_within)
    assert result_within.approved is True


def test_rejects_when_max_trades_reached():
    guard = _guard(max_trades_per_day=5)
    state = DailyTradeState(trade_count=5)
    result = _base_check(guard, state=state)
    assert result.approved is False
    assert result.reason == RejectionReason.max_trades_reached


def test_rejects_outside_allowed_session():
    tokyo_only = TradingSession("tokyo", time(0, 0), time(9, 0))
    guard = _guard(allowed_sessions=[tokyo_only])
    result = _base_check(guard, now=LONDON_NOON)  # noon UTC is outside 00:00-09:00
    assert result.approved is False
    assert result.reason == RejectionReason.outside_trading_session


def test_approves_inside_allowed_session():
    london_session = TradingSession("london", time(7, 0), time(16, 0))
    guard = _guard(allowed_sessions=[london_session])
    result = _base_check(guard, now=LONDON_NOON)
    assert result.approved is True


def test_rejects_during_high_impact_news_blackout():
    guard = _guard(news_blackout_minutes_before=15, news_blackout_minutes_after=15)
    news = NewsEvent(
        timestamp=LONDON_NOON + timedelta(minutes=10), currency="USD", impact="high", title="NFP"
    )
    result = _base_check(guard, upcoming_news=[news])
    assert result.approved is False
    assert result.reason == RejectionReason.news_blackout


def test_ignores_low_impact_news():
    guard = _guard(news_blackout_min_impact="high")
    news = NewsEvent(
        timestamp=LONDON_NOON + timedelta(minutes=5), currency="USD", impact="low", title="Minor release"
    )
    result = _base_check(guard, upcoming_news=[news])
    assert result.approved is True


def test_ignores_news_for_unrelated_currency():
    guard = _guard()
    news = NewsEvent(
        timestamp=LONDON_NOON + timedelta(minutes=5), currency="JPY", impact="high", title="BOJ rate decision"
    )
    result = _base_check(guard, upcoming_news=[news], symbol_currencies=("EUR", "USD"))
    assert result.approved is True


def test_rejects_wide_spread():
    guard = _guard(max_spread_pips=Decimal("2.0"))
    result = _base_check(guard, current_spread_pips=Decimal("3.5"))
    assert result.approved is False
    assert result.reason == RejectionReason.spread_too_wide


def test_checks_run_in_priority_order_loss_limit_first():
    """When multiple conditions fail at once, daily loss limit is checked first."""
    guard = _guard(max_daily_loss_pct=Decimal("0.01"), max_trades_per_day=0)
    state = DailyTradeState(realized_pnl=Decimal("-200"), trade_count=99)
    result = _base_check(guard, state=state)
    assert result.reason == RejectionReason.daily_loss_limit_hit
