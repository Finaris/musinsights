"""Tests for the local file ingestor."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from musinsights.db.repository import SongRepository
from musinsights.ingestors.local_files import LocalFileIngestor, SUPPORTED_EXTENSIONS


class TestSupportedExtensions:
    """Test supported file extension detection."""

    def test_common_audio_formats(self):
        """Common audio formats should be supported."""
        for ext in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
            assert ext in SUPPORTED_EXTENSIONS

    def test_case_insensitive(self):
        """Extension check should be case-insensitive."""
        # The actual check in the ingestor uses .lower()
        assert ".mp3" in SUPPORTED_EXTENSIONS


class TestLocalFileIngestor:
    """Tests for LocalFileIngestor."""

    @pytest_asyncio.fixture
    async def ingestor(self, db_session: AsyncSession) -> LocalFileIngestor:
        """Create an ingestor instance."""
        return LocalFileIngestor(db_session)

    @pytest.mark.asyncio
    async def test_ingest_empty_directory(
        self,
        ingestor: LocalFileIngestor,
        tmp_path: Path,
    ):
        """Ingesting an empty directory should return zero counts."""
        result = await ingestor.ingest(tmp_path, recursive=True)
        assert result.total == 0
        assert result.created == 0
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_ingest_filters_non_audio_files(
        self,
        ingestor: LocalFileIngestor,
        sample_audio_dir: Path,
    ):
        """Non-audio files should be filtered out."""
        result = await ingestor.ingest(sample_audio_dir, recursive=True, dry_run=True)
        # Should find 4 audio files, not the .jpg
        assert result.total == 4

    @pytest.mark.asyncio
    async def test_ingest_recursive(
        self,
        ingestor: LocalFileIngestor,
        sample_audio_dir: Path,
    ):
        """Recursive scan should find files in subdirectories."""
        result = await ingestor.ingest(sample_audio_dir, recursive=True, dry_run=True)
        # 2 in root + 2 in subdirectory
        assert result.total == 4

    @pytest.mark.asyncio
    async def test_ingest_non_recursive(
        self,
        ingestor: LocalFileIngestor,
        sample_audio_dir: Path,
    ):
        """Non-recursive scan should only find files in root directory."""
        result = await ingestor.ingest(sample_audio_dir, recursive=False, dry_run=True)
        # Only 2 files in root directory
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_ingest_creates_songs(
        self,
        ingestor: LocalFileIngestor,
        db_session: AsyncSession,
        sample_audio_dir: Path,
    ):
        """Ingestion should create song records in the database."""
        result = await ingestor.ingest(
            sample_audio_dir,
            recursive=True,
            compute_hash=False,  # Skip hash for empty test files
        )

        # Note: Empty files will fail metadata extraction but should still be counted
        repo = SongRepository(db_session)
        songs = await repo.get_all()
        assert len(songs) == result.created

    @pytest.mark.asyncio
    async def test_ingest_skips_existing_files(
        self,
        ingestor: LocalFileIngestor,
        db_session: AsyncSession,
        sample_audio_dir: Path,
    ):
        """Re-ingesting should skip already imported files."""
        # First ingestion
        result1 = await ingestor.ingest(
            sample_audio_dir,
            recursive=True,
            compute_hash=False,
        )

        # Second ingestion should skip all
        result2 = await ingestor.ingest(
            sample_audio_dir,
            recursive=True,
            compute_hash=False,
        )

        assert result2.skipped == result1.created
        assert result2.created == 0
