import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.execution.copytrading_sizing import ScalingMode

__all__ = ["ScalingMode", "CopyTradingLink"]


class CopyTradingLink(Base):
    """
    A one-directional link: every order successfully placed on `source_account_id`
    gets mirrored to `follower_account_id`, scaled per `scaling_mode`. One follower
    can subscribe to multiple sources (multiple rows); one source can have many
    followers (multiple rows) — this is a plain edge list, not a tree, so fan-out and
    multi-source following both fall out of the schema for free.
    """

    __tablename__ = "copy_trading_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    follower_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scaling_mode: Mapped[ScalingMode] = mapped_column(Enum(ScalingMode, name="scaling_mode"), nullable=False)
    scaling_value: Mapped[float] = mapped_column(Numeric(10, 4), default=1.0)
    max_follower_volume: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
