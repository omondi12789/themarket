import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.marketdata.models import OHLCVBar
from app.marketdata.timescale_session import TimescaleSessionLocal
from app.models.prediction import Prediction
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predictions", tags=["predictions"])


class PredictionOut(BaseModel):
    id: uuid.UUID
    symbol: str
    direction: str
    probability_up: float
    confidence: float
    model_type: str
    cv_accuracy_mean: float
    as_of: datetime
    created_at: datetime
    top_features: dict | None = None
    model_breakdown: dict | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_prediction(cls, prediction: Prediction) -> "PredictionOut":
        raw = prediction.raw_response or {}
        return cls(
            id=prediction.id,
            symbol=prediction.symbol,
            direction=prediction.direction,
            probability_up=prediction.probability_up,
            confidence=prediction.confidence,
            model_type=prediction.model_type,
            cv_accuracy_mean=prediction.cv_accuracy_mean,
            as_of=prediction.as_of,
            created_at=prediction.created_at,
            top_features=raw.get("model_info", {}).get("top_features"),
            model_breakdown=raw.get("prediction", {}).get("model_breakdown"),
        )


class GeneratePredictionRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    lookback_bars: int = 1000
    force_retrain: bool = False


@router.post("/generate", response_model=PredictionOut, status_code=status.HTTP_201_CREATED)
async def generate_prediction(
    payload: GeneratePredictionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PredictionOut:
    """
    Pulls the real bar history for `symbol` from TimescaleDB (populated by the
    scheduled backfill task — app/tasks/market_data_tasks.py), sends it to the
    ai-engine's directional forecaster, and persists the resulting prediction.
    Returns 404 if there isn't enough backfilled history yet for this symbol.
    """
    async with TimescaleSessionLocal() as ts_session:
        result = await ts_session.execute(
            select(OHLCVBar)
            .where(OHLCVBar.symbol == payload.symbol, OHLCVBar.timeframe == payload.timeframe)
            .order_by(OHLCVBar.timestamp.desc())
            .limit(payload.lookback_bars)
        )
        bars = list(result.scalars().all())

    if len(bars) < 200:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Only {len(bars)} bars available for {payload.symbol}/{payload.timeframe} — "
                "need at least 200. Run the backfill job (app/marketdata/ingest.py or the "
                "scheduled Celery task) for this symbol first."
            ),
        )

    bars.reverse()  # ascending order for the ai-engine
    settings = get_settings()

    request_body = {
        "symbol": payload.symbol,
        "force_retrain": payload.force_retrain,
        "bars": [
            {
                "timestamp": b.timestamp.isoformat(),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{settings.ai_engine_url}/predictions/generate", json=request_body)
        resp.raise_for_status()
        payload_json = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ai-engine error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"could not reach ai-engine: {exc}"
        ) from exc

    pred_data = payload_json["prediction"]
    model_info = payload_json["model_info"]

    prediction = Prediction(
        symbol=payload.symbol,
        direction=pred_data["direction"],
        probability_up=pred_data["probability_up"],
        confidence=pred_data["confidence"],
        model_type=model_info["model_type"],
        cv_accuracy_mean=model_info["cv_accuracy_mean"],
        as_of=datetime.fromisoformat(pred_data["as_of"]),
        raw_response=payload_json,
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)
    return PredictionOut.from_prediction(prediction)


@router.get("", response_model=list[PredictionOut])
async def list_predictions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PredictionOut]:
    query = select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)
    if symbol:
        query = query.where(Prediction.symbol == symbol)
    result = await db.execute(query)
    return [PredictionOut.from_prediction(p) for p in result.scalars().all()]


@router.get("/accuracy", response_model=dict)
async def prediction_accuracy(
    symbol: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Real accuracy stats from predictions that have been evaluated (was_correct is
    non-null — set by a separate evaluation job comparing `direction` against actual
    price movement after `as_of`, not implemented as part of this endpoint). Returns
    evaluated_count=0 honestly if the evaluation job hasn't run yet, rather than
    fabricating an accuracy number.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(Prediction).where(Prediction.created_at >= since, Prediction.was_correct.is_not(None))
    if symbol:
        query = query.where(Prediction.symbol == symbol)

    result = await db.execute(query)
    evaluated = list(result.scalars().all())

    if not evaluated:
        return {"evaluated_count": 0, "accuracy": None, "note": "no evaluated predictions in this window yet"}

    correct = sum(1 for p in evaluated if p.was_correct)
    return {
        "evaluated_count": len(evaluated),
        "correct_count": correct,
        "accuracy": correct / len(evaluated),
    }
