import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_read_db
from app.models.account import TradingAccount
from app.models.portfolio import EquitySnapshot
from app.models.trading import Position
from app.models.user import User

router = APIRouter(prefix="/risk", tags=["risk"])


class SymbolExposure(BaseModel):
    symbol: str
    net_volume: float  # positive = net long, negative = net short
    gross_volume: float
    unrealized_pnl: float
    position_count: int


class AccountRiskSummary(BaseModel):
    account_id: uuid.UUID
    is_live: bool
    equity: float
    margin: float | None
    free_margin: float | None
    margin_utilization_pct: float | None
    total_unrealized_pnl: float
    open_position_count: int
    exposures: list[SymbolExposure]


@router.get("/summary", response_model=list[AccountRiskSummary])
async def risk_summary(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_read_db)
) -> list[AccountRiskSummary]:
    """
    Real, live-derived risk exposure: current open positions grouped by symbol
    (net/gross volume, unrealized PnL) plus the most recent margin snapshot from the
    broker (via app.tasks.portfolio_tasks' scheduled snapshots). Historical
    risk-adjusted metrics (Sharpe/VaR/CVaR/drawdown) live in GET /api/portfolio/performance —
    kept separate since one is "risk right now" and the other is "risk over time".
    """
    accounts_result = await db.execute(select(TradingAccount).where(TradingAccount.user_id == user.id))
    accounts = list(accounts_result.scalars().all())

    summaries: list[AccountRiskSummary] = []
    for account in accounts:
        positions_result = await db.execute(
            select(Position).where(Position.account_id == account.id, Position.closed_at.is_(None))
        )
        positions = list(positions_result.scalars().all())

        by_symbol: dict[str, list[Position]] = {}
        for p in positions:
            by_symbol.setdefault(p.symbol, []).append(p)

        exposures = []
        for symbol, symbol_positions in by_symbol.items():
            net = sum((p.volume if p.side.value == "buy" else -p.volume) for p in symbol_positions)
            gross = sum(p.volume for p in symbol_positions)
            pnl = sum(p.unrealized_pnl for p in symbol_positions)
            exposures.append(
                SymbolExposure(
                    symbol=symbol,
                    net_volume=float(net),
                    gross_volume=float(gross),
                    unrealized_pnl=float(pnl),
                    position_count=len(symbol_positions),
                )
            )

        latest_snapshot_result = await db.execute(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account.id)
            .order_by(EquitySnapshot.captured_at.desc())
            .limit(1)
        )
        latest_snapshot = latest_snapshot_result.scalar_one_or_none()

        margin_utilization = None
        margin_val = None
        free_margin_val = None
        if latest_snapshot is not None:
            margin_val = float(latest_snapshot.margin)
            free_margin_val = float(latest_snapshot.free_margin)
            total_margin_pool = margin_val + free_margin_val
            if total_margin_pool > 0:
                margin_utilization = (margin_val / total_margin_pool) * 100

        summaries.append(
            AccountRiskSummary(
                account_id=account.id,
                is_live=account.is_live,
                equity=float(latest_snapshot.equity) if latest_snapshot else float(account.equity),
                margin=margin_val,
                free_margin=free_margin_val,
                margin_utilization_pct=margin_utilization,
                total_unrealized_pnl=float(sum(p.unrealized_pnl for p in positions)),
                open_position_count=len(positions),
                exposures=exposures,
            )
        )

    return summaries
