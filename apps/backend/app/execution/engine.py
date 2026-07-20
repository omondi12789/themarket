"""
Execution engine: the layer between a trading decision (symbol, side, size, stops)
and a broker adapter's place_order() call. Adds what a raw adapter call doesn't:
- Latency measurement around every broker round-trip.
- Slippage measurement (requested vs. filled price).
- Position lifecycle management: trailing stop, break-even move, partial close.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

from app.brokers.base import (
    BrokerAdapter,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerPosition,
    OrderRequest,
    OrderResult,
)
from app.execution.risk_guard import DailyTradeState, RiskGuard, RiskCheckResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionReport:
    order_result: OrderResult
    requested_price: Decimal | None
    filled_price: Decimal | None
    slippage_pips: Decimal | None
    latency_ms: float


class ExecutionEngine:
    def __init__(self, broker: BrokerAdapter, risk_guard: RiskGuard):
        self.broker = broker
        self.risk_guard = risk_guard

    async def execute(
        self, request: OrderRequest, risk_check: RiskCheckResult
    ) -> ExecutionReport:
        if not risk_check.approved:
            raise PermissionError(
                f"order blocked by risk guard: {risk_check.reason} — {risk_check.detail}"
            )

        start = time.perf_counter()
        result = await self.broker.place_order(request)
        latency_ms = (time.perf_counter() - start) * 1000

        slippage_pips = None
        if request.price is not None and result.filled_price is not None:
            direction = 1 if request.side == BrokerOrderSide.buy else -1
            slippage_pips = (result.filled_price - request.price) * direction * Decimal("10000")

        logger.info(
            "order %s %s %s vol=%s latency=%.1fms slippage=%s pips",
            result.broker_order_id, request.side.value, request.symbol,
            request.volume, latency_ms, slippage_pips,
        )

        if latency_ms > 1000:
            logger.warning(
                "high execution latency (%.0fms) for %s — scalping strategies should "
                "monitor this metric and back off if it trends upward",
                latency_ms, request.symbol,
            )

        return ExecutionReport(
            order_result=result,
            requested_price=request.price,
            filled_price=result.filled_price,
            slippage_pips=slippage_pips,
            latency_ms=latency_ms,
        )

    async def apply_trailing_stop(
        self, position: BrokerPosition, trail_distance: Decimal
    ) -> Decimal | None:
        """
        Computes the new stop-loss for a trailing stop, given the current price
        embedded in the position snapshot. Returns None if the trail hasn't moved
        favorably enough to update (avoids spamming modify-order calls every tick).
        Caller is responsible for actually submitting the SL modification to the
        broker — kept separate so this stays broker-call-free and unit-testable.
        """
        if position.side == BrokerOrderSide.buy:
            new_stop = position.current_price - trail_distance
            if position.stop_loss is None or new_stop > position.stop_loss:
                return new_stop
        else:
            new_stop = position.current_price + trail_distance
            if position.stop_loss is None or new_stop < position.stop_loss:
                return new_stop
        return None

    def should_move_to_breakeven(
        self, position: BrokerPosition, breakeven_trigger_rr: Decimal, initial_stop_distance: Decimal
    ) -> bool:
        """
        True once unrealized profit reaches `breakeven_trigger_rr` multiples of the
        initial stop distance (e.g. 1.0 = move to breakeven once the trade is up by
        as much as it was originally risking).
        """
        if position.side == BrokerOrderSide.buy:
            profit_distance = position.current_price - position.entry_price
        else:
            profit_distance = position.entry_price - position.current_price

        if initial_stop_distance <= 0:
            return False
        return (profit_distance / initial_stop_distance) >= breakeven_trigger_rr

    async def partial_close(
        self, position: BrokerPosition, close_fraction: Decimal
    ) -> OrderResult:
        """close_fraction in (0, 1) — e.g. 0.5 closes half the position."""
        if not (Decimal("0") < close_fraction < Decimal("1")):
            raise ValueError("close_fraction must be strictly between 0 and 1")
        close_volume = (position.volume * close_fraction).quantize(Decimal("0.01"))
        return await self.broker.close_position(position.broker_position_id, volume=close_volume)
