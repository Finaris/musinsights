"""Database engine and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from musinsights.config import settings
from musinsights.db.models import Base


def create_engine(url: str | None = None) -> AsyncEngine:
    """Create an async database engine.

    Args:
        url: Database URL. If None, uses the URL from settings.

    Returns:
        AsyncEngine instance.
    """
    db_url = url or settings.database_url
    return create_async_engine(
        db_url,
        echo=False,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory.

    Args:
        engine: The database engine to use.

    Returns:
        Async session factory.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Default engine and session factory
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get the default database engine, creating it if necessary."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the default session factory, creating it if necessary."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session as a context manager.

    Yields:
        AsyncSession instance.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_database(engine: AsyncEngine | None = None) -> None:
    """Initialize the database schema.

    Args:
        engine: Optional engine to use. If None, uses the default engine.
    """
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Close the default database engine."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
