import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StrategyTrade(Base):
    """
    One row per closed trade, tagged by strategy — this is the data
    app.execution.allocator.compute_allocations() needs (a list of realized returns
    per strategy_tag).

    Honest gap, stated plainly: nothing in this codebase automatically writes a row
    here yet. Order.strategy_tag exists and orders get tagged at placement time, but
    there is no position-close handler anywhere in this project that computes a
    trade's final realized PnL and inserts the corresponding StrategyTrade row —
    that's because position lifecycle (open -> track -> close with realized PnL) was
    never fully wired end-to-end (Position rows exist in the schema but nothing
    currently closes them with a realized figure; the execution engine only tracks
    unrealized_pnl live via broker snapshots). Wiring "on position close, insert a
    StrategyTrade row" wherever that close handler eventually lives is the remaining
    integration work — the allocator algorithm itself, and this table it reads from,
    are both real and ready for that data once it exists.
    """

    __tablename__ = "strategy_trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_tag: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    pnl: Mapped[float] = mapped_column(Numeric(18, 2))
    return_pct: Mapped[float] = mapped_column(Numeric(10, 6))  # pnl / account equity at trade open
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
