"""
Paper trading adapter: implements BrokerAdapter fully, but fills orders against real
live quotes (from app.marketdata's provider factory) instead of a live broker. This
is what powers a public demo mode — anyone can click around the terminal and place
"trades" against real, current market prices with zero funded-account risk, and zero
extra code path in the execution engine (it's the same BrokerAdapter interface).

Not a backtester: this runs forward in real time against live prices, tracking a
simulated account (balance, positions, PnL) in memory (or Redis, for persistence
across restarts — see `redis_key_prefix`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.brokers.base import (
    AccountSnapshot,
    BrokerAdapter,
    BrokerOrderError,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerPosition,
    OrderRequest,
    OrderResult,
    Quote,
)
from app.core.config import Settings
from app.marketdata.factory import get_configured_providers


class PaperTradingAdapter(BrokerAdapter):
    broker_type = "paper"

    def __init__(
        self,
        settings: Settings,
        starting_balance: Decimal = Decimal("10000"),
        spread_pips: Decimal = Decimal("1.0"),
        leverage: int = 100,
        pip_size: Decimal = Decimal("0.0001"),
        pip_value_per_lot: Decimal = Decimal("10"),
    ):
        self._settings = settings
        self._providers = None  # lazy — only fetched on first quote request
        self.balance = starting_balance
        self.equity = starting_balance
        self.leverage = leverage
        self.spread_pips = spread_pips
        self.pip_size = pip_size
        self.pip_value_per_lot = pip_value_per_lot
        self._positions: dict[str, BrokerPosition] = {}
        self._connected = False

    async def connect(self) -> None:
        self._providers = get_configured_providers(self._settings)
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_account_snapshot(self) -> AccountSnapshot:
        await self._refresh_unrealized()
        margin_used = sum(
            (p.volume * self.pip_value_per_lot * 100) / self.leverage for p in self._positions.values()
        )
        return AccountSnapshot(
            login="paper-demo",
            broker_server="paper-trading-simulator",
            balance=self.balance,
            equity=self.equity,
            margin=Decimal(str(margin_used)),
            free_margin=self.equity - Decimal(str(margin_used)),
            currency="USD",
            leverage=self.leverage,
            is_live=False,
        )

    async def get_quote(self, symbol: str) -> Quote:
        if not self._connected or self._providers is None:
            raise RuntimeError("call connect() before requesting quotes")

        last_error: Exception | None = None
        for provider in self._providers:
            try:
                tick = await provider.get_latest_quote(symbol)
                half_spread = (self.spread_pips * self.pip_size) / 2
                return Quote(
                    symbol=symbol,
                    bid=tick.bid - half_spread,
                    ask=tick.ask + half_spread if tick.ask != tick.bid else tick.bid + 2 * half_spread,
                    timestamp=tick.timestamp,
                )
            except Exception as exc:  # noqa: BLE001 — deliberately broad, we failover to the next provider
                last_error = exc
                continue
        raise RuntimeError(f"no market data provider returned a quote for {symbol}: {last_error}")

    async def stream_quotes(self, symbols: list[str]):
        import asyncio

        while True:
            for s in symbols:
                yield await self.get_quote(s)
            await asyncio.sleep(1.0)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        if request.order_type != BrokerOrderType.market:
            raise BrokerOrderError("PaperTradingAdapter currently only fills market orders instantly")

        quote = await self.get_quote(request.symbol)
        fill_price = quote.ask if request.side == BrokerOrderSide.buy else quote.bid
        position_id = str(uuid.uuid4())

        self._positions[position_id] = BrokerPosition(
            broker_position_id=position_id,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            entry_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=Decimal("0"),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )

        return OrderResult(
            broker_order_id=position_id,
            status="filled",
            filled_price=fill_price,
            filled_volume=request.volume,
            submitted_at=datetime.now(timezone.utc),
            raw={"simulated": True, "spread_pips": str(self.spread_pips)},
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        # No resting/pending orders in this simplified simulator (market orders fill
        # instantly) — nothing to cancel, but the method exists to satisfy the interface.
        return None

    async def get_open_positions(self) -> list[BrokerPosition]:
        await self._refresh_unrealized()
        return list(self._positions.values())

    async def close_position(self, broker_position_id: str, volume: Decimal | None = None) -> OrderResult:
        position = self._positions.get(broker_position_id)
        if position is None:
            raise BrokerOrderError(f"paper position {broker_position_id} not found")

        quote = await self.get_quote(position.symbol)
        exit_price = quote.bid if position.side == BrokerOrderSide.buy else quote.ask
        close_volume = volume if volume is not None else position.volume

        direction = 1 if position.side == BrokerOrderSide.buy else -1
        pips = (exit_price - position.entry_price) * direction / self.pip_size
        pnl = pips * self.pip_value_per_lot * close_volume
        self.balance += pnl

        if volume is not None and volume < position.volume:
            self._positions[broker_position_id] = BrokerPosition(
                broker_position_id=broker_position_id,
                symbol=position.symbol,
                side=position.side,
                volume=position.volume - volume,
                entry_price=position.entry_price,
                current_price=exit_price,
                unrealized_pnl=Decimal("0"),
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
            )
        else:
            del self._positions[broker_position_id]

        return OrderResult(
            broker_order_id=broker_position_id,
            status="filled",
            filled_price=exit_price,
            filled_volume=close_volume,
            submitted_at=datetime.now(timezone.utc),
            raw={"simulated": True, "realized_pnl": str(pnl)},
        )

    async def _refresh_unrealized(self) -> None:
        total_unrealized = Decimal("0")
        for pos_id, position in list(self._positions.items()):
            quote = await self.get_quote(position.symbol)
            current_price = quote.bid if position.side == BrokerOrderSide.buy else quote.ask
            direction = 1 if position.side == BrokerOrderSide.buy else -1
            pips = (current_price - position.entry_price) * direction / self.pip_size
            unrealized = pips * self.pip_value_per_lot * position.volume

            self._positions[pos_id] = BrokerPosition(
                broker_position_id=position.broker_position_id,
                symbol=position.symbol,
                side=position.side,
                volume=position.volume,
                entry_price=position.entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
            )
            total_unrealized += unrealized

        self.equity = self.balance + total_unrealized
