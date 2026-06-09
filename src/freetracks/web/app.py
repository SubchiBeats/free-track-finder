"""FastAPI application — JSON API over the SearchEngine + static frontend host.

Endpoints
    GET  /api/platforms              list supported platforms + capabilities
    POST /api/search                 run a multi-platform search with filters
    GET  /api/track                  fetch full details for a single track URL
    GET  /api/keys/compatible        Camelot-compatible keys for the wheel
    GET  /api/stream                 resolve a SoundCloud preview to a playable URL
    POST /api/export                 render a crate as csv/json/m3u (file download)
    GET  /                           the vanilla HTML/CSS/JS frontend

The API and frontend share one origin (localhost), so no CORS config is needed
for normal use. A permissive CORS policy is enabled anyway to ease development
(e.g. opening the frontend from a different port).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from freetracks.core.engine import SearchEngine
from freetracks.core.filters import TrackFilter
from freetracks.core.models import SearchResults
from freetracks.export import export_csv_string, export_json_string, export_m3u_string
from freetracks.platforms import PLATFORM_NAMES
from freetracks.platforms.soundcloud import SoundCloudScanner
from freetracks.utils.keys import get_compatible_keys
from freetracks.web.schemas import ExportRequest, SearchRequest

logger = logging.getLogger(__name__)

# Project root holds the frontend/ directory (src/freetracks/web/app.py -> root).
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

app = FastAPI(
    title="Free Track Finder",
    description="Find legitimately free DJ tracks across SoundCloud, Bandcamp, and Hypeddit.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_PLATFORM_INFO = {
    "soundcloud": {
        "name": "SoundCloud",
        "download_type": "Direct / free-download link",
        "metadata": "BPM, key, genre, tags, plays, likes, preview",
        "notes": "Tracks with a download button or a free-download link enabled.",
    },
    "bandcamp": {
        "name": "Bandcamp",
        "download_type": "Name your price ($0)",
        "metadata": "Genre, tags, duration, release date, preview",
        "notes": (
            "Multi-format choice on download (MP3/FLAC/WAV). "
            "Free tracks are sparse, so searches can take longer."
        ),
    },
    "hypeddit": {
        "name": "Hypeddit",
        "download_type": "Gated (social action)",
        "metadata": "Title, artist, artwork, preview (via SoundCloud)",
        "notes": "Requires follow/repost/subscribe to download. Browse is genre-based.",
    },
}


@app.get("/api/platforms")
async def platforms() -> JSONResponse:
    """List supported platforms and their capabilities."""
    return JSONResponse(
        [{"id": p, **_PLATFORM_INFO.get(p, {})} for p in PLATFORM_NAMES]
    )


@app.post("/api/search")
async def search(req: SearchRequest) -> JSONResponse:
    """Run a multi-platform search with filtering and sorting."""
    track_filter = TrackFilter(
        bpm_min=req.bpm_min,
        bpm_max=req.bpm_max,
        key=req.key,
        genres=req.genres,
        formats=req.to_audio_formats(),
        min_bitrate_kbps=req.min_bitrate_kbps,
        quality_tiers=req.quality_tiers,
        exclude_gated=req.exclude_gated,
        download_types=req.download_types,
        exclude_unknown_bpm=req.exclude_unknown_bpm,
        max_duration_seconds=req.max_duration_seconds,
        min_duration_seconds=req.min_duration_seconds,
    )

    engine = SearchEngine()
    try:
        results = await engine.search(
            query=req.query,
            platforms=req.platforms,
            track_filter=track_filter,
            sort_by=req.sort_by,
            sort_reverse=req.sort_reverse,
            max_results=req.max_results,
        )
    except Exception as e:  # noqa: BLE001 - surface any engine failure cleanly
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}") from e

    return JSONResponse(results.model_dump(mode="json"))


@app.get("/api/track")
async def track_details(
    url: str = Query(..., description="Track page URL"),
    platform: str | None = Query(None),
) -> JSONResponse:
    """Fetch full metadata for a single track URL."""
    engine = SearchEngine()
    track = await engine.get_track_details(url, platform=platform)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found or not a free download.")
    return JSONResponse(track.model_dump(mode="json"))


@app.get("/api/keys/compatible")
async def compatible_keys(
    key: str = Query(..., description="Standard or Camelot key"),
) -> JSONResponse:
    """Return harmonically compatible Camelot keys for the wheel."""
    return JSONResponse({"key": key, "compatible": get_compatible_keys(key)})


@app.get("/api/stream")
async def stream(
    url: str = Query(..., description="SoundCloud progressive transcoding URL"),
) -> JSONResponse:
    """Resolve a SoundCloud preview transcoding URL into a playable media URL.

    SoundCloud preview URLs are ``api-v2`` transcoding endpoints that must be
    called with a client_id; they return ``{"url": "<cdn mp3>"}``. Bandcamp
    preview URLs are already directly playable and don't need this endpoint.
    """
    if "soundcloud.com" not in url:
        # Already a direct media URL (e.g. Bandcamp) — nothing to resolve.
        return JSONResponse({"url": url})

    scanner = SoundCloudScanner()
    try:
        client_id = await scanner._resolve_client_id()
        client = await scanner._get_client()
        resp = await client.get(url, params={"client_id": client_id})
        resp.raise_for_status()
        media_url = resp.json().get("url")
        if not media_url:
            raise HTTPException(status_code=502, detail="No playable URL returned by SoundCloud.")
        return JSONResponse({"url": media_url})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not resolve stream: {e}") from e
    finally:
        await scanner.close()


@app.get("/api/audio")
async def audio_proxy(url: str = Query(..., description="Preview/stream URL to proxy")):
    """Stream a remote preview through our origin so the browser can analyse it.

    Cross-origin audio can be *played* but not *read* (Web Audio BPM analysis
    needs the raw bytes, which CORS blocks). Proxying via localhost makes the
    bytes same-origin. SoundCloud transcodings are resolved first.
    """
    from fastapi.responses import StreamingResponse

    media_url = url
    scanner = None
    if "soundcloud.com" in url and "/media/" in url:
        scanner = SoundCloudScanner()
        try:
            client_id = await scanner._resolve_client_id()
            client = await scanner._get_client()
            resp = await client.get(url, params={"client_id": client_id})
            resp.raise_for_status()
            media_url = resp.json().get("url", url)
        except Exception as e:  # noqa: BLE001
            if scanner:
                await scanner.close()
            raise HTTPException(status_code=502, detail=f"Could not resolve stream: {e}") from e

    try:
        upstream = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        r = await upstream.get(media_url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        await upstream.aclose()
        raise HTTPException(status_code=502, detail=f"Audio fetch failed: {e}") from e

    async def _iter():
        try:
            yield r.content
        finally:
            await upstream.aclose()
            if scanner:
                await scanner.close()

    return StreamingResponse(_iter(), media_type=r.headers.get("content-type", "audio/mpeg"))


_EXPORT_MEDIA = {
    "csv": ("text/csv", "ftf_crate.csv"),
    "json": ("application/json", "ftf_crate.json"),
    "m3u": ("audio/x-mpegurl", "ftf_crate.m3u8"),
}


@app.post("/api/export")
async def export(req: ExportRequest) -> Response:
    """Render a list of tracks (a crate) as a downloadable csv/json/m3u file."""
    try:
        results = SearchResults.model_validate({"query": req.query, "tracks": req.tracks})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid tracks: {e}") from e

    if req.format == "csv":
        body = export_csv_string(results, verbose=True)
    elif req.format == "json":
        body = export_json_string(results)
    else:
        body = export_m3u_string(results)

    media_type, filename = _EXPORT_MEDIA[req.format]
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# ---- Audio format converter (ffmpeg) ----

_CONVERT_FORMATS = {
    # target -> (file extension, extra ffmpeg args)
    "mp3": ("mp3", ["-codec:a", "libmp3lame", "-b:a", "320k"]),
    "wav": ("wav", ["-codec:a", "pcm_s16le"]),
    "flac": ("flac", ["-codec:a", "flac"]),
    "aiff": ("aiff", ["-codec:a", "pcm_s16be"]),
}
_CONVERT_MEDIA = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "aiff": "audio/aiff",
}
_MAX_UPLOAD_BYTES = 80 * 1024 * 1024  # 80 MB


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


@app.get("/api/convert/available")
async def convert_available() -> dict:
    """Report whether ffmpeg is installed (drives the converter UI state)."""
    return {
        "available": _ffmpeg_path() is not None,
        "formats": list(_CONVERT_FORMATS.keys()),
    }


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    target: str = Form(...),
) -> Response:
    """Convert an uploaded audio file to a target format via ffmpeg."""
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        raise HTTPException(
            status_code=503,
            detail="ffmpeg is not installed on the server. Install it (e.g. "
            "'winget install ffmpeg' on Windows) and restart, then try again.",
        )
    target = target.lower().strip()
    if target not in _CONVERT_FORMATS:
        raise HTTPException(status_code=422, detail=f"Unsupported target format '{target}'.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 80 MB).")

    ext, extra_args = _CONVERT_FORMATS[target]
    src_suffix = Path(file.filename or "audio").suffix or ".bin"
    stem = Path(file.filename or "audio").stem or "audio"

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{src_suffix}"
        dst = Path(tmp) / f"out.{ext}"
        src.write_bytes(data)

        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-i", str(src), *extra_args, str(dst),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="Conversion timed out.") from None

        if proc.returncode != 0 or not dst.exists():
            msg = (stderr or b"").decode(errors="replace")[-300:]
            raise HTTPException(status_code=422, detail=f"Conversion failed: {msg}")

        out = dst.read_bytes()

    return Response(
        content=out,
        media_type=_CONVERT_MEDIA[target],
        headers={"Content-Disposition": f'attachment; filename="{stem}.{ext}"'},
    )


# Mount the static frontend LAST so /api routes take precedence. html=True
# serves index.html at "/" and falls back to it for client-side routing.
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
else:  # pragma: no cover - only hit if frontend dir is missing
    logger.warning("Frontend directory not found at %s", _FRONTEND_DIR)
