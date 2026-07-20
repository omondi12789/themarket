import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SentimentSnapshot(Base):
    __tablename__ = "sentiment_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "EUR USD" or "forex"
    mean_score: Mapped[float] = mapped_column(Float)
    n_headlines: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(32))  # "finbert" | "lexicon_fallback" | "mixed"
    news_source: Mapped[str] = mapped_column(String(32))  # "newsapi" | "finnhub"
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
