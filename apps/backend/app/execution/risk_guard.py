"""
Pre-trade risk guards. Every order from the scalping/execution engine passes through
`RiskGuard.check()` before it reaches a broker adapter. This is a hard gate, not
advisory — a rejection here means the order is never sent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal
from enum import Enum


class RejectionReason(str, Enum):
    daily_loss_limit_hit = "daily_loss_limit_hit"
    max_trades_reached = "max_trades_reached"
    outside_trading_session = "outside_trading_session"
    news_blackout = "news_blackout"
    spread_too_wide = "spread_too_wide"
    concentration_limit_exceeded = "concentration_limit_exceeded"


@dataclass(frozen=True)
class RiskCheckResult:
    approved: bool
    reason: RejectionReason | None = None
    detail: str = ""


@dataclass
class TradingSession:
    """UTC start/end for a session window, e.g. London 07:00-16:00 UTC."""

    name: str
    start_utc: time
    end_utc: time

    def contains(self, ts: datetime) -> bool:
        t = ts.astimezone(timezone.utc).time()
        if self.start_utc <= self.end_utc:
            return self.start_utc <= t <= self.end_utc
        return t >= self.start_utc or t <= self.end_utc  # wraps midnight


# Standard forex session windows (UTC), commonly used for session-filtered strategies.
SYDNEY = TradingSession("sydney", time(21, 0), time(6, 0))
TOKYO = TradingSession("tokyo", time(0, 0), time(9, 0))
LONDON = TradingSession("london", time(7, 0), time(16, 0))
NEW_YORK = TradingSession("new_york", time(12, 0), time(21, 0))


@dataclass
class NewsEvent:
    timestamp: datetime
    currency: str
    impact: str  # "low" | "medium" | "high"
    title: str


@dataclass
class DailyTradeState:
    """Mutable per-account, per-day counters — reset at UTC midnight by the caller."""

    trade_count: int = 0
    realized_pnl: Decimal = Decimal("0")
    day: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskGuardConfig:
    max_daily_loss_pct: Decimal = Decimal("0.03")  # 3% of starting-of-day equity
    max_trades_per_day: int = 20
    max_spread_pips: Decimal = Decimal("3.0")
    allowed_sessions: list[TradingSession] = field(default_factory=lambda: [LONDON, NEW_YORK])
    news_blackout_minutes_before: int = 15
    news_blackout_minutes_after: int = 15
    news_blackout_min_impact: str = "high"
    max_correlated_same_direction_positions: int = 3  # hard cap, independent of the size-reduction in sizing.py


class RiskGuard:
    def __init__(self, config: RiskGuardConfig):
        self.config = config

    def check(
        self,
        *,
        state: DailyTradeState,
        starting_equity: Decimal,
        current_spread_pips: Decimal,
        now: datetime,
        upcoming_news: list[NewsEvent],
        symbol_currencies: tuple[str, str],
        correlated_same_direction_count: int = 0,
    ) -> RiskCheckResult:
        # 1. Daily loss limit
        loss_limit = starting_equity * self.config.max_daily_loss_pct
        if state.realized_pnl <= -loss_limit:
            return RiskCheckResult(
                False, RejectionReason.daily_loss_limit_hit,
                f"realized PnL {state.realized_pnl} breached -{loss_limit} limit for the day",
            )

        # 2. Max trades per day
        if state.trade_count >= self.config.max_trades_per_day:
            return RiskCheckResult(
                False, RejectionReason.max_trades_reached,
                f"{state.trade_count} trades already taken today (limit {self.config.max_trades_per_day})",
            )

        # 3. Session filter
        if self.config.allowed_sessions and not any(s.contains(now) for s in self.config.allowed_sessions):
            return RiskCheckResult(
                False, RejectionReason.outside_trading_session,
                f"{now.isoformat()} is outside allowed sessions "
                f"({[s.name for s in self.config.allowed_sessions]})",
            )

        # 4. News blackout
        impact_rank = {"low": 0, "medium": 1, "high": 2}
        min_rank = impact_rank[self.config.news_blackout_min_impact]
        for event in upcoming_news:
            if event.currency not in symbol_currencies:
                continue
            if impact_rank.get(event.impact, 0) < min_rank:
                continue
            minutes_to_event = (event.timestamp - now).total_seconds() / 60
            if -self.config.news_blackout_minutes_after <= minutes_to_event <= self.config.news_blackout_minutes_before:
                return RiskCheckResult(
                    False, RejectionReason.news_blackout,
                    f"{event.title} ({event.impact} impact, {event.currency}) at {event.timestamp.isoformat()}",
                )

        # 5. Spread filter
        if current_spread_pips > self.config.max_spread_pips:
            return RiskCheckResult(
                False, RejectionReason.spread_too_wide,
                f"spread {current_spread_pips} pips exceeds max {self.config.max_spread_pips}",
            )

        # 6. Concentration limit — hard cap on correlated same-direction exposure,
        # independent of sizing.py's soft size-reduction for the same scenario.
        if correlated_same_direction_count >= self.config.max_correlated_same_direction_positions:
            return RiskCheckResult(
                False, RejectionReason.concentration_limit_exceeded,
                f"{correlated_same_direction_count} correlated same-direction positions already open "
                f"(limit {self.config.max_correlated_same_direction_positions})",
            )

        return RiskCheckResult(True)
