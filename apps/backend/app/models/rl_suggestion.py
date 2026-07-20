import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RLSizingSuggestion(Base):
    """
    Append-only log of every RL position-sizing suggestion. Same rationale as
    Prediction (app/models/prediction.py): lets you later evaluate whether the
    agent's suggested size, applied historically, would have actually helped —
    without that record, "the agent looks good in training" is unfalsifiable.
    """

    __tablename__ = "rl_sizing_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    suggested_size: Mapped[float] = mapped_column(Float)
    action_index: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    agent_trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
