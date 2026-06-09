"""Request models for the web API.

Responses reuse the existing Pydantic models (``Track`` / ``SearchResults``)
via ``model_dump(mode="json")`` — no separate response schema needed.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from freetracks.core.models import AudioFormat


class SearchRequest(BaseModel):
    """Incoming search + filter parameters from the frontend."""

    query: str = Field(..., min_length=1, max_length=200)
    platforms: Optional[list[str]] = None

    # Filters (all optional)
    bpm_min: Optional[float] = None
    bpm_max: Optional[float] = None
    key: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    min_bitrate_kbps: Optional[int] = None
    quality_tiers: list[str] = Field(default_factory=list)
    exclude_gated: bool = False
    download_types: list[str] = Field(default_factory=list)
    exclude_unknown_bpm: bool = False
    max_duration_seconds: Optional[float] = None
    min_duration_seconds: Optional[float] = None

    # Sorting + paging
    sort_by: str = "popularity"
    sort_reverse: bool = True
    max_results: int = Field(default=50, ge=1, le=200)

    def to_audio_formats(self) -> list[AudioFormat]:
        return [AudioFormat.from_string(f) for f in self.formats if f]


class ExportRequest(BaseModel):
    """A batch of tracks (e.g. a crate) to render as a downloadable file."""

    tracks: list[dict]
    format: str = Field(..., pattern="^(csv|json|m3u)$")
    query: str = "crate"
