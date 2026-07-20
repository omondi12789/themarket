"""
WebSocket endpoint for live price streaming. The frontend terminal currently has
nothing pushing it live prices (the order ticket only reads a price at submit time);
this is what a real-time quote ticker / chart price line would subscribe to.

Uses each broker adapter's `stream_quotes()` async generator (already implemented on
every adapter — MT5 polls the terminal, MetaApi polls its REST API, Paper polls the
market data provider) and forwards ticks to the browser over a single WebSocket
connection per subscribed symbol set.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.brokers.base import BrokerConnectionError
from app.brokers.factory import get_broker_adapter
from app.core.config import get_settings
from app.core.security import TokenError, decode_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/quotes")
async def quotes_websocket(websocket: WebSocket) -> None:
    """
    Client connects with `?token=<access_token>&symbols=EURUSD,GBPUSD`. Streams
    {"symbol": ..., "bid": ..., "ask": ..., "timestamp": ...} JSON messages as they
    arrive from the broker adapter's stream_quotes() generator.
    """
    token = websocket.query_params.get("token")
    symbols_param = websocket.query_params.get("symbols", "EURUSD")
    symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]

    try:
        decode_token(token, "access") if token else None
    except TokenError:
        await websocket.close(code=4001, reason="invalid or expired token")
        return

    await websocket.accept()
    settings = get_settings()

    try:
        adapter = get_broker_adapter(settings)
    except BrokerConnectionError as exc:
        await websocket.send_json({"error": f"no broker configured: {exc}"})
        await websocket.close(code=4002)
        return

    try:
        await adapter.connect()
    except BrokerConnectionError as exc:
        await websocket.send_json({"error": f"broker connection failed: {exc}"})
        await websocket.close(code=4002)
        return

    stream_task: asyncio.Task | None = None

    async def _forward_quotes() -> None:
        async for quote in adapter.stream_quotes(symbols):
            await websocket.send_json(
                {
                    "symbol": quote.symbol,
                    "bid": float(quote.bid),
                    "ask": float(quote.ask),
                    "spread": float(quote.spread),
                    "timestamp": quote.timestamp.isoformat(),
                }
            )

    try:
        stream_task = asyncio.create_task(_forward_quotes())
        while True:
            done, _pending = await asyncio.wait(
                [stream_task, asyncio.ensure_future(websocket.receive_text())],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=60,
            )
            if stream_task in done:
                stream_task.result()  # re-raise if the stream generator errored
                break
    except WebSocketDisconnect:
        logger.info("quotes websocket disconnected (symbols=%s)", symbols)
    except Exception:
        logger.exception("quotes websocket error (symbols=%s)", symbols)
    finally:
        if stream_task is not None:
            stream_task.cancel()
        await adapter.disconnect()
