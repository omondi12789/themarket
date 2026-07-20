"""
TimescaleDB connection for time-series market data.

Deliberately separate from app/db/session.py (the main Postgres app DB for
users/orders/positions): time-series tick/bar data has completely different access
patterns (huge append-only writes, range-scan reads) and belongs on TimescaleDB's
hypertables, not the OLTP database.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Reuses the same asyncpg driver as the main DB; points at the timescaledb service.
timescale_engine = create_async_engine(
    settings.database_url.replace("@postgres:", "@timescaledb:").replace("/forex", "/forex_ticks"),
    pool_pre_ping=True,
)
TimescaleSessionLocal = async_sessionmaker(timescale_engine, expire_on_commit=False, class_=AsyncSession)


class TimescaleBase(DeclarativeBase):
    pass


async def get_timescale_db() -> AsyncGenerator[AsyncSession, None]:
    async with TimescaleSessionLocal() as session:
        yield session
