"""Tests for playlist title parsing and match-week grouping.

Uses real playlist entries (titles only - factual match listings, not
creative/copyrighted content, unlike broadcast commentary transcripts)
pulled from the actual NPL Men's NSW YouTube playlist via yt-dlp, so the
parsing regex is verified against real data rather than titles I made up
to fit my own pattern.
"""
from npl_engine.playlist import group_into_match_weeks, parse_teams_from_title

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
