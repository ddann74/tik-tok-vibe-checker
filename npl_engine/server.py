"""FastAPI service implementing the PRD §6.1 API contract.

Endpoints: GET /, GET /health, POST /analyze_match, GET /search_key_moments.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .detection import KeyMoment, detect_key_moments, summarize
from .playlist import DEFAULT_PLAYLIST_URL, fetch_playlist_entries, group_into_match_weeks, load_cache, save_cache
from .storage import StoredMatch, backend_mode, store
from .transcript import InvalidYouTubeURL, extract_video_id, fetch_transcript, timestamped_video_url

app = FastAPI(title="NPL NSW Intelligence Engine", version=__version__)

# CORS: localhost only, per PRD §7. No wildcard origins.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _key_moment_to_dict(m: KeyMoment, video_id: str) -> dict:
    return {
        "timestamp": m.timestamp,
        "event_type": m.event_type,
        "description": m.description,
        "confidence": m.confidence,
        "player": m.player,
        "team": m.team,
        "video_url": timestamped_video_url(video_id, m.start_seconds),
    }


def _seed_sample_match() -> None:
    """Pre-load the sample match so /search_key_moments has data even before
    any real /analyze_match call (mirrors the frontend's "Load Sample")."""
    from .transcript import SAMPLE_TRANSCRIPT

    moments = detect_key_moments(SAMPLE_TRANSCRIPT)
    match_id = hashlib.sha1(b"sample-match", usedforsecurity=False).hexdigest()[:8]
    store.put(
        StoredMatch(
            match_id=match_id,
            youtube_url="https://www.youtube.com/watch?v=sample00001",
            title="NPL NSW Sample Match (APIA Leichhardt vs Sydney United)",
            key_moments=moments,
            source="sample",
            transcript_segments=len(SAMPLE_TRANSCRIPT),
        )
    )


_seed_sample_match()


@app.get("/")
def root():
    return {
        "name": "NPL NSW Intelligence Engine",
        "version": __version__,
        "status": "running",
        "endpoints": ["/health", "/analyze_match", "/search_key_moments", "/match_weeks"],
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
    }


@app.post("/analyze_match")
def analyze_match(url: str = Query(..., description="YouTube match video URL")):
    try:
        video_id = extract_video_id(url)
    except InvalidYouTubeURL as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    segments, source = fetch_transcript(video_id)
    key_moments = detect_key_moments(segments)
    match_id = hashlib.sha1(video_id.encode(), usedforsecurity=False).hexdigest()[:8]
    title = f"NPL NSW Match {match_id}"

    store.put(
        StoredMatch(
            match_id=match_id,
            youtube_url=url,
            title=title,
            key_moments=key_moments,
            source=source,
            transcript_segments=len(segments),
        )
    )

    return {
        "status": "success",
        "match_id": match_id,
        "title": title,
        "youtube_url": url,
        "key_moments_count": len(key_moments),
        "key_moments": [_key_moment_to_dict(m, video_id) for m in key_moments],
        "summary": summarize(key_moments),
        "transcript_segments": len(segments),
        "source": source,
        "storage_backend": backend_mode(),
    }


@app.get("/search_key_moments")
def search_key_moments(q: str = Query(..., min_length=1), top_k: int = Query(10, ge=1, le=100)):
    results = store.search(q, top_k=top_k)
    return {"query": q, "count": len(results), "results": results}


@app.get("/match_weeks")
def match_weeks():
    """Served from a cache built by scripts/refresh_playlist_cache.py, not
    fetched live - see that script's docstring for why. Returns an empty
    weeks list (not an error) if the cache hasn't been generated yet, same
    degrade-gracefully rule as every other optional data source here."""
    cache = load_cache()
    return {
        "generated_at": cache.get("generated_at"),
        "estimated": True,
        "note": "Week numbers are estimated from video upload-date clustering, not the league's official round numbers.",
        "weeks": cache.get("weeks", []),
    }


@app.post("/match_weeks/refresh")
def refresh_match_weeks(playlist_url: str = Query(DEFAULT_PLAYLIST_URL)):
    """Runs the same fetch scripts/refresh_playlist_cache.py does, but
    triggered from the browser instead of the terminal - so refreshing
    just needs the server itself to have real internet + yt-dlp installed
    (true on a normal machine; not true in the sandbox this was built in).
    Returns 502 if the fetch came back empty - no yt-dlp, no network, bad
    playlist URL - rather than silently leaving a stale/empty cache and
    claiming success.
    """
    entries = fetch_playlist_entries(playlist_url)
    if not entries:
        raise HTTPException(
            status_code=502,
            detail=(
                "Fetched 0 playlist entries. Check that yt-dlp is installed "
                "(pip install yt-dlp) and this server has internet access to youtube.com."
            ),
        )
    weeks = group_into_match_weeks(entries)
    save_cache(weeks)
    return {
        "status": "success",
        "entries_fetched": len(entries),
        "weeks": len(weeks),
        "games": sum(len(w.games) for w in weeks),
    }


# Mounted at /ui (not /) because GET / is a JSON API root per PRD §6.1/§5.1;
# the frontend is also just a static file that can be opened directly.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/ui", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
