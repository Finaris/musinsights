"""Data ingestors for various music sources."""

from musinsights.ingestors.base import BaseIngestor, IngestResult
from musinsights.ingestors.local_files import LocalFileIngestor

__all__ = [
    "BaseIngestor",
    "IngestResult",
    "LocalFileIngestor",
]
