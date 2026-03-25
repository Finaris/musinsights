"""Base classes for data ingestors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from musinsights.db.models import Song

SourceT = TypeVar("SourceT")


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, source: str, error: str) -> None:
        """Record an error during ingestion."""
        self.errors += 1
        self.error_details.append({"source": source, "error": error})


class BaseIngestor(ABC, Generic[SourceT]):
    """Abstract base class for all data ingestors.

    Ingestors are responsible for:
    1. Scanning a data source (local files, API, etc.)
    2. Extracting metadata from the source
    3. Creating or updating Song records in the database

    Each ingestor implementation handles a specific source type.
    """

    source_name: str = "unknown"

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the ingestor.

        Args:
            session: Async database session for persisting data.
        """
        self.session = session

    @abstractmethod
    async def ingest(self, source: SourceT, **kwargs: Any) -> IngestResult:
        """Ingest data from the source.

        Args:
            source: The source to ingest from (path, API credentials, etc.)
            **kwargs: Additional options for the ingestion.

        Returns:
            IngestResult with counts of processed items.
        """
        pass

    @abstractmethod
    async def extract_metadata(self, item: Any) -> dict[str, Any]:
        """Extract metadata from a single source item.

        Args:
            item: A single item from the source (file path, API response, etc.)

        Returns:
            Dictionary of metadata fields.
        """
        pass

    async def find_existing(self, **identifiers: Any) -> Song | None:
        """Find an existing song by various identifiers.

        Subclasses should override to implement source-specific lookups.

        Args:
            **identifiers: Key-value pairs to search for (file_path, file_hash, etc.)

        Returns:
            Existing Song if found, None otherwise.
        """
        from musinsights.db.repository import SongRepository

        repo = SongRepository(self.session)

        if file_path := identifiers.get("file_path"):
            return await repo.get_by_file_path(file_path)

        if file_hash := identifiers.get("file_hash"):
            return await repo.get_by_file_hash(file_hash)

        return None

    async def create_song(self, metadata: dict[str, Any]) -> Song:
        """Create a new Song record from metadata.

        Args:
            metadata: Dictionary of song metadata.

        Returns:
            Created Song object.
        """
        song = Song(
            title=metadata.get("title", "Unknown"),
            artist=metadata.get("artist", "Unknown"),
            album=metadata.get("album"),
            duration_ms=metadata.get("duration_ms"),
            file_path=metadata.get("file_path"),
            file_hash=metadata.get("file_hash"),
            source=self.source_name,
            external_ids=metadata.get("external_ids"),
        )
        self.session.add(song)
        await self.session.flush()
        return song
