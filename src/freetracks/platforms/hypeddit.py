"""Hypeddit scanner — catalogs gated free downloads.

Hypeddit (and similar services like Toneden) host 'download gates' where
artists offer free tracks in exchange for social actions (follow, repost,
subscribe, etc).

This scanner finds these gated downloads and catalogs them. It does NOT
bypass the gates — the user still needs to complete the gate action to
get the actual file. But knowing what's available and its metadata is
valuable for building a crate list.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

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


class HypedditScanner(PlatformScanner):
    """Scanner for Hypeddit gated free downloads."""

    platform_name = "hypeddit"
    base_url = "https://hypeddit.com"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        super().__init__(rate_limiter or RateLimiter(1.0))

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        """Search Hypeddit's free download charts and listings.

        Hypeddit has genre charts and a search function for finding
        gated downloads.
        """
        tracks: list[Track] = []

        # Search Hypeddit's free download pages
        search_url = f"{self.base_url}/search"
        params = {"q": query, "type": "gates"}

        try:
            response = await self._get(search_url, params=params)
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".gate-card, .track-card, .search-result-item")

            for result in results[:max_results]:
                track = self._parse_gate_card(result)
                if track is not None:
                    tracks.append(track)

        except httpx.HTTPStatusError as e:
            logger.warning(f"Hypeddit search error: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Hypeddit search failed: {e}")

        # Also try genre-specific chart pages if query looks like a genre
        chart_tracks = await self._search_charts(query, max_results - len(tracks))
        tracks.extend(chart_tracks)

        logger.info(f"Hypeddit: found {len(tracks)} gated downloads for '{query}'")
        return tracks[:max_results]

    async def _search_charts(self, genre_query: str, max_results: int) -> list[Track]:
        """Search Hypeddit's genre charts for free downloads."""
        tracks: list[Track] = []

        # Common genre slugs on Hypeddit
        genre_slugs = {
            "house": "house",
            "tech house": "tech-house",
            "deep house": "deep-house",
            "progressive house": "progressive-house",
            "bass house": "bass-house",
            "melodic house": "melodic-house",
            "afro house": "afro-house",
            "techno": "techno",
            "melodic techno": "melodic-techno",
            "drum and bass": "drum-and-bass",
            "dnb": "drum-and-bass",
            "dubstep": "dubstep",
            "future bass": "future-bass",
            "trap": "trap",
            "edm": "edm",
            "trance": "trance",
        }

        query_lower = genre_query.lower().strip()
        slug = genre_slugs.get(query_lower)

        if not slug:
            # Try fuzzy match
            for genre_name, genre_slug in genre_slugs.items():
                if query_lower in genre_name or genre_name in query_lower:
                    slug = genre_slug
                    break

        if not slug:
            return tracks

        chart_url = f"{self.base_url}/charts/{slug}"
        try:
            response = await self._get(chart_url)
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.select(".chart-item, .gate-card, .track-card")

            for result in results[:max_results]:
                track = self._parse_gate_card(result, default_genre=genre_query.title())
                if track is not None:
                    tracks.append(track)

        except Exception as e:
            logger.debug(f"Hypeddit chart fetch failed for {slug}: {e}")

        return tracks

    async def get_track_details(self, track_url: str) -> Track | None:
        """Fetch metadata from a Hypeddit gate page."""
        try:
            response = await self._get(track_url)
        except Exception as e:
            logger.warning(f"Could not fetch {track_url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        return self._parse_gate_page(soup, track_url)

    def _parse_gate_card(self, el, default_genre: str | None = None) -> Track | None:
        """Parse a gate card element from search or chart results."""
        # Title
        title_el = el.select_one(".track-title, .gate-title, h3, h4")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # Artist
        artist_el = el.select_one(".artist-name, .track-artist, .subtitle")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        # URL
        link_el = el.select_one("a[href]")
        url = ""
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("/"):
                url = f"{self.base_url}{href}"
            elif href.startswith("http"):
                url = href

        if not url:
            return None

        # Genre
        genre_el = el.select_one(".genre, .tag")
        genre = genre_el.get_text(strip=True) if genre_el else default_genre

        # Artwork
        artwork_url = None
        img_el = el.select_one("img")
        if img_el:
            artwork_url = img_el.get("src") or img_el.get("data-src")

        return Track(
            title=title,
            artist=artist,
            platform=Platform.HYPEDDIT,
            url=url,
            download_type=DownloadType.GATED,
            file_format=AudioFormat.MP3,  # Most Hypeddit gates offer MP3
            genre=genre,
            artwork_url=artwork_url,
        )

    def _parse_gate_page(self, soup: BeautifulSoup, url: str) -> Track | None:
        """Parse a full Hypeddit gate page for detailed metadata."""
        # Title
        title_el = soup.select_one("h1, .track-title, .gate-title")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        # Artist
        artist_el = soup.select_one(".artist-name, .track-artist, h2")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        # Try to find metadata in page scripts (Hypeddit often embeds JSON-LD or data)
        bpm = None
        key = None
        genre = None
        description = None

        # Check for structured data
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                ld_data = json.loads(script.string)
                if isinstance(ld_data, dict):
                    genre = ld_data.get("genre")
                    description = ld_data.get("description")
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract from page text
        page_text = soup.get_text(" ", strip=True)
        if not bpm:
            bpm = self._extract_bpm(page_text)
        if not key:
            key = self._extract_key(page_text)

        # Genre from tags
        tag_els = soup.select(".tag, .genre-tag")
        tags = [t.get_text(strip=True) for t in tag_els]
        if not genre and tags:
            genre = tags[0]

        # Artwork
        artwork_url = None
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image:
            artwork_url = og_image.get("content")

        return Track(
            title=title,
            artist=artist,
            platform=Platform.HYPEDDIT,
            url=url,
            download_type=DownloadType.GATED,
            file_format=AudioFormat.MP3,
            bpm=bpm,
            key=key,
            genre=genre,
            tags=tags,
            description=description[:500] if description else None,
            artwork_url=artwork_url,
        )

    @staticmethod
    def _extract_bpm(text: str) -> float | None:
        match = re.search(r'(\d{2,3})\s*bpm', text, re.IGNORECASE)
        if match:
            bpm = float(match.group(1))
            if 60 <= bpm <= 200:
                return bpm
        return None

    @staticmethod
    def _extract_key(text: str) -> str | None:
        patterns = [
            r'\b([A-G][b#]?m(?:in(?:or)?)?)\b',
            r'\b(\d{1,2}[AB])\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_key(match.group(1).strip())
        return None
