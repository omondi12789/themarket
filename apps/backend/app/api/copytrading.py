import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.accounts import _get_owned_account
from app.api.deps import get_current_user
from app.db.session import get_db
from app.execution.copytrading_sizing import ScalingMode
from app.models.copy_trading import CopyTradingLink
from app.models.user import User

router = APIRouter(prefix="/copytrading", tags=["copytrading"])


class CreateLinkRequest(BaseModel):
    source_account_id: uuid.UUID
    follower_account_id: uuid.UUID
    scaling_mode: ScalingMode
    scaling_value: float = 1.0
    max_follower_volume: float | None = None


class LinkOut(BaseModel):
    id: uuid.UUID
    source_account_id: uuid.UUID
    follower_account_id: uuid.UUID
    scaling_mode: ScalingMode
    scaling_value: float
    max_follower_volume: float | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/links", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(
    payload: CreateLinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CopyTradingLink:
    """
    Both accounts must belong to the requesting user — this endpoint deliberately
    does not support "follow someone else's account" (that would need a consent/
    invitation flow between different users, which is a real product feature but a
    materially larger scope than this endpoint covers; ownership-only for now).
    """
    source = await _get_owned_account(payload.source_account_id, user, db)
    follower = await _get_owned_account(payload.follower_account_id, user, db)

    if source.id == follower.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source and follower cannot be the same account")

    link = CopyTradingLink(
        source_account_id=source.id,
        follower_account_id=follower.id,
        scaling_mode=payload.scaling_mode,
        scaling_value=payload.scaling_value,
        max_follower_volume=payload.max_follower_volume,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


@router.get("/links", response_model=list[LinkOut])
async def list_links(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[CopyTradingLink]:
    from app.models.account import TradingAccount

    result = await db.execute(
        select(CopyTradingLink)
        .join(TradingAccount, CopyTradingLink.source_account_id == TradingAccount.id)
        .where(TradingAccount.user_id == user.id)
    )
    return list(result.scalars().all())


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    link = await db.get(CopyTradingLink, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found")
    await _get_owned_account(link.source_account_id, user, db)  # ownership check
    await db.delete(link)
    await db.commit()
