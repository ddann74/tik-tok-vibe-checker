"""Tests for match-report calibration.

Uses synthetic segments/moments written for this test (not real broadcast
commentary) - the kickoff-detection regex itself was separately validated
against a real match transcript during development (see PRD_v2.md /
README), but that transcript isn't checked in here (copyrighted).
"""
from npl_engine.calibration import (
    MatchReportEvent,
    calibrate,
    detect_halftime_seconds,
    detect_kickoff_seconds,
    estimate_match_minute,
)
from npl_engine.detection import KeyMoment


def test_detect_kickoff_seconds_finds_common_phrasing():
    segments = [
        {"start": 0.0, "text": "Welcome along to today's coverage."},
        {"start": 120.0, "text": "We're away for kickoff here at the ground."},
        {"start": 300.0, "text": "Some other commentary."},
    ]
    assert detect_kickoff_seconds(segments) == 120.0


def test_detect_kickoff_seconds_returns_none_not_a_guess():
    segments = [{"start": 0.0, "text": "No relevant phrasing here at all."}]
    assert detect_kickoff_seconds(segments) is None


def test_detect_halftime_seconds():
    segments = [
        {"start": 0.0, "text": "Kick off."},
        {"start": 2700.0, "text": "That's halftime here, nil-nil."},
    ]
    assert detect_halftime_seconds(segments) == 2700.0


def test_estimate_match_minute_relative_to_kickoff():
    # kickoff at 120s, event at 120 + 10*60 = 720s -> minute 10
    assert estimate_match_minute(720.0, 120.0) == 10


def test_estimate_match_minute_none_without_kickoff():
    assert estimate_match_minute(720.0, None) is None


def test_estimate_match_minute_none_before_kickoff():
    # pre-match chatter timestamped before the detected kickoff
    assert estimate_match_minute(50.0, 120.0) is None


def _moment(event_type: str, start_seconds: float, description="x", team=None) -> KeyMoment:
    return KeyMoment(
        timestamp="0:00",
        event_type=event_type,
        description=description,
        confidence=0.8,
        start_seconds=start_seconds,
        team=team,
    )


def test_calibrate_matches_by_type_and_minute_within_tolerance():
    kickoff = 0.0
    moments = [_moment("goal", 74 * 60, "scores")]
    report = [MatchReportEvent(event_type="goal", minute=75)]
    result = calibrate(moments, report, kickoff, minute_tolerance=5)
    assert len(result.matched) == 1
    assert result.matched[0]["video_estimated_minute"] == 74
    assert result.matched[0]["corrected_to_report_minute"] is True
    assert result.corrected_timestamps == 1
    assert result.missed_in_video == []
    assert result.unconfirmed_in_report == []


def test_calibrate_reports_missed_event_not_found_in_video():
    moments = [_moment("goal", 10 * 60)]
    report = [MatchReportEvent(event_type="red_card", minute=80)]
    result = calibrate(moments, report, kickoff_seconds=0.0)
    assert result.matched == []
    assert len(result.missed_in_video) == 1
    assert len(result.unconfirmed_in_report) == 1


def test_calibrate_falls_back_to_half_only_matching_without_precise_minute():
    kickoff = 0.0
    moments = [_moment("penalty", 74 * 60)]
    report = [MatchReportEvent(event_type="penalty", half=2)]
    result = calibrate(moments, report, kickoff)
    assert len(result.matched) == 1
    assert result.matched[0]["report_minute"] is None
    assert result.corrected_timestamps == 0, "no precise report minute means nothing to correct to"


def test_calibrate_does_not_match_wrong_half():
    kickoff = 0.0
    moments = [_moment("penalty", 10 * 60)]  # first-half timing
    report = [MatchReportEvent(event_type="penalty", half=2)]
    result = calibrate(moments, report, kickoff)
    assert result.matched == []
    assert len(result.missed_in_video) == 1


def test_calibrate_without_kickoff_falls_back_to_type_only_when_report_has_no_timing():
    moments = [_moment("yellow_card", 500.0)]
    report = [MatchReportEvent(event_type="yellow_card")]  # no minute, no half
    result = calibrate(moments, report, kickoff_seconds=None)
    assert len(result.matched) == 1
    assert result.matched[0]["video_estimated_minute"] is None


def test_calibrate_skips_candidate_when_teams_disagree():
    # Same event type, same half, would match on timing alone - but the
    # video moment is tagged for the other team, so it must not be matched
    # to this report event (and the report event should end up "missed").
    kickoff = 0.0
    moments = [_moment("goal", 10 * 60, team="Home FC")]
    report = [MatchReportEvent(event_type="goal", minute=10, team="Away FC")]
    result = calibrate(moments, report, kickoff)
    assert result.matched == []
    assert len(result.missed_in_video) == 1
    assert len(result.unconfirmed_in_report) == 1


def test_calibrate_matches_and_marks_team_verified_when_teams_agree():
    kickoff = 0.0
    moments = [_moment("goal", 10 * 60, team="Home FC")]
    report = [MatchReportEvent(event_type="goal", minute=10, team="Home FC")]
    result = calibrate(moments, report, kickoff)
    assert len(result.matched) == 1
    assert result.matched[0]["team_verified"] is True


def test_calibrate_matches_with_team_unverified_when_team_data_missing():
    # This is the common real-world case: KeyMoment.team is None because
    # detection.py never guesses team from commentary. The match still
    # happens on type + timing, but team_verified must be False so a
    # caller doesn't mistake it for a confirmed identity match.
    kickoff = 0.0
    moments = [_moment("goal", 10 * 60)]  # team=None
    report = [MatchReportEvent(event_type="goal", minute=10, team="Home FC")]
    result = calibrate(moments, report, kickoff)
    assert len(result.matched) == 1
    assert result.matched[0]["team_verified"] is False
