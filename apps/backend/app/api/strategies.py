import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.strategy import Strategy
from app.models.user import User
from app.tasks.allocator_tasks import _reallocate_capital

router = APIRouter(prefix="/strategies", tags=["strategies"])


class RegisterStrategyRequest(BaseModel):
    tag: str
    name: str
    description: str | None = None
    min_allocation_pct: float = 0.0
    max_allocation_pct: float = 1.0


class StrategyOut(BaseModel):
    id: uuid.UUID
    tag: str
    name: str
    description: str | None
    is_active: bool
    capital_allocation_pct: float
    min_allocation_pct: float
    max_allocation_pct: float
    last_reallocated_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[StrategyOut])
async def list_strategies(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Strategy]:
    result = await db.execute(select(Strategy).order_by(Strategy.capital_allocation_pct.desc()))
    return list(result.scalars().all())


@router.post("", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def register_strategy(
    payload: RegisterStrategyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Strategy:
    existing = await db.execute(select(Strategy).where(Strategy.tag == payload.tag))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"strategy tag '{payload.tag}' already registered")

    strategy = Strategy(
        tag=payload.tag,
        name=payload.name,
        description=payload.description,
        min_allocation_pct=payload.min_allocation_pct,
        max_allocation_pct=payload.max_allocation_pct,
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.post("/reallocate", status_code=status.HTTP_200_OK)
async def trigger_reallocation(user: User = Depends(get_current_user)) -> dict:
    """
    Manually triggers the same reallocation logic as the daily scheduled Celery task
    (app.tasks.allocator_tasks) — useful for testing/demoing without waiting for the
    midnight schedule. Runs the real allocator against whatever StrategyTrade rows
    currently exist (see StrategyTrade's docstring for the honest gap: nothing yet
    writes those rows from live position closes, so this returns default allocations
    for any strategy with no trade history).
    """
    return await _reallocate_capital()
