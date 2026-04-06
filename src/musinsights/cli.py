"""CLI interface for MusInsights."""

import asyncio
from pathlib import Path
from typing import Optional

import asyncclick as click
from rich.console import Console
from rich.table import Table

from musinsights import __version__
from musinsights.config import settings
from musinsights.db import close_engine, get_session, init_database

console = Console()


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(version=__version__, prog_name="musinsights")
def cli() -> None:
    """MusInsights: High-level insights into your favorite music."""
    pass


@cli.command()
async def init() -> None:
    """Initialize the database and data directory."""
    try:
        # Ensure data directory exists
        data_dir = settings.ensure_data_dir()
        console.print(f"[green]Created data directory:[/green] {data_dir.absolute()}")

        # Initialize database
        await init_database()
        console.print("[green]Database initialized successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error initializing database:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@cli.group()
def ingest() -> None:
    """Ingest music data from various sources."""
    pass


@ingest.command("local")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", "-r", is_flag=True, help="Scan directories recursively")
@click.option("--dry-run", is_flag=True, help="Show what would be ingested without saving")
async def ingest_local(path: Path, recursive: bool, dry_run: bool) -> None:
    """Ingest music files from a local directory."""
    from musinsights.ingestors.local_files import LocalFileIngestor

    try:
        async with get_session() as session:
            ingestor = LocalFileIngestor(session)
            result = await ingestor.ingest(path, recursive=recursive, dry_run=dry_run)

            if dry_run:
                console.print(f"[yellow]Dry run:[/yellow] Would ingest {result.total} files")
                console.print(f"  New: {result.created}")
                console.print(f"  Skipped (existing): {result.skipped}")
            else:
                console.print(f"[green]Ingested {result.created} new songs[/green]")
                if result.skipped > 0:
                    console.print(f"  Skipped {result.skipped} existing files")
                if result.duplicates > 0:
                    console.print(f"  [yellow]Duplicates: {result.duplicates}[/yellow]")
                if result.errors > 0:
                    console.print(f"  [red]Errors: {result.errors}[/red]")

    except Exception as e:
        console.print(f"[red]Error during ingestion:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@ingest.command("spotify")
@click.option("--auth", is_flag=True, help="Authenticate with Spotify")
async def ingest_spotify(auth: bool) -> None:
    """Ingest music data from Spotify."""
    if not settings.spotify_client_id:
        console.print(
            "[red]Spotify credentials not configured.[/red]\n"
            "Set MUSINSIGHTS_SPOTIFY_CLIENT_ID and MUSINSIGHTS_SPOTIFY_CLIENT_SECRET "
            "environment variables."
        )
        raise click.Abort()

    console.print("[yellow]Spotify ingestion not yet implemented.[/yellow]")
    # TODO: Implement Spotify ingestion


@cli.group()
def analyze() -> None:
    """Analyze ingested songs."""
    pass


@analyze.command("all")
@click.option("--force", "-f", is_flag=True, help="Re-analyze all songs, even if already analyzed")
@click.option("--limit", "-l", type=int, help="Maximum number of songs to analyze")
async def analyze_all(force: bool, limit: Optional[int]) -> None:
    """Analyze all unanalyzed songs."""
    from musinsights.analyzers.audio import AudioAnalyzer
    from musinsights.db import SongRepository

    try:
        async with get_session() as session:
            repo = SongRepository(session)

            if force:
                songs = await repo.get_all(limit=limit)
            else:
                songs = await repo.get_unanalyzed(limit=limit)

            if not songs:
                console.print("[yellow]No songs to analyze.[/yellow]")
                return

            console.print(f"[blue]Analyzing {len(songs)} songs...[/blue]")

            analyzer = AudioAnalyzer(session)
            results = await analyzer.analyze_batch(list(songs))

            console.print(f"[green]Successfully analyzed {results.success} songs[/green]")
            if results.failed > 0:
                console.print(f"[red]Failed to analyze {results.failed} songs[/red]")

    except Exception as e:
        console.print(f"[red]Error during analysis:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@cli.group()
def export() -> None:
    """Export data to various formats."""
    pass


@export.command("json")
@click.argument("output", type=click.Path(path_type=Path))
@click.option("--compact", is_flag=True, help="Output minified JSON without indentation")
async def export_json(output: Path, compact: bool) -> None:
    """Export all songs and features to JSON."""
    from musinsights.exporters.formats import export_to_json

    try:
        async with get_session() as session:
            await export_to_json(session, output, pretty=not compact)
            console.print(f"[green]Exported data to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error during export:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@export.command("csv")
@click.argument("output", type=click.Path(path_type=Path))
async def export_csv(output: Path) -> None:
    """Export all songs and features to CSV."""
    from musinsights.exporters.formats import export_to_csv

    try:
        async with get_session() as session:
            await export_to_csv(session, output)
            console.print(f"[green]Exported data to {output}[/green]")

    except Exception as e:
        console.print(f"[red]Error during export:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@cli.command()
async def stats() -> None:
    """Show statistics about the music library."""
    from musinsights.db import SongRepository

    try:
        async with get_session() as session:
            repo = SongRepository(session)

            total = await repo.count()
            local = await repo.count(source="local")
            spotify = await repo.count(source="spotify")
            unanalyzed = len(await repo.get_unanalyzed())

            table = Table(title="Library Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Songs", str(total))
            table.add_row("Local Files", str(local))
            table.add_row("From Spotify", str(spotify))
            table.add_row("Unanalyzed", str(unanalyzed))
            table.add_row("Analyzed", str(total - unanalyzed))

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error fetching statistics:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


def main() -> None:
    """Entry point for the CLI."""
    cli(_anyio_backend="asyncio")


if __name__ == "__main__":
    main()
