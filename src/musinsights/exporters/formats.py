"""Export functions for various data formats."""

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from musinsights.db.models import Song


def _serialize_datetime(obj: Any) -> Any:
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def _fetch_songs_with_features(session: AsyncSession) -> Sequence[Song]:
    """Fetch all songs with their features eagerly loaded.

    Args:
        session: Database session.

    Returns:
        Sequence of Song objects with features loaded.
    """
    stmt = (
        select(Song)
        .options(
            selectinload(Song.audio_features),
            selectinload(Song.spectral_features),
        )
        .order_by(Song.artist, Song.title)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


def _song_to_dict(song: Song, include_features: bool = True) -> dict[str, Any]:
    """Convert a Song object to a nested dictionary (for JSON).

    Args:
        song: Song object to convert.
        include_features: Whether to include audio and spectral features.

    Returns:
        Dictionary representation of the song.
    """
    data: dict[str, Any] = {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "duration_ms": song.duration_ms,
        "file_path": song.file_path,
        "file_hash": song.file_hash,
        "source": song.source,
        "external_ids": song.external_ids,
        "created_at": song.created_at.isoformat() if song.created_at else None,
        "updated_at": song.updated_at.isoformat() if song.updated_at else None,
    }

    if include_features and song.audio_features:
        af = song.audio_features
        data["audio_features"] = {
            "tempo": af.tempo,
            "time_signature": af.time_signature,
            "key": af.key,
            "mode": af.mode,
            "loudness": af.loudness,
            "energy": af.energy,
            "danceability": af.danceability,
            "valence": af.valence,
            "acousticness": af.acousticness,
            "instrumentalness": af.instrumentalness,
            "speechiness": af.speechiness,
            "analyzed_at": af.analyzed_at.isoformat() if af.analyzed_at else None,
        }

    if include_features and song.spectral_features:
        sf = song.spectral_features
        data["spectral_features"] = {
            "spectral_centroid": sf.spectral_centroid,
            "spectral_rolloff": sf.spectral_rolloff,
            "zero_crossing_rate": sf.zero_crossing_rate,
            "analyzed_at": sf.analyzed_at.isoformat() if sf.analyzed_at else None,
        }

    return data


def _song_to_flat_dict(song: Song) -> dict[str, Any]:
    """Convert a Song object to a flat dictionary (for CSV).

    Args:
        song: Song object to convert.

    Returns:
        Flat dictionary with all fields at top level.
    """
    data = _song_to_dict(song, include_features=False)

    # Remove fields not suitable for CSV
    data.pop("file_path", None)
    data.pop("file_hash", None)
    data.pop("external_ids", None)
    data.pop("created_at", None)
    data.pop("updated_at", None)

    # Flatten audio features
    if song.audio_features:
        af = song.audio_features
        data.update({
            "tempo": af.tempo,
            "time_signature": af.time_signature,
            "key": af.key,
            "mode": af.mode,
            "loudness": af.loudness,
            "energy": af.energy,
            "danceability": af.danceability,
            "valence": af.valence,
            "acousticness": af.acousticness,
            "instrumentalness": af.instrumentalness,
            "speechiness": af.speechiness,
        })

    # Flatten spectral features
    if song.spectral_features:
        sf = song.spectral_features
        data.update({
            "spectral_centroid": sf.spectral_centroid,
            "spectral_rolloff": sf.spectral_rolloff,
            "zero_crossing_rate": sf.zero_crossing_rate,
        })

    return data


async def export_to_json(
    session: AsyncSession,
    output_path: Path,
    pretty: bool = True,
) -> int:
    """Export all songs and features to JSON.

    Args:
        session: Database session.
        output_path: Path to write the JSON file.
        pretty: Whether to pretty-print the JSON.

    Returns:
        Number of songs exported.
    """
    songs = await _fetch_songs_with_features(session)

    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_songs": len(songs),
        "songs": [_song_to_dict(song) for song in songs],
    }

    indent = 2 if pretty else None

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=_serialize_datetime)

    return len(songs)


# CSV column order
CSV_COLUMNS = [
    "id",
    "title",
    "artist",
    "album",
    "duration_ms",
    "source",
    "tempo",
    "time_signature",
    "key",
    "mode",
    "loudness",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "instrumentalness",
    "speechiness",
    "spectral_centroid",
    "spectral_rolloff",
    "zero_crossing_rate",
]


async def export_to_csv(
    session: AsyncSession,
    output_path: Path,
) -> int:
    """Export all songs and features to CSV.

    Args:
        session: Database session.
        output_path: Path to write the CSV file.

    Returns:
        Number of songs exported.
    """
    import csv

    songs = await _fetch_songs_with_features(session)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        for song in songs:
            writer.writerow(_song_to_flat_dict(song))

    return len(songs)


# Convenience exports
export_json = export_to_json
export_csv = export_to_csv
