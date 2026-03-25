"""Repository pattern for database operations."""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from musinsights.db.models import AudioFeatures, ListeningHistory, Song, SpectralFeatures


class SongRepository:
    """Repository for Song-related database operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with a database session.

        Args:
            session: An async database session.
        """
        self.session = session

    async def create(self, song: Song) -> Song:
        """Create a new song in the database.

        Args:
            song: The Song object to create.

        Returns:
            The created Song object with ID populated.
        """
        self.session.add(song)
        await self.session.flush()
        return song

    async def get_by_id(self, song_id: str, load_features: bool = False) -> Optional[Song]:
        """Get a song by its ID.

        Args:
            song_id: The UUID of the song.
            load_features: Whether to eagerly load audio and spectral features.

        Returns:
            The Song object if found, None otherwise.
        """
        stmt = select(Song).where(Song.id == song_id)
        if load_features:
            stmt = stmt.options(
                selectinload(Song.audio_features),
                selectinload(Song.spectral_features),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_file_path(self, file_path: str) -> Optional[Song]:
        """Get a song by its file path.

        Args:
            file_path: The local file path of the song.

        Returns:
            The Song object if found, None otherwise.
        """
        stmt = select(Song).where(Song.file_path == file_path)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_file_hash(self, file_hash: str) -> Optional[Song]:
        """Get a song by its file hash.

        Args:
            file_hash: The SHA256 hash of the audio file.

        Returns:
            The Song object if found, None otherwise.
        """
        stmt = select(Song).where(Song.file_hash == file_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        source: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Sequence[Song]:
        """Get all songs, optionally filtered by source.

        Args:
            source: Optional source filter (e.g., 'local', 'spotify').
            limit: Maximum number of songs to return.
            offset: Number of songs to skip.

        Returns:
            List of Song objects.
        """
        stmt = select(Song).order_by(Song.created_at.desc())
        if source:
            stmt = stmt.where(Song.source == source)
        if limit:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_unanalyzed(self, limit: Optional[int] = None) -> Sequence[Song]:
        """Get songs that haven't been analyzed yet.

        Args:
            limit: Maximum number of songs to return.

        Returns:
            List of Song objects without audio features.
        """
        stmt = (
            select(Song)
            .outerjoin(AudioFeatures)
            .where(AudioFeatures.song_id.is_(None))
            .order_by(Song.created_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, song: Song) -> Song:
        """Update an existing song.

        Args:
            song: The Song object with updated fields.

        Returns:
            The updated Song object.
        """
        await self.session.flush()
        return song

    async def delete(self, song_id: str) -> bool:
        """Delete a song by its ID.

        Args:
            song_id: The UUID of the song to delete.

        Returns:
            True if the song was deleted, False if not found.
        """
        song = await self.get_by_id(song_id)
        if song:
            await self.session.delete(song)
            return True
        return False

    async def count(self, source: Optional[str] = None) -> int:
        """Count total songs, optionally filtered by source.

        Args:
            source: Optional source filter.

        Returns:
            Number of songs.
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Song)
        if source:
            stmt = stmt.where(Song.source == source)
        result = await self.session.execute(stmt)
        return result.scalar_one()


class AudioFeaturesRepository:
    """Repository for AudioFeatures database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, features: AudioFeatures) -> AudioFeatures:
        """Create audio features for a song."""
        self.session.add(features)
        await self.session.flush()
        return features

    async def get_by_song_id(self, song_id: str) -> Optional[AudioFeatures]:
        """Get audio features for a specific song."""
        stmt = select(AudioFeatures).where(AudioFeatures.song_id == song_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, features: AudioFeatures) -> AudioFeatures:
        """Create or update audio features for a song."""
        existing = await self.get_by_song_id(features.song_id)
        if existing:
            # Update existing record
            for key, value in vars(features).items():
                if not key.startswith("_") and key != "song_id":
                    setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.create(features)


class ListeningHistoryRepository:
    """Repository for ListeningHistory database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, entry: ListeningHistory) -> ListeningHistory:
        """Create a listening history entry."""
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_by_song_id(
        self,
        song_id: str,
        limit: Optional[int] = None,
    ) -> Sequence[ListeningHistory]:
        """Get listening history for a specific song."""
        stmt = (
            select(ListeningHistory)
            .where(ListeningHistory.song_id == song_id)
            .order_by(ListeningHistory.played_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent(self, limit: int = 50) -> Sequence[ListeningHistory]:
        """Get recent listening history entries."""
        stmt = (
            select(ListeningHistory)
            .options(selectinload(ListeningHistory.song))
            .order_by(ListeningHistory.played_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
