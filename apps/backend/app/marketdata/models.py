from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.marketdata.timescale_session import TimescaleBase


class OHLCVBar(TimescaleBase):
    """
    One row per (symbol, timeframe, timestamp). The composite primary key
    (symbol, timeframe, timestamp) matches how the hypertable is partitioned
    (see the migration's create_hypertable call, partitioned on `timestamp`).
    """

    __tablename__ = "ohlcv_bars"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(4), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    source: Mapped[str] = mapped_column(String(32))
