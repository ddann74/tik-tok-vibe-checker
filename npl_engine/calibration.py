"""Calibrates detected key moments against an official match report:
checks accuracy (does a reported event have a matching detection?) and,
where the report gives a precise minute, corrects the detected timestamp
to it.

Two honesty constraints baked into the design:

1. Video timestamps aren't match minutes - a broadcast has pre-match
   build-up, half-time, injury stoppages, etc. Converting requires finding
   the actual kickoff moment in the transcript, which is a heuristic
   (regex over commentary phrasing), not a guaranteed-correct anchor.
   estimate_match_minute() returns None rather than a wrong number when no
   kickoff phrase was found, so a broken calibration is visibly broken
   rather than silently offset.
2. "Calibrating against a match report" only works as well as the report's
   own precision. A narrative recap ("a second-half penalty") only
   supports a coarse pre/post-halftime check, not minute-level
   correction - MatchReportEvent.minute is optional, and comparison logic
   must not claim precision the report didn't have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .detection import KeyMoment

_KICKOFF_RE = re.compile(
    r"(?i)\b(we'?re away for kick[\s-]?off|kicks? off|get(?:s|ting)? underway|we'?re underway"
    r"|underway (?:here|now)|referee gets us underway)\b"
)

_HALFTIME_RE = re.compile(r"(?i)\b(half[\s-]?time|end of the first half|halime)\b")


def detect_kickoff_seconds(segments: list[dict]) -> float | None:
    """Best-effort: returns the start_seconds of the first segment matching
    common kickoff phrasing, or None if no such phrase was found. Returning
    None (not 0.0, not a guess) is deliberate - callers must not silently
    treat "no kickoff found" as "kickoff at video start"."""
    for seg in segments:
        if _KICKOFF_RE.search(seg.get("text", "")):
            return float(seg.get("start", 0.0))
    return None


def detect_halftime_seconds(segments: list[dict]) -> float | None:
    for seg in segments:
        if _HALFTIME_RE.search(seg.get("text", "")):
            return float(seg.get("start", 0.0))
    return None


def estimate_match_minute(start_seconds: float, kickoff_seconds: float | None) -> int | None:
    if kickoff_seconds is None or start_seconds < kickoff_seconds:
        return None
    return int((start_seconds - kickoff_seconds) // 60)


@dataclass
class MatchReportEvent:
    event_type: str
    minute: int | None = None  # None if the report doesn't give a precise minute
    player: str | None = None
    team: str | None = None
    half: int | None = None  # 1 or 2, if the report only says "second half" etc.


@dataclass
class CalibrationResult:
    matched: list[dict]
    missed_in_video: list[MatchReportEvent]  # reported but no matching detection
    unconfirmed_in_report: list[KeyMoment]  # detected but not in the report
    corrected_timestamps: int  # how many matches got their timestamp corrected to the report's minute


def calibrate(
    key_moments: list[KeyMoment],
    report_events: list[MatchReportEvent],
    kickoff_seconds: float | None,
    minute_tolerance: int = 5,
) -> CalibrationResult:
    """Matches report_events to key_moments by event_type + rough timing
    proximity, not by exact identity - there's no reliable shared key (no
    player names in most reports, no guaranteed minute in the video).

    Matching rule: same event_type, and if both a report minute and an
    estimated video minute are available, within `minute_tolerance`
    minutes of each other. If the report only gives a half (1 or 2) and
    the video's estimated minute is unavailable/unknown, falls back to a
    half-only match: pre/post-45 using the video's own halftime marker
    when present, else unmatched (not guessed).
    """
    unmatched_moments = list(key_moments)
    matched: list[dict] = []
    missed: list[MatchReportEvent] = []
    corrected = 0

    for report_event in report_events:
        candidate = None
        candidate_est_minute = None
        for moment in unmatched_moments:
            if moment.event_type != report_event.event_type:
                continue
            est_minute = estimate_match_minute(moment.start_seconds, kickoff_seconds)
            if report_event.minute is not None and est_minute is not None:
                if abs(est_minute - report_event.minute) <= minute_tolerance:
                    candidate = moment
                    candidate_est_minute = est_minute
                    break
            elif report_event.half is not None and est_minute is not None:
                moment_half = 1 if est_minute <= 45 else 2
                if moment_half == report_event.half:
                    candidate = moment
                    candidate_est_minute = est_minute
                    break
            elif report_event.minute is None and report_event.half is None:
                # No timing info in the report at all - match on type only,
                # first available candidate.
                candidate = moment
                candidate_est_minute = est_minute
                break

        if candidate is not None:
            unmatched_moments.remove(candidate)
            corrected_this_one = False
            if report_event.minute is not None and candidate_est_minute != report_event.minute:
                corrected_this_one = True
                corrected += 1
            matched.append(
                {
                    "event_type": report_event.event_type,
                    "report_minute": report_event.minute,
                    "video_estimated_minute": candidate_est_minute,
                    "corrected_to_report_minute": corrected_this_one,
                    "description": candidate.description,
                }
            )
        else:
            missed.append(report_event)

    return CalibrationResult(
        matched=matched,
        missed_in_video=missed,
        unconfirmed_in_report=unmatched_moments,
        corrected_timestamps=corrected,
    )
