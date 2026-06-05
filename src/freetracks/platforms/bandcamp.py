"""Bandcamp scanner — finds 'name your price' releases with $0 minimum.

Bandcamp's public search page is now a JavaScript-rendered shell, so the old
HTML-scraping approach returned nothing. Instead this scanner uses Bandcamp's
internal search API (the same ``bcsearch_public_api`` endpoint the site's own
search box calls) to find candidate tracks, then fetches each track page and
reads the embedded ``data-tralbum`` JSON blob to confirm the track is a true
$0 name-your-price download and to pull rich metadata (duration, artwork,
tags, release date, and a streamable preview URL).

Rate limiting is strict here — Bandcamp is an artist-first platform and we
want to be respectful. Because confirming "free" requires one page fetch per
candidate, we stop as soon as we have enough free tracks.
"""

from __future__ import annotations

import json
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

_SEARCH_API = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"

# A browser-like User-Agent — Bandcamp's API/pages are unfriendly to obvious bots.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# How many search candidates to inspect per query before giving up. Free
# name-your-price tracks are a minority of results, so we look past max_results.
_MAX_CANDIDATES = 40


class BandcampScanner(PlatformScanner):
    """Scanner for Bandcamp 'name your price' free releases."""

    platform_name = "bandcamp"
    base_url = "https://bandcamp.com"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        # Be very conservative with Bandcamp - 1 req/sec
        super().__init__(rate_limiter or RateLimiter(1.0))

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Search Bandcamp for name-your-price ($0) tracks."""
        candidates = await self._search_candidates(query)
        if not candidates:
            logger.info(f"Bandcamp: no search candidates for '{query}'")
            return []

        tracks: list[Track] = []
        for url in candidates[:_MAX_CANDIDATES]:
            if len(tracks) >= max_results:
                break
            track = await self._fetch_free_track(url)
            if track is not None:
                tracks.append(track)

        logger.info(f"Bandcamp: found {len(tracks)} name-your-price tracks for '{query}'")
        return tracks

    async def _search_candidates(self, query: str) -> list[str]:
        """Query Bandcamp's internal search API for candidate track URLs."""
        await self.rate_limiter.acquire()
        client = await self._get_client()
        payload = {"search_text": query, "search_filter": "t", "full_page": False}
        try:
            response = await client.post(
                _SEARCH_API,
                json=payload,
                headers={"User-Agent": _BROWSER_UA, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"Bandcamp search error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.warning(f"Bandcamp search failed: {e}")
            return []

        results = data.get("auto", {}).get("results", [])
        urls = []
        for item in results:
            if item.get("type") == "t" and item.get("item_url_path"):
                urls.append(item["item_url_path"])
        return urls

    async def get_track_details(self, track_url: str) -> Track | None:
        """Fetch full metadata from a Bandcamp track page (free tracks only)."""
        return await self._fetch_free_track(track_url)

    async def _fetch_free_track(self, track_url: str) -> Track | None:
        """Fetch a track page and return a Track only if it's $0 name-your-price."""
        await self.rate_limiter.acquire()
        client = await self._get_client()
        try:
            response = await client.get(track_url, headers={"User-Agent": _BROWSER_UA})
            response.raise_for_status()
        except Exception as e:
            logger.debug(f"Bandcamp page fetch failed for {track_url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        el = soup.select_one("[data-tralbum]")
        if el is None:
            return None

        try:
            data = json.loads(el["data-tralbum"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

        return self._parse_tralbum(data, soup, track_url)

    def _parse_tralbum(self, data: dict, soup: BeautifulSoup, url: str) -> Track | None:
        """Build a Track from the data-tralbum JSON, or None if not free."""
        current = data.get("current", {})
        trackinfo_list = data.get("trackinfo") or []
        ti = trackinfo_list[0] if trackinfo_list else {}

        # Confirm true name-your-price: $0 minimum, not a fixed price, and
        # the track itself is downloadable for free.
        minimum_price = current.get("minimum_price")
        is_set_price = current.get("is_set_price")
        is_free = (
            minimum_price == 0
            and not is_set_price
            and (ti.get("has_free_download") or ti.get("is_downloadable") or data.get("FREE"))
        )
        if not is_free:
            return None

        title = ti.get("title") or current.get("title") or "Unknown"
        artist = data.get("artist") or current.get("artist") or "Unknown"

        # Duration (seconds, float)
        duration_seconds = ti.get("duration")

        # Artwork from art_id
        art_id = data.get("art_id") or current.get("art_id")
        artwork_url = f"https://f4.bcbits.com/img/a{art_id}_10.jpg" if art_id else None

        # Streamable preview (mp3-128)
        preview_url = (ti.get("file") or {}).get("mp3-128")

        # Tags / genre from the page
        tag_els = soup.select("a.tag")
        tags = [t.get_text(strip=True) for t in tag_els]
        genre = tags[0] if tags else None

        # BPM / key from tags + description
        description = current.get("about") or ""
        all_text = " ".join(tags) + " " + description
        bpm = self._extract_bpm(all_text)
        key = self._extract_key(all_text)

        # Release date — Bandcamp uses RFC-2822-ish strings like
        # "01 Feb 2011 00:00:00 GMT".
        release_date = self._parse_bc_date(
            current.get("release_date") or current.get("publish_date")
        )

        # Name-your-price offers a format choice on download; MP3 is the default.
        file_format = AudioFormat.MP3

        return Track(
            title=title,
            artist=artist,
            platform=Platform.BANDCAMP,
            url=url,
            download_url=url,  # NYP download happens on the track page itself
            preview_url=preview_url,
            download_type=DownloadType.NAME_YOUR_PRICE,
            file_format=file_format,
            bpm=bpm,
            key=key,
            genre=genre,
            tags=tags,
            duration_seconds=duration_seconds,
            release_date=release_date,
            description=description[:500] if description else None,
            artwork_url=artwork_url,
            artist_url=data.get("url", url).rsplit("/track/", 1)[0] if "/track/" in url else None,
            play_count=ti.get("play_count"),
        )

    @staticmethod
    def _parse_bc_date(date_str: str | None) -> datetime | None:
        """Parse a Bandcamp date string like '01 Feb 2011 00:00:00 GMT'."""
        if not date_str:
            return None
        for fmt in ("%d %b %Y %H:%M:%S %Z", "%d %b %Y %H:%M:%S GMT"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_bpm(text: str) -> float | None:
        """Extract BPM from text."""
        patterns = [
            r"(\d{2,3})\s*bpm",
            r"bpm\s*[:=]?\s*(\d{2,3})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                bpm = float(match.group(1))
                if 60 <= bpm <= 200:
                    return bpm
        return None

    @staticmethod
    def _extract_key(text: str) -> str | None:
        """Extract musical key from text."""
        patterns = [
            r"\b([A-G][b#]?m(?:in(?:or)?)?)\b",
            r"\b([A-G][b#]?\s+(?:minor|major))\b",
            r"\b(\d{1,2}[AB])\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_key(match.group(1).strip())
        return None
