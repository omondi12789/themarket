import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.crypto import encrypt_broker_credentials
from app.db.session import get_db
from app.models.account import BrokerType, TradingAccount
from app.models.trading import Position
from app.models.user import User

router = APIRouter(prefix="/accounts", tags=["accounts"])


class ConnectAccountRequest(BaseModel):
    broker_type: BrokerType
    broker_login: str
    broker_server: str
    broker_password: str  # never persisted in plaintext — encrypted before storage
    is_live: bool = False


class AccountOut(BaseModel):
    id: uuid.UUID
    broker_type: BrokerType
    broker_login: str
    broker_server: str
    is_live: bool
    balance: float
    equity: float
    currency: str

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    id: uuid.UUID
    symbol: str
    side: str
    volume: float
    entry_price: float
    unrealized_pnl: float

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TradingAccount]:
    result = await db.execute(select(TradingAccount).where(TradingAccount.user_id == user.id))
    return list(result.scalars().all())


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def connect_account(
    payload: ConnectAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradingAccount:
    encrypted = encrypt_broker_credentials(
        {"password": payload.broker_password, "broker_type": payload.broker_type.value}
    )
    account = TradingAccount(
        user_id=user.id,
        broker_type=payload.broker_type,
        broker_login=payload.broker_login,
        broker_server=payload.broker_server,
        encrypted_credentials=encrypted,
        is_live=payload.is_live,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def _get_owned_account(account_id: uuid.UUID, user: User, db: AsyncSession) -> TradingAccount:
    result = await db.execute(
        select(TradingAccount).where(TradingAccount.id == account_id, TradingAccount.user_id == user.id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return account


@router.get("/{account_id}/positions", response_model=list[PositionOut])
async def list_positions(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Position]:
    await _get_owned_account(account_id, user, db)  # ownership check
    result = await db.execute(
        select(Position).where(Position.account_id == account_id, Position.closed_at.is_(None))
    )
    return list(result.scalars().all())
