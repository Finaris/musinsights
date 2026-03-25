"""Database models and repository layer."""

from musinsights.db.engine import (
    close_engine,
    create_engine,
    get_engine,
    get_session,
    get_session_factory,
    init_database,
)
from musinsights.db.models import AudioFeatures, Base, ListeningHistory, Song, SpectralFeatures
from musinsights.db.repository import (
    AudioFeaturesRepository,
    ListeningHistoryRepository,
    SongRepository,
)

__all__ = [
    # Models
    "Base",
    "Song",
    "AudioFeatures",
    "SpectralFeatures",
    "ListeningHistory",
    # Engine/Session
    "create_engine",
    "get_engine",
    "get_session",
    "get_session_factory",
    "init_database",
    "close_engine",
    # Repositories
    "SongRepository",
    "AudioFeaturesRepository",
    "ListeningHistoryRepository",
]
