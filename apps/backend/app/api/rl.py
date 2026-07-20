import logging
import uuid
from datetime import datetime

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
from app.models.rl_suggestion import RLSizingSuggestion
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rl", tags=["rl"])


class TrainRLRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    lookback_bars: int = 2000
    n_episodes: int = 150
    episode_length: int = 200


async def _fetch_bars(symbol: str, timeframe: str, lookback_bars: int) -> list[dict]:
    async with TimescaleSessionLocal() as ts_session:
        result = await ts_session.execute(
            select(OHLCVBar)
            .where(OHLCVBar.symbol == symbol, OHLCVBar.timeframe == timeframe)
            .order_by(OHLCVBar.timestamp.desc())
            .limit(lookback_bars)
        )
        bars = list(result.scalars().all())

    bars.reverse()
    return [
        {
            "timestamp": b.timestamp.isoformat(),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in bars
    ]


@router.post("/train", status_code=status.HTTP_200_OK)
async def train_rl_agent(
    payload: TrainRLRequest, user: User = Depends(get_current_user)
) -> dict:
    """
    Pulls real TimescaleDB history and triggers RL training on the ai-engine. This is
    a slow call (100+ training episodes) — the ai-engine endpoint itself warns about
    this; the frontend should treat this as a long-running admin action, not
    something to call inline with a trade.
    """
    bars = await _fetch_bars(payload.symbol, payload.timeframe, payload.lookback_bars)
    min_needed = payload.episode_length + 100
    if len(bars) < min_needed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"only {len(bars)} bars available for {payload.symbol}/{payload.timeframe}, need {min_needed}",
        )

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # training is slow; generous timeout
            resp = await client.post(
                f"{settings.ai_engine_url}/rl/train",
                json={
                    "symbol": payload.symbol,
                    "bars": bars,
                    "n_episodes": payload.n_episodes,
                    "episode_length": payload.episode_length,
                },
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ai-engine error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"could not reach ai-engine: {exc}"
        ) from exc


class SuggestSizeRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    lookback_bars: int = 300


class RLSuggestionOut(BaseModel):
    id: uuid.UUID
    symbol: str
    suggested_size: float
    action_index: int
    confidence: float
    agent_trained_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/suggest-size", response_model=RLSuggestionOut, status_code=status.HTTP_201_CREATED)
async def suggest_position_size(
    payload: SuggestSizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RLSuggestionOut:
    bars = await _fetch_bars(payload.symbol, payload.timeframe, payload.lookback_bars)
    if len(bars) < 120:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"only {len(bars)} bars available for {payload.symbol}/{payload.timeframe}, need at least 120",
        )

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ai_engine_url}/rl/suggest-size", json={"symbol": payload.symbol, "bars": bars}
            )
        resp.raise_for_status()
        result = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no trained RL agent for {payload.symbol} — call /api/rl/train first",
            ) from exc
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ai-engine error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"could not reach ai-engine: {exc}"
        ) from exc

    suggestion = RLSizingSuggestion(
        symbol=payload.symbol,
        suggested_size=result["suggested_size"],
        action_index=result["action_index"],
        confidence=result["confidence"],
        agent_trained_at=datetime.fromisoformat(result["agent_trained_at"]),
        raw_response=result,
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.get("/suggestions", response_model=list[RLSuggestionOut])
async def list_suggestions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RLSizingSuggestion]:
    query = select(RLSizingSuggestion).order_by(RLSizingSuggestion.created_at.desc()).limit(limit)
    if symbol:
        query = query.where(RLSizingSuggestion.symbol == symbol)
    result = await db.execute(query)
    return list(result.scalars().all())
