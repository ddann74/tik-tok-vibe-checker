"""Fetches the NPL Men's NSW YouTube playlist and writes a grouped
match-week cache to disk, so the running app can serve /match_weeks
without hitting YouTube on every request.

This needs real internet access to youtube.com and yt-dlp installed
(`pip install yt-dlp`) - it does NOT work from a sandbox that blocks
outbound YouTube access. Run it on a machine with normal internet, then
either commit data/playlist_cache.json or point PLAYLIST_CACHE_PATH at
wherever you keep it.

Usage:
    python scripts/refresh_playlist_cache.py
    python scripts/refresh_playlist_cache.py --playlist-url <url>
"""
from __future__ import annotations

import argparse
import sys

from npl_engine.playlist import DEFAULT_PLAYLIST_URL, fetch_playlist_entries, group_into_match_weeks, save_cache


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--playlist-url", default=DEFAULT_PLAYLIST_URL)
    args = parser.parse_args()

    entries = fetch_playlist_entries(args.playlist_url)
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
