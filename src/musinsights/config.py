"""Configuration management for MusInsights."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="MUSINSIGHTS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database settings
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/musinsights.db",
        description="Async SQLAlchemy database URL",
    )

    # Data directory
    data_dir: Path = Field(
        default=Path("./data"),
        description="Directory for storing data files",
    )

    # Spotify settings (optional)
    spotify_client_id: str | None = Field(
        default=None,
        description="Spotify API client ID",
    )
    spotify_client_secret: str | None = Field(
        default=None,
        description="Spotify API client secret",
    )
    spotify_redirect_uri: str = Field(
        default="http://localhost:8888/callback",
        description="Spotify OAuth redirect URI",
    )

    # Analysis settings
    analysis_workers: int = Field(
        default=4,
        description="Number of parallel workers for audio analysis",
    )
    analysis_batch_size: int = Field(
        default=10,
        description="Number of songs to process per batch",
    )

    def ensure_data_dir(self) -> Path:
        """Ensure the data directory exists and return its path."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


# Global settings instance
settings = Settings()
