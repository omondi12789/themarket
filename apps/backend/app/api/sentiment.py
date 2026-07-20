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
from app.models.sentiment import SentimentSnapshot
from app.models.user import User
from app.news.client import NewsFetchError, fetch_headlines_with_failover

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])


class SentimentSnapshotOut(BaseModel):
    id: uuid.UUID
    query: str
    mean_score: float
    n_headlines: int
    method: str
    news_source: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/refresh", response_model=SentimentSnapshotOut, status_code=status.HTTP_201_CREATED)
async def refresh_sentiment(
    query: str = Query(default="forex", description='e.g. "EUR USD", "forex", "ECB rate decision"'),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SentimentSnapshot:
    """
    Real-time sentiment only — fetches current headlines and scores them now. There
    is no historical news backfill in this project, so this snapshot reflects
    sentiment as of right now, not a point-in-time historical value. See
    ai-engine's /sentiment/score docstring for why this isn't wired into the
    DirectionalForecaster's historical training.
    """
    settings = get_settings()
    try:
        headlines, source = await fetch_headlines_with_failover(
            query, settings.newsapi_key, settings.finnhub_news_key
        )
    except NewsFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if not headlines:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no recent headlines found for '{query}'")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ai_engine_url}/sentiment/score",
                json={"headlines": [h.title for h in headlines]},
            )
        resp.raise_for_status()
        result = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"could not reach ai-engine: {exc}"
        ) from exc

    aggregate = result["aggregate"]
    snapshot = SentimentSnapshot(
        query=query,
        mean_score=aggregate["mean_score"],
        n_headlines=aggregate["n_headlines"],
        method=aggregate["method"],
        news_source=source,
        raw_response=result,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


@router.get("/history", response_model=list[SentimentSnapshotOut])
async def sentiment_history(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SentimentSnapshot]:
    stmt = select(SentimentSnapshot).order_by(SentimentSnapshot.created_at.desc()).limit(limit)
    if query:
        stmt = stmt.where(SentimentSnapshot.query == query)
    result = await db.execute(stmt)
    return list(result.scalars().all())
