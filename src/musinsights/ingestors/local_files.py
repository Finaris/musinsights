"""Local file ingestor for scanning and importing music files."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiofiles
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from musinsights.ingestors.base import BaseIngestor, IngestResult

# Supported audio file extensions
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus", ".wma", ".aac"}


class LocalFileIngestor(BaseIngestor[Path]):
    """Ingestor for local audio files.

    Scans directories for supported audio files, extracts metadata
    using mutagen, and stores song records in the database.
    """

    source_name = "local"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def ingest(
        self,
        source: Path,
        recursive: bool = True,
        dry_run: bool = False,
        compute_hash: bool = True,
    ) -> IngestResult:
        """Ingest audio files from a local directory.

        Args:
            source: Path to a file or directory to ingest.
            recursive: Whether to scan subdirectories recursively.
            dry_run: If True, only count files without saving.
            compute_hash: Whether to compute file hashes for deduplication.

        Returns:
            IngestResult with counts of processed files.
        """
        result = IngestResult()

        async for file_path in self._scan_files(source, recursive):
            result.total += 1

            try:
                # Extract metadata
                metadata = await self.extract_metadata(file_path)

                if compute_hash:
                    metadata["file_hash"] = await self._compute_file_hash(file_path)

                # Check for existing song by file path or hash
                existing = await self.find_existing(
                    file_path=str(file_path.absolute()),
                    file_hash=metadata.get("file_hash"),
                )

                if existing:
                    result.skipped += 1
                    continue

                if not dry_run:
                    try:
                        # Use savepoint so we can recover from constraint violations
                        async with self.session.begin_nested():
                            await self.create_song(metadata)
                        result.created += 1
                    except IntegrityError:
                        # Duplicate detected at database level (race condition or
                        # path normalization mismatch) - treat as skip, not error
                        result.add_duplicate()
                else:
                    result.created += 1  # Count as would-be-created in dry run

            except Exception as e:
                result.add_error(str(file_path), str(e))

        return result

    async def _scan_files(
        self, path: Path, recursive: bool
    ) -> AsyncIterator[Path]:
        """Scan for audio files in a path.

        Args:
            path: File or directory path to scan.
            recursive: Whether to scan subdirectories.

        Yields:
            Paths to audio files.
        """
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path
            return

        pattern = "**/*" if recursive else "*"

        # Run glob in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(
            None, lambda: list(path.glob(pattern))
        )

        for file_path in files:
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield file_path

    async def extract_metadata(self, item: Path) -> dict[str, Any]:
        """Extract metadata from an audio file using mutagen.

        Args:
            item: Path to the audio file.

        Returns:
            Dictionary of metadata fields.
        """
        # Run mutagen in thread pool (it's synchronous and does I/O)
        loop = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(
            None, self._extract_metadata_sync, item
        )
        return metadata

    def _extract_metadata_sync(self, file_path: Path) -> dict[str, Any]:
        """Synchronous metadata extraction using mutagen.

        Args:
            file_path: Path to the audio file.

        Returns:
            Dictionary of metadata fields.
        """
        metadata: dict[str, Any] = {
            "file_path": str(file_path.absolute()),
            "title": file_path.stem,  # Default to filename
            "artist": "Unknown",
            "album": None,
            "duration_ms": None,
        }

        try:
            audio = MutagenFile(file_path, easy=True)

            if audio is None:
                return metadata

            # Get duration
            if hasattr(audio, "info") and hasattr(audio.info, "length"):
                metadata["duration_ms"] = int(audio.info.length * 1000)

            # Extract tags based on file type
            if isinstance(audio, (EasyID3, FLAC)) or hasattr(audio, "tags"):
                self._extract_common_tags(audio, metadata)
            elif isinstance(audio, MP4):
                self._extract_mp4_tags(audio, metadata)

        except Exception:
            # If mutagen fails, return metadata with filename as title
            pass

        return metadata

    def _extract_common_tags(
        self, audio: Any, metadata: dict[str, Any]
    ) -> None:
        """Extract tags from common formats (MP3, FLAC, OGG).

        Args:
            audio: Mutagen audio object.
            metadata: Metadata dict to update.
        """
        tags = audio.tags if hasattr(audio, "tags") else audio

        if tags is None:
            return

        # Try different tag formats
        if "title" in tags:
            metadata["title"] = self._get_tag_value(tags["title"])
        elif "TIT2" in tags:
            metadata["title"] = str(tags["TIT2"])

        if "artist" in tags:
            metadata["artist"] = self._get_tag_value(tags["artist"])
        elif "TPE1" in tags:
            metadata["artist"] = str(tags["TPE1"])

        if "album" in tags:
            metadata["album"] = self._get_tag_value(tags["album"])
        elif "TALB" in tags:
            metadata["album"] = str(tags["TALB"])

    def _extract_mp4_tags(self, audio: MP4, metadata: dict[str, Any]) -> None:
        """Extract tags from MP4/M4A files.

        Args:
            audio: MP4 audio object.
            metadata: Metadata dict to update.
        """
        if audio.tags is None:
            return

        tags = audio.tags

        if "\xa9nam" in tags:  # Title
            metadata["title"] = tags["\xa9nam"][0]

        if "\xa9ART" in tags:  # Artist
            metadata["artist"] = tags["\xa9ART"][0]

        if "\xa9alb" in tags:  # Album
            metadata["album"] = tags["\xa9alb"][0]

    def _get_tag_value(self, tag: Any) -> str:
        """Safely extract a string value from a tag.

        Args:
            tag: Tag value (could be list or string).

        Returns:
            String value.
        """
        if isinstance(tag, list) and tag:
            return str(tag[0])
        return str(tag)

    async def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of an audio file.

        Args:
            file_path: Path to the audio file.

        Returns:
            Hex-encoded SHA256 hash.
        """
        sha256_hash = hashlib.sha256()

        async with aiofiles.open(file_path, "rb") as f:
            # Read in chunks to handle large files
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()
