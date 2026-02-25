"""
Database setup — supports both SQLite (local dev) and PostgreSQL (Supabase).
Auto-creates tables on startup.

NOTE: Supabase connection pooler (port 6543, transaction mode) requires
      prepared_statement_cache_size=0 because pgbouncer doesn't support
      named prepared statements.
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

logger = logging.getLogger("aegis.db")

# Detect driver for engine kwargs
_is_sqlite = settings.database_url.startswith("sqlite")
_is_pooler = ":6543/" in settings.database_url  # Supabase pooler uses port 6543

_engine_kwargs: dict = dict(echo=settings.debug)

if _is_sqlite:
    # SQLite: no pool_pre_ping, no connect_args needed
    pass
elif _is_pooler:
    # Supabase connection pooler (transaction mode) — must disable prepared statements
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        connect_args={
            "prepared_statement_cache_size": 0,      # Required for pgbouncer
            "statement_cache_size": 0,                # Required for pgbouncer
            "server_settings": {"jit": "off"},        # Faster for short queries
        },
    )
else:
    # Direct PostgreSQL connection
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables (idempotent)."""
    from models import Base  # noqa: ensure models are imported
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        driver = "SQLite" if _is_sqlite else "PostgreSQL (pooler)" if _is_pooler else "PostgreSQL"
        logger.info(f"Database ready ({driver})")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
