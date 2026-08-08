"""Regex-based key-moment detection for NPL match commentary transcripts.

This is the "pattern matching" tier described in the source report (no AI /
YouTube Vision MCP involved — that tier is out of scope for v1, see PRD §8).
Patterns are intentionally tighter than the report's originals (e.g. requiring
word boundaries, dropping bare "net"/"strike"/"yellow") because the loose
originals produce obvious false positives on ordinary commentary. Accuracy
claims are only meaningful if they're measured against tests/fixtures/*, see
tests/test_detection.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EVENT_TYPES: tuple[str, ...] = (
    "own_goal",
    "red_card",
    "penalty",
    "yellow_card",
    "substitution",
    "goal",
)

# Checked in this order: more specific event types must win over the broad
# "goal" pattern (e.g. "own goal" and "penalty ... scores" should not also
# register as a plain goal).
_PRIORITY = ("own_goal", "red_card", "penalty", "yellow_card", "substitution", "goal")

PATTERNS: dict[str, list[re.Pattern]] = {
    "goal": [
        re.compile(
            # "scores?" deliberately excludes bare "score" (matches "scores"/"scored"
            # only) - "the final score" / "the score is 1-0" are not goal events.
            r"(?i)\b(scores|scored|headers? (?:it |them )?(?:in|home)|volleys? (?:it |them )?in"
            r"|finishes? (?:it |past)|strikes? (?:it |past)|(?:back of|into) the net"
            r"|past the (?:keeper|goalkeeper)|beats? the (?:keeper|goalkeeper))\b"
        ),
        re.compile(r"(?i)\b(equaliser|equalizer|leveller)\b"),
        re.compile(r"(?i)\b(opening|equalising|equalizing|winning|late|second|third|fourth) goal\b"),
    ],
    "yellow_card": [
        re.compile(
            r"(?i)\b(yellow card|(?:goes|going|first (?:one|player) )?into the book"
            r"|finds (?:himself|herself) in the book|shown a yellow|booked for|booking for)\b"
        ),
    ],
    "red_card": [
        re.compile(r"(?i)\b(red card|sent off|dismissed|straight red|second yellow)\b"),
    ],
    "substitution": [
        re.compile(
            r"(?i)\b(substitution|replaces|comes on for|comes in for|makes way for|is replaced by"
            r"|brought on for|replace (?:him|her|them)"
            r"|(?:enters?|entered|come|comes) (?:into )?the (?:fray|frag|freight|game) for)\b"
        ),
    ],
    "penalty": [
        re.compile(r"(?i)\b(penalty awarded|penalty kick|spot kick|from the spot|converts the penalty|steps up to take (?:the|a) penalty)\b"),
    ],
    "own_goal": [
        re.compile(
            r"(?i)\b(own goal|into (?:his|her|their) own net|deflect(?:s|ed) past (?:his|her|their) own (?:keeper|goalkeeper))\b"
        ),
    ],
}

# Base confidence per event type. Deliberately below the source report's
# fabricated 85-96% range until real precision/recall is measured per event
# type against a labeled set (see tests/test_detection.py + PRD §9).
_BASE_CONFIDENCE: dict[str, float] = {
    "own_goal": 0.65,
    "red_card": 0.80,
    "penalty": 0.75,
    "yellow_card": 0.70,
    "substitution": 0.70,
    "goal": 0.75,
}

_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,2})\b")
_LEADING_STOPWORDS = {"The", "A", "An", "It", "That", "This", "Goal", "Penalty"}


@dataclass
class KeyMoment:
    timestamp: str
    event_type: str
    description: str
    confidence: float
    player: str | None = None
    team: str | None = None
    start_seconds: float = 0.0


def classify_segment(text: str) -> tuple[str, float] | None:
    """Classify a single transcript line. Returns (event_type, confidence) or None."""
    if not text or not text.strip():
        return None
    for event_type in _PRIORITY:
        hits = 0
        for pattern in PATTERNS[event_type]:
            if pattern.search(text):
                hits += 1
        if hits:
            confidence = min(0.99, _BASE_CONFIDENCE[event_type] + 0.07 * (hits - 1))
            return event_type, round(confidence, 2)
    return None


def _guess_player(text: str) -> str | None:
    """Best-effort proper-noun extraction. No roster/NER backing it — may be
    wrong or absent. Team extraction is intentionally NOT attempted: without a
    squad list there's no reliable way to tell a player name from a team name
    using regex alone, so `team` is left null (see PRD §8, honesty over a
    guessed field)."""
    for match in _PROPER_NOUN_RE.finditer(text):
        candidate = match.group(1)
        first_word = candidate.split()[0]
        if first_word in _LEADING_STOPWORDS:
            continue
        return candidate
    return None


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def detect_key_moments(segments: list[dict]) -> list[KeyMoment]:
    """segments: list of {"start": float_seconds, "text": str}."""
    moments: list[KeyMoment] = []
    for seg in segments:
        text = seg.get("text", "")
        result = classify_segment(text)
        if result is None:
            continue
        event_type, confidence = result
        moments.append(
            KeyMoment(
                timestamp=format_timestamp(seg.get("start", 0.0)),
                event_type=event_type,
                description=text.strip(),
                confidence=confidence,
                player=_guess_player(text),
                team=None,
                start_seconds=float(seg.get("start", 0.0)),
            )
        )
    return moments


def summarize(moments: list[KeyMoment]) -> str:
    goals = sum(1 for m in moments if m.event_type in ("goal", "own_goal", "penalty"))
    cards = sum(1 for m in moments if m.event_type in ("yellow_card", "red_card"))
    subs = sum(1 for m in moments if m.event_type == "substitution")
    total = len(moments)
    return f"{goals} goals | {cards} cards | {subs} substitutions | {total} total moments"
