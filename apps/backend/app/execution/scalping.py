"""
Scalping engine: orchestrates a single trade decision end-to-end for short-timeframe
(1-5min/tick) strategies. This is the glue layer the spec asked for — everything else
(sizing, risk_guard, engine) is reusable by swing/position strategies too; this module
is what's scalping-specific: tight ATR stops, small reward:risk, and a strict pipeline
that refuses to trade through any risk-guard rejection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.brokers.base import BrokerAdapter, BrokerOrderSide, BrokerOrderType, OrderRequest, Quote
from app.execution.engine import ExecutionEngine, ExecutionReport
from app.execution.risk_guard import DailyTradeState, NewsEvent, RiskGuard
from app.execution.sizing import atr_based_stops, volatility_scaled_size

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScalpSignal:
    symbol: str
    side: BrokerOrderSide
    confidence: float  # 0-1, from the AI decision system
    atr: Decimal


@dataclass(frozen=True)
class ScalpConfig:
    risk_per_trade_pct: Decimal = Decimal("0.0025")  # 0.25% — tight, scalping-appropriate
    atr_stop_multiple: Decimal = Decimal("1.0")
    reward_risk_ratio: Decimal = Decimal("1.5")
    min_confidence: float = 0.6


class ScalpingEngine:
    def __init__(
        self,
        broker: BrokerAdapter,
        risk_guard: RiskGuard,
        execution_engine: ExecutionEngine,
        config: ScalpConfig | None = None,
    ):
        self.broker = broker
        self.risk_guard = risk_guard
        self.execution_engine = execution_engine
        self.config = config or ScalpConfig()

    async def process_signal(
        self,
        signal: ScalpSignal,
        *,
        account_equity: Decimal,
        pip_value_per_lot: Decimal,
        daily_state: DailyTradeState,
        starting_equity: Decimal,
        upcoming_news: list[NewsEvent],
        now,
    ) -> ExecutionReport | None:
        if signal.confidence < self.config.min_confidence:
            logger.info(
                "scalp signal for %s rejected: confidence %.2f below threshold %.2f",
                signal.symbol, signal.confidence, self.config.min_confidence,
            )
            return None

        quote: Quote = await self.broker.get_quote(signal.symbol)
        spread_pips = quote.spread * Decimal("10000")

        risk_check = self.risk_guard.check(
            state=daily_state,
            starting_equity=starting_equity,
            current_spread_pips=spread_pips,
            now=now,
            upcoming_news=upcoming_news,
            symbol_currencies=(signal.symbol[:3], signal.symbol[3:]),
        )
        if not risk_check.approved:
            logger.info("scalp signal for %s rejected by risk guard: %s", signal.symbol, risk_check.detail)
            return None

        entry_price = quote.ask if signal.side == BrokerOrderSide.buy else quote.bid
        stops = atr_based_stops(
            entry_price=entry_price,
            atr=signal.atr,
            side=signal.side.value,
            stop_multiple=self.config.atr_stop_multiple,
            reward_risk_ratio=self.config.reward_risk_ratio,
        )
        sizing = volatility_scaled_size(
            account_equity=account_equity,
            risk_per_trade_pct=self.config.risk_per_trade_pct,
            atr=signal.atr,
            atr_stop_multiple=self.config.atr_stop_multiple,
            pip_value_per_lot=pip_value_per_lot,
        )
        if sizing.volume <= 0:
            logger.warning("scalp signal for %s produced zero position size — skipping", signal.symbol)
            return None

        order = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            order_type=BrokerOrderType.market,
            volume=sizing.volume,
            stop_loss=stops.stop_loss,
            take_profit=stops.take_profit,
            comment=f"scalp conf={signal.confidence:.2f}",
        )

        report = await self.execution_engine.execute(order, risk_check)
        daily_state.trade_count += 1
        return report
