import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BrokerType(str, enum.Enum):
    mt5 = "mt5"
    mt4 = "mt4"
    metaapi = "metaapi"
    paper = "paper"  # simulated demo account — real live quotes, no funded broker needed


class TradingAccount(Base):
    """A user's connected broker account (MT4/MT5/MetaApi)."""

    __tablename__ = "trading_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_type: Mapped[BrokerType] = mapped_column(Enum(BrokerType, name="broker_type"), nullable=False)
    broker_login: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_server: Mapped[str] = mapped_column(String(128), nullable=False)
    # Encrypted at the application layer before persisting — never store plaintext broker passwords.
    encrypted_credentials: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_live: Mapped[bool] = mapped_column(default=False)
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    equity: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
