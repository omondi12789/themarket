from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def normalize_database_url(url: str) -> str:
    """Ensure SQLAlchemy uses the asyncpg driver for PostgreSQL URLs."""
    if url.startswith("postgresql://") and "+asyncpg" not in url and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# Pool tuning for production concurrency: pool_size is the number of persistent
# connections kept open per worker process; max_overflow allows temporary bursts
# above that under load spikes (see infra/loadtest for the tool that tells you
# whether these numbers are actually right for your traffic). pool_recycle avoids
# holding connections open longer than most managed Postgres providers' idle-connection
# timeout (RDS defaults vary; 30 min is a safe conservative value).
engine = create_async_engine(
    normalize_database_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Optional read-replica engine: set DATABASE_READ_REPLICA_URL to point read-only
# endpoints (dashboard aggregates, scanner, history listings) at an RDS read replica
# instead of the primary, taking that traffic off the write path. Falls back to the
# primary engine when unset, so this is safe to leave unconfigured in dev/single-instance
# deployments — nothing breaks, you just don't get the read/write split.
_read_replica_url = getattr(settings, "database_read_replica_url", None)
read_engine = (
    create_async_engine(
        normalize_database_url(_read_replica_url),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
    )
    if _read_replica_url
    else engine
)
AsyncReadSessionLocal = async_sessionmaker(read_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Use for read-only endpoints that can tolerate replica lag (typically single-digit
    seconds) — dashboards, scanners, history views. Never use for anything that reads
    its own just-written data in the same request (e.g. read-after-write in an order
    placement flow), since the replica may not have caught up yet.
    """
    async with AsyncReadSessionLocal() as session:
        yield session
