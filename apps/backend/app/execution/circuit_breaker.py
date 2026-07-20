"""
Circuit breaker: the last line of defense between a runaway strategy/bug and real
account damage. Distinct from RiskGuard (which blocks *new* orders based on rules) —
this actively closes *existing* positions when intraday drawdown breaches a hard
threshold, and sets a flag that blocks all new order placement until manually reset.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.brokers.base import BrokerAdapter, BrokerConnectionError, BrokerOrderError

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    max_intraday_drawdown_pct: Decimal = Decimal("0.05")  # 5% — hard stop, more conservative than RiskGuard's soft daily loss limit
    max_single_position_loss_pct: Decimal = Decimal("0.02")  # flatten one runaway position before it drags the whole account


@dataclass
class CircuitBreakerState:
    tripped: bool = False
    trip_reason: str | None = None
    day_start_equity: Decimal = Decimal("0")


class CircuitBreakerTrippedError(Exception):
    """Raised by anything that tries to place a new order while the breaker is tripped."""


class CircuitBreaker:
    def __init__(self, broker: BrokerAdapter, config: CircuitBreakerConfig | None = None):
        self.broker = broker
        self.config = config or CircuitBreakerConfig()

    async def check_and_enforce(self, state: CircuitBreakerState) -> CircuitBreakerState:
        """
        Call this on every equity-snapshot tick (or before every order). If a
        threshold is breached, flattens every open position and trips the breaker —
        after which `check_and_enforce`/order placement should raise
        CircuitBreakerTrippedError until a human resets `state.tripped = False`.
        """
        if state.tripped:
            raise CircuitBreakerTrippedError(f"circuit breaker is tripped: {state.trip_reason}")

        try:
            snapshot = await self.broker.get_account_snapshot()
        except BrokerConnectionError as exc:
            logger.error("circuit breaker could not fetch account snapshot: %s", exc)
            return state  # fail open on connectivity issues — don't flatten on a network blip

        if state.day_start_equity <= 0:
            state.day_start_equity = snapshot.equity  # first observation of the day seeds the baseline

        drawdown_pct = (state.day_start_equity - snapshot.equity) / state.day_start_equity
        if drawdown_pct >= self.config.max_intraday_drawdown_pct:
            await self._flatten_everything(
                f"intraday drawdown {drawdown_pct:.2%} breached {self.config.max_intraday_drawdown_pct:.2%} limit"
            )
            state.tripped = True
            state.trip_reason = (
                f"intraday drawdown {drawdown_pct:.2%} >= {self.config.max_intraday_drawdown_pct:.2%}"
            )
            return state

        # Per-position runaway-loss check, independent of total drawdown — a single
        # bad position can be worth flattening even if the account overall is fine.
        positions = await self.broker.get_open_positions()
        for position in positions:
            loss_pct = -position.unrealized_pnl / snapshot.equity if snapshot.equity > 0 else Decimal("0")
            if loss_pct >= self.config.max_single_position_loss_pct:
                try:
                    await self.broker.close_position(position.broker_position_id)
                    logger.warning(
                        "circuit breaker flattened runaway position %s (%s): loss %.2f%% of equity",
                        position.broker_position_id, position.symbol, loss_pct * 100,
                    )
                except BrokerOrderError as exc:
                    logger.error("circuit breaker failed to flatten position %s: %s", position.broker_position_id, exc)

        return state

    async def _flatten_everything(self, reason: str) -> None:
        logger.error("CIRCUIT BREAKER TRIPPED: %s — flattening all open positions", reason)
        positions = await self.broker.get_open_positions()
        for position in positions:
            try:
                await self.broker.close_position(position.broker_position_id)
            except BrokerOrderError as exc:
                logger.error(
                    "circuit breaker: failed to close position %s during flatten — MANUAL INTERVENTION NEEDED: %s",
                    position.broker_position_id, exc,
                )
