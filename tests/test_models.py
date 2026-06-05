"""Tests for Track model and TrackFilter."""

import pytest
from datetime import datetime

from freetracks.core.models import Track, Platform, DownloadType, AudioFormat
from freetracks.core.filters import TrackFilter, sort_tracks


def _make_track(**overrides) -> Track:
    """Factory for test tracks with sensible defaults."""
    defaults = {
        "title": "Test Track",
        "artist": "Test Artist",
        "platform": Platform.SOUNDCLOUD,
        "url": "https://soundcloud.com/test/track",
        "bpm": 126.0,
        "key": "Am",
        "genre": "Tech House",
        "file_format": AudioFormat.MP3,
        "bitrate_kbps": 320,
        "duration_seconds": 390.0,
        "download_type": DownloadType.DIRECT,
    }
    defaults.update(overrides)
    return Track(**defaults)


class TestTrackModel:
    def test_camelot_key(self):
        track = _make_track(key="Am")
        assert track.camelot_key == "8A"

    def test_camelot_key_none(self):
        track = _make_track(key=None)
        assert track.camelot_key is None

    def test_file_size_mb(self):
        track = _make_track(file_size_bytes=50_000_000)
        assert track.file_size_mb == 47.7

    def test_duration_formatted(self):
        track = _make_track(duration_seconds=392.0)
        assert track.duration_formatted == "6:32"

    def test_duration_formatted_with_hours(self):
        track = _make_track(duration_seconds=3661.0)
        assert track.duration_formatted == "1:01:01"

    def test_quality_tier_lossless(self):
        track = _make_track(file_format=AudioFormat.WAV)
        assert track.quality_tier == "lossless"

    def test_quality_tier_high(self):
        track = _make_track(file_format=AudioFormat.MP3, bitrate_kbps=320)
        assert track.quality_tier == "high"

    def test_quality_tier_medium(self):
        track = _make_track(file_format=AudioFormat.MP3, bitrate_kbps=192)
        assert track.quality_tier == "medium"

    def test_matches_bpm_range(self):
        track = _make_track(bpm=126.0)
        assert track.matches_bpm_range(120, 128) is True
        assert track.matches_bpm_range(128, 135) is False
        assert track.matches_bpm_range(None, None) is True

    def test_matches_key_standard(self):
        track = _make_track(key="Am")
        assert track.matches_key("Am") is True
        assert track.matches_key("Cm") is False

    def test_matches_key_camelot(self):
        track = _make_track(key="Am")
        assert track.matches_key("8A") is True
        assert track.matches_key("5A") is False

    def test_to_row(self):
        track = _make_track()
        row = track.to_row()
        assert row["title"] == "Test Track"
        assert row["artist"] == "Test Artist"
        assert row["camelot"] == "8A"

    def test_audio_format_from_string(self):
        assert AudioFormat.from_string("mp3") == AudioFormat.MP3
        assert AudioFormat.from_string("WAV") == AudioFormat.WAV
        assert AudioFormat.from_string(".flac") == AudioFormat.FLAC
        assert AudioFormat.from_string("aif") == AudioFormat.AIFF
        assert AudioFormat.from_string("weird") == AudioFormat.UNKNOWN


class TestTrackFilter:
    def test_bpm_filter(self):
        tracks = [
            _make_track(title="slow", bpm=100),
            _make_track(title="right", bpm=126),
            _make_track(title="fast", bpm=140),
        ]
        f = TrackFilter(bpm_min=120, bpm_max=130)
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "right"

    def test_key_filter(self):
        tracks = [
            _make_track(title="am", key="Am"),
            _make_track(title="cm", key="Cm"),
        ]
        f = TrackFilter(key="8A")
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "am"

    def test_genre_filter(self):
        tracks = [
            _make_track(title="house", genre="Tech House"),
            _make_track(title="dnb", genre="Drum and Bass"),
        ]
        f = TrackFilter(genres=["tech house"])
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "house"

    def test_format_filter(self):
        tracks = [
            _make_track(title="mp3", file_format=AudioFormat.MP3),
            _make_track(title="wav", file_format=AudioFormat.WAV),
        ]
        f = TrackFilter(formats=[AudioFormat.WAV])
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "wav"

    def test_exclude_gated(self):
        tracks = [
            _make_track(title="direct", download_type=DownloadType.DIRECT),
            _make_track(title="gated", download_type=DownloadType.GATED),
        ]
        f = TrackFilter(exclude_gated=True)
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "direct"

    def test_combined_filters(self):
        tracks = [
            _make_track(title="perfect", bpm=126, key="Am", genre="Tech House"),
            _make_track(title="wrong bpm", bpm=100, key="Am", genre="Tech House"),
            _make_track(title="wrong key", bpm=126, key="Cm", genre="Tech House"),
            _make_track(title="wrong genre", bpm=126, key="Am", genre="DnB"),
        ]
        f = TrackFilter(bpm_min=120, bpm_max=130, key="Am", genres=["tech house"])
        result = f.apply(tracks)
        assert len(result) == 1
        assert result[0].title == "perfect"

    def test_no_filters(self):
        tracks = [_make_track(), _make_track()]
        f = TrackFilter()
        assert f.is_active is False
        assert len(f.apply(tracks)) == 2

    def test_describe(self):
        f = TrackFilter(bpm_min=120, bpm_max=128, key="Am", genres=["house"])
        desc = f.describe()
        assert "BPM" in desc
        assert "Key" in desc
        assert "house" in desc


class TestSortTracks:
    def test_sort_by_bpm(self):
        tracks = [
            _make_track(title="fast", bpm=140),
            _make_track(title="slow", bpm=100),
            _make_track(title="mid", bpm=126),
        ]
        sorted_tracks = sort_tracks(tracks, sort_by="bpm", reverse=True)
        assert sorted_tracks[0].title == "fast"
        assert sorted_tracks[-1].title == "slow"

    def test_sort_by_title(self):
        tracks = [
            _make_track(title="Zebra"),
            _make_track(title="Alpha"),
            _make_track(title="Middle"),
        ]
        sorted_tracks = sort_tracks(tracks, sort_by="title", reverse=False)
        assert sorted_tracks[0].title == "Alpha"
        assert sorted_tracks[-1].title == "Zebra"

    def test_sort_by_popularity(self):
        tracks = [
            _make_track(title="unpopular", play_count=10),
            _make_track(title="viral", play_count=100_000),
            _make_track(title="medium", play_count=5_000),
        ]
        sorted_tracks = sort_tracks(tracks, sort_by="popularity", reverse=True)
        assert sorted_tracks[0].title == "viral"
