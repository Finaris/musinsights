"""MusicBrainz API integration for metadata lookup."""

import asyncio
import time
from dataclasses import dataclass

import musicbrainzngs

# Configure the MusicBrainz client
musicbrainzngs.set_useragent(
    "MusInsights",
    "0.1.0",
    "https://github.com/Finaris/musinsights",
)


@dataclass
class MusicBrainzMatch:
    """Result of a MusicBrainz lookup."""

    recording_id: str
    artist_id: str
    title: str
    artist: str
    score: int  # Match confidence 0-100


class MusicBrainzService:
    """Service for looking up MusicBrainz IDs."""

    # Rate limit: 1 request per second for unauthenticated requests
    MIN_REQUEST_INTERVAL = 1.0

    def __init__(self) -> None:
        self._last_request_time: float = 0

    async def _rate_limit(self) -> None:
        """Ensure we don't exceed MusicBrainz rate limits."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    async def lookup_recording(
        self,
        title: str,
        artist: str,
        duration_ms: int | None = None,
    ) -> MusicBrainzMatch | None:
        """Look up a recording by title and artist.

        Args:
            title: The track title.
            artist: The artist name.
            duration_ms: Optional duration in milliseconds for better matching.

        Returns:
            MusicBrainzMatch if found with good confidence, None otherwise.
        """
        await self._rate_limit()

        # Build search query
        query = f'recording:"{title}" AND artist:"{artist}"'

        try:
            # Run the blocking API call in a thread pool
            result = await asyncio.to_thread(
                musicbrainzngs.search_recordings,
                query=query,
                limit=5,
            )
        except musicbrainzngs.WebServiceError:
            # Log but don't crash on API errors
            return None

        recordings = result.get("recording-list", [])
        if not recordings:
            return None

        # Find best match
        best_match: MusicBrainzMatch | None = None
        best_score = 0

        for recording in recordings:
            score = int(recording.get("ext:score", 0))

            # Must have at least one artist credit
            artist_credits = recording.get("artist-credit", [])
            if not artist_credits:
                continue

            # Get first artist (primary artist)
            first_credit = artist_credits[0]
            if isinstance(first_credit, dict) and "artist" in first_credit:
                artist_info = first_credit["artist"]
                artist_id = artist_info.get("id")
                artist_name = artist_info.get("name", "")
            else:
                continue

            recording_id = recording.get("id")
            recording_title = recording.get("title", "")

            if not recording_id or not artist_id:
                continue

            # If duration provided, check it's within 5 seconds
            if duration_ms is not None:
                recording_length = recording.get("length")
                if recording_length:
                    diff = abs(int(recording_length) - duration_ms)
                    if diff > 5000:  # More than 5 seconds difference
                        score -= 20  # Penalize but don't disqualify

            if score > best_score:
                best_score = score
                best_match = MusicBrainzMatch(
                    recording_id=recording_id,
                    artist_id=artist_id,
                    title=recording_title,
                    artist=artist_name,
                    score=score,
                )

        # Only return if we have a reasonably confident match
        if best_match and best_match.score >= 80:
            return best_match

        return None

    async def lookup_artist(self, artist_name: str) -> str | None:
        """Look up an artist's MusicBrainz ID by name.

        Args:
            artist_name: The artist name to search for.

        Returns:
            MusicBrainz artist ID if found, None otherwise.
        """
        await self._rate_limit()

        try:
            result = await asyncio.to_thread(
                musicbrainzngs.search_artists,
                query=f'artist:"{artist_name}"',
                limit=1,
            )
        except musicbrainzngs.WebServiceError:
            return None

        artists = result.get("artist-list", [])
        if artists:
            return artists[0].get("id")
        return None
