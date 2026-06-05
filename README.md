# 🎧 Free Track Finder

**Find legitimately free DJ tracks across SoundCloud, Bandcamp, and gated platforms — organized with the metadata DJs actually need.**

Free Track Finder scans music platforms for tracks that artists have explicitly made available for free download, and returns organized results with BPM, key, genre, file format, file size, and more. Built by a DJ, for DJs.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

---

## What It Does

- **SoundCloud** — Finds tracks with the official free download button enabled by the artist
- **Bandcamp** — Finds "name your price" releases where the minimum is $0
- **Hypeddit / Toneden** — Detects gated free downloads (social follow/repost gates) and catalogs them
- **Metadata Extraction** — Pulls BPM, musical key (+ Camelot notation), genre, duration, file format, bitrate, and file size
- **DJ-Optimized Filtering** — Filter by BPM range, Camelot key, genre, file format, minimum bitrate
- **Export** — Save results as CSV, JSON, or M3U playlists importable into Serato, rekordbox, Traktor, etc.
- **Playlist Integration** — Export as SoundCloud-compatible playlists or crate-ready file lists

---

## Installation

```bash
# Clone the repo
git clone https://github.com/SubchiBeats/free-track-finder.git
cd free-track-finder

# Install with pip
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

### Requirements

- Python 3.10+
- See `requirements.txt` for dependencies

---

## Quick Start

```bash
# Search for free house tracks on SoundCloud
ftf search "deep house" --platform soundcloud --bpm-min 120 --bpm-max 128

# Find free drum & bass on Bandcamp in WAV format
ftf search "drum and bass" --platform bandcamp --format wav

# Search all platforms, filter by Camelot key for harmonic mixing
ftf search "melodic techno" --key 8A --bpm-min 130 --bpm-max 138

# Export results to CSV for your records
ftf search "tech house" --export csv --output my_tracks.csv

# Export as M3U playlist
ftf search "afro house" --export m3u --output crate.m3u

# Search with multiple genres
ftf search "house" --genre "tech house,deep house,afro house"

# Show detailed track info
ftf search "progressive house" --verbose
```

---

## CLI Reference

### `ftf search <query>`

| Flag | Description | Example |
|------|-------------|---------|
| `--platform` | Platform to search (`soundcloud`, `bandcamp`, `hypeddit`, `all`) | `--platform soundcloud` |
| `--bpm-min` | Minimum BPM | `--bpm-min 120` |
| `--bpm-max` | Maximum BPM | `--bpm-max 128` |
| `--key` | Musical key (standard or Camelot notation) | `--key 8A` or `--key Am` |
| `--genre` | Filter by genre (comma-separated) | `--genre "tech house,minimal"` |
| `--format` | Audio file format | `--format wav` |
| `--min-bitrate` | Minimum bitrate in kbps | `--min-bitrate 320` |
| `--max-results` | Max tracks to return (default: 50) | `--max-results 100` |
| `--sort` | Sort by field (`bpm`, `date`, `popularity`, `title`) | `--sort bpm` |
| `--export` | Export format (`csv`, `json`, `m3u`) | `--export csv` |
| `--output` | Output file path | `--output tracks.csv` |
| `--verbose` | Show all available metadata | `--verbose` |
| `--rate-limit` | Requests per second (default: 2) | `--rate-limit 1` |

### `ftf platforms`

List supported platforms and their current status.

### `ftf export <input> <format>`

Convert a previously saved JSON result to another format.

---

## Output Fields

Every track result includes as much of the following as the platform provides:

| Field | Description | Example |
|-------|-------------|---------|
| Title | Track name | `Midnight Drive` |
| Artist | Artist / uploader | `DJ Smooth` |
| Platform | Source platform | `soundcloud` |
| URL | Link to track page | `https://soundcloud.com/...` |
| Genre | Genre tag(s) | `Tech House` |
| BPM | Beats per minute | `126` |
| Key | Musical key | `Am` |
| Camelot | Camelot wheel notation | `8A` |
| Duration | Track length | `6:32` |
| Format | Audio file type | `WAV` |
| Bitrate | Audio bitrate | `320 kbps` |
| File Size | Download size | `48.2 MB` |
| Download Type | How it's available | `direct` / `gated` / `name_your_price` |
| Released | Release / upload date | `2025-11-15` |
| Plays | Play count | `12,450` |
| Likes | Like / favorite count | `342` |
| Tags | Artist-applied tags | `house, deep, summer` |

---

## Camelot Key Reference

For DJs using harmonic mixing, results include both standard key and Camelot notation:

```
1A  = Ab minor    1B  = B major
2A  = Eb minor    2B  = F# major
3A  = Bb minor    3B  = Db major
4A  = F minor     4B  = Ab major
5A  = C minor     5B  = Eb major
6A  = G minor     6B  = Bb major
7A  = D minor     7B  = F major
8A  = A minor     8B  = C major
9A  = E minor     9B  = G major
10A = B minor     10B = D major
11A = F# minor    11B = A major
12A = Db minor    12B = E major
```

---

## Project Structure

```
free-track-finder/
├── src/freetracks/
│   ├── cli.py              # CLI entry point (Click)
│   ├── core/
│   │   ├── models.py       # Track data model
│   │   ├── filters.py      # BPM, key, genre, format filtering
│   │   └── engine.py       # Search orchestration
│   ├── platforms/
│   │   ├── base.py         # Abstract platform scanner
│   │   ├── soundcloud.py   # SoundCloud free download scanner
│   │   ├── bandcamp.py     # Bandcamp name-your-price scanner
│   │   └── hypeddit.py     # Hypeddit gated download scanner
│   ├── export/
│   │   ├── csv_export.py   # CSV export
│   │   ├── json_export.py  # JSON export
│   │   └── m3u_export.py   # M3U playlist export
│   └── utils/
│       ├── rate_limiter.py  # Respectful rate limiting
│       ├── keys.py          # Musical key / Camelot utilities
│       └── formatting.py    # Duration, file size formatting
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Adding a New Platform

Free Track Finder is designed to be extensible. To add a new platform:

```python
from freetracks.platforms.base import PlatformScanner
from freetracks.core.models import Track

class MyPlatformScanner(PlatformScanner):
    platform_name = "myplatform"

    async def search(self, query: str, max_results: int = 50) -> list[Track]:
        # Your scraping / API logic here
        ...

    async def get_track_details(self, track_url: str) -> Track | None:
        # Fetch full metadata for a single track
        ...
```

Then register it in `src/freetracks/platforms/__init__.py`.

---

## Ethics & Legal

This tool **only** finds tracks that artists have explicitly made available for free:

- ✅ SoundCloud tracks with the download button enabled by the uploader
- ✅ Bandcamp releases set to "name your price" with a $0 minimum
- ✅ Tracks offered through promotional gated downloads (Hypeddit, Toneden)
- ❌ Does **not** rip, convert, or circumvent any download restrictions
- ❌ Does **not** download streams or bypass paywalls

All requests respect platform rate limits and `robots.txt`. This is a discovery tool — it helps you find what artists are already giving away.

---

## Roadmap

- [ ] Spotify metadata cross-reference (match BPM/key from Spotify for tracks found elsewhere)
- [ ] Rekordbox XML export for direct crate import
- [ ] Web UI dashboard
- [ ] Scheduled searches with notifications for new free releases
- [ ] Artist follow list — auto-scan favorite artists for new free drops
- [ ] Audio preview playback in terminal (via `mpv` / `ffplay`)
- [ ] Duplicate detection across platforms

---

## Contributing

PRs welcome. If you DJ and code, this is the project for you.

1. Fork the repo
2. Create a feature branch
3. Add tests for new functionality
4. Submit a PR

---

## License

MIT — free as the tracks you'll find with it.
