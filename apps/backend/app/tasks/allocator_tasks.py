import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.execution.allocator import StrategyBounds, compute_allocations
from app.models.strategy import Strategy
from app.models.strategy_trade import StrategyTrade

logger = logging.getLogger(__name__)


async def _reallocate_capital(lookback_days: int = 90) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    async with AsyncSessionLocal() as session:
        strategies_result = await session.execute(select(Strategy).where(Strategy.is_active))
        strategies = list(strategies_result.scalars().all())

        if not strategies:
            return {"reallocated": 0, "note": "no active strategies registered"}

        strategy_returns: dict[str, list[float]] = {}
        bounds: dict[str, StrategyBounds] = {}

        for strat in strategies:
            trades_result = await session.execute(
                select(StrategyTrade)
                .where(StrategyTrade.strategy_tag == strat.tag, StrategyTrade.closed_at >= since)
                .order_by(StrategyTrade.closed_at.asc())
            )
            trades = list(trades_result.scalars().all())
            strategy_returns[strat.tag] = [float(t.return_pct) for t in trades]
            bounds[strat.tag] = StrategyBounds(
                min_allocation_pct=float(strat.min_allocation_pct),
                max_allocation_pct=float(strat.max_allocation_pct),
            )

        allocations = compute_allocations(strategy_returns, bounds=bounds)

        now = datetime.now(timezone.utc)
        for strat in strategies:
            strat.capital_allocation_pct = allocations.get(strat.tag, 0.0)
            strat.last_reallocated_at = now

        await session.commit()

        return {
            "reallocated": len(strategies),
            "allocations": allocations,
            "lookback_days": lookback_days,
        }


@celery_app.task(name="app.tasks.allocator_tasks.reallocate_capital_task")
def reallocate_capital_task() -> dict:
    return asyncio.run(_reallocate_capital())
