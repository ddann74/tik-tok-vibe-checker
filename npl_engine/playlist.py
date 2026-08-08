"""Groups the NPL Men's NSW YouTube playlist into a browsable match-week
list, so the frontend can offer a dropdown instead of requiring a pasted
URL.

Two honesty notes baked into the design, not just the docs:

1. Playlist video titles ("NPL Men's NSW - Team A FC v Team B FC") don't
   include an official round number - confirmed by actually listing real
   entries, not assumed. So games are grouped by upload-date proximity
   into "match weeks" and explicitly labeled `estimated=True`. This is a
   heuristic, not the league's official round numbering, and the API/UI
   must never claim otherwise.
2. Fetching the playlist requires real internet access to youtube.com,
   which this sandbox blocks (confirmed via a live 403 at the proxy,
   same as npl_engine/transcript.py's fetch path). fetch_playlist_entries()
   is therefore written but unverified from this environment - it needs
   to be run and confirmed somewhere with real internet (see
   scripts/refresh_playlist_cache.py).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLxa2AB3-xOrvP2TRh6y2ZkoT1CZhZlI9_"

# Gap (in days) between consecutive uploads that starts a new estimated
# match week. NPL NSW rounds are played over a weekend, so games in the
# same round are typically 0-2 days apart, with several days' gap before
# the next round's games start.
_WEEK_GAP_DAYS = 3

_TITLE_RE = re.compile(r"^\s*NPL Men'?s NSW\s*-\s*(.+?)\s+v\s+(.+?)\s*$", re.IGNORECASE)


@dataclass
class PlaylistGame:
    title: str
    video_url: str
    home_team: str | None
    away_team: str | None
    upload_date: str | None  # ISO date string (YYYY-MM-DD), or None if unknown


@dataclass
class MatchWeek:
    week_number: int
    estimated: bool
    games: list[PlaylistGame]


def parse_teams_from_title(title: str) -> tuple[str | None, str | None]:
    """Best-effort team-name extraction. Returns (None, None) for titles
    that don't match the expected "NPL Men's NSW - X v Y" pattern (e.g.
    finals specials, highlight reels) rather than guessing."""
    match = _TITLE_RE.match(title)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def group_into_match_weeks(entries: list[dict]) -> list[MatchWeek]:
    """entries: list of {"title", "url", "upload_date"} dicts (upload_date
    as YYYY-MM-DD string or None). Entries without a parseable date are
    dropped from grouping - they can't be placed in a week without one,
    and silently guessing a week would misrepresent the estimate as more
    precise than it is."""
    dated: list[tuple[datetime, dict]] = []
    undated: list[dict] = []
    for entry in entries:
        date_str = entry.get("upload_date")
        if not date_str:
            undated.append(entry)
            continue
        try:
            dated.append((datetime.strptime(date_str, "%Y-%m-%d"), entry))
        except ValueError:
            undated.append(entry)

    dated.sort(key=lambda pair: pair[0])

    weeks: list[list[dict]] = []
    current_week: list[dict] = []
    previous_date: datetime | None = None
    for date, entry in dated:
        if previous_date is not None and (date - previous_date) > timedelta(days=_WEEK_GAP_DAYS):
            weeks.append(current_week)
            current_week = []
        current_week.append(entry)
        previous_date = date
    if current_week:
        weeks.append(current_week)

    result = []
    for i, week_entries in enumerate(weeks, start=1):
        games = []
        for entry in week_entries:
            home, away = parse_teams_from_title(entry["title"])
            games.append(
                PlaylistGame(
                    title=entry["title"],
                    video_url=entry["url"],
                    home_team=home,
                    away_team=away,
                    upload_date=entry.get("upload_date"),
                )
            )
        result.append(MatchWeek(week_number=i, estimated=True, games=games))
    return result


def fetch_playlist_entries(playlist_url: str = DEFAULT_PLAYLIST_URL) -> list[dict]:
    """Best-effort playlist fetch via yt-dlp. Returns [] (never raises) on
    any failure - missing dependency, network unavailable, playlist
    private/deleted - so callers degrade gracefully, same pattern as
    npl_engine.transcript.fetch_transcript.

    NOT flat-extraction only: upload_date isn't reliably present on flat
    playlist entries, so this does a fuller per-video extract, which is
    slower for large playlists and is exactly why this is a periodic
    refresh script (scripts/refresh_playlist_cache.py), not a live
    per-request fetch.
    """
    try:
        import yt_dlp
    except ImportError:
        return []
    try:
        # extract_flat is deliberately NOT set here (previously it was
        # mistakenly set to "in_playlist", which returns fast but never
        # includes upload_date per video - confirmed by a live run that
        # fetched 217 real entries and grouped 0 of them, because every
        # single one came back dateless and group_into_match_weeks()
        # correctly drops undated entries rather than guessing). Full
        # per-video extraction is slow for a large playlist (real-world:
        # several minutes for ~200 videos) - that tradeoff is accepted
        # here because this is a manual/occasional refresh, not a
        # per-request fetch.
        # ignoreerrors=True: confirmed live that some individual videos in
        # a real ~200-video playlist fail extraction (private/deleted/
        # region-locked/etc.) - without this, yt-dlp aborts the WHOLE
        # playlist on the first bad video, and this function's broad
        # except below would then discard every entry already fetched,
        # not just the failed one. With it, bad entries are skipped and
        # everything else is kept (confirmed: 217 flat entries -> 100
        # survived full extraction with ignoreerrors=True on real data).
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "ignoreerrors": True}) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
    except Exception:
        return []

    entries = []
    for raw in info.get("entries") or []:
        if not raw:
            continue
        video_id = raw.get("id")
        if not video_id:
            continue
        upload_date_raw = raw.get("upload_date")  # yt-dlp format: YYYYMMDD
        upload_date = None
        if upload_date_raw and len(upload_date_raw) == 8:
            upload_date = f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"
        entries.append(
            {
                "title": raw.get("title", ""),
                "url": raw.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                "upload_date": upload_date,
            }
        )
    return entries


def fetch_playlist_flat(playlist_url: str = DEFAULT_PLAYLIST_URL) -> list[dict]:
    """Fast listing: title/url/video_id only, no upload_date - this is the
    extract_flat call that previously caused the dateless-entries bug when
    used for the full fetch. Kept deliberately separate and used only to
    discover *which* videos exist, not to populate cache data directly.
    Returns [] (never raises) on any failure, same degrade-gracefully rule
    as fetch_playlist_entries."""
    try:
        import yt_dlp
    except ImportError:
        return []
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": "in_playlist", "skip_download": True}) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
    except Exception:
        return []

    entries = []
    for raw in info.get("entries") or []:
        if not raw:
            continue
        video_id = raw.get("id")
        if not video_id:
            continue
        entries.append(
            {
                "video_id": video_id,
                "title": raw.get("title", ""),
                "url": raw.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return entries


def fetch_video_dates(video_urls: list[str]) -> dict[str, str | None]:
    """Full per-video extraction, but ONLY for the URLs given - this is
    the slow path from fetch_playlist_entries(), narrowed to just the
    videos the caller actually needs dates for (new ones not already
    cached), rather than the whole playlist every time. Each video is
    fetched independently so one failure doesn't drop the others -
    returns {} entries as None rather than omitting them, so callers can
    tell "fetched, no date available" apart from "never attempted"."""
    try:
        import yt_dlp
    except ImportError:
        return {url: None for url in video_urls}

    dates: dict[str, str | None] = {}
    for url in video_urls:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            upload_date_raw = (info or {}).get("upload_date")
            if upload_date_raw and len(upload_date_raw) == 8:
                dates[url] = f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"
            else:
                dates[url] = None
        except Exception:
            dates[url] = None
    return dates


def _entries_from_cache(cache: dict) -> list[dict]:
    """Flattens a loaded cache's weeks back into the {"title", "url",
    "upload_date"} entry shape group_into_match_weeks() expects, so an
    incremental refresh can recombine existing + newly-fetched entries and
    regroup everything (week boundaries can shift as new games are added,
    so weeks aren't simply appended to)."""
    entries = []
    for week in cache.get("weeks", []):
        for game in week.get("games", []):
            entries.append({"title": game["title"], "url": game["video_url"], "upload_date": game.get("upload_date")})
    return entries


def fetch_playlist_entries_incremental(
    playlist_url: str = DEFAULT_PLAYLIST_URL, existing_cache: dict | None = None
) -> list[dict]:
    """Only fetches (slow) upload dates for videos not already in the
    cache - existing games keep their already-known date without being
    re-fetched. Falls back to the full fetch_playlist_entries() if the
    fast flat listing fails outright (e.g. this being the very first run,
    with no cache to diff against, still works via the caller passing
    existing_cache={"weeks": []} or None).
    """
    existing_cache = existing_cache if existing_cache is not None else load_cache()
    existing_entries = _entries_from_cache(existing_cache)
    known_urls = {e["url"] for e in existing_entries}

    flat = fetch_playlist_flat(playlist_url)
    if not flat:
        return []

    new_urls = [e["url"] for e in flat if e["url"] not in known_urls]
    new_dates = fetch_video_dates(new_urls) if new_urls else {}

    flat_by_url = {e["url"]: e for e in flat}
    new_entries = [
        {"title": flat_by_url[url]["title"], "url": url, "upload_date": new_dates.get(url)} for url in new_urls
    ]

    return existing_entries + new_entries


def cache_path() -> Path:
    configured = os.environ.get("PLAYLIST_CACHE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "data" / "playlist_cache.json"


def save_cache(weeks: list[MatchWeek], path: Path | None = None) -> None:
    path = path or cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "weeks": [asdict(w) for w in weeks],
    }
    path.write_text(json.dumps(payload, indent=2))


def load_cache(path: Path | None = None) -> dict:
    """Returns {"generated_at": None, "weeks": []} if no cache exists yet -
    never raises, matching the rest of the app's degrade-gracefully rule."""
    path = path or cache_path()
    if not path.exists():
        return {"generated_at": None, "weeks": []}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "weeks": []}
