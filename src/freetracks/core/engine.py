"""Search engine — orchestrates multi-platform scanning with filtering and sorting."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from freetracks.core.models import SearchResults, Track
from freetracks.core.filters import TrackFilter, sort_tracks
from freetracks.platforms import get_scanner, get_all_scanners, PLATFORM_NAMES
from freetracks.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class SearchEngine:
    """Orchestrates searches across platforms with filtering and sorting.

    Usage:
        engine = SearchEngine()
        results = await engine.search(
            query="deep house",
            platforms=["soundcloud", "bandcamp"],
            track_filter=TrackFilter(bpm_min=120, bpm_max=128),
            sort_by="popularity",
            max_results=50,
        )
    """

    def __init__(self, rate_limit_rps: float = 2.0):
        self.rate_limit_rps = rate_limit_rps

    async def search(
        self,
        query: str,
        platforms: list[str] | None = None,
        track_filter: TrackFilter | None = None,
        sort_by: str = "date",
        sort_reverse: bool = True,
        max_results: int = 50,
    ) -> SearchResults:
        """Run a search across one or more platforms.

        Args:
            query: Search terms.
            platforms: List of platform names to search. None = all platforms.
            track_filter: Optional filter to apply to results.
            sort_by: Sort key (bpm, date, popularity, title, duration, quality, size).
            sort_reverse: Sort descending (True) or ascending (False).
            max_results: Maximum total tracks to return after filtering.

        Returns:
            SearchResults with filtered, sorted tracks.
        """
        start_time = time.monotonic()
        platform_list = platforms or PLATFORM_NAMES
        errors: list[str] = []

        # Create scanners
        scanners = []
        for p in platform_list:
            try:
                scanner = get_scanner(p, rate_limiter=RateLimiter(self.rate_limit_rps))
                scanners.append(scanner)
            except ValueError as e:
                errors.append(str(e))

        if not scanners:
            return SearchResults(
                query=query,
                errors=errors,
                search_time_seconds=time.monotonic() - start_time,
            )

        # Search all platforms concurrently
        per_platform_limit = max_results * 2  # Fetch extra to allow for filtering
        tasks = [
            self._search_platform(scanner, query, per_platform_limit)
            for scanner in scanners
        ]

        results_per_platform = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all tracks and errors
        all_tracks: list[Track] = []
        for scanner, result in zip(scanners, results_per_platform):
            if isinstance(result, Exception):
                error_msg = f"{scanner.platform_name}: {result}"
                logger.warning(error_msg)
                errors.append(error_msg)
            else:
                all_tracks.extend(result)

        # Clean up scanners
        for scanner in scanners:
            await scanner.close()

        total_found = len(all_tracks)

        # Apply filters
        if track_filter and track_filter.is_active:
            all_tracks = track_filter.apply(all_tracks)
            logger.info(
                f"Filtered {total_found} -> {len(all_tracks)} tracks "
                f"({track_filter.describe()})"
            )

        # Sort
        all_tracks = sort_tracks(all_tracks, sort_by=sort_by, reverse=sort_reverse)

        # Trim to max
        all_tracks = all_tracks[:max_results]

        elapsed = time.monotonic() - start_time

        return SearchResults(
            query=query,
            platform_filter=",".join(platform_list) if platforms else None,
            tracks=all_tracks,
            total_found=total_found,
            search_time_seconds=elapsed,
            errors=errors,
        )

    async def _search_platform(
        self,
        scanner,
        query: str,
        max_results: int,
    ) -> list[Track]:
        """Search a single platform, handling errors gracefully."""
        logger.info(f"Searching {scanner.platform_name} for '{query}'...")
        return await scanner.search(query, max_results=max_results)

    async def get_track_details(self, url: str, platform: str | None = None) -> Track | None:
        """Get full details for a single track URL.

        If platform is not specified, tries to detect it from the URL.
        """
        if platform is None:
            platform = self._detect_platform(url)

        if platform is None:
            logger.warning(f"Could not detect platform for URL: {url}")
            return None

        scanner = get_scanner(platform, rate_limiter=RateLimiter(self.rate_limit_rps))
        try:
            return await scanner.get_track_details(url)
        finally:
            await scanner.close()

    @staticmethod
    def _detect_platform(url: str) -> str | None:
        """Detect which platform a URL belongs to."""
        url_lower = url.lower()
        if "soundcloud.com" in url_lower:
            return "soundcloud"
        elif "bandcamp.com" in url_lower:
            return "bandcamp"
        elif "hypeddit.com" in url_lower:
            return "hypeddit"
        elif "toneden.io" in url_lower:
            return "toneden"
        return None
