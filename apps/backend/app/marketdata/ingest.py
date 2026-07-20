"""
Historical bar backfill job.

Pulls bars for a symbol/timeframe/date-range from the first healthy configured
provider (with failover to the next), and upserts into the ohlcv_bars hypertable.
Run standalone (`python -m app.marketdata.ingest`) or scheduled via Celery beat
(wired in app/tasks — see Phase 7 scalping engine, which reuses this same job for
its rolling-window data needs).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.marketdata.base import MarketDataError, MarketDataProvider, Timeframe
from app.marketdata.factory import get_configured_providers
from app.marketdata.models import OHLCVBar
from app.marketdata.timescale_session import TimescaleSessionLocal

logger = logging.getLogger(__name__)


async def _fetch_with_failover(
    providers: list[MarketDataProvider],
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
):
    last_error: Exception | None = None
    for provider in providers:
        try:
            bars = await provider.get_historical_bars(symbol, timeframe, start, end)
            return bars, provider.provider_name
        except MarketDataError as exc:
            logger.warning("provider %s failed for %s: %s — trying next", provider.provider_name, symbol, exc)
            last_error = exc
    raise MarketDataError(f"All configured providers failed for {symbol}: {last_error}")


async def backfill_symbol(symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> int:
    settings = get_settings()
    providers = get_configured_providers(settings)

    bars, source = await _fetch_with_failover(providers, symbol, timeframe, start, end)
    if not bars:
        return 0

    async with TimescaleSessionLocal() as session:
        stmt = pg_insert(OHLCVBar).values(
            [
                {
                    "symbol": b.symbol,
                    "timeframe": b.timeframe.value,
                    "timestamp": b.timestamp,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "source": source,
                }
                for b in bars
            ]
        )
        # Idempotent re-runs: same symbol/timeframe/timestamp overwrites rather than
        # duplicating, so backfill jobs can safely overlap date ranges.
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "source": stmt.excluded.source,
            },
        )
        await session.execute(stmt)
        await session.commit()

    logger.info("backfilled %d bars for %s %s from %s", len(bars), symbol, timeframe.value, source)
    return len(bars)


async def backfill_watchlist(symbols: list[str], timeframe: Timeframe, lookback_days: int) -> None:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    results = await asyncio.gather(
        *(backfill_symbol(s, timeframe, start, end) for s in symbols), return_exceptions=True
    )
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            logger.error("backfill failed for %s: %s", symbol, result)


DEFAULT_WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(backfill_watchlist(DEFAULT_WATCHLIST, Timeframe.h1, lookback_days=30))
