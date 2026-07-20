import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.accounts import _get_owned_account
from app.api.deps import get_current_user
from app.brokers.base import BrokerConnectionError, BrokerOrderError, BrokerOrderSide, BrokerOrderType, OrderRequest
from app.brokers.factory import get_adapter_for_account
from app.core.config import get_settings
from app.db.session import get_db
from app.execution.copytrading import mirror_order
from app.models.audit import record_audit_event
from app.models.trading import Order, OrderSide, OrderStatus, OrderType
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])


class PlaceOrderRequest(BaseModel):
    account_id: uuid.UUID | None = None  # falls back to the user's first account if omitted
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.market
    volume: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy_tag: str | None = None


class OrderOut(BaseModel):
    id: uuid.UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    volume: float
    broker_order_id: str | None

    model_config = {"from_attributes": True}


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: PlaceOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Order:
    account_id = payload.account_id
    if account_id is None:
        from app.models.account import TradingAccount

        result = await db.execute(
            select(TradingAccount).where(TradingAccount.user_id == user.id).limit(1)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No connected broker account. Connect one via POST /api/accounts first.",
            )
    else:
        account = await _get_owned_account(account_id, user, db)

    order = Order(
        account_id=account.id,
        symbol=payload.symbol,
        side=payload.side,
        order_type=payload.order_type,
        volume=Decimal(str(payload.volume)),
        price=Decimal(str(payload.price)) if payload.price is not None else None,
        stop_loss=Decimal(str(payload.stop_loss)) if payload.stop_loss is not None else None,
        take_profit=Decimal(str(payload.take_profit)) if payload.take_profit is not None else None,
        strategy_tag=payload.strategy_tag,
        status=OrderStatus.pending,
    )
    db.add(order)
    await db.flush()  # assigns order.id without committing yet

    settings = get_settings()

    if payload.order_type == OrderType.stop_limit:
        # BrokerOrderType (app/brokers/base.py) intentionally only models market/limit/stop —
        # the three types every adapter (MT5, MetaApi) can express directly. stop_limit orders
        # aren't wired to live execution yet; reject clearly rather than silently downgrading
        # to a plain stop/limit order, which would change the trade's actual risk profile.
        order.status = OrderStatus.rejected
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stop_limit orders are not yet supported for live execution.",
        )

    broker_request: OrderRequest | None = None
    try:
        adapter = get_adapter_for_account(account, settings)
        await adapter.connect()
        try:
            broker_request = OrderRequest(
                symbol=payload.symbol,
                side=BrokerOrderSide(payload.side.value),
                order_type=BrokerOrderType(payload.order_type.value),
                volume=Decimal(str(payload.volume)),
                price=Decimal(str(payload.price)) if payload.price is not None else None,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                comment=payload.strategy_tag or "themarket-ai",
            )
            result = await adapter.place_order(broker_request)
            order.status = OrderStatus.filled if payload.order_type == OrderType.market else OrderStatus.submitted
            order.broker_order_id = result.broker_order_id
            if result.filled_price is not None:
                order.price = result.filled_price
        finally:
            await adapter.disconnect()

    except BrokerConnectionError as exc:
        logger.error("broker connection failed for account %s: %s", account.id, exc)
        order.status = OrderStatus.rejected
    except BrokerOrderError as exc:
        logger.error("broker rejected order for account %s: %s", account.id, exc)
        order.status = OrderStatus.rejected

    await record_audit_event(
        db,
        action="order.place",
        user_id=user.id,
        resource_type="order",
        resource_id=str(order.id),
        detail={
            "symbol": order.symbol,
            "side": order.side.value,
            "volume": float(order.volume),
            "status": order.status.value,
            "account_id": str(account.id),
            "is_live": account.is_live,
        },
    )

    copy_trade_results: list[dict] = []
    if order.status in (OrderStatus.filled, OrderStatus.submitted) and broker_request is not None:
        # Mirror to followers AFTER the source order is known-good, and failures here
        # never roll back or fail the source order itself — a follower's broken
        # broker connection is that follower's problem, not the leader's.
        try:
            copy_trade_results = await mirror_order(db, settings, account, broker_request)
            if copy_trade_results:
                await record_audit_event(
                    db,
                    action="order.copy_trade_mirror",
                    user_id=user.id,
                    resource_type="order",
                    resource_id=str(order.id),
                    detail={"source_account_id": str(account.id), "results": copy_trade_results},
                )
        except Exception:
            logger.exception("copy trading mirror step failed for order %s (source order unaffected)", order.id)

    await db.commit()
    await db.refresh(order)

    if order.status == OrderStatus.rejected:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Order was recorded but rejected by the broker/connection — see order history for details.",
        )

    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Order]:
    from app.models.account import TradingAccount

    result = await db.execute(
        select(Order)
        .join(TradingAccount, Order.account_id == TradingAccount.id)
        .where(TradingAccount.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(200)
    )
    return list(result.scalars().all())
