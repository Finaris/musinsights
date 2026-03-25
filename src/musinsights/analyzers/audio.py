"""Audio analyzer using librosa for feature extraction."""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from musinsights.analyzers.base import AnalysisResult, BaseAnalyzer, SongFeatures
from musinsights.config import settings
from musinsights.db.models import AudioFeatures, Song, SpectralFeatures


def _analyze_file_sync(file_path: str) -> dict[str, Any]:
    """Synchronous audio analysis using librosa.

    This function runs in a separate process to avoid GIL limitations.

    Args:
        file_path: Path to the audio file.

    Returns:
        Dictionary containing all extracted features.
    """
    import librosa

    # Load audio file
    y, sr = librosa.load(file_path, sr=22050, mono=True)

    features: dict[str, Any] = {}

    # Basic audio features
    try:
        # Tempo and beat
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        features["tempo"] = float(tempo) if not isinstance(tempo, np.ndarray) else float(tempo[0])
    except Exception:
        features["tempo"] = None

    try:
        # Loudness (RMS energy converted to dB)
        rms = librosa.feature.rms(y=y)[0]
        features["loudness"] = float(20 * np.log10(np.mean(rms) + 1e-10))
    except Exception:
        features["loudness"] = None

    try:
        # Energy (normalized RMS)
        rms = librosa.feature.rms(y=y)[0]
        features["energy"] = float(np.mean(rms) / (np.max(rms) + 1e-10))
    except Exception:
        features["energy"] = None

    try:
        # Key detection using chroma features
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        features["key"] = int(np.argmax(chroma_mean))  # 0-11
        features["chroma_mean"] = chroma_mean.tobytes()
    except Exception:
        features["key"] = None
        features["chroma_mean"] = None

    try:
        # Zero crossing rate
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        features["zero_crossing_rate"] = float(np.mean(zcr))
    except Exception:
        features["zero_crossing_rate"] = None

    # Spectral features
    try:
        # Spectral centroid (brightness)
        spec_cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        features["spectral_centroid"] = float(np.mean(spec_cent))
    except Exception:
        features["spectral_centroid"] = None

    try:
        # Spectral rolloff
        spec_roll = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        features["spectral_rolloff"] = float(np.mean(spec_roll))
    except Exception:
        features["spectral_rolloff"] = None

    try:
        # Spectral contrast
        spec_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        features["spectral_contrast"] = np.mean(spec_contrast, axis=1).tobytes()
    except Exception:
        features["spectral_contrast"] = None

    # MFCCs
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        features["mfcc_mean"] = np.mean(mfcc, axis=1).tobytes()
        features["mfcc_std"] = np.std(mfcc, axis=1).tobytes()
    except Exception:
        features["mfcc_mean"] = None
        features["mfcc_std"] = None

    return features


class AudioAnalyzer(BaseAnalyzer):
    """Analyzer using librosa for audio feature extraction.

    Extracts tempo, key, energy, spectral features, and MFCCs from audio files.
    Uses multiprocessing to parallelize analysis of multiple songs.
    """

    analyzer_name = "audio"

    def __init__(self, session: AsyncSession, max_workers: int | None = None) -> None:
        """Initialize the analyzer.

        Args:
            session: Async database session.
            max_workers: Maximum parallel workers. Defaults to settings value.
        """
        super().__init__(session)
        self.max_workers = max_workers or settings.analysis_workers

    async def analyze(self, song: Song) -> SongFeatures:
        """Analyze a single song using librosa.

        Args:
            song: Song object with a valid file_path.

        Returns:
            SongFeatures containing extracted features.

        Raises:
            ValueError: If song has no file_path.
            FileNotFoundError: If the file doesn't exist.
        """
        if not song.file_path:
            raise ValueError(f"Song {song.id} has no file_path")

        file_path = Path(song.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Run analysis in process pool
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=1) as executor:
            features = await loop.run_in_executor(
                executor, _analyze_file_sync, str(file_path)
            )

        return self._create_features(song.id, features)

    async def analyze_batch(
        self,
        songs: Sequence[Song],
        progress_callback: Any | None = None,
    ) -> AnalysisResult:
        """Analyze multiple songs in parallel using multiprocessing.

        Args:
            songs: List of Song objects to analyze.
            progress_callback: Optional callback(current, total, song).

        Returns:
            AnalysisResult with success/failure counts.
        """
        result = AnalysisResult()

        # Filter songs with valid file paths
        valid_songs = [s for s in songs if s.file_path and Path(s.file_path).exists()]

        if not valid_songs:
            return result

        loop = asyncio.get_event_loop()

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Create tasks for all songs
            tasks = [
                loop.run_in_executor(executor, _analyze_file_sync, song.file_path)
                for song in valid_songs
            ]

            # Process results as they complete
            for i, (song, task) in enumerate(zip(valid_songs, asyncio.as_completed(tasks))):
                try:
                    features_dict = await task
                    features = self._create_features(song.id, features_dict)

                    if features.audio_features:
                        await self.save_audio_features(song, features.audio_features)

                    if features.spectral_features:
                        await self.save_spectral_features(song, features.spectral_features)

                    result.success += 1

                    if progress_callback:
                        progress_callback(i + 1, len(valid_songs), song)

                except Exception as e:
                    result.add_error(song.id, str(e))

        return result

    def _create_features(
        self, song_id: str, features: dict[str, Any]
    ) -> SongFeatures:
        """Create feature objects from extracted data.

        Args:
            song_id: ID of the song.
            features: Dictionary of extracted features.

        Returns:
            SongFeatures with AudioFeatures and SpectralFeatures.
        """
        audio_features = AudioFeatures(
            song_id=song_id,
            tempo=features.get("tempo"),
            key=features.get("key"),
            loudness=features.get("loudness"),
            energy=features.get("energy"),
            # These would require more sophisticated analysis:
            # danceability, valence, acousticness, instrumentalness, speechiness
        )

        spectral_features = SpectralFeatures(
            song_id=song_id,
            mfcc_mean=features.get("mfcc_mean"),
            mfcc_std=features.get("mfcc_std"),
            spectral_centroid=features.get("spectral_centroid"),
            spectral_rolloff=features.get("spectral_rolloff"),
            spectral_contrast=features.get("spectral_contrast"),
            chroma_mean=features.get("chroma_mean"),
            zero_crossing_rate=features.get("zero_crossing_rate"),
        )

        return SongFeatures(
            audio_features=audio_features,
            spectral_features=spectral_features,
        )
