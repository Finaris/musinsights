"""SQLAlchemy models for the MusInsights database."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def generate_uuid() -> str:
    """Generate a UUID string for use as primary key."""
    return str(uuid.uuid4())


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass


class Song(Base):
    """Primary entity representing a song."""

    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    artist: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    album: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_ids: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    audio_features: Mapped[Optional["AudioFeatures"]] = relationship(
        back_populates="song", uselist=False, cascade="all, delete-orphan"
    )
    spectral_features: Mapped[Optional["SpectralFeatures"]] = relationship(
        back_populates="song", uselist=False, cascade="all, delete-orphan"
    )
    listening_history: Mapped[list["ListeningHistory"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Song(title='{self.title}', artist='{self.artist}')>"


class AudioFeatures(Base):
    """Audio features extracted from waveform analysis."""

    __tablename__ = "audio_features"

    song_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    tempo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_signature: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    key: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-11 for C to B
    mode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1=major, 0=minor
    loudness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # dB
    energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    danceability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    valence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    acousticness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    instrumentalness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    speechiness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    analyzed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationship
    song: Mapped["Song"] = relationship(back_populates="audio_features")

    def __repr__(self) -> str:
        return f"<AudioFeatures(song_id='{self.song_id}', tempo={self.tempo})>"


class SpectralFeatures(Base):
    """Detailed spectral features from audio analysis."""

    __tablename__ = "spectral_features"

    song_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    mfcc_mean: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    mfcc_std: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    spectral_centroid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spectral_rolloff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spectral_contrast: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    chroma_mean: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    zero_crossing_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationship
    song: Mapped["Song"] = relationship(back_populates="spectral_features")

    def __repr__(self) -> str:
        return f"<SpectralFeatures(song_id='{self.song_id}')>"


class ListeningHistory(Base):
    """Record of when songs were played."""

    __tablename__ = "listening_history"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    song_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("songs.id", ondelete="CASCADE"), index=True
    )
    played_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationship
    song: Mapped["Song"] = relationship(back_populates="listening_history")

    def __repr__(self) -> str:
        return f"<ListeningHistory(song_id='{self.song_id}', played_at='{self.played_at}')>"
