# MusInsights

High-level insights into one's favorite music through audio analysis and data ingestion.

## Features

- **Local File Ingestion**: Scan your music library and extract metadata from MP3, FLAC, WAV, M4A, and more
- **Audio Analysis**: Extract tempo, key, energy, spectral features, and MFCCs using librosa
- **Spotify Integration**: Import your listening history and saved tracks (coming soon)
- **Flexible Export**: Export data to JSON, CSV, or Parquet for further analysis
- **Async Pipeline**: Built with asyncio for efficient batch processing of large libraries

## Installation

```bash
# Clone the repository
git clone https://github.com/Finaris/musinsights.git
cd musinsights

# Install with uv
uv sync

# Or install with pip
pip install -e .
```

## Quick Start

```bash
# Initialize the database
musinsights init

# Ingest music from a local directory
musinsights ingest local ~/Music --recursive

# Analyze all unanalyzed songs
musinsights analyze all

# View library statistics
musinsights stats

# Export data to JSON
musinsights export json library.json --pretty
```

## CLI Commands

### `musinsights init`
Initialize the database and data directory.

### `musinsights ingest`
Ingest music data from various sources:
- `musinsights ingest local <path>` - Scan local directories
- `musinsights ingest spotify --auth` - Import from Spotify (requires API credentials)

### `musinsights analyze`
Run audio analysis on ingested songs:
- `musinsights analyze all` - Analyze all unanalyzed songs
- `musinsights analyze all --force` - Re-analyze all songs

### `musinsights export`
Export data to various formats:
- `musinsights export json <output>` - Export to JSON
- `musinsights export csv <output>` - Export to CSV

### `musinsights stats`
Display library statistics.

## Configuration

Set environment variables or create a `.env` file:

```bash
# Database (default: SQLite in ./data/)
MUSINSIGHTS_DATABASE_URL=sqlite+aiosqlite:///./data/musinsights.db

# Spotify API (optional)
MUSINSIGHTS_SPOTIFY_CLIENT_ID=your_client_id
MUSINSIGHTS_SPOTIFY_CLIENT_SECRET=your_client_secret

# Analysis settings
MUSINSIGHTS_ANALYSIS_WORKERS=4
MUSINSIGHTS_ANALYSIS_BATCH_SIZE=10
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
pytest

# Run linter
ruff check src/

# Run type checker
mypy src/
```

## Architecture

```
musinsights/
├── src/musinsights/
│   ├── cli.py           # Click-based CLI
│   ├── config.py        # Pydantic settings
│   ├── db/              # SQLAlchemy models & repository
│   ├── ingestors/       # Data source adapters
│   ├── analyzers/       # Audio analysis modules
│   ├── pipeline/        # Orchestration engine
│   └── exporters/       # Export formats
└── tests/
```

## License

MIT
