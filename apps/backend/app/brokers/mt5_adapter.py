"""
MetaTrader 5 adapter — official `MetaTrader5` Python package.

Reality check (this is the free, first-priority option from the spec):
- Free, but only works against a *running* MT5 terminal — local machine or a Windows VPS.
- The package is Windows-only (it talks to the terminal via native IPC). On Linux/macOS
  you run it inside a Windows VM/VPS, or under Wine — there is no official Linux build.
  That's why this repo also ships the MetaApi adapter (`metaapi.py`) as a cloud fallback
  that works from any OS/container, at the cost of MetaApi's own free-tier limits.
- No official async API: MetaTrader5's calls are blocking, so this adapter runs them in
  a thread pool via `asyncio.to_thread` to keep the rest of the service non-blocking.
- Historical/live data quality depends entirely on what your broker's MT5 server provides.

Install: pip install MetaTrader5   (Windows only)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from app.brokers.base import (
    AccountSnapshot,
    BrokerAdapter,
    BrokerConnectionError,
    BrokerOrderError,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerPosition,
    OrderRequest,
    OrderResult,
    Quote,
)

try:
    import MetaTrader5 as mt5  # type: ignore
except ImportError:  # pragma: no cover - only available on Windows
    mt5 = None


class MT5Adapter(BrokerAdapter):
    broker_type = "mt5"

    def __init__(self, login: int, password: str, server: str, terminal_path: str | None = None):
        if mt5 is None:
            raise BrokerConnectionError(
                "MetaTrader5 package is not installed/available. It is Windows-only; "
                "run this adapter on a Windows host/VPS or use the MetaApi adapter instead."
            )
        self._login = login
        self._password = password
        self._server = server
        self._terminal_path = terminal_path

    async def connect(self) -> None:
        def _connect() -> bool:
            kwargs = {"login": self._login, "password": self._password, "server": self._server}
            if self._terminal_path:
                return mt5.initialize(self._terminal_path, **kwargs)
            return mt5.initialize(**kwargs)

        ok = await asyncio.to_thread(_connect)
        if not ok:
            error = mt5.last_error()
            raise BrokerConnectionError(f"MT5 initialize() failed: {error}")

    async def disconnect(self) -> None:
        await asyncio.to_thread(mt5.shutdown)

    async def get_account_snapshot(self) -> AccountSnapshot:
        info = await asyncio.to_thread(mt5.account_info)
        if info is None:
            raise BrokerConnectionError(f"account_info() failed: {mt5.last_error()}")
        return AccountSnapshot(
            login=str(info.login),
            broker_server=self._server,
            balance=Decimal(str(info.balance)),
            equity=Decimal(str(info.equity)),
            margin=Decimal(str(info.margin)),
            free_margin=Decimal(str(info.margin_free)),
            currency=info.currency,
            leverage=info.leverage,
            is_live=(info.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL),
        )

    async def get_quote(self, symbol: str) -> Quote:
        tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            raise BrokerConnectionError(f"symbol_info_tick({symbol}) failed: {mt5.last_error()}")
        return Quote(
            symbol=symbol,
            bid=Decimal(str(tick.bid)),
            ask=Decimal(str(tick.ask)),
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
        )

    async def stream_quotes(self, symbols: list[str]):
        """
        MetaTrader5's python package has no native push/streaming API — it's a
        request/response terminal bridge. We poll on a short interval per symbol,
        which is the standard approach for this package; latency is bounded by the
        poll interval plus terminal IPC round-trip (typically 10-50ms locally).
        """
        for s in symbols:
            await asyncio.to_thread(mt5.symbol_select, s, True)

        while True:
            for s in symbols:
                yield await self.get_quote(s)
            await asyncio.sleep(0.25)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        order_type_map = {
            (BrokerOrderSide.buy, BrokerOrderType.market): mt5.ORDER_TYPE_BUY,
            (BrokerOrderSide.sell, BrokerOrderType.market): mt5.ORDER_TYPE_SELL,
            (BrokerOrderSide.buy, BrokerOrderType.limit): mt5.ORDER_TYPE_BUY_LIMIT,
            (BrokerOrderSide.sell, BrokerOrderType.limit): mt5.ORDER_TYPE_SELL_LIMIT,
            (BrokerOrderSide.buy, BrokerOrderType.stop): mt5.ORDER_TYPE_BUY_STOP,
            (BrokerOrderSide.sell, BrokerOrderType.stop): mt5.ORDER_TYPE_SELL_STOP,
            (BrokerOrderSide.buy, BrokerOrderType.stop_limit): mt5.ORDER_TYPE_BUY_STOP_LIMIT,
            (BrokerOrderSide.sell, BrokerOrderType.stop_limit): mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }
        mt5_type = order_type_map[(request.side, request.order_type)]

        tick = await self.get_quote(request.symbol)
        price = float(request.price) if request.price else float(
            tick.ask if request.side == BrokerOrderSide.buy else tick.bid
        )

        req = {
            "action": mt5.TRADE_ACTION_DEAL
            if request.order_type == BrokerOrderType.market
            else mt5.TRADE_ACTION_PENDING,
            "symbol": request.symbol,
            "volume": float(request.volume),
            "type": mt5_type,
            "price": price,
            "sl": float(request.stop_loss) if request.stop_loss else 0.0,
            "tp": float(request.take_profit) if request.take_profit else 0.0,
            "comment": request.comment or "themarket-ai",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if request.order_type == BrokerOrderType.stop_limit and request.stop_price:
            req["stoplimit"] = float(request.stop_price)

        result = await asyncio.to_thread(mt5.order_send, req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerOrderError(f"order_send failed: retcode={getattr(result, 'retcode', None)}")

        return OrderResult(
            broker_order_id=str(result.order),
            status="filled" if request.order_type == BrokerOrderType.market else "submitted",
            filled_price=Decimal(str(result.price)) if result.price else None,
            filled_volume=Decimal(str(result.volume)),
            submitted_at=datetime.now(timezone.utc),
            raw=result._asdict(),
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        req = {"action": mt5.TRADE_ACTION_REMOVE, "order": int(broker_order_id)}
        result = await asyncio.to_thread(mt5.order_send, req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerOrderError(f"cancel failed: retcode={getattr(result, 'retcode', None)}")

    async def get_open_positions(self) -> list[BrokerPosition]:
        positions = await asyncio.to_thread(mt5.positions_get)
        if positions is None:
            return []
        return [
            BrokerPosition(
                broker_position_id=str(p.ticket),
                symbol=p.symbol,
                side=BrokerOrderSide.buy if p.type == mt5.POSITION_TYPE_BUY else BrokerOrderSide.sell,
                volume=Decimal(str(p.volume)),
                entry_price=Decimal(str(p.price_open)),
                current_price=Decimal(str(p.price_current)),
                unrealized_pnl=Decimal(str(p.profit)),
                stop_loss=Decimal(str(p.sl)) if p.sl else None,
                take_profit=Decimal(str(p.tp)) if p.tp else None,
            )
            for p in positions
        ]

    async def close_position(self, broker_position_id: str, volume: Decimal | None = None) -> OrderResult:
        positions = await asyncio.to_thread(mt5.positions_get, ticket=int(broker_position_id))
        if not positions:
            raise BrokerOrderError(f"position {broker_position_id} not found")
        pos = positions[0]

        close_side = BrokerOrderSide.sell if pos.type == mt5.POSITION_TYPE_BUY else BrokerOrderSide.buy
        close_volume = float(volume) if volume else pos.volume
        tick = await self.get_quote(pos.symbol)
        price = float(tick.bid if close_side == BrokerOrderSide.sell else tick.ask)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": mt5.ORDER_TYPE_SELL if close_side == BrokerOrderSide.sell else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": price,
            "comment": "themarket-ai-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = await asyncio.to_thread(mt5.order_send, req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerOrderError(f"close_position failed: retcode={getattr(result, 'retcode', None)}")

        return OrderResult(
            broker_order_id=str(result.order),
            status="filled",
            filled_price=Decimal(str(result.price)) if result.price else None,
            filled_volume=Decimal(str(result.volume)),
            submitted_at=datetime.now(timezone.utc),
            raw=result._asdict(),
        )
