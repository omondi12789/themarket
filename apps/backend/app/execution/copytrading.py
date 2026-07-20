"""
Copy trading I/O orchestration: mirrors a successfully-filled order from a source
("leader") account to its followers, scaled per each CopyTradingLink's rule. The
sizing math itself lives in app/execution/copytrading_sizing.py (zero dependencies,
independently testable) — this module is only the broker/DB wiring around it.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerConnectionError, BrokerOrderError, OrderRequest
from app.brokers.factory import get_adapter_for_account
from app.core.config import Settings
from app.execution.copytrading_sizing import ScalingMode, compute_follower_volume
from app.models.account import TradingAccount
from app.models.copy_trading import CopyTradingLink

logger = logging.getLogger(__name__)


async def mirror_order(
    db: AsyncSession,
    settings: Settings,
    source_account: TradingAccount,
    source_order: OrderRequest,
) -> list[dict]:
    """
    Called after a source account's order has been successfully placed (see
    app/api/orders.py). Finds active CopyTradingLink rows for this source account,
    computes each follower's scaled volume, and places the mirrored order on each
    follower's own broker connection. Each follower's mirror is independent — one
    follower's broker being down doesn't block or roll back the others, and none of
    this blocks/fails the original source order (which has already been committed
    by the time this runs).
    """
    links_result = await db.execute(
        select(CopyTradingLink).where(
            CopyTradingLink.source_account_id == source_account.id, CopyTradingLink.is_active
        )
    )
    links = list(links_result.scalars().all())
    if not links:
        return []

    results = []
    for link in links:
        follower_account = await db.get(TradingAccount, link.follower_account_id)
        if follower_account is None:
            logger.warning("copy trading link %s references a missing follower account", link.id)
            continue

        try:
            source_equity = source_account.equity if link.scaling_mode == ScalingMode.equity_proportional else None
            follower_equity = follower_account.equity if link.scaling_mode == ScalingMode.equity_proportional else None

            follower_volume = compute_follower_volume(
                source_volume=source_order.volume,
                scaling_mode=link.scaling_mode,
                scaling_value=Decimal(str(link.scaling_value)),
                source_equity=Decimal(str(source_equity)) if source_equity is not None else None,
                follower_equity=Decimal(str(follower_equity)) if follower_equity is not None else None,
                max_follower_volume=(
                    Decimal(str(link.max_follower_volume)) if link.max_follower_volume is not None else None
                ),
            )

            if follower_volume <= 0:
                results.append({"follower_account_id": str(follower_account.id), "status": "skipped_below_min_volume"})
                continue

            follower_request = OrderRequest(
                symbol=source_order.symbol,
                side=source_order.side,
                order_type=source_order.order_type,
                volume=follower_volume,
                price=source_order.price,
                stop_loss=source_order.stop_loss,
                take_profit=source_order.take_profit,
                comment=f"copy-trade from {source_account.id}",
            )

            adapter = get_adapter_for_account(follower_account, settings)
            await adapter.connect()
            try:
                result = await adapter.place_order(follower_request)
                results.append(
                    {
                        "follower_account_id": str(follower_account.id),
                        "status": "mirrored",
                        "volume": str(follower_volume),
                        "broker_order_id": result.broker_order_id,
                    }
                )
            finally:
                await adapter.disconnect()

        except (BrokerConnectionError, BrokerOrderError) as exc:
            logger.error("copy trade to follower %s failed: %s", link.follower_account_id, exc)
            results.append({"follower_account_id": str(link.follower_account_id), "status": "failed", "error": str(exc)})
        except ValueError as exc:
            logger.error("copy trade sizing failed for follower %s: %s", link.follower_account_id, exc)
            results.append({"follower_account_id": str(link.follower_account_id), "status": "sizing_error", "error": str(exc)})

    return results
