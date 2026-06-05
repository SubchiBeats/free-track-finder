"""Bandcamp scanner — finds 'name your price' releases with $0 minimum.

Bandcamp doesn't have a public API, so this scanner scrapes search results
and individual release pages. It only surfaces tracks where the artist has
set a $0 minimum price (true free downloads).

Rate limiting is strict here — Bandcamp is an artist-first platform and
we want to be respectful.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urljoin

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


class BandcampScanner(PlatformScanner):
    """Scanner for Bandcamp 'name your price' free releases."""

    platform_name = "bandcamp"
    base_url = "https://bandcamp.com"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        # Be very conservative with Bandcamp - 1 req/sec
        super().__init__(rate_limiter or RateLimiter(1.0))

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Search Bandcamp for name-your-price tracks."""
        tracks: list[Track] = []
        page = 1

        while len(tracks) < max_results:
            search_url = f"{self.base_url}/search"
            params = {
                "q": query,
                "item_type": "t",  # Tracks only
                "page": page,
            }

            try:
                response = await self._get(search_url, params=params)
            except httpx.HTTPStatusError as e:
                logger.warning(f"Bandcamp search error: {e.response.status_code}")
                break
            except Exception as e:
                logger.warning(f"Bandcamp request failed: {e}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".result-items .searchresult")

            if not results:
                break

            for result in results:
                if len(tracks) >= max_results:
                    break

                track = self._parse_search_result(result)
                if track is not None:
                    tracks.append(track)

            # Check if there are more pages
            next_link = soup.select_one(".pager .next a")
            if next_link:
                page += 1
            else:
                break

        logger.info(f"Bandcamp: found {len(tracks)} name-your-price tracks for '{query}'")
        return tracks

    async def get_track_details(self, track_url: str) -> Track | None:
        """Fetch full metadata from a Bandcamp track/album page."""
        try:
            response = await self._get(track_url)
        except Exception as e:
            logger.warning(f"Could not fetch {track_url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        return self._parse_track_page(soup, track_url)

    def _parse_search_result(self, result_el) -> Track | None:
        """Parse a single search result element.

        Returns None if the track isn't name-your-price or we can't parse it.
        """
        # Check if it's name-your-price (free)
        subhead = result_el.select_one(".subhead")
        price_el = result_el.select_one(".price, .released")

        # Look for "name your price" indicator
        result_text = result_el.get_text(" ", strip=True).lower()
        is_free = "name your price" in result_text

        if not is_free:
            return None

        # Extract basic info
        heading = result_el.select_one(".heading a")
        if not heading:
            return None

        title = heading.get_text(strip=True)
        url = heading.get("href", "").split("?")[0]

        # Artist
        artist_el = result_el.select_one(".subhead")
        artist = "Unknown"
        if artist_el:
            artist_text = artist_el.get_text(strip=True)
            # Format is typically "from AlbumName by ArtistName" or just "by ArtistName"
            by_match = re.search(r'by\s+(.+)', artist_text)
            if by_match:
                artist = by_match.group(1).strip()

        # Genre from tags
        genre = None
        tags = []
        tag_els = result_el.select(".tag")
        if tag_els:
            tags = [t.get_text(strip=True) for t in tag_els]
            genre = tags[0] if tags else None

        # Release date
        release_date = None
        released_el = result_el.select_one(".released")
        if released_el:
            date_text = released_el.get_text(strip=True)
            date_match = re.search(r'released\s+(.+)', date_text, re.IGNORECASE)
            if date_match:
                try:
                    release_date = datetime.strptime(date_match.group(1).strip(), "%B %d, %Y")
                except ValueError:
                    pass

        # Artwork
        artwork_url = None
        art_el = result_el.select_one(".art img")
        if art_el:
            artwork_url = art_el.get("src")

        return Track(
            title=title,
            artist=artist,
            platform=Platform.BANDCAMP,
            url=url,
            download_type=DownloadType.NAME_YOUR_PRICE,
            file_format=AudioFormat.MP3,  # Bandcamp offers multiple, MP3 is default free tier
            genre=genre,
            tags=tags,
            release_date=release_date,
            artwork_url=artwork_url,
        )

    def _parse_track_page(self, soup: BeautifulSoup, url: str) -> Track | None:
        """Parse a full Bandcamp track page for detailed metadata."""
        # Check if it's name-your-price
        buy_link = soup.select_one(".buyItem .buyItemExtra .buyItemNy498")
        price_el = soup.select_one(".base-text-color[itemprop='price']")

        is_free = False
        if price_el:
            price_text = price_el.get("content", "").strip()
            if price_text in ("0", "0.00", "0.0"):
                is_free = True

        # Also check for "name your price" text
        page_text = soup.get_text(" ", strip=True).lower()
        if "name your price" in page_text:
            is_free = True

        if not is_free:
            return None

        # Title
        title_el = soup.select_one("h2.trackTitle, .trackTitle")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        # Artist
        artist_el = soup.select_one("#name-section a, span[itemprop='byArtist'] a")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        # Duration
        duration_el = soup.select_one("meta[itemprop='duration']")
        duration_seconds = None
        if duration_el:
            dur_str = duration_el.get("content", "")
            duration_seconds = self._parse_iso_duration(dur_str)

        # Tags / genre
        tag_els = soup.select(".tralbumData.tralbum-tags a.tag")
        tags = [t.get_text(strip=True) for t in tag_els]
        genre = tags[0] if tags else None

        # Try to get BPM/key from tags or description
        description = ""
        desc_el = soup.select_one(".tralbumData.tralbum-about")
        if desc_el:
            description = desc_el.get_text(" ", strip=True)

        all_text = " ".join(tags) + " " + description
        bpm = self._extract_bpm(all_text)
        key = self._extract_key(all_text)

        # Release date
        release_date = None
        date_el = soup.select_one("meta[itemprop='datePublished']")
        if date_el:
            try:
                release_date = datetime.strptime(date_el["content"], "%Y%m%d")
            except (ValueError, KeyError):
                pass

        # Artwork
        artwork_url = None
        art_el = soup.select_one("#tralbumArt a.popupImage img, .popupImage img")
        if art_el:
            artwork_url = art_el.get("src")

        # Available formats — Bandcamp name-your-price offers multiple
        # We note this as MP3 by default but the user gets format choice on download
        available_formats = [AudioFormat.MP3]
        format_text = page_text
        if "flac" in format_text:
            available_formats.append(AudioFormat.FLAC)
        if "wav" in format_text:
            available_formats.append(AudioFormat.WAV)
        if "aiff" in format_text:
            available_formats.append(AudioFormat.AIFF)

        return Track(
            title=title,
            artist=artist,
            platform=Platform.BANDCAMP,
            url=url,
            download_type=DownloadType.NAME_YOUR_PRICE,
            file_format=AudioFormat.MP3,  # Default; Bandcamp lets you choose
            bpm=bpm,
            key=key,
            genre=genre,
            tags=tags,
            duration_seconds=duration_seconds,
            release_date=release_date,
            description=description[:500] if description else None,
            artwork_url=artwork_url,
            artist_url=url.rsplit("/", 2)[0] if "/" in url else None,
        )

    @staticmethod
    def _parse_iso_duration(iso_str: str) -> float | None:
        """Parse ISO 8601 duration (P00H03M45S) to seconds."""
        match = re.match(r'P(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_str)
        if not match:
            return None
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return float(hours * 3600 + minutes * 60 + seconds)

    @staticmethod
    def _extract_bpm(text: str) -> float | None:
        """Extract BPM from text."""
        patterns = [
            r'(\d{2,3})\s*bpm',
            r'bpm\s*[:=]?\s*(\d{2,3})',
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
            r'\b([A-G][b#]?m(?:in(?:or)?)?)\b',
            r'\b([A-G][b#]?\s+(?:minor|major))\b',
            r'\b(\d{1,2}[AB])\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_key(match.group(1).strip())
        return None
