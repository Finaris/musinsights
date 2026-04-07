"""ListenBrainz API integration for scrobbling and listening history."""

from dataclasses import dataclass
from datetime import datetime

import httpx

from musinsights.config import settings

# ListenBrainz API base URL
API_BASE = "https://api.listenbrainz.org"


@dataclass
class Listen:
    """A single listen event."""

    track_name: str
    artist_name: str
    listened_at: int  # Unix timestamp
    release_name: str | None = None
    recording_mbid: str | None = None
    artist_mbid: str | None = None
    duration_ms: int | None = None


@dataclass
class SubmitResult:
    """Result of a listen submission."""

    success: bool
    message: str


class ListenBrainzService:
    """Service for interacting with the ListenBrainz API."""

    def __init__(self, token: str | None = None) -> None:
        """Initialize the service.

        Args:
            token: ListenBrainz user token. If not provided, uses settings.
        """
        self.token = token or settings.listenbrainz_token
        if not self.token:
            raise ValueError(
                "ListenBrainz token required. Set MUSINSIGHTS_LISTENBRAINZ_TOKEN "
                "environment variable or pass token directly."
            )

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers for API requests."""
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    async def submit_listen(self, listen: Listen) -> SubmitResult:
        """Submit a single listen to ListenBrainz.

        Args:
            listen: The listen event to submit.

        Returns:
            SubmitResult indicating success or failure.
        """
        payload = self._build_listen_payload([listen], "single")
        return await self._submit_payload(payload)

    async def submit_listens(self, listens: list[Listen]) -> SubmitResult:
        """Submit multiple listens to ListenBrainz.

        Args:
            listens: List of listen events to submit (max 1000).

        Returns:
            SubmitResult indicating success or failure.
        """
        if len(listens) > 1000:
            return SubmitResult(
                success=False,
                message="Cannot submit more than 1000 listens at once",
            )

        payload = self._build_listen_payload(listens, "import")
        return await self._submit_payload(payload)

    async def submit_now_playing(self, listen: Listen) -> SubmitResult:
        """Submit a "now playing" notification to ListenBrainz.

        Args:
            listen: The currently playing track.

        Returns:
            SubmitResult indicating success or failure.
        """
        payload = self._build_listen_payload([listen], "playing_now")
        return await self._submit_payload(payload)

    def _build_listen_payload(
        self, listens: list[Listen], listen_type: str
    ) -> dict:
        """Build the JSON payload for a listen submission.

        Args:
            listens: List of listens to include.
            listen_type: One of "single", "import", or "playing_now".

        Returns:
            JSON-serializable payload dict.
        """
        payload_listens = []
        for listen in listens:
            track_metadata: dict = {
                "track_name": listen.track_name,
                "artist_name": listen.artist_name,
            }

            if listen.release_name:
                track_metadata["release_name"] = listen.release_name

            # Add additional info if available
            additional_info: dict = {}
            if listen.recording_mbid:
                additional_info["recording_mbid"] = listen.recording_mbid
            if listen.artist_mbid:
                additional_info["artist_mbids"] = [listen.artist_mbid]
            if listen.duration_ms:
                additional_info["duration_ms"] = listen.duration_ms

            if additional_info:
                track_metadata["additional_info"] = additional_info

            listen_data: dict = {"track_metadata": track_metadata}

            # Only add listened_at for non-playing_now submissions
            if listen_type != "playing_now":
                listen_data["listened_at"] = listen.listened_at

            payload_listens.append(listen_data)

        return {
            "listen_type": listen_type,
            "payload": payload_listens,
        }

    async def _submit_payload(self, payload: dict) -> SubmitResult:
        """Submit a payload to the ListenBrainz API.

        Args:
            payload: The JSON payload to submit.

        Returns:
            SubmitResult indicating success or failure.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{API_BASE}/1/submit-listens",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return SubmitResult(success=True, message="Listen(s) submitted successfully")

                # Handle error responses
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", response.text)
                except Exception:
                    error_msg = response.text

                return SubmitResult(success=False, message=f"API error: {error_msg}")

            except httpx.TimeoutException:
                return SubmitResult(success=False, message="Request timed out")
            except httpx.RequestError as e:
                return SubmitResult(success=False, message=f"Request failed: {e}")

    async def validate_token(self) -> tuple[bool, str]:
        """Validate the user token with ListenBrainz.

        Returns:
            Tuple of (is_valid, username or error message).
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{API_BASE}/1/validate-token",
                    headers=self._get_headers(),
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid"):
                        return True, data.get("user_name", "unknown")
                    return False, "Token is invalid"

                return False, f"API returned status {response.status_code}"

            except httpx.RequestError as e:
                return False, f"Request failed: {e}"


def create_listen_from_song(
    song: "Song",  # type: ignore  # noqa: F821
    listened_at: datetime | None = None,
) -> Listen:
    """Create a Listen object from a Song model.

    Args:
        song: The Song object to create a listen from.
        listened_at: When the song was played. Defaults to now.

    Returns:
        A Listen object ready for submission.
    """
    if listened_at is None:
        listened_at = datetime.utcnow()

    return Listen(
        track_name=song.title,
        artist_name=song.artist,
        listened_at=int(listened_at.timestamp()),
        release_name=song.album,
        recording_mbid=song.musicbrainz_recording_id,
        artist_mbid=song.musicbrainz_artist_id,
        duration_ms=song.duration_ms,
    )
