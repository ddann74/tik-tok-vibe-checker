"""Real PostgreSQL persistence, active only when POSTGRES_URL is set and a
live connection actually succeeds. Unlike the earlier honest stub (which
read POSTGRES_URL and never used it), this genuinely persists matches and
key moments and reloads them on startup - proven by
tests/test_pg_storage.py, which restarts a fresh MatchStore against the
same database and checks the data survived, not just that nothing crashed.

Still unverified against anything other than a local PostgreSQL instance in
this sandbox - a managed production Postgres (connection pooling limits,
network latency, TLS requirements) may behave differently. See PRD_v2.md.
"""
from __future__ import annotations

import os

from .detection import KeyMoment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    youtube_url TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    transcript_segments INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS key_moments (
    id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence REAL NOT NULL,
    player TEXT,
    team TEXT,
    start_seconds REAL NOT NULL DEFAULT 0,
    UNIQUE (match_id, idx)
);
-- ADD COLUMN IF NOT EXISTS so a database created before this field existed
-- (e.g. by an earlier version of this app) picks it up on next connect,
-- rather than silently keeping stale schema.
ALTER TABLE key_moments ADD COLUMN IF NOT EXISTS start_seconds REAL NOT NULL DEFAULT 0;
"""


def connect(url: str | None = None):
    """Best-effort connection. Returns None (never raises) on any failure so
    callers can degrade to in-memory-only, same pattern as npl_engine.storage
    uses for Chroma."""
    url = url or os.environ.get("POSTGRES_URL")
    if not url:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        conn = psycopg.connect(url, autocommit=True, connect_timeout=3)
        conn.execute(_SCHEMA)
        return conn
    except Exception:
        return None


def upsert_match(conn, match) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (match_id, youtube_url, title, source, transcript_segments)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (match_id) DO UPDATE SET
                youtube_url = EXCLUDED.youtube_url,
                title = EXCLUDED.title,
                source = EXCLUDED.source,
                transcript_segments = EXCLUDED.transcript_segments
            """,
            (match.match_id, match.youtube_url, match.title, match.source, match.transcript_segments),
        )
        cur.execute("DELETE FROM key_moments WHERE match_id = %s", (match.match_id,))
        for idx, m in enumerate(match.key_moments):
            cur.execute(
                """
                INSERT INTO key_moments
                    (match_id, idx, timestamp, event_type, description, confidence, player, team, start_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    match.match_id, idx, m.timestamp, m.event_type, m.description,
                    m.confidence, m.player, m.team, m.start_seconds,
                ),
            )


def load_all_matches(conn) -> list:
    from .storage import StoredMatch  # local import to avoid a circular import

    matches = []
    with conn.cursor() as cur:
        cur.execute("SELECT match_id, youtube_url, title, source, transcript_segments FROM matches")
        rows = cur.fetchall()
    for match_id, youtube_url, title, source, transcript_segments in rows:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT timestamp, event_type, description, confidence, player, team, start_seconds "
                "FROM key_moments WHERE match_id = %s ORDER BY idx",
                (match_id,),
            )
            moment_rows = cur.fetchall()
        moments = [
            KeyMoment(
                timestamp=ts, event_type=et, description=desc, confidence=conf,
                player=player, team=team, start_seconds=start_seconds,
            )
            for ts, et, desc, conf, player, team, start_seconds in moment_rows
        ]
        matches.append(StoredMatch(match_id, youtube_url, title, moments, source, transcript_segments))
    return matches
