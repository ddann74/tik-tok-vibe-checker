"""In-memory match/key-moment storage with keyword search.

The source report claimed optional PostgreSQL (structured facts) and Chroma
(semantic vector search) backends. Neither is wired up here: doing so
honestly would require a live Postgres instance and an embedding model,
neither of which can be verified in this environment. Per PRD §8, an
unimplemented "optional" backend must not be claimed as working — so this
module always runs in-memory / keyword-search mode, and callers can see that
via `backend_mode()`. Wiring in a real Postgres/Chroma backend is tracked as
a follow-up (PRD §8, open risk 2), not asserted as done.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .detection import KeyMoment


@dataclass
class StoredMatch:
    match_id: str
    youtube_url: str
    title: str
    key_moments: list[KeyMoment]
    source: str
    transcript_segments: int


class MatchStore:
    def __init__(self) -> None:
        self._matches: dict[str, StoredMatch] = {}

    def put(self, match: StoredMatch) -> None:
        self._matches[match.match_id] = match

    def get(self, match_id: str) -> StoredMatch | None:
        return self._matches.get(match_id)

    def all_moments(self) -> list[tuple[StoredMatch, KeyMoment]]:
        return [(m, mo) for m in self._matches.values() for mo in m.key_moments]

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        query = (query or "").strip().lower()
        if not query:
            return []
        terms = query.split()
        scored: list[tuple[int, StoredMatch, KeyMoment]] = []
        for match, moment in self.all_moments():
            haystack = f"{moment.event_type} {moment.description} {moment.player or ''}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, match, moment))
        scored.sort(key=lambda t: t[0], reverse=True)
        results = []
        for score, match, moment in scored[:top_k]:
            results.append(
                {
                    "match_id": match.match_id,
                    "youtube_url": match.youtube_url,
                    "timestamp": moment.timestamp,
                    "event_type": moment.event_type,
                    "description": moment.description,
                    "confidence": moment.confidence,
                    "player": moment.player,
                    "team": moment.team,
                    "score": score,
                }
            )
        return results


def backend_mode() -> dict:
    """Reports what storage backends were *requested* via env vars vs what's
    actually active. Never claims a backend is live unless it truly is."""
    return {
        "postgres_requested": bool(os.environ.get("POSTGRES_URL")),
        "postgres_active": False,
        "chroma_requested": bool(os.environ.get("CHROMA_PATH")),
        "chroma_active": False,
        "active_backend": "in_memory_keyword_search",
    }


store = MatchStore()
