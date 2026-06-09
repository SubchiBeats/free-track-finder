"""CLI for Free Track Finder.

Uses Click for argument parsing and Rich for beautiful terminal output.
All commands are async under the hood — the CLI wraps them with asyncio.run().
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from freetracks.core.engine import SearchEngine
from freetracks.core.filters import TrackFilter
from freetracks.core.models import AudioFormat, DownloadType, SearchResults
from freetracks.export import export_csv, export_json, export_m3u
from freetracks.platforms import PLATFORM_NAMES
from freetracks.utils.formatting import truncate

# Windows consoles often default to a legacy codepage (cp1252) that can't encode
# the emoji/Unicode in our output, which crashes Click's help and Rich rendering.
# Force UTF-8 on the standard streams so the CLI works on any terminal.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="Free Track Finder")
def cli():
    """🎧 Free Track Finder — Discover legitimately free DJ tracks."""
    pass


@cli.command()
@click.argument("query")
@click.option(
    "--platform", "-p",
    type=click.Choice(PLATFORM_NAMES + ["all"], case_sensitive=False),
    default="all",
    help="Platform to search (default: all)",
)
@click.option("--bpm-min", type=float, default=None, help="Minimum BPM")
@click.option("--bpm-max", type=float, default=None, help="Maximum BPM")
@click.option("--key", "-k", type=str, default=None,
              help="Musical key (standard or Camelot, e.g. Am or 8A)")
@click.option("--genre", "-g", type=str, default=None, help="Filter by genre (comma-separated)")
@click.option("--format", "-f", "file_format", type=str, default=None,
              help="Audio format (mp3, wav, flac, aiff)")
@click.option("--min-bitrate", type=int, default=None, help="Minimum bitrate in kbps")
@click.option("--max-results", "-n", type=int, default=50,
              help="Max tracks to return (default: 50)")
@click.option(
    "--sort", "-s",
    type=click.Choice(["bpm", "date", "popularity", "title", "duration", "quality", "likes"]),
    default="popularity",
    help="Sort results by (default: popularity)",
)
@click.option(
    "--export", "-e", "export_format",
    type=click.Choice(["csv", "json", "m3u"]),
    default=None,
    help="Export format",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
@click.option("--no-gated", is_flag=True, default=False, help="Exclude gated downloads")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show all metadata columns")
@click.option("--rate-limit", type=float, default=2.0, help="Requests per second (default: 2)")
@click.option("--sc-client-id", type=str, default=None, help="SoundCloud client_id (optional)")
def search(
    query: str,
    platform: str,
    bpm_min: float | None,
    bpm_max: float | None,
    key: str | None,
    genre: str | None,
    file_format: str | None,
    min_bitrate: int | None,
    max_results: int,
    sort: str,
    export_format: str | None,
    output: str | None,
    no_gated: bool,
    verbose: bool,
    rate_limit: float,
    sc_client_id: str | None,
):
    """Search for free tracks across platforms.

    Examples:

        ftf search "deep house" --bpm-min 120 --bpm-max 128

        ftf search "melodic techno" --platform soundcloud --key 8A

        ftf search "drum and bass" --format wav --export csv -o tracks.csv
    """
    # Build filter
    genres = [g.strip() for g in genre.split(",")] if genre else []
    formats = [AudioFormat.from_string(file_format)] if file_format else []

    track_filter = TrackFilter(
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        key=key,
        genres=genres,
        formats=formats,
        min_bitrate_kbps=min_bitrate,
        exclude_gated=no_gated,
    )

    platforms = None if platform == "all" else [platform]

    # Show search banner
    console.print()
    search_info = f"[bold]Searching:[/bold] {query}"
    if track_filter.is_active:
        search_info += f"\n[dim]{track_filter.describe()}[/dim]"
    console.print(Panel(search_info, title="🎧 Free Track Finder", border_style="cyan"))

    # Run the async search
    engine = SearchEngine(rate_limit_rps=rate_limit)
    with console.status("[cyan]Scanning platforms...", spinner="dots"):
        results = asyncio.run(
            engine.search(
                query=query,
                platforms=platforms,
                track_filter=track_filter,
                sort_by=sort,
                max_results=max_results,
            )
        )

    # Show errors if any
    for error in results.errors:
        console.print(f"  [yellow]⚠ {error}[/yellow]")

    if not results.tracks:
        console.print("\n[yellow]No free tracks found matching your criteria.[/yellow]")
        console.print("[dim]Try broadening your search or checking different platforms.[/dim]")
        return

    # Display results
    _display_results_table(results, verbose)

    # Export if requested
    if export_format:
        _handle_export(results, export_format, output, verbose)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind (default: 8000)")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes (dev)")
def serve(host: str, port: int, reload: bool):
    """Launch the web app (API + browser UI) at http://localhost:8000.

    Requires the web extra: pip install -e ".[web]"
    """
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]The web server needs extra dependencies.[/red]\n"
            'Install them with:  [bold]pip install -e ".[web]"[/bold]'
        )
        raise SystemExit(1) from None

    url = f"http://{host}:{port}"
    console.print(
        Panel(
            f"[bold]Free Track Finder[/bold] web app\n\n"
            f"  Open [cyan link {url}]{url}[/]\n"
            f"  API docs at [cyan]{url}/docs[/cyan]\n\n"
            f"[dim]Press Ctrl+C to stop.[/dim]",
            title="🎧 Serving",
            border_style="cyan",
        )
    )
    uvicorn.run("freetracks.web.app:app", host=host, port=port, reload=reload)


@cli.command()
def platforms():
    """List supported platforms and their capabilities."""
    console.print()
    table = Table(title="Supported Platforms", box=box.ROUNDED)
    table.add_column("Platform", style="cyan bold")
    table.add_column("Download Type", style="green")
    table.add_column("Metadata")
    table.add_column("Notes", style="dim")

    table.add_row(
        "SoundCloud",
        "Direct download",
        "BPM, key, genre, tags, plays, likes",
        "Tracks with download button enabled",
    )
    table.add_row(
        "Bandcamp",
        "Name your price ($0)",
        "Genre, tags, duration, release date",
        "Multi-format choice on download (MP3/FLAC/WAV)",
    )
    table.add_row(
        "Hypeddit",
        "Gated (social action)",
        "Genre, BPM (when tagged)",
        "Requires follow/repost/subscribe to download",
    )

    console.print(table)
    console.print()


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.argument("format", type=click.Choice(["csv", "json", "m3u"]))
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
def convert(input_file: str, format: str, output: str | None):
    """Convert a previously saved JSON result to another format.

    Example:
        ftf convert results.json csv -o results.csv
    """
    import json as json_module

    with open(input_file, "r", encoding="utf-8") as f:
        data = json_module.load(f)

    results = SearchResults.model_validate({
        "query": data.get("meta", {}).get("query", "converted"),
        "tracks": data.get("tracks", []),
    })

    _handle_export(results, format, output)


def _download_cell(track) -> Text:
    """A clickable terminal hyperlink that opens the most direct download location.

    Prefers the track's direct ``download_url`` when known, otherwise links to the
    track page (where the download / "name your price" / unlock button lives).
    The label reflects how the track is obtained so DJs know what to expect.
    """
    target = track.download_url or track.url
    if track.download_type == DownloadType.NAME_YOUR_PRICE:
        label, color = "⬇ Free $0", "bold green"
    elif track.download_type == DownloadType.GATED:
        label, color = "🔒 Unlock", "bold yellow"
    else:
        label, color = "⬇ Download", "bold green"
    return Text(label, style=f"{color} link {target}")


def _display_results_table(results: SearchResults, verbose: bool = False):
    """Render search results as a Rich table."""
    table = Table(
        title=f"Found {results.track_count} free tracks",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        pad_edge=True,
    )

    # Core columns
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="bold white", max_width=35)
    table.add_column("Artist", style="cyan", max_width=20)
    table.add_column("BPM", style="yellow", justify="right", width=5)
    table.add_column("Key", style="green", width=5)
    table.add_column("Cam", style="green dim", width=4)
    table.add_column("Genre", style="magenta", max_width=18)
    table.add_column("Dur", style="dim", width=6)
    table.add_column("Fmt", style="blue", width=4)
    table.add_column("Quality", style="blue dim", width=8)
    table.add_column("Get", justify="center", width=12, no_wrap=True)
    table.add_column("Platform", style="dim", width=11)

    if verbose:
        table.add_column("Size", style="dim", width=8)
        table.add_column("Plays", style="dim", justify="right", width=8)
        table.add_column("Likes", style="dim", justify="right", width=6)

    for i, track in enumerate(results.tracks, 1):
        row_data = track.to_row(verbose=verbose)

        # Clickable title -> track page; clickable Get -> direct download (or page).
        title_cell = Text(truncate(row_data["title"], 35), style=f"bold white link {track.url}")
        get_cell = _download_cell(track)

        row = [
            str(i),
            title_cell,
            truncate(row_data["artist"], 20),
            str(row_data["bpm"]),
            str(row_data["key"]),
            str(row_data["camelot"]),
            truncate(str(row_data["genre"]), 18),
            str(row_data["duration"]),
            str(row_data["format"]),
            str(row_data["quality"]),
            get_cell,
            str(row_data["platform"]),
        ]

        if verbose:
            row.extend([
                str(row_data.get("size", "—")),
                str(row_data.get("plays", "—")),
                str(row_data.get("likes", "—")),
            ])

        table.add_row(*row)

    console.print()
    console.print(table)

    # Summary bar
    summary_parts = [
        f"[cyan]{results.track_count}[/cyan] tracks",
        f"[dim]in {results.search_time_seconds:.1f}s[/dim]",
    ]
    if results.bpm_range:
        summary_parts.append(f"BPM range: [yellow]{results.bpm_range}[/yellow]")
    if results.format_breakdown:
        fmt_str = ", ".join(f"{k}: {v}" for k, v in results.format_breakdown.items())
        summary_parts.append(f"Formats: [blue]{fmt_str}[/blue]")

    console.print(f"\n  {'  •  '.join(summary_parts)}")
    console.print(
        "  [dim]Tip: click a [bold]Title[/bold] to open the track page, or the "
        "[bold]Get[/bold] link to jump straight to the download "
        "(Ctrl/⌘-click in some terminals). Use [bold]-v[/bold] for full copy/paste URLs.[/dim]"
    )

    if verbose:
        console.print("\n  [bold]Download links[/bold] [dim](full URLs — click or copy):[/dim]")
        for i, track in enumerate(results.tracks, 1):
            target = track.download_url or track.url
            console.print(
                Text.assemble(("  ", ""), (f"{i:>2}. ", "dim"), (target, f"cyan link {target}"))
            )

    console.print()


def _handle_export(
    results: SearchResults,
    export_format: str,
    output: str | None,
    verbose: bool = True,
):
    """Handle export to file or stdout."""
    if output is None:
        # Generate default filename
        safe_query = results.query.replace(" ", "_")[:30]
        output = f"ftf_{safe_query}.{export_format}"

    output_path = Path(output)

    if export_format == "csv":
        export_csv(results, output_path, verbose=verbose)
    elif export_format == "json":
        export_json(results, output_path)
    elif export_format == "m3u":
        export_m3u(results, output_path)

    console.print(f"  [green]✓[/green] Exported to [bold]{output_path}[/bold]")
    console.print()


if __name__ == "__main__":
    cli()
