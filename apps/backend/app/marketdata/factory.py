"""
Market data provider factory + failover.

Unlike the broker factory (which picks exactly one adapter), market data benefits from
failover: if Polygon is rate-limited or down, fall through to TwelveData, then Finnhub.
Each provider has different rate limits and free-tier constraints (see each adapter's
module docstring), so this also gives simple resilience against any single provider's
outage or quota exhaustion.
"""
from __future__ import annotations

from app.core.config import Settings
from app.marketdata.base import MarketDataProvider


def get_configured_providers(settings: Settings) -> list[MarketDataProvider]:
    """Returns every provider with a configured API key, in priority order."""
    providers: list[MarketDataProvider] = []

    if settings.polygon_api_key:
        from app.marketdata.polygon_adapter import PolygonAdapter

        providers.append(PolygonAdapter(api_key=settings.polygon_api_key))

    if settings.twelvedata_api_key:
        from app.marketdata.twelvedata_adapter import TwelveDataAdapter

        providers.append(TwelveDataAdapter(api_key=settings.twelvedata_api_key))

    if settings.finnhub_api_key:
        from app.marketdata.finnhub_adapter import FinnhubAdapter

        providers.append(FinnhubAdapter(api_key=settings.finnhub_api_key))

    if not providers:
        raise ValueError(
            "No market data provider configured. Set at least one of "
            "POLYGON_API_KEY / TWELVEDATA_API_KEY / FINNHUB_API_KEY in .env."
        )
    return providers
