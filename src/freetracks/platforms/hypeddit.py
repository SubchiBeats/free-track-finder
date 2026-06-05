"""Hypeddit scanner — catalogs gated free downloads.

Hypeddit hosts 'download gates' where artists offer free tracks in exchange
for social actions (follow, repost, subscribe). This scanner finds those gates
and catalogs them — it does NOT bypass the gate; the user still completes the
social action on Hypeddit to get the file.

The old implementation hit a non-existent ``/search?type=gates`` endpoint and
guessed at CSS classes. The real site renders genre/chart listings as hidden
``<span data-trackid=... data-permalink=... data-directlink=...>`` carriers:
each one points at a Hypeddit gate URL and the underlying SoundCloud track.
Hypeddit doesn't expose title/BPM/artwork inline, so we enrich the top results
by resolving their SoundCloud permalinks through the SoundCloud API (which we
already know how to talk to).
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from freetracks.core.models import (
    AudioFormat,
    DownloadType,
    Platform,
    Track,
)
from freetracks.platforms.base import PlatformScanner
from freetracks.platforms.soundcloud import SoundCloudScanner
from freetracks.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# How many gates to enrich via SoundCloud per search (each costs ~1 request).
_MAX_ENRICH = 15


class HypedditScanner(PlatformScanner):
    """Scanner for Hypeddit gated free downloads."""

    platform_name = "hypeddit"
    base_url = "https://hypeddit.com"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        super().__init__(rate_limiter or RateLimiter(1.5))
        # Reused to resolve SoundCloud metadata for gate entries.
        self._sc = SoundCloudScanner(rate_limiter=RateLimiter(1.5))

    async def close(self) -> None:
        await self._sc.close()
        await super().close()

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Find Hypeddit gates by genre (falling back to the downloads chart)."""
        gates = await self._list_gates(query)
        if not gates:
            logger.info(f"Hypeddit: no gates found for '{query}'")
            return []

        # Enrich the top N gates with SoundCloud metadata.
        tracks: list[Track] = []
        for gate in gates[: min(max_results, _MAX_ENRICH)]:
            track = await self._enrich_gate(gate)
            if track is not None:
                tracks.append(track)

        logger.info(f"Hypeddit: found {len(tracks)} gated downloads for '{query}'")
        return tracks

    async def _list_gates(self, query: str) -> list[dict]:
        """Fetch a Hypeddit listing page and parse its gate data-carriers.

        Tries /music/genre/<slug> first (query treated as a genre), then falls
        back to the global downloads chart.
        """
        slug = query.strip().lower().replace(" ", "-").replace("&", "and")
        urls = [
            f"{self.base_url}/music/genre/{slug}",
            f"{self.base_url}/charts/downloads",
        ]

        for url in urls:
            html = await self._fetch(url)
            if html is None:
                continue
            gates = self._parse_gates(html)
            if gates:
                logger.debug(f"Hypeddit: {len(gates)} gates from {url}")
                return gates
        return []

    async def _fetch(self, url: str) -> str | None:
        await self.rate_limiter.acquire()
        client = await self._get_client()
        try:
            response = await client.get(url, headers={"User-Agent": _BROWSER_UA})
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.debug(f"Hypeddit {url} -> {e.response.status_code}")
            return None
        except Exception as e:
            logger.debug(f"Hypeddit fetch failed for {url}: {e}")
            return None

    @staticmethod
    def _parse_gates(html: str) -> list[dict]:
        """Extract gate descriptors from span[data-trackid] carriers.

        Only SoundCloud-backed gates are usable (we enrich via SoundCloud).
        De-duplicates by gate uid while preserving page order.
        """
        soup = BeautifulSoup(html, "html.parser")
        gates: list[dict] = []
        seen: set[str] = set()
        for el in soup.select("span[data-trackid][data-permalink]"):
            uid = el.get("data-uid")
            permalink = el.get("data-permalink", "")
            if not uid or uid in seen:
                continue
            if "soundcloud.com" not in permalink:
                continue  # only SoundCloud-backed gates can be enriched
            seen.add(uid)
            gates.append(
                {
                    "uid": uid,
                    "permalink": permalink,
                    "gate_url": el.get("data-directlink") or f"https://hypeddit.com/track/{uid}",
                    "ftype": el.get("data-ftype", ""),
                }
            )
        return gates

    async def _enrich_gate(self, gate: dict) -> Track | None:
        """Resolve a gate's SoundCloud permalink into a full Track."""
        try:
            sc_track = await self._sc.get_track_details(gate["permalink"])
        except Exception as e:
            logger.debug(f"Hypeddit enrich failed for {gate['permalink']}: {e}")
            sc_track = None

        if sc_track is None:
            return None

        # Re-badge the SoundCloud track as a Hypeddit gated download, pointing
        # the download/url at the Hypeddit gate the user must complete.
        return sc_track.model_copy(
            update={
                "platform": Platform.HYPEDDIT,
                "url": gate["gate_url"],
                "download_url": gate["gate_url"],
                "download_type": DownloadType.GATED,
                "file_format": sc_track.file_format or AudioFormat.MP3,
            }
        )

    async def get_track_details(self, track_url: str) -> Track | None:
        """Fetch metadata from a single Hypeddit gate page.

        Resolves the gate's underlying SoundCloud track when present.
        """
        html = await self._fetch(track_url)
        if html is None:
            return None
        soup = BeautifulSoup(html, "html.parser")
        # Gate pages embed the SoundCloud track id in the player iframe.
        iframe = soup.select_one('iframe[src*="api.soundcloud.com/tracks/"]')
        if iframe:
            import re

            m = re.search(r"api\.soundcloud\.com/tracks/(\d+)", iframe.get("src", ""))
            if m:
                sc_url = f"https://api.soundcloud.com/tracks/{m.group(1)}"
                sc_track = await self._sc.get_track_details(sc_url)
                if sc_track is not None:
                    return sc_track.model_copy(
                        update={
                            "platform": Platform.HYPEDDIT,
                            "url": track_url,
                            "download_url": track_url,
                            "download_type": DownloadType.GATED,
                        }
                    )
        return None
