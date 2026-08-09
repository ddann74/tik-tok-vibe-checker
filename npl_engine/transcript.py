"""YouTube URL validation and transcript retrieval.

No MCP servers (TubePilot / yt-dlp / YouTube Vision) are available in this
environment, so transcripts are fetched directly via youtube-transcript-api
(no API key required). If a transcript can't be fetched — no captions,
network unavailable, video unreachable — this degrades to a deterministic
sample transcript rather than failing the request, and callers are told via
the `source` field. This mirrors the PRD's storage-degradation requirement:
the system must keep working without its optional/unavailable dependencies.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

class InvalidYouTubeURL(ValueError):
    pass


_ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")


def extract_video_id(url: str) -> str:
    if not url or not isinstance(url, str):
        raise InvalidYouTubeURL("URL is required")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _ALLOWED_HOSTS:
        raise InvalidYouTubeURL(f"'{url}' is not a recognizable YouTube video URL")

    candidate: str | None = None
    if parsed.hostname == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.path.startswith("/embed/"):
        candidate = parsed.path[len("/embed/") :].split("/")[0]
    elif parsed.path.startswith("/shorts/"):
        candidate = parsed.path[len("/shorts/") :].split("/")[0]

    if not candidate or not _VIDEO_ID_RE.match(candidate):
        raise InvalidYouTubeURL(f"'{url}' is not a recognizable YouTube video URL")
    return candidate


def timestamped_video_url(video_id: str, start_seconds: float) -> str:
    """Canonical youtube.com/watch URL that jumps to a specific moment,
    regardless of what URL format the video was originally requested with
    (youtu.be, /embed/, /shorts/ all normalize to this)."""
    return f"https://www.youtube.com/watch?v={video_id}&t={max(0, int(start_seconds))}s"


# Deterministic sample transcript used for "Load Sample" and as a fallback
# when live transcript retrieval fails. Mirrors the example in the source
# report (APIA Leichhardt vs Sydney United) but is explicitly marked as
# sample data, never presented as a real broadcast.
SAMPLE_TRANSCRIPT: list[dict] = [
    {"start": 125.0, "text": "Early pressure here from APIA Leichhardt down the left flank."},
    {"start": 754.0, "text": "Payne strikes past the goalkeeper, what a finish into the bottom corner!"},
    {"start": 1290.0, "text": "That's a yellow card shown for the late challenge, goes into the book."},
    {"start": 1875.0, "text": "Sydney United win a penalty awarded after the trip inside the box."},
    {"start": 1920.0, "text": "Garcia steps up to take the penalty and converts the penalty calmly."},
    {"start": 2430.0, "text": "Substitution for APIA, Nguyen comes on for the tiring Payne."},
    {"start": 2865.0, "text": "Careless challenge there, and that's a straight red card, he's sent off!"},
    {"start": 3320.0, "text": "Deflects past his own keeper, an unfortunate own goal to finish the match."},
    {"start": 3600.0, "text": "The referee blows the final whistle, that concludes the match."},
]


def _fetch_live_transcript(video_id: str) -> list[dict] | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        return [{"start": snippet.start, "text": snippet.text} for snippet in fetched]
    except Exception:
        return None


def fetch_transcript(video_id: str) -> tuple[list[dict], str]:
    """Returns (segments, source) where source is "live" or "sample_fallback"."""
    live = _fetch_live_transcript(video_id)
    if live:
        return live, "live"
    return SAMPLE_TRANSCRIPT, "sample_fallback"
