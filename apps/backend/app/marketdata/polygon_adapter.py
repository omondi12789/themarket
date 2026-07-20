"""
Polygon.io adapter (forex aggregates + last quote).

Real REST API: https://polygon.io/docs/forex
- Aggregates: GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
  Forex tickers are prefixed with "C:", e.g. "C:EURUSD".
- Last quote: GET /v1/last_quote/currencies/{from}/{to}

Free tier: 5 API calls/minute, end-of-day data only (no real-time). Paid tiers unlock
real-time and higher rate limits — check polygon.io/pricing for current numbers before
relying on specific limits in code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.marketdata.base import Bar, MarketDataError, MarketDataProvider, Tick, Timeframe

_TIMEFRAME_MAP: dict[Timeframe, tuple[int, str]] = {
    Timeframe.m1: (1, "minute"),
    Timeframe.m5: (5, "minute"),
    Timeframe.m15: (15, "minute"),
    Timeframe.h1: (1, "hour"),
    Timeframe.h4: (4, "hour"),
    Timeframe.d1: (1, "day"),
}


class PolygonAdapter(MarketDataProvider):
    provider_name = "polygon"
    _BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)

    @staticmethod
    def _to_polygon_ticker(symbol: str) -> str:
        # "EURUSD" -> "C:EURUSD"
        return symbol if symbol.startswith("C:") else f"C:{symbol}"

    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        multiplier, timespan = _TIMEFRAME_MAP[timeframe]
        ticker = self._to_polygon_ticker(symbol)
        url = (
            f"{self._BASE_URL}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/"
            f"{start.date().isoformat()}/{end.date().isoformat()}"
        )
        resp = await self._client.get(
            url, params={"apiKey": self._api_key, "sort": "asc", "limit": 50000}
        )
        if resp.status_code != 200:
            raise MarketDataError(f"Polygon aggregates request failed: {resp.status_code} {resp.text}")

        payload = resp.json()
        results = payload.get("results", [])
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                open=Decimal(str(r["o"])),
                high=Decimal(str(r["h"])),
                low=Decimal(str(r["l"])),
                close=Decimal(str(r["c"])),
                volume=Decimal(str(r.get("v", 0))),
                timestamp=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
            )
            for r in results
        ]

    async def get_latest_quote(self, symbol: str) -> Tick:
        base, quote = symbol[:3], symbol[3:]
        url = f"{self._BASE_URL}/v1/last_quote/currencies/{base}/{quote}"
        resp = await self._client.get(url, params={"apiKey": self._api_key})
        if resp.status_code != 200:
            raise MarketDataError(f"Polygon last_quote request failed: {resp.status_code} {resp.text}")

        payload = resp.json().get("last", {})
        return Tick(
            symbol=symbol,
            bid=Decimal(str(payload["bid"])),
            ask=Decimal(str(payload["ask"])),
            timestamp=datetime.fromtimestamp(payload["timestamp"] / 1000, tz=timezone.utc),
        )
