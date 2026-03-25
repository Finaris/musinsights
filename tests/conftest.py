"""Pytest configuration and fixtures."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from musinsights.db.models import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an in-memory SQLite database session for testing."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_audio_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample audio files.

    Note: This creates empty files for testing file discovery.
    Actual audio analysis requires real audio files.
    """
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()

    # Create subdirectories
    artist_dir = audio_dir / "Artist Name"
    artist_dir.mkdir()
    album_dir = artist_dir / "Album Name"
    album_dir.mkdir()

    # Create dummy audio files (empty, for testing file discovery only)
    (audio_dir / "song1.mp3").touch()
    (audio_dir / "song2.flac").touch()
    (album_dir / "track01.mp3").touch()
    (album_dir / "track02.m4a").touch()

    # Create a non-audio file to test filtering
    (audio_dir / "cover.jpg").touch()

    return audio_dir
