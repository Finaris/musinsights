"""CLI interface for MusInsights."""

from pathlib import Path

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
async def analyze_all(force: bool, limit: int | None) -> None:
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


@cli.group()
def enrich() -> None:
    """Enrich songs with external metadata."""
    pass


@enrich.command("mbid")
@click.option("--limit", "-l", type=int, help="Maximum number of songs to process")
@click.option("--force", "-f", is_flag=True, help="Re-lookup even if MBID already exists")
async def enrich_mbid(limit: int | None, force: bool) -> None:
    """Enrich songs with MusicBrainz IDs."""
    from musinsights.db import SongRepository
    from musinsights.services.musicbrainz import MusicBrainzService

    try:
        async with get_session() as session:
            repo = SongRepository(session)
            mb_service = MusicBrainzService()

            if force:
                songs = await repo.get_all(limit=limit)
            else:
                songs = await repo.get_without_mbid(limit=limit)

            if not songs:
                console.print("[yellow]No songs to enrich.[/yellow]")
                return

            console.print(f"[blue]Looking up MusicBrainz IDs for {len(songs)} songs...[/blue]")
            console.print("[dim]Rate limited to 1 request/second[/dim]")

            found = 0
            not_found = 0

            for song in songs:
                match = await mb_service.lookup_recording(
                    title=song.title,
                    artist=song.artist,
                    duration_ms=song.duration_ms,
                )

                if match:
                    song.musicbrainz_recording_id = match.recording_id
                    song.musicbrainz_artist_id = match.artist_id
                    await repo.update(song)
                    found += 1
                    console.print(
                        f"  [green]\u2713[/green] {song.artist} - {song.title} "
                        f"[dim](score: {match.score})[/dim]"
                    )
                else:
                    not_found += 1
                    console.print(f"  [yellow]\u2717[/yellow] {song.artist} - {song.title}")

            console.print(f"\n[green]Found MBIDs for {found} songs[/green]")
            if not_found > 0:
                console.print(f"[yellow]Could not find MBIDs for {not_found} songs[/yellow]")

    except Exception as e:
        console.print(f"[red]Error during enrichment:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@cli.group()
def listenbrainz() -> None:
    """ListenBrainz integration commands."""
    pass


@listenbrainz.command("auth")
async def listenbrainz_auth() -> None:
    """Validate ListenBrainz authentication."""
    from musinsights.services.listenbrainz import ListenBrainzService

    if not settings.listenbrainz_token:
        console.print(
            "[red]ListenBrainz token not configured.[/red]\n"
            "Set MUSINSIGHTS_LISTENBRAINZ_TOKEN environment variable.\n"
            "Get your token at: https://listenbrainz.org/settings/"
        )
        raise click.Abort()

    try:
        service = ListenBrainzService()
        valid, result = await service.validate_token()

        if valid:
            console.print(f"[green]Token valid![/green] Authenticated as: {result}")
        else:
            console.print(f"[red]Token invalid:[/red] {result}")
            raise click.Abort()

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@listenbrainz.command("submit")
@click.argument("song_id", required=False)
@click.option("--all", "submit_all", is_flag=True, help="Submit all songs as historical listens")
@click.option("--now-playing", is_flag=True, help="Submit as currently playing (not a listen)")
async def listenbrainz_submit(
    song_id: str | None, submit_all: bool, now_playing: bool
) -> None:
    """Submit listen(s) to ListenBrainz.

    SONG_ID is the UUID of a song to submit. Use --all to submit all songs.
    """
    from musinsights.db import SongRepository
    from musinsights.services.listenbrainz import (
        ListenBrainzService,
        create_listen_from_song,
    )

    if not song_id and not submit_all:
        console.print("[red]Provide a SONG_ID or use --all flag[/red]")
        raise click.Abort()

    if not settings.listenbrainz_token:
        console.print(
            "[red]ListenBrainz token not configured.[/red]\n"
            "Set MUSINSIGHTS_LISTENBRAINZ_TOKEN environment variable."
        )
        raise click.Abort()

    try:
        service = ListenBrainzService()

        async with get_session() as session:
            repo = SongRepository(session)

            if submit_all:
                songs = list(await repo.get_all())
                if not songs:
                    console.print("[yellow]No songs in library.[/yellow]")
                    return

                console.print(f"[blue]Submitting {len(songs)} songs to ListenBrainz...[/blue]")

                listens = [create_listen_from_song(song) for song in songs]
                result = await service.submit_listens(listens)

                if result.success:
                    console.print(f"[green]{result.message}[/green]")
                else:
                    console.print(f"[red]{result.message}[/red]")
                    raise click.Abort()

            else:
                song = await repo.get_by_id(song_id)  # type: ignore
                if not song:
                    console.print(f"[red]Song not found:[/red] {song_id}")
                    raise click.Abort()

                listen = create_listen_from_song(song)

                if now_playing:
                    result = await service.submit_now_playing(listen)
                else:
                    result = await service.submit_listen(listen)

                if result.success:
                    console.print(
                        f"[green]\u2713[/green] Submitted: {song.artist} - {song.title}"
                    )
                else:
                    console.print(f"[red]{result.message}[/red]")
                    raise click.Abort()

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error submitting listen:[/red] {e}")
        raise click.Abort()
    finally:
        await close_engine()


@listenbrainz.command("import")
@click.option("--username", "-u", help="ListenBrainz username (uses config if not provided)")
@click.option("--limit", "-l", type=int, help="Maximum number of listens to import")
async def listenbrainz_import(username: str | None, limit: int | None) -> None:
    """Import listening history from ListenBrainz.

    Fetches your listening history and matches listens to songs in your local library
    using MusicBrainz recording IDs.
    """
    from musinsights.db import ListeningHistory, ListeningHistoryRepository, SongRepository
    from musinsights.services.listenbrainz import ListenBrainzService

    # Get username from option or settings
    user = username or settings.listenbrainz_username
    if not user:
        console.print(
            "[red]ListenBrainz username required.[/red]\n"
            "Use --username or set MUSINSIGHTS_LISTENBRAINZ_USERNAME environment variable."
        )
        raise click.Abort()

    try:
        # Token is optional for fetching public listen history
        try:
            service = ListenBrainzService()
        except ValueError:
            # Create service without token validation for read-only operations
            service = ListenBrainzService.__new__(ListenBrainzService)
            service.token = None

        console.print(f"[blue]Fetching listening history for {user}...[/blue]")

        def progress(count: int) -> None:
            console.print(f"  Fetched {count} listens...", end="\r")

        listens = await service.get_all_listens(username=user, progress_callback=progress)

        if limit:
            listens = listens[:limit]

        console.print(f"\n[green]Fetched {len(listens)} listens[/green]")

        if not listens:
            return

        # Match to local library
        async with get_session() as session:
            song_repo = SongRepository(session)
            history_repo = ListeningHistoryRepository(session)

            # Build lookup by MBID
            all_songs = await song_repo.get_all()
            mbid_to_song = {
                song.musicbrainz_recording_id: song
                for song in all_songs
                if song.musicbrainz_recording_id
            }

            matched = 0
            unmatched = 0
            imported = 0

            for listen in listens:
                song = None

                # Try to match by MBID first
                if listen.recording_mbid:
                    song = mbid_to_song.get(listen.recording_mbid)

                if song:
                    matched += 1
                    # Create listening history entry
                    entry = ListeningHistory(
                        song_id=song.id,
                        played_at=listen.listened_at,
                        source="listenbrainz",
                        context={"recording_mbid": listen.recording_mbid},
                    )
                    await history_repo.create(entry)
                    imported += 1
                else:
                    unmatched += 1

            console.print(f"\n[green]Matched {matched} listens to local library[/green]")
            console.print(f"[green]Imported {imported} listening history entries[/green]")
            if unmatched > 0:
                console.print(f"[yellow]{unmatched} listens could not be matched[/yellow]")
                console.print(
                    "[dim]Tip: Run 'musinsights enrich mbid' to add MusicBrainz IDs[/dim]"
                )

    except Exception as e:
        console.print(f"[red]Error importing history:[/red] {e}")
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
            without_mbid = len(await repo.get_without_mbid())

            table = Table(title="Library Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Songs", str(total))
            table.add_row("Local Files", str(local))
            table.add_row("From Spotify", str(spotify))
            table.add_row("Unanalyzed", str(unanalyzed))
            table.add_row("Analyzed", str(total - unanalyzed))
            table.add_row("With MusicBrainz ID", str(total - without_mbid))

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
