import asyncio
import logging

from sqlalchemy import select

from app.brokers.factory import get_adapter_for_account
from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.execution.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState
from app.models.account import TradingAccount

logger = logging.getLogger(__name__)

# In-process state per account for this worker's lifetime. A production deployment
# with multiple worker processes would move this to Redis so all workers agree on
# whether an account's breaker is tripped — flagged here rather than silently
# assuming single-worker deployment.
_BREAKER_STATE: dict[str, CircuitBreakerState] = {}


async def _check_all_accounts() -> dict:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TradingAccount))
        accounts = list(result.scalars().all())

    tripped, checked, errors = [], 0, 0
    for account in accounts:
        state = _BREAKER_STATE.setdefault(str(account.id), CircuitBreakerState())
        if state.tripped:
            continue  # already tripped — needs manual reset, don't re-check

        try:
            adapter = get_adapter_for_account(account, settings)
            await adapter.connect()
            try:
                breaker = CircuitBreaker(adapter, CircuitBreakerConfig())
                new_state = await breaker.check_and_enforce(state)
                _BREAKER_STATE[str(account.id)] = new_state
                if new_state.tripped:
                    tripped.append(str(account.id))
            finally:
                await adapter.disconnect()
            checked += 1
        except Exception:
            logger.exception("circuit breaker check failed for account %s", account.id)
            errors += 1

    return {"checked": checked, "tripped": tripped, "errors": errors}


@celery_app.task(name="app.tasks.circuit_breaker_tasks.check_circuit_breakers_task")
def check_circuit_breakers_task() -> dict:
    return asyncio.run(_check_all_accounts())
