"""Abstract base class for platform scanners.

Each platform implements this interface to provide a consistent way to
search and retrieve free tracks.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from freetracks.core.models import Track
from freetracks.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class PlatformScanner(ABC):
    """Base class for all platform scanners."""

    platform_name: str = "unknown"
    base_url: str = ""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self.rate_limiter = rate_limiter or RateLimiter(2.0)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "FreeTrackFinder/0.1 "
                        "(https://github.com/free-track-finder; DJ music discovery tool)"
                    ),
                },
            )
        return self._client

    async def close(self) -> None:
        """Clean up HTTP client resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """Rate-limited GET request."""
        await self.rate_limiter.acquire()
        client = await self._get_client()
        logger.debug(f"[{self.platform_name}] GET {url} params={params}")
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response

    @abstractmethod
    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Search the platform for free tracks matching a query.

        Args:
            query: Search terms (genre, artist, style, etc.)
            max_results: Maximum number of tracks to return.

        Returns:
            List of Track objects with as much metadata as the platform provides.
        """
        ...

    @abstractmethod
    async def get_track_details(self, track_url: str) -> Track | None:
        """Fetch full metadata for a single track by its URL.

        Useful for enriching results or checking a specific track.

        Args:
            track_url: Full URL of the track page.

        Returns:
            A Track object with full metadata, or None if not found / not free.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform={self.platform_name}>"
