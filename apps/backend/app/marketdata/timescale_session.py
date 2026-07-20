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


def _build_timescale_url() -> str | None:
    """Return a usable TimescaleDB URL when available; otherwise skip initialization."""
    if not settings.database_url:
        return None
    try:
        url = settings.database_url.replace("@postgres:", "@timescaledb:").replace("/forex", "/forex_ticks")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    except Exception:
        return None


# Reuses the same asyncpg driver as the main DB; points at the timescaledb service.
_timescale_url = _build_timescale_url()
timescale_engine = (
    create_async_engine(_timescale_url, pool_pre_ping=True)
    if _timescale_url
    else None
)
TimescaleSessionLocal = (
    async_sessionmaker(timescale_engine, expire_on_commit=False, class_=AsyncSession)
    if timescale_engine is not None
    else None
)


class TimescaleBase(DeclarativeBase):
    pass


async def get_timescale_db() -> AsyncGenerator[AsyncSession, None]:
    if TimescaleSessionLocal is None:
        raise RuntimeError("TimescaleDB is not configured")
    async with TimescaleSessionLocal() as session:
        yield session
