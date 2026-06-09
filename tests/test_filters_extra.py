"""Tests for the newer TrackFilter behaviour: download types, known-BPM, duration."""

from freetracks.core.filters import TrackFilter
from freetracks.core.models import AudioFormat, DownloadType, Platform, Track


def _make_track(**overrides) -> Track:
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


class TestDownloadTypeFilter:
    def test_keeps_only_selected_types(self):
        direct = _make_track(download_type=DownloadType.DIRECT)
        gated = _make_track(download_type=DownloadType.GATED)
        nyp = _make_track(download_type=DownloadType.NAME_YOUR_PRICE)
        f = TrackFilter(download_types=["direct", "name_your_price"])
        kept = f.apply([direct, gated, nyp])
        assert direct in kept and nyp in kept
        assert gated not in kept

    def test_empty_download_types_keeps_all(self):
        tracks = [_make_track(download_type=dt) for dt in DownloadType]
        assert len(TrackFilter(download_types=[]).apply(tracks)) == len(tracks)

    def test_download_types_makes_filter_active(self):
        assert TrackFilter(download_types=["direct"]).is_active


class TestKnownBpmFilter:
    def test_unknown_bpm_kept_by_default(self):
        unknown = _make_track(bpm=None)
        # A BPM bound is set, but exclude_unknown_bpm is False -> keep it.
        f = TrackFilter(bpm_min=120, bpm_max=130)
        assert unknown in f.apply([unknown])

    def test_unknown_bpm_excluded_when_requested(self):
        unknown = _make_track(bpm=None)
        known = _make_track(bpm=125.0)
        f = TrackFilter(bpm_min=120, bpm_max=130, exclude_unknown_bpm=True)
        kept = f.apply([unknown, known])
        assert known in kept and unknown not in kept

    def test_exclude_unknown_bpm_noop_without_bound(self):
        unknown = _make_track(bpm=None)
        # No BPM bound -> exclude_unknown_bpm should not drop anything.
        f = TrackFilter(exclude_unknown_bpm=True)
        assert unknown in f.apply([unknown])

    def test_in_range_bpm_still_kept(self):
        track = _make_track(bpm=125.0)
        f = TrackFilter(bpm_min=120, bpm_max=130, exclude_unknown_bpm=True)
        assert track in f.apply([track])


class TestDurationFilter:
    def test_hides_long_mixes(self):
        song = _make_track(duration_seconds=300.0)
        mix = _make_track(duration_seconds=3600.0)
        f = TrackFilter(max_duration_seconds=570)  # 9:30
        kept = f.apply([song, mix])
        assert song in kept and mix not in kept

    def test_unknown_duration_kept(self):
        track = _make_track(duration_seconds=None)
        f = TrackFilter(max_duration_seconds=570)
        assert track in f.apply([track])
