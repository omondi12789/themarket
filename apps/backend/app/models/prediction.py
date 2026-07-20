import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Prediction(Base):
    """
    Append-only log of every AI prediction generated, independent of whether it was
    acted on. This is what lets you later compute "was the model actually right?" by
    joining against realized price at the prediction's `as_of` + 1 bar — critical for
    honestly evaluating the forecaster rather than only trusting its self-reported
    cross-validation accuracy.
    """

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(4))  # "up" | "down"
    probability_up: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    model_type: Mapped[str] = mapped_column(String(128))
    cv_accuracy_mean: Mapped[float] = mapped_column(Float)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Filled in later by an evaluation job comparing `direction` against what the
    # market actually did after `as_of` — null until then.
    actual_direction: Mapped[str | None] = mapped_column(String(4), nullable=True)
    was_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
