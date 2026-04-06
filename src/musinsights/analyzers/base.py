"""Base classes for audio analyzers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from musinsights.db.models import AudioFeatures, Song, SpectralFeatures
from musinsights.db.repository import AudioFeaturesRepository


@dataclass
class AnalysisResult:
    """Result of an analysis operation."""

    success: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, song_id: str, error: str) -> None:
        """Record an analysis error."""
        self.failed += 1
        self.errors.append({"song_id": song_id, "error": error})


@dataclass
class SongFeatures:
    """Container for all features extracted from a song."""

    audio_features: AudioFeatures | None = None
    spectral_features: SpectralFeatures | None = None


class BaseAnalyzer(ABC):
    """Abstract base class for audio analyzers.

    Analyzers are responsible for:
    1. Loading audio data from a song's file
    2. Extracting various features (tempo, key, spectral, etc.)
    3. Storing the features in the database

    Each analyzer implementation focuses on a specific type of analysis.
    """

    analyzer_name: str = "unknown"

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the analyzer.

        Args:
            session: Async database session for persisting features.
        """
        self.session = session

    @abstractmethod
    async def analyze(self, song: Song) -> SongFeatures:
        """Analyze a single song.

        Args:
            song: The Song object to analyze (must have a valid file_path).

        Returns:
            SongFeatures containing the extracted features.
        """
        pass

    async def analyze_batch(
        self,
        songs: Sequence[Song],
        progress_callback: Any | None = None,
    ) -> AnalysisResult:
        """Analyze a batch of songs.

        Default implementation processes songs sequentially.
        Subclasses can override to implement parallel processing.

        Args:
            songs: List of Song objects to analyze.
            progress_callback: Optional callback for progress updates.

        Returns:
            AnalysisResult with success/failure counts.
        """
        result = AnalysisResult()

        for i, song in enumerate(songs):
            try:
                features = await self.analyze(song)

                if features.audio_features:
                    await self.save_audio_features(song, features.audio_features)

                if features.spectral_features:
                    await self.save_spectral_features(song, features.spectral_features)

                result.success += 1

                if progress_callback:
                    progress_callback(i + 1, len(songs), song)

            except Exception as e:
                result.add_error(song.id, str(e))

        return result

    async def save_audio_features(
        self, song: Song, features: AudioFeatures
    ) -> AudioFeatures:
        """Save audio features to the database.

        Args:
            song: The Song the features belong to.
            features: The AudioFeatures to save.

        Returns:
            The saved AudioFeatures object.
        """
        features.song_id = song.id
        repo = AudioFeaturesRepository(self.session)
        return await repo.upsert(features)

    async def save_spectral_features(
        self, song: Song, features: SpectralFeatures
    ) -> SpectralFeatures:
        """Save spectral features to the database.

        Args:
            song: The Song the features belong to.
            features: The SpectralFeatures to save.

        Returns:
            The saved SpectralFeatures object.
        """
        features.song_id = song.id
        self.session.add(features)
        await self.session.flush()
        return features
