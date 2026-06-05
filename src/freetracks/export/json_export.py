"""JSON export — machine-readable search results.

Useful for:
- Piping into other tools
- Building web UIs on top of results
- Archiving search history
- Integration with custom workflows
"""

from __future__ import annotations

import json
from pathlib import Path

from freetracks.core.models import SearchResults


def export_json(results: SearchResults, output_path: str | Path, pretty: bool = True) -> Path:
    """Export search results to JSON.

    Args:
        results: SearchResults to export.
        output_path: File path for JSON output.
        pretty: Pretty-print with indentation (default True).

    Returns:
        Path to the written file.
    """
    path = Path(output_path)
    data = _results_to_dict(results)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2 if pretty else None, default=str, ensure_ascii=False)

    return path


def export_json_string(results: SearchResults, pretty: bool = True) -> str:
    """Export search results to a JSON string."""
    data = _results_to_dict(results)
    return json.dumps(data, indent=2 if pretty else None, default=str, ensure_ascii=False)


def _results_to_dict(results: SearchResults) -> dict:
    """Convert SearchResults to a serializable dict."""
    return {
        "meta": {
            "query": results.query,
            "platform_filter": results.platform_filter,
            "total_found": results.total_found,
            "track_count": results.track_count,
            "search_time_seconds": round(results.search_time_seconds, 2),
            "platforms_searched": results.platforms_searched,
            "bpm_range": results.bpm_range,
            "format_breakdown": results.format_breakdown,
            "errors": results.errors,
        },
        "tracks": [
            {
                "title": t.title,
                "artist": t.artist,
                "platform": t.platform.value,
                "url": t.url,
                "track_id": t.track_id,
                "download_url": t.download_url,
                "download_type": t.download_type.value,
                "file_format": t.file_format.value,
                "file_size_bytes": t.file_size_bytes,
                "file_size_mb": t.file_size_mb,
                "bitrate_kbps": t.bitrate_kbps,
                "quality_tier": t.quality_tier,
                "bpm": t.bpm,
                "key": t.key,
                "camelot_key": t.camelot_key,
                "genre": t.genre,
                "tags": t.tags,
                "duration_seconds": t.duration_seconds,
                "duration_formatted": t.duration_formatted,
                "play_count": t.play_count,
                "like_count": t.like_count,
                "repost_count": t.repost_count,
                "release_date": t.release_date.isoformat() if t.release_date else None,
                "artwork_url": t.artwork_url,
                "artist_url": t.artist_url,
                "description": t.description,
            }
            for t in results.tracks
        ],
    }
