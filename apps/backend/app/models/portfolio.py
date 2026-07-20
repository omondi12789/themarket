import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EquitySnapshot(Base):
    """
    One row per (account, timestamp) — written every 15 minutes by
    app.tasks.portfolio_tasks.snapshot_all_account_equity_task. This is what makes
    the dashboard/performance equity curve real instead of illustrative: it's a
    ground-truth time series pulled from the broker's own account_info, not derived
    from local order records (which could drift from the broker's actual state).
    """

    __tablename__ = "equity_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    free_margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
