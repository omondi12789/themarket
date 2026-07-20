import asyncio
import logging

from app.celery_app import celery_app
from app.marketdata.base import Timeframe
from app.marketdata.ingest import DEFAULT_WATCHLIST, backfill_watchlist

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.market_data_tasks.backfill_watchlist_task", bind=True, max_retries=3)
def backfill_watchlist_task(self, symbols: list[str] | None = None, timeframe: str = "1h", lookback_days: int = 2):
    """
    Scheduled hourly via celery beat (see app/celery_app.py). Short lookback since this
    runs frequently — the initial deep-history backfill is a one-off manual run of
    `python -m app.marketdata.ingest` with a larger lookback_days.
    """
    try:
        asyncio.run(
            backfill_watchlist(
                symbols or DEFAULT_WATCHLIST, Timeframe(timeframe), lookback_days=lookback_days
            )
        )
    except Exception as exc:
        logger.exception("backfill_watchlist_task failed")
        raise self.retry(exc=exc, countdown=60) from exc
