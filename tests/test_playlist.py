"""Tests for playlist title parsing and match-week grouping.

Uses real playlist entries (titles only - factual match listings, not
creative/copyrighted content, unlike broadcast commentary transcripts)
pulled from the actual NPL Men's NSW YouTube playlist via yt-dlp, so the
parsing regex is verified against real data rather than titles I made up
to fit my own pattern.
"""
from npl_engine.playlist import build_match_report_search_url, group_into_match_weeks, parse_teams_from_title

# Real titles from https://www.youtube.com/playlist?list=PLxa2AB3-xOrvP2TRh6y2ZkoT1CZhZlI9_
REAL_TITLES = [
    "NPL Men's NSW - St George City FA v Rockdale Ilinden FC",
    "NPL Men's NSW - St George FC v APIA Leichhardt FC",
    "NPL Men's NSW - NWS Spirit FC v Blacktown City FC",
    "NPL Men's NSW - Sutherland Sharks FC v Sydney FC",
    "NPL Men's NSW - SD Raiders FC v Western Sydney Wanderers FC",
    "NPL Men's NSW - Manly United FC v Marconi Stallions FC",
    "NPL Men's NSW - UNSW FC v Sydney Olympic FC",
    "NPL Men's NSW - Wollongong Wolves FC v Sydney United 58 FC",
    "NPL Men's NSW - Sydney Olympic FC v APIA Leichhardt FC",
    "NPL Men's NSW - Marconi Stallions FC v St George City FA",
    "NPL Men's NSW - Blacktown City FC v Sydney FC",
    "NPL Men's NSW - Sydney United 58 FC v NWS Spirit FC",
    "NPL Men's NSW - Rockdale Ilinden FC v Manly United FC",
    "NPL Men's NSW - St George FC v SD Raiders FC",
    "NPL Men's NSW - Sutherland Sharks FC v Wollongong Wolves FC",
]


def test_parses_all_real_titles():
    for title in REAL_TITLES:
        home, away = parse_teams_from_title(title)
        assert home, f"failed to parse home team from: {title}"
        assert away, f"failed to parse away team from: {title}"
        assert home != away


def test_parses_specific_known_matchup():
    home, away = parse_teams_from_title(REAL_TITLES[0])
    assert home == "St George City FA"
    assert away == "Rockdale Ilinden FC"


def test_unparseable_title_returns_none_none_not_a_guess():
    # A finals special / highlight reel title that doesn't fit the
    # "NPL Men's NSW - X v Y" pattern must not be force-parsed into
    # nonsense team names.
    assert parse_teams_from_title("NPL NSW Grand Final Highlights 2026") == (None, None)
    assert parse_teams_from_title("") == (None, None)


def test_group_into_match_weeks_clusters_by_date_gap():
    entries = [
        {"title": REAL_TITLES[0], "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "upload_date": "2026-05-01"},
        {"title": REAL_TITLES[1], "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "upload_date": "2026-05-02"},
        {"title": REAL_TITLES[2], "url": "https://www.youtube.com/watch?v=ccccccccccc", "upload_date": "2026-05-03"},
        # >3 day gap - new week
        {"title": REAL_TITLES[3], "url": "https://www.youtube.com/watch?v=ddddddddddd", "upload_date": "2026-05-08"},
        {"title": REAL_TITLES[4], "url": "https://www.youtube.com/watch?v=eeeeeeeeeee", "upload_date": "2026-05-09"},
    ]
    weeks = group_into_match_weeks(entries)
    assert len(weeks) == 2
    assert len(weeks[0].games) == 3
    assert len(weeks[1].games) == 2
    assert all(w.estimated is True for w in weeks)
    assert weeks[0].week_number == 1
    assert weeks[1].week_number == 2
    # games carry through their parsed team names
    assert weeks[0].games[0].home_team == "St George City FA"
    # and a working match-report search link, per-game
    assert weeks[0].games[0].match_report_search_url.startswith("https://www.google.com/search?q=")
    assert "St+George+City+FA" in weeks[0].games[0].match_report_search_url


def test_build_match_report_search_url_is_a_real_search_link_not_a_guessed_article():
    # NPL NSW match reports are round-review blog posts with unpredictable
    # slug suffixes (confirmed by checking real published URLs) - there is
    # no way to construct the exact article URL from team names/date, so
    # this must be a search link (always resolves), never a fabricated
    # direct link that might 404.
    url = build_match_report_search_url("St George City FA", "Rockdale Ilinden FC", "2026-05-01")
    assert url.startswith("https://www.google.com/search?q=")
    assert "St+George+City+FA" in url
    assert "Rockdale+Ilinden+FC" in url
    assert "NPL+NSW" in url
    assert "2026" in url


def test_build_match_report_search_url_falls_back_without_team_names():
    url = build_match_report_search_url(None, None, None)
    assert url.startswith("https://www.google.com/search?q=")
    assert "NPL+NSW+match+report" in url


def test_group_into_match_weeks_drops_undated_entries_rather_than_guessing():
    entries = [
        {"title": REAL_TITLES[0], "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "upload_date": "2026-05-01"},
        {"title": REAL_TITLES[1], "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "upload_date": None},
    ]
    weeks = group_into_match_weeks(entries)
    total_games = sum(len(w.games) for w in weeks)
    assert total_games == 1


def test_group_into_match_weeks_empty_input():
    assert group_into_match_weeks([]) == []


def test_fetch_playlist_entries_degrades_to_empty_list_without_yt_dlp(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("simulated: yt-dlp not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    from npl_engine.playlist import fetch_playlist_entries

    assert fetch_playlist_entries("https://www.youtube.com/playlist?list=whatever") == []


def test_entries_from_cache_flattens_weeks_back_into_entries():
    from npl_engine.playlist import _entries_from_cache

    cache = {
        "weeks": [
            {
                "week_number": 1,
                "games": [
                    {"title": REAL_TITLES[0], "video_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "upload_date": "2026-05-01"},
                    {"title": REAL_TITLES[1], "video_url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "upload_date": "2026-05-02"},
                ],
            }
        ]
    }
    entries = _entries_from_cache(cache)
    assert entries == [
        {"title": REAL_TITLES[0], "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "upload_date": "2026-05-01"},
        {"title": REAL_TITLES[1], "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "upload_date": "2026-05-02"},
    ]


def test_entries_from_cache_empty_when_no_weeks():
    from npl_engine.playlist import _entries_from_cache

    assert _entries_from_cache({"weeks": []}) == []
    assert _entries_from_cache({}) == []


def test_fetch_playlist_entries_incremental_only_fetches_dates_for_new_videos(monkeypatch):
    import npl_engine.playlist as playlist_module

    known_url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    new_url = "https://www.youtube.com/watch?v=zzzzzzzzzzz"

    existing_cache = {
        "weeks": [
            {
                "week_number": 1,
                "games": [{"title": REAL_TITLES[0], "video_url": known_url, "upload_date": "2026-05-01"}],
            }
        ]
    }

    monkeypatch.setattr(
        playlist_module,
        "fetch_playlist_flat",
        lambda playlist_url: [
            {"video_id": "aaaaaaaaaaa", "title": REAL_TITLES[0], "url": known_url},
            {"video_id": "zzzzzzzzzzz", "title": REAL_TITLES[1], "url": new_url},
        ],
    )

    fetch_video_dates_calls = []

    def fake_fetch_video_dates(urls):
        fetch_video_dates_calls.append(list(urls))
        return {new_url: "2026-06-01"}

    monkeypatch.setattr(playlist_module, "fetch_video_dates", fake_fetch_video_dates)

    entries = playlist_module.fetch_playlist_entries_incremental("whatever", existing_cache=existing_cache)

    # Only the new video's URL should have been sent for date-fetching -
    # the known one keeps its cached date without a redundant slow fetch.
    assert fetch_video_dates_calls == [[new_url]]
    entries_by_url = {e["url"]: e for e in entries}
    assert entries_by_url[known_url]["upload_date"] == "2026-05-01"
    assert entries_by_url[new_url]["upload_date"] == "2026-06-01"
    assert len(entries) == 2


def test_fetch_playlist_entries_incremental_empty_cache_fetches_everything(monkeypatch):
    import npl_engine.playlist as playlist_module

    url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    monkeypatch.setattr(
        playlist_module,
        "fetch_playlist_flat",
        lambda playlist_url: [{"video_id": "aaaaaaaaaaa", "title": REAL_TITLES[0], "url": url}],
    )
    monkeypatch.setattr(playlist_module, "fetch_video_dates", lambda urls: {url: "2026-05-01"})

    entries = playlist_module.fetch_playlist_entries_incremental("whatever", existing_cache={"weeks": []})
    assert len(entries) == 1
    assert entries[0]["upload_date"] == "2026-05-01"


def test_fetch_playlist_entries_incremental_returns_empty_when_flat_listing_fails(monkeypatch):
    import npl_engine.playlist as playlist_module

    monkeypatch.setattr(playlist_module, "fetch_playlist_flat", lambda playlist_url: [])
    entries = playlist_module.fetch_playlist_entries_incremental("whatever", existing_cache={"weeks": []})
    assert entries == []
