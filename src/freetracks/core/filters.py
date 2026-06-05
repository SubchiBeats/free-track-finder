"""Track filtering — apply DJ-relevant filters to search results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone
from typing import Optional

from freetracks.core.models import AudioFormat, Track
from freetracks.utils.keys import standard_to_camelot


@dataclass
class TrackFilter:
    """Composable filter for narrowing track results.

    All fields are optional — only active filters are applied. Tracks pass
    if they match ALL active filters (AND logic).
    """

    bpm_min: Optional[float] = None
    bpm_max: Optional[float] = None
    key: Optional[str] = None  # Accepts both standard and Camelot
    genres: list[str] = field(default_factory=list)
    formats: list[AudioFormat] = field(default_factory=list)
    min_bitrate_kbps: Optional[int] = None
    min_duration_seconds: Optional[float] = None
    max_duration_seconds: Optional[float] = None
    quality_tiers: list[str] = field(default_factory=list)  # "lossless", "high", "medium"
    exclude_gated: bool = False  # Skip gated downloads
    platforms: list[str] = field(default_factory=list)

    def apply(self, tracks: list[Track]) -> list[Track]:
        """Filter a list of tracks, returning only those that match all criteria."""
        return [t for t in tracks if self._matches(t)]

    def _matches(self, track: Track) -> bool:
        """Check if a single track passes all active filters."""
        # BPM range
        if not track.matches_bpm_range(self.bpm_min, self.bpm_max):
            return False

        # Musical key
        if self.key is not None:
            if not track.matches_key(self.key):
                return False

        # Genre (case-insensitive partial match — "tech house" matches "Tech House")
        if self.genres:
            if track.genre is None:
                return False
            track_genre_lower = track.genre.lower()
            track_tags_lower = [t.lower() for t in track.tags]
            if not any(
                g.lower() in track_genre_lower or any(g.lower() in tag for tag in track_tags_lower)
                for g in self.genres
            ):
                return False

        # Audio format
        if self.formats and track.file_format not in self.formats:
            return False

        # Minimum bitrate
        if self.min_bitrate_kbps is not None:
            if track.bitrate_kbps is not None and track.bitrate_kbps < self.min_bitrate_kbps:
                return False

        # Duration range
        if self.min_duration_seconds is not None:
            if (
                track.duration_seconds is not None
                and track.duration_seconds < self.min_duration_seconds
            ):
                return False
        if self.max_duration_seconds is not None:
            if (
                track.duration_seconds is not None
                and track.duration_seconds > self.max_duration_seconds
            ):
                return False

        # Quality tier
        if self.quality_tiers and track.quality_tier not in self.quality_tiers:
            return False

        # Exclude gated downloads
        if self.exclude_gated and track.download_type.value == "gated":
            return False

        # Platform filter
        if self.platforms and track.platform.value not in self.platforms:
            return False

        return True

    @property
    def is_active(self) -> bool:
        """Returns True if any filter criteria are set."""
        return any([
            self.bpm_min is not None,
            self.bpm_max is not None,
            self.key is not None,
            len(self.genres) > 0,
            len(self.formats) > 0,
            self.min_bitrate_kbps is not None,
            self.min_duration_seconds is not None,
            self.max_duration_seconds is not None,
            len(self.quality_tiers) > 0,
            self.exclude_gated,
            len(self.platforms) > 0,
        ])

    def describe(self) -> str:
        """Human-readable summary of active filters."""
        parts = []
        if self.bpm_min is not None or self.bpm_max is not None:
            lo = f"{self.bpm_min:.0f}" if self.bpm_min else "?"
            hi = f"{self.bpm_max:.0f}" if self.bpm_max else "?"
            parts.append(f"BPM {lo}–{hi}")
        if self.key:
            camelot = standard_to_camelot(self.key)
            key_display = f"{self.key} ({camelot})" if camelot else self.key
            parts.append(f"Key: {key_display}")
        if self.genres:
            parts.append(f"Genre: {', '.join(self.genres)}")
        if self.formats:
            parts.append(f"Format: {', '.join(f.value.upper() for f in self.formats)}")
        if self.min_bitrate_kbps:
            parts.append(f"Min bitrate: {self.min_bitrate_kbps} kbps")
        if self.exclude_gated:
            parts.append("No gated downloads")
        if self.platforms:
            parts.append(f"Platforms: {', '.join(self.platforms)}")
        return " | ".join(parts) if parts else "No filters"


def sort_tracks(
    tracks: list[Track],
    sort_by: str = "date",
    reverse: bool = True,
) -> list[Track]:
    """Sort tracks by a given field.

    Supported sort keys: bpm, date, popularity, title, duration, quality, size
    """
    quality_rank = {"lossless": 3, "high": 2, "medium": 1, "low": 0, "unknown": -1}

    def _date_key(t: Track) -> float:
        """Epoch seconds for sorting, robust to mixed tz-aware/naive datetimes.

        Different platforms produce different tzinfo (SoundCloud is tz-aware,
        Bandcamp naive), which can't be compared directly — normalise to a float.
        """
        d = t.release_date
        if d is None:
            return 0.0
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()

    sort_funcs = {
        "bpm": lambda t: (t.bpm or 0),
        "date": _date_key,
        "popularity": lambda t: (t.play_count or 0),
        "title": lambda t: t.title.lower(),
        "duration": lambda t: (t.duration_seconds or 0),
        "quality": lambda t: quality_rank.get(t.quality_tier, -1),
        "size": lambda t: (t.file_size_bytes or 0),
        "likes": lambda t: (t.like_count or 0),
    }

    key_func = sort_funcs.get(sort_by, sort_funcs["date"])
    return sorted(tracks, key=key_func, reverse=reverse)
