import asyncio
import logging

from sqlalchemy import select

from app.brokers.base import BrokerConnectionError
from app.brokers.factory import get_adapter_for_account
from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.account import TradingAccount
from app.models.portfolio import EquitySnapshot

logger = logging.getLogger(__name__)


async def _snapshot_account(account: TradingAccount, settings) -> None:
    adapter = get_adapter_for_account(account, settings)
    await adapter.connect()
    try:
        snapshot = await adapter.get_account_snapshot()
    finally:
        await adapter.disconnect()

    async with AsyncSessionLocal() as session:
        session.add(
            EquitySnapshot(
                account_id=account.id,
                balance=snapshot.balance,
                equity=snapshot.equity,
                margin=snapshot.margin,
                free_margin=snapshot.free_margin,
            )
        )
        # Also keep the account row's cached balance/equity fresh for cheap reads
        # (e.g. the accounts list endpoint) that don't want to hit the broker live.
        db_account = await session.get(TradingAccount, account.id)
        if db_account is not None:
            db_account.balance = snapshot.balance
            db_account.equity = snapshot.equity
        await session.commit()


async def _snapshot_all_accounts() -> dict:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TradingAccount))
        accounts = list(result.scalars().all())

    succeeded, failed = 0, 0
    for account in accounts:
        try:
            await _snapshot_account(account, settings)
            succeeded += 1
        except BrokerConnectionError as exc:
            logger.warning("equity snapshot skipped for account %s: %s", account.id, exc)
            failed += 1
        except Exception:
            logger.exception("equity snapshot failed unexpectedly for account %s", account.id)
            failed += 1

    return {"total": len(accounts), "succeeded": succeeded, "failed": failed}


@celery_app.task(name="app.tasks.portfolio_tasks.snapshot_all_account_equity_task")
def snapshot_all_account_equity_task() -> dict:
    return asyncio.run(_snapshot_all_accounts())
