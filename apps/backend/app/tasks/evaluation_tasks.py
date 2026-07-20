"""
Evaluates predictions whose outcome is now knowable: for each unevaluated prediction
older than one bar interval, look up the realized close price at (and after) `as_of`
in TimescaleDB, compare to the bar the prediction was made on, and set
`actual_direction` / `was_correct`. This is what makes /api/predictions/accuracy a
real number instead of a permanent "not evaluated yet".
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.marketdata.models import OHLCVBar
from app.marketdata.timescale_session import TimescaleSessionLocal
from app.models.prediction import Prediction

logger = logging.getLogger(__name__)

# Must match the timeframe predictions are currently generated against
# (app/api/predictions.py's GeneratePredictionRequest.timeframe default).
_TIMEFRAME = "1h"
_TIMEFRAME_DELTA = timedelta(hours=1)


async def _evaluate_pending_predictions(max_predictions: int = 200) -> dict:
    cutoff = datetime.now(timezone.utc) - _TIMEFRAME_DELTA
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Prediction)
            .where(Prediction.was_correct.is_(None), Prediction.as_of <= cutoff)
            .order_by(Prediction.as_of.asc())
            .limit(max_predictions)
        )
        pending = list(result.scalars().all())

        if not pending:
            return {"evaluated": 0, "skipped_no_data": 0}

        evaluated, skipped = 0, 0
        async with TimescaleSessionLocal() as ts_session:
            for prediction in pending:
                # The bar the prediction was made "as of" (its close is the baseline).
                base_bar_result = await ts_session.execute(
                    select(OHLCVBar).where(
                        OHLCVBar.symbol == prediction.symbol,
                        OHLCVBar.timeframe == _TIMEFRAME,
                        OHLCVBar.timestamp == prediction.as_of,
                    )
                )
                base_bar = base_bar_result.scalar_one_or_none()

                # The next bar after that — its close tells us what actually happened.
                next_bar_result = await ts_session.execute(
                    select(OHLCVBar)
                    .where(
                        OHLCVBar.symbol == prediction.symbol,
                        OHLCVBar.timeframe == _TIMEFRAME,
                        OHLCVBar.timestamp > prediction.as_of,
                    )
                    .order_by(OHLCVBar.timestamp.asc())
                    .limit(1)
                )
                next_bar = next_bar_result.scalar_one_or_none()

                if base_bar is None or next_bar is None:
                    skipped += 1
                    continue

                actual_direction = "up" if next_bar.close > base_bar.close else "down"
                prediction.actual_direction = actual_direction
                prediction.was_correct = actual_direction == prediction.direction
                evaluated += 1

            await session.commit()

        return {"evaluated": evaluated, "skipped_no_data": skipped}


@celery_app.task(name="app.tasks.evaluation_tasks.evaluate_pending_predictions_task")
def evaluate_pending_predictions_task() -> dict:
    return asyncio.run(_evaluate_pending_predictions())
