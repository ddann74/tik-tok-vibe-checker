"""Fetches the NPL Men's NSW YouTube playlist and writes a grouped
match-week cache to disk, so the running app can serve /match_weeks
without hitting YouTube on every request.

This needs real internet access to youtube.com and yt-dlp installed
(`pip install yt-dlp`) - it does NOT work from a sandbox that blocks
outbound YouTube access. Run it on a machine with normal internet, then
either commit data/playlist_cache.json or point PLAYLIST_CACHE_PATH at
wherever you keep it.

By default this is INCREMENTAL: games already in the cache keep their
known date without being re-fetched, and only new games get the slow
per-video fetch. Pass --full to force re-fetching every video's date from
scratch (e.g. if you suspect the cache is corrupted, or a date needs
correcting).

Usage:
    python scripts/refresh_playlist_cache.py
    python scripts/refresh_playlist_cache.py --full
    python scripts/refresh_playlist_cache.py --playlist-url <url>
"""
from __future__ import annotations

import argparse
import sys

from npl_engine.playlist import (
    DEFAULT_PLAYLIST_URL,
    fetch_playlist_entries,
    fetch_playlist_entries_incremental,
    group_into_match_weeks,
    load_cache,
    save_cache,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--playlist-url", default=DEFAULT_PLAYLIST_URL)
    parser.add_argument("--full", action="store_true", help="Re-fetch every video's date, not just new ones.")
    args = parser.parse_args()

    if args.full:
        entries = fetch_playlist_entries(args.playlist_url)
    else:
        existing = load_cache()
        already_known = sum(len(w.get("games", [])) for w in existing.get("weeks", []))
        entries = fetch_playlist_entries_incremental(args.playlist_url, existing_cache=existing)
        print(f"Incremental refresh: {already_known} games already cached, checking for new ones only.")

    if not entries:
        print(
            "Fetched 0 entries. Either yt-dlp isn't installed (pip install yt-dlp), "
            "the playlist URL is wrong, or this machine can't reach YouTube.",
            file=sys.stderr,
        )
        return 1

    undated = sum(1 for e in entries if not e.get("upload_date"))
    weeks = group_into_match_weeks(entries)
    save_cache(weeks)

    total_games = sum(len(w.games) for w in weeks)
    print(f"Fetched {len(entries)} playlist entries ({undated} without a usable upload date, excluded from grouping).")
    print(f"Grouped into {len(weeks)} estimated match weeks, {total_games} games total.")
    print("Cache written. These are DATE-based estimates, not the league's official round numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
