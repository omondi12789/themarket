"""
Finnhub adapter.

Real REST API: https://finnhub.io/docs/api
- Forex candles: GET /forex/candle?symbol=OANDA:EUR_USD&resolution=1&from=...&to=...
- Forex tick/quote: Finnhub's free tier does not expose real-time forex bid/ask quotes
  (that's a premium feature) — free tier forex data is candle/OHLC only. This adapter
  is used for historical bars; get_latest_quote() is implemented via the most recent
  candle close as an approximation, with that limitation documented below.

Free tier: 60 API calls/minute at time of writing — check finnhub.io/pricing before
depending on specific numbers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.marketdata.base import Bar, MarketDataError, MarketDataProvider, Tick, Timeframe

_RESOLUTION_MAP: dict[Timeframe, str] = {
    Timeframe.m1: "1",
    Timeframe.m5: "5",
    Timeframe.m15: "15",
    Timeframe.h1: "60",
    Timeframe.h4: "240",
    Timeframe.d1: "D",
}


class FinnhubAdapter(MarketDataProvider):
    provider_name = "finnhub"
    _BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str, exchange: str = "OANDA", client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._exchange = exchange
        self._client = client or httpx.AsyncClient(timeout=15.0)

    def _to_finnhub_symbol(self, symbol: str) -> str:
        # "EURUSD" -> "OANDA:EUR_USD"
        return f"{self._exchange}:{symbol[:3]}_{symbol[3:]}"

    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        resp = await self._client.get(
            f"{self._BASE_URL}/forex/candle",
            params={
                "symbol": self._to_finnhub_symbol(symbol),
                "resolution": _RESOLUTION_MAP[timeframe],
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
                "token": self._api_key,
            },
        )
        payload = resp.json()
        if resp.status_code != 200 or payload.get("s") != "ok":
            raise MarketDataError(f"Finnhub forex/candle failed: {payload}")

        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
                volume=Decimal(str(v)),
                timestamp=datetime.fromtimestamp(t, tz=timezone.utc),
            )
            for o, h, l, c, v, t in zip(
                payload["o"], payload["h"], payload["l"], payload["c"], payload["v"], payload["t"]
            )
        ]

    async def get_latest_quote(self, symbol: str) -> Tick:
        # Approximation: free-tier Finnhub has no forex bid/ask endpoint, so we use the
        # most recent 1-minute candle's close for both sides. Use Polygon/TwelveData or
        # a broker adapter directly if you need a real bid/ask spread.
        now = datetime.now(timezone.utc)
        bars = await self.get_historical_bars(
            symbol, Timeframe.m1, now.replace(minute=now.minute - 5 if now.minute >= 5 else 0), now
        )
        if not bars:
            raise MarketDataError(f"No recent candle data for {symbol}")

        last = bars[-1]
        return Tick(symbol=symbol, bid=last.close, ask=last.close, timestamp=last.timestamp)
