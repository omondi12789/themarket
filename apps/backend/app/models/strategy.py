import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Strategy(Base):
    """
    A registered strategy that orders can be tagged with (see Order.strategy_tag).
    `capital_allocation_pct` is the fraction of total tradeable capital this strategy
    is currently allowed to risk — set by the allocator (app/execution/allocator.py),
    not by strategies themselves, so no single strategy can silently grant itself
    more capital than the portfolio-level policy allows.
    """

    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # matches Order.strategy_tag
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    capital_allocation_pct: Mapped[float] = mapped_column(Numeric(5, 4), default=0)  # 0.0000 - 1.0000
    min_allocation_pct: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    max_allocation_pct: Mapped[float] = mapped_column(Numeric(5, 4), default=1)
    last_reallocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
