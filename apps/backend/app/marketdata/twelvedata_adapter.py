"""
TwelveData adapter.

Real REST API: https://twelvedata.com/docs
- Time series: GET /time_series?symbol=EUR/USD&interval=1min&apikey=...
- Real-time price: GET /price?symbol=EUR/USD&apikey=...

Free tier: 8 requests/minute, 800/day at time of writing — check twelvedata.com/pricing
for current limits before depending on specific numbers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.marketdata.base import Bar, MarketDataError, MarketDataProvider, Tick, Timeframe

_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.m1: "1min",
    Timeframe.m5: "5min",
    Timeframe.m15: "15min",
    Timeframe.h1: "1h",
    Timeframe.h4: "4h",
    Timeframe.d1: "1day",
}


class TwelveDataAdapter(MarketDataProvider):
    provider_name = "twelvedata"
    _BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)

    @staticmethod
    def _to_pair(symbol: str) -> str:
        # "EURUSD" -> "EUR/USD"
        return symbol if "/" in symbol else f"{symbol[:3]}/{symbol[3:]}"

    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        resp = await self._client.get(
            f"{self._BASE_URL}/time_series",
            params={
                "symbol": self._to_pair(symbol),
                "interval": _INTERVAL_MAP[timeframe],
                "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
                "apikey": self._api_key,
                "order": "ASC",
                "outputsize": 5000,
            },
        )
        payload = resp.json()
        if resp.status_code != 200 or payload.get("status") == "error":
            raise MarketDataError(f"TwelveData time_series failed: {payload}")

        values = payload.get("values", [])
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                open=Decimal(v["open"]),
                high=Decimal(v["high"]),
                low=Decimal(v["low"]),
                close=Decimal(v["close"]),
                volume=Decimal(v.get("volume", 0) or 0),
                timestamp=datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                ),
            )
            for v in values
        ]

    async def get_latest_quote(self, symbol: str) -> Tick:
        resp = await self._client.get(
            f"{self._BASE_URL}/quote",
            params={"symbol": self._to_pair(symbol), "apikey": self._api_key},
        )
        payload = resp.json()
        if resp.status_code != 200 or payload.get("status") == "error":
            raise MarketDataError(f"TwelveData quote failed: {payload}")

        # TwelveData's /quote returns a last close, not a bid/ask spread; use close for
        # both sides with a documented caveat — for true bid/ask, pair with a broker
        # adapter's get_quote() instead (this endpoint is best for indicative pricing).
        price = Decimal(payload["close"])
        return Tick(
            symbol=symbol,
            bid=price,
            ask=price,
            timestamp=datetime.now(timezone.utc),
        )
