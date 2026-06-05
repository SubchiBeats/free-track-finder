"""SoundCloud scanner — finds tracks with free downloads enabled.

SoundCloud's public API (v2) is used to search for tracks where the artist
has enabled the download button. This respects the artist's intent — we only
surface tracks they've explicitly made downloadable.

Note: SoundCloud's API requires a client_id. This scanner extracts one from
the public website (the same ID the web player uses). If SoundCloud changes
their API structure, this may need updating.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from freetracks.core.models import (
    AudioFormat,
    DownloadType,
    Platform,
    Track,
)
from freetracks.platforms.base import PlatformScanner
from freetracks.utils.keys import normalize_key
from freetracks.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_API_V2_BASE = "https://api-v2.soundcloud.com"


class SoundCloudScanner(PlatformScanner):
    """Scanner for SoundCloud free downloads."""

    platform_name = "soundcloud"
    base_url = "https://soundcloud.com"

    def __init__(self, client_id: str | None = None, rate_limiter: RateLimiter | None = None):
        super().__init__(rate_limiter or RateLimiter(1.5))  # Be gentle with SC
        self._client_id = client_id

    async def _resolve_client_id(self) -> str:
        """Extract a client_id from SoundCloud's public web assets.

        The web player includes the client_id in its JavaScript bundles.
        This is the same ID any browser user gets — we're not bypassing anything.
        """
        if self._client_id:
            return self._client_id

        logger.info("Resolving SoundCloud client_id from public assets...")
        client = await self._get_client()

        # Fetch the homepage
        response = await client.get("https://soundcloud.com", timeout=15.0)
        response.raise_for_status()

        # Find script URLs in the page
        soup = BeautifulSoup(response.text, "html.parser")
        scripts = soup.find_all("script", src=True)
        script_urls = [
            s["src"] for s in scripts
            if "sndcdn.com" in s.get("src", "") or "soundcloud.com" in s.get("src", "")
        ]

        # Search scripts for client_id pattern
        for script_url in script_urls[-5:]:  # Check the last few scripts
            await self.rate_limiter.acquire()
            try:
                resp = await client.get(script_url, timeout=10.0)
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', resp.text)
                if match:
                    self._client_id = match.group(1)
                    logger.info(f"Resolved client_id: {self._client_id[:8]}...")
                    return self._client_id
            except Exception:
                continue

        raise RuntimeError(
            "Could not resolve SoundCloud client_id. SoundCloud may have changed their "
            "asset structure. You can provide one manually with --sc-client-id."
        )

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Search SoundCloud for tracks with downloads enabled."""
        client_id = await self._resolve_client_id()
        tracks: list[Track] = []
        offset = 0
        limit = min(max_results, 50)  # SC API caps at 50 per request

        while len(tracks) < max_results:
            params = {
                "q": query,
                "client_id": client_id,
                "limit": limit,
                "offset": offset,
                "filter.downloadable": "true",  # Only downloadable tracks
            }

            try:
                response = await self._get(f"{_API_V2_BASE}/search/tracks", params=params)
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.warning(f"SoundCloud API error: {e.response.status_code}")
                break
            except Exception as e:
                logger.warning(f"SoundCloud request failed: {e}")
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for item in collection:
                track = self._parse_track(item)
                if track is not None:
                    tracks.append(track)
                    if len(tracks) >= max_results:
                        break

            # Check for more pages
            if data.get("next_href"):
                offset += limit
            else:
                break

        logger.info(f"SoundCloud: found {len(tracks)} free tracks for '{query}'")
        return tracks

    async def get_track_details(self, track_url: str) -> Track | None:
        """Resolve a SoundCloud URL to full track metadata."""
        client_id = await self._resolve_client_id()

        try:
            params = {"url": track_url, "client_id": client_id}
            response = await self._get(f"{_API_V2_BASE}/resolve", params=params)
            data = response.json()
        except Exception as e:
            logger.warning(f"Could not resolve {track_url}: {e}")
            return None

        if data.get("kind") != "track":
            return None

        return self._parse_track(data)

    def _parse_track(self, data: dict) -> Track | None:
        """Parse a SoundCloud API track object into our Track model."""
        if not data.get("downloadable") and not data.get("has_downloads_left"):
            # Not actually downloadable
            return None

        # Parse release date
        release_date = None
        date_str = data.get("release_date") or data.get("created_at") or data.get("display_date")
        if date_str:
            try:
                release_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Parse genre
        genre = data.get("genre", "").strip() or None

        # Parse tags
        tag_list_raw = data.get("tag_list", "")
        tags = self._parse_tag_list(tag_list_raw)

        # Try to extract BPM and key from tags or description
        bpm = None
        key = None
        description = data.get("description", "") or ""

        # Check tags for BPM/key info
        all_text = " ".join(tags) + " " + description
        bpm = self._extract_bpm(all_text)
        key = self._extract_key(all_text)

        # Determine format — SC typically serves MP3 for downloads
        file_format = AudioFormat.MP3

        # Duration
        duration_ms = data.get("full_duration") or data.get("duration")
        duration_seconds = duration_ms / 1000.0 if duration_ms else None

        # Artwork
        artwork_url = data.get("artwork_url")
        if artwork_url:
            artwork_url = artwork_url.replace("-large", "-t500x500")

        return Track(
            title=data.get("title", "Unknown"),
            artist=data.get("user", {}).get("username", "Unknown"),
            platform=Platform.SOUNDCLOUD,
            url=data.get("permalink_url", ""),
            track_id=str(data.get("id", "")),
            download_type=DownloadType.DIRECT,
            file_format=file_format,
            bitrate_kbps=128 if file_format == AudioFormat.MP3 else None,  # SC default
            bpm=bpm,
            key=key,
            genre=genre,
            tags=tags,
            duration_seconds=duration_seconds,
            play_count=data.get("playback_count"),
            like_count=data.get("likes_count") or data.get("favoritings_count"),
            repost_count=data.get("reposts_count"),
            comment_count=data.get("comment_count"),
            release_date=release_date,
            description=description[:500] if description else None,
            artwork_url=artwork_url,
            artist_url=data.get("user", {}).get("permalink_url"),
        )

    @staticmethod
    def _parse_tag_list(tag_list: str) -> list[str]:
        """Parse SoundCloud's tag_list format.

        SC uses a weird format: quoted multi-word tags and unquoted single-word tags
        e.g. '"tech house" deep minimal "free download"'
        """
        if not tag_list:
            return []
        tags = []
        in_quote = False
        current = []
        for char in tag_list:
            if char == '"':
                in_quote = not in_quote
                if not in_quote and current:
                    tags.append("".join(current).strip())
                    current = []
            elif char == " " and not in_quote:
                if current:
                    tags.append("".join(current).strip())
                    current = []
            else:
                current.append(char)
        if current:
            tags.append("".join(current).strip())
        return [t for t in tags if t]

    @staticmethod
    def _extract_bpm(text: str) -> float | None:
        """Try to extract BPM from text (tags, description)."""
        patterns = [
            r'(\d{2,3})\s*bpm',
            r'bpm\s*[:=]?\s*(\d{2,3})',
            r'tempo\s*[:=]?\s*(\d{2,3})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                bpm = float(match.group(1))
                if 60 <= bpm <= 200:  # Sanity check
                    return bpm
        return None

    @staticmethod
    def _extract_key(text: str) -> str | None:
        """Try to extract musical key from text."""
        patterns = [
            r'key\s*[:=]?\s*([A-G][b#]?\s*(?:min(?:or)?|maj(?:or)?|m))',
            r'\b([A-G][b#]?m(?:in(?:or)?)?)\b',
            r'\b([A-G][b#]?\s+(?:minor|major))\b',
            r'\b(\d{1,2}[AB])\b',  # Camelot notation
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw_key = match.group(1).strip()
                normalized = normalize_key(raw_key)
                if normalized:
                    return normalized
        return None
