"""
MetaApi.cloud adapter — real cloud broker gateway to MT4/MT5 accounts.

Reality check (this is the spec's priority-2 fallback):
- Works from any OS/container (unlike the official MetaTrader5 package, which is
  Windows-only) because MetaApi hosts the actual MT4/MT5 terminal for you in their cloud
  and exposes a REST/WebSocket API + Python SDK.
- Free tier exists but is limited: at time of writing it's capped to a small number of
  trading accounts and has request-rate limits; production/scale use requires a paid
  plan. Check https://metaapi.cloud/pricing for current numbers before relying on it.
- Latency is inherently higher than a co-located MT5 terminal, since your order has to
  travel to MetaApi's cloud, then to the broker's server. Fine for swing/position
  trading; a real handicap for sub-second scalping — see docs/broker-comparison.md.
- Install: pip install metaapi-cloud-sdk
"""
from __future__ import annotations

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
    from metaapi_cloud_sdk import MetaApi  # type: ignore
except ImportError:  # pragma: no cover - installed via requirements at deploy time
    MetaApi = None


class MetaApiAdapter(BrokerAdapter):
    broker_type = "metaapi"

    def __init__(self, token: str, account_id: str):
        if MetaApi is None:
            raise BrokerConnectionError(
                "metaapi-cloud-sdk is not installed. Add it to requirements.txt and "
                "`pip install metaapi-cloud-sdk`."
            )
        self._api = MetaApi(token)
        self._account_id = account_id
        self._account = None
        self._connection = None

    async def connect(self) -> None:
        try:
            self._account = await self._api.metatrader_account_api.get_account(self._account_id)
            if self._account.state != "DEPLOYED":
                await self._account.deploy()
            await self._account.wait_connected()

            self._connection = self._account.get_rpc_connection()
            await self._connection.connect()
            await self._connection.wait_synchronized()
        except Exception as exc:  # MetaApi raises its own exception hierarchy
            raise BrokerConnectionError(f"MetaApi connect failed: {exc}") from exc

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()

    async def get_account_snapshot(self) -> AccountSnapshot:
        info = await self._connection.get_account_information()
        return AccountSnapshot(
            login=str(info["login"]),
            broker_server=info.get("server", ""),
            balance=Decimal(str(info["balance"])),
            equity=Decimal(str(info["equity"])),
            margin=Decimal(str(info["margin"])),
            free_margin=Decimal(str(info["freeMargin"])),
            currency=info["currency"],
            leverage=int(info["leverage"]),
            is_live=not info.get("isDemo", False),
        )

    async def get_quote(self, symbol: str) -> Quote:
        price = await self._connection.get_symbol_price(symbol)
        return Quote(
            symbol=symbol,
            bid=Decimal(str(price["bid"])),
            ask=Decimal(str(price["ask"])),
            timestamp=datetime.now(timezone.utc),
        )

    async def stream_quotes(self, symbols: list[str]):
        """
        Uses MetaApi's streaming connection + a synchronization listener would be the
        production approach (push-based, low overhead). To keep this adapter's public
        surface identical to MT5Adapter's polling generator, we poll here too; swap in
        `account.get_streaming_connection()` + an `on_symbol_price_updated` listener
        for lower latency once you're past prototyping.
        """
        import asyncio

        while True:
            for s in symbols:
                yield await self.get_quote(s)
            await asyncio.sleep(0.5)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            if request.order_type == BrokerOrderType.market:
                method = (
                    self._connection.create_market_buy_order
                    if request.side == BrokerOrderSide.buy
                    else self._connection.create_market_sell_order
                )
                result = await method(
                    request.symbol,
                    float(request.volume),
                    stop_loss=float(request.stop_loss) if request.stop_loss else None,
                    take_profit=float(request.take_profit) if request.take_profit else None,
                    options={"comment": request.comment or "themarket-ai"},
                )
            else:
                method = (
                    self._connection.create_limit_buy_order
                    if request.side == BrokerOrderSide.buy
                    else self._connection.create_limit_sell_order
                )
                result = await method(
                    request.symbol,
                    float(request.volume),
                    float(request.price),
                    stop_loss=float(request.stop_loss) if request.stop_loss else None,
                    take_profit=float(request.take_profit) if request.take_profit else None,
                    options={"comment": request.comment or "themarket-ai"},
                )
        except Exception as exc:
            raise BrokerOrderError(f"MetaApi order failed: {exc}") from exc

        return OrderResult(
            broker_order_id=str(result.get("orderId") or result.get("positionId")),
            status="filled" if request.order_type == BrokerOrderType.market else "submitted",
            filled_price=Decimal(str(result["price"])) if result.get("price") else None,
            filled_volume=request.volume,
            submitted_at=datetime.now(timezone.utc),
            raw=result,
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        try:
            await self._connection.cancel_order(broker_order_id)
        except Exception as exc:
            raise BrokerOrderError(f"MetaApi cancel failed: {exc}") from exc

    async def get_open_positions(self) -> list[BrokerPosition]:
        positions = await self._connection.get_positions()
        return [
            BrokerPosition(
                broker_position_id=str(p["id"]),
                symbol=p["symbol"],
                side=BrokerOrderSide.buy if p["type"] == "POSITION_TYPE_BUY" else BrokerOrderSide.sell,
                volume=Decimal(str(p["volume"])),
                entry_price=Decimal(str(p["openPrice"])),
                current_price=Decimal(str(p["currentPrice"])),
                unrealized_pnl=Decimal(str(p["profit"])),
                stop_loss=Decimal(str(p["stopLoss"])) if p.get("stopLoss") else None,
                take_profit=Decimal(str(p["takeProfit"])) if p.get("takeProfit") else None,
            )
            for p in positions
        ]

    async def close_position(self, broker_position_id: str, volume: Decimal | None = None) -> OrderResult:
        try:
            if volume is not None:
                result = await self._connection.close_position_partially(
                    broker_position_id, float(volume)
                )
            else:
                result = await self._connection.close_position(broker_position_id)
        except Exception as exc:
            raise BrokerOrderError(f"MetaApi close_position failed: {exc}") from exc

        return OrderResult(
            broker_order_id=str(result.get("orderId", broker_position_id)),
            status="filled",
            filled_price=Decimal(str(result["price"])) if result.get("price") else None,
            filled_volume=volume if volume is not None else Decimal("0"),
            submitted_at=datetime.now(timezone.utc),
            raw=result,
        )
