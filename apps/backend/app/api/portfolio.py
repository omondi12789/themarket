import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_read_db
from app.models.account import TradingAccount
from app.models.portfolio import EquitySnapshot
from app.models.user import User

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class EquityPoint(BaseModel):
    captured_at: datetime
    equity: float
    balance: float


class EquityHistoryResponse(BaseModel):
    account_id: uuid.UUID
    points: list[EquityPoint]


@router.get("/equity-history", response_model=list[EquityHistoryResponse])
async def equity_history(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
) -> list[EquityHistoryResponse]:
    """
    Real equity history from app.tasks.portfolio_tasks' scheduled snapshots — not
    derived/interpolated. Accounts with no snapshots yet (e.g. just connected, before
    the next 15-minute beat tick) simply return an empty points list rather than a
    fabricated curve.
    """
    accounts_result = await db.execute(select(TradingAccount).where(TradingAccount.user_id == user.id))
    accounts = list(accounts_result.scalars().all())

    since = datetime.now(timezone.utc) - timedelta(days=days)
    responses = []
    for account in accounts:
        snap_result = await db.execute(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account.id, EquitySnapshot.captured_at >= since)
            .order_by(EquitySnapshot.captured_at.asc())
        )
        snapshots = list(snap_result.scalars().all())
        responses.append(
            EquityHistoryResponse(
                account_id=account.id,
                points=[
                    EquityPoint(captured_at=s.captured_at, equity=float(s.equity), balance=float(s.balance))
                    for s in snapshots
                ],
            )
        )
    return responses


class PerformanceResponse(BaseModel):
    account_id: uuid.UUID
    n_observations: int
    metrics: dict | None
    note: str | None = None


@router.get("/performance", response_model=list[PerformanceResponse])
async def performance_analytics(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
) -> list[PerformanceResponse]:
    """
    Real Sharpe/Sortino/Calmar/drawdown/VaR/CVaR computed from actual equity snapshot
    history (not synthetic), via the ai-engine's risk/summary endpoint. Needs at least
    5 snapshots (roughly 75 minutes at the default 15-min snapshot interval) to
    produce a meaningful return series — returns metrics=None with an honest note
    below that, rather than a fabricated number.
    """
    settings = get_settings()
    accounts_result = await db.execute(select(TradingAccount).where(TradingAccount.user_id == user.id))
    accounts = list(accounts_result.scalars().all())

    since = datetime.now(timezone.utc) - timedelta(days=days)
    responses: list[PerformanceResponse] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for account in accounts:
            snap_result = await db.execute(
                select(EquitySnapshot)
                .where(EquitySnapshot.account_id == account.id, EquitySnapshot.captured_at >= since)
                .order_by(EquitySnapshot.captured_at.asc())
            )
            snapshots = list(snap_result.scalars().all())

            if len(snapshots) < 5:
                responses.append(
                    PerformanceResponse(
                        account_id=account.id,
                        n_observations=len(snapshots),
                        metrics=None,
                        note=(
                            f"only {len(snapshots)} equity snapshots in the last {days} days — "
                            "need at least 5 for a meaningful performance calculation. "
                            "Snapshots are captured every 15 minutes once the account is connected."
                        ),
                    )
                )
                continue

            equities = [float(s.equity) for s in snapshots]
            returns = [
                (equities[i] - equities[i - 1]) / equities[i - 1]
                for i in range(1, len(equities))
                if equities[i - 1] != 0
            ]

            try:
                resp = await client.post(
                    f"{settings.ai_engine_url}/risk/summary",
                    json={"returns": returns, "periods_per_year": 252 * 24 * 4},  # 15-min bars/year
                )
                resp.raise_for_status()
                metrics = resp.json()
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=f"could not reach ai-engine: {exc}"
                ) from exc

            responses.append(
                PerformanceResponse(account_id=account.id, n_observations=len(snapshots), metrics=metrics)
            )

    return responses
