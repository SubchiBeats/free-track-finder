"""CSV export — save search results to a spreadsheet-friendly format.

Exports all track metadata as a CSV file that can be opened in Excel,
Google Sheets, or imported into DJ library management tools.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from freetracks.core.models import Track, SearchResults


# Column order optimized for DJ workflow
CSV_COLUMNS = [
    "title",
    "artist",
    "bpm",
    "key",
    "camelot",
    "genre",
    "duration",
    "format",
    "quality",
    "bitrate",
    "file_size",
    "download_type",
    "platform",
    "plays",
    "likes",
    "released",
    "tags",
    "url",
    "download_url",
]


def export_csv(results: SearchResults, output_path: str | Path, verbose: bool = True) -> Path:
    """Export search results to CSV.

    Args:
        results: SearchResults containing tracks to export.
        output_path: File path for the CSV output.
        verbose: Include all columns (True) or just essentials (False).

    Returns:
        Path to the written file.
    """
    path = Path(output_path)

    columns = CSV_COLUMNS if verbose else CSV_COLUMNS[:13]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for track in results.tracks:
            row = _track_to_csv_row(track)
            writer.writerow(row)

    return path


def export_csv_string(results: SearchResults, verbose: bool = True) -> str:
    """Export search results to a CSV string (for stdout or piping)."""
    columns = CSV_COLUMNS if verbose else CSV_COLUMNS[:13]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()

    for track in results.tracks:
        row = _track_to_csv_row(track)
        writer.writerow(row)

    return output.getvalue()


def _track_to_csv_row(track: Track) -> dict:
    """Convert a Track to a flat dict matching CSV column names."""
    return {
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm or "",
        "key": track.key or "",
        "camelot": track.camelot_key or "",
        "genre": track.genre or "",
        "duration": track.duration_formatted or "",
        "format": track.file_format.value.upper(),
        "quality": track.quality_tier,
        "bitrate": f"{track.bitrate_kbps}" if track.bitrate_kbps else "",
        "file_size": f"{track.file_size_mb}" if track.file_size_mb else "",
        "download_type": track.download_type.value,
        "platform": track.platform.value,
        "plays": track.play_count or "",
        "likes": track.like_count or "",
        "released": track.release_date.strftime("%Y-%m-%d") if track.release_date else "",
        "tags": "; ".join(track.tags) if track.tags else "",
        "url": track.url,
        "download_url": track.download_url or "",
    }
