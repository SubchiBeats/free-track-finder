"""Track data model — the central data structure for all platform results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from freetracks.utils.keys import standard_to_camelot, camelot_to_standard


class Platform(str, Enum):
    SOUNDCLOUD = "soundcloud"
    BANDCAMP = "bandcamp"
    HYPEDDIT = "hypeddit"
    TONEDEN = "toneden"


class DownloadType(str, Enum):
    DIRECT = "direct"  # Click and download, no gate
    GATED = "gated"  # Requires social action (follow/repost/email)
    NAME_YOUR_PRICE = "name_your_price"  # Bandcamp $0 minimum


class AudioFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"
    AIFF = "aiff"
    OGG = "ogg"
    AAC = "aac"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, s: str) -> "AudioFormat":
        """Parse format from a string, handling common variations."""
        normalized = s.strip().lower().replace(".", "")
        mapping = {
            "mp3": cls.MP3,
            "wav": cls.WAV,
            "wave": cls.WAV,
            "flac": cls.FLAC,
            "aiff": cls.AIFF,
            "aif": cls.AIFF,
            "ogg": cls.OGG,
            "vorbis": cls.OGG,
            "aac": cls.AAC,
            "m4a": cls.AAC,
        }
        return mapping.get(normalized, cls.UNKNOWN)


class Track(BaseModel):
    """A single track with all available DJ-relevant metadata.

    Not all fields will be populated for every track — platforms provide
    different levels of detail. Fields default to None when unavailable.
    """

    # === Identity ===
    title: str
    artist: str
    platform: Platform
    url: str  # Track page URL
    track_id: Optional[str] = None  # Platform-specific ID

    # === Download Info ===
    download_url: Optional[str] = None
    download_type: DownloadType = DownloadType.DIRECT
    file_format: AudioFormat = AudioFormat.UNKNOWN
    file_size_bytes: Optional[int] = None
    bitrate_kbps: Optional[int] = None

    # === Musical Metadata ===
    bpm: Optional[float] = None
    key: Optional[str] = None  # Standard notation: Am, Cm, F#m, Bb, etc.
    genre: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None
    energy: Optional[int] = None  # 1-10 subjective energy level if available

    # === Social / Discovery ===
    play_count: Optional[int] = None
    like_count: Optional[int] = None
    repost_count: Optional[int] = None
    comment_count: Optional[int] = None
    release_date: Optional[datetime] = None
    description: Optional[str] = None
    artwork_url: Optional[str] = None
    artist_url: Optional[str] = None

    # === Computed Fields ===

    @computed_field
    @property
    def camelot_key(self) -> Optional[str]:
        """Convert standard key notation to Camelot wheel notation."""
        if self.key is None:
            return None
        return standard_to_camelot(self.key)

    @computed_field
    @property
    def file_size_mb(self) -> Optional[float]:
        """File size in megabytes, rounded to 1 decimal."""
        if self.file_size_bytes is None:
            return None
        return round(self.file_size_bytes / (1024 * 1024), 1)

    @computed_field
    @property
    def duration_formatted(self) -> Optional[str]:
        """Duration as M:SS or H:MM:SS string."""
        if self.duration_seconds is None:
            return None
        total = int(self.duration_seconds)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @computed_field
    @property
    def quality_tier(self) -> str:
        """Quick quality assessment based on format and bitrate."""
        if self.file_format in (AudioFormat.WAV, AudioFormat.FLAC, AudioFormat.AIFF):
            return "lossless"
        if self.bitrate_kbps and self.bitrate_kbps >= 320:
            return "high"
        if self.bitrate_kbps and self.bitrate_kbps >= 192:
            return "medium"
        if self.bitrate_kbps and self.bitrate_kbps > 0:
            return "low"
        return "unknown"

    def matches_bpm_range(self, bpm_min: float | None, bpm_max: float | None) -> bool:
        """Check if track BPM falls within a range. None bounds = no limit."""
        if self.bpm is None:
            return True  # Don't exclude tracks with unknown BPM
        if bpm_min is not None and self.bpm < bpm_min:
            return False
        if bpm_max is not None and self.bpm > bpm_max:
            return False
        return True

    def matches_key(self, target_key: str) -> bool:
        """Check if track matches a key (accepts both standard and Camelot)."""
        if self.key is None:
            return True
        target_upper = target_key.strip().upper()
        # Check if target is Camelot notation
        if any(target_upper.endswith(s) for s in ("A", "B")) and target_upper[:-1].isdigit():
            return self.camelot_key == target_upper
        # Standard key comparison
        target_standard = target_key.strip()
        return self.key.lower() == target_standard.lower()

    def to_row(self, verbose: bool = False) -> dict:
        """Convert to a flat dict suitable for table display or CSV export."""
        row = {
            "title": self.title,
            "artist": self.artist,
            "platform": self.platform.value,
            "bpm": self.bpm or "—",
            "key": self.key or "—",
            "camelot": self.camelot_key or "—",
            "genre": self.genre or "—",
            "duration": self.duration_formatted or "—",
            "format": self.file_format.value.upper(),
            "quality": self.quality_tier,
            "size": f"{self.file_size_mb} MB" if self.file_size_mb else "—",
            "download": self.download_type.value,
            "url": self.url,
        }
        if verbose:
            row.update({
                "bitrate": f"{self.bitrate_kbps} kbps" if self.bitrate_kbps else "—",
                "plays": f"{self.play_count:,}" if self.play_count else "—",
                "likes": f"{self.like_count:,}" if self.like_count else "—",
                "released": self.release_date.strftime("%Y-%m-%d") if self.release_date else "—",
                "tags": ", ".join(self.tags) if self.tags else "—",
                "download_url": self.download_url or "—",
            })
        return row


class SearchResults(BaseModel):
    """Container for a batch of search results with metadata."""

    query: str
    platform_filter: Optional[str] = None
    tracks: list[Track] = Field(default_factory=list)
    total_found: int = 0
    search_time_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @computed_field
    @property
    def platforms_searched(self) -> list[str]:
        return sorted(set(t.platform.value for t in self.tracks))

    @computed_field
    @property
    def format_breakdown(self) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for t in self.tracks:
            fmt = t.file_format.value.upper()
            breakdown[fmt] = breakdown.get(fmt, 0) + 1
        return breakdown

    @computed_field
    @property
    def bpm_range(self) -> Optional[str]:
        bpms = [t.bpm for t in self.tracks if t.bpm is not None]
        if not bpms:
            return None
        return f"{min(bpms):.0f}–{max(bpms):.0f}"
