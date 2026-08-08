"""Tests for real Postgres persistence. Skipped entirely if POSTGRES_URL
isn't set - these are integration tests against a live database, not
something to fake with a mock. CI provides a real Postgres service
container (see .github/workflows/ci.yml); locally, point POSTGRES_URL at
any Postgres instance to run these.

The point of test_data_survives_a_simulated_restart is specifically to
prove persistence, not just "no crash on connect" - a MatchStore that
merely doesn't error without actually reloading data would pass a weaker
test and still be lying about being a persistence layer.
"""
import os
import uuid

import pytest

from npl_engine.detection import detect_key_moments
from npl_engine.storage import MatchStore, StoredMatch
from npl_engine.transcript import SAMPLE_TRANSCRIPT

pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_URL"), reason="POSTGRES_URL not set - skipping live Postgres integration tests"
)


def _cleanup(match_id: str):
    from npl_engine import pg_storage

    conn = pg_storage.connect()
    if conn is not None:
        conn.execute("DELETE FROM matches WHERE match_id = %s", (match_id,))
        conn.close()


def test_postgres_backend_reports_active_when_connected():
    store = MatchStore()
    assert store.postgres_active is True


def test_data_survives_a_simulated_restart():
    match_id = f"pgtest-{uuid.uuid4().hex[:8]}"
    moments = detect_key_moments(SAMPLE_TRANSCRIPT)
    try:
        store1 = MatchStore()
        store1.put(StoredMatch(match_id, "https://example.com/x", "Test Match", moments, "sample", len(SAMPLE_TRANSCRIPT)))

        # Fresh instance - simulates a process restart. If this only reads
        # from the first instance's in-memory dict, this would fail.
        store2 = MatchStore()
        recovered = store2.get(match_id)

        assert recovered is not None
        assert recovered.title == "Test Match"
        assert len(recovered.key_moments) == len(moments)
        assert recovered.key_moments[0].event_type == moments[0].event_type
        assert recovered.key_moments[0].description == moments[0].description
    finally:
        _cleanup(match_id)


def test_upsert_overwrites_rather_than_duplicates():
    match_id = f"pgtest-{uuid.uuid4().hex[:8]}"
    moments = detect_key_moments(SAMPLE_TRANSCRIPT)
    try:
        store = MatchStore()
        original = StoredMatch(match_id, "https://example.com/x", "First Title", moments, "sample", len(SAMPLE_TRANSCRIPT))
        store.put(original)
        updated = StoredMatch(match_id, "https://example.com/x", "Second Title", moments[:2], "live", 2)
        store.put(updated)

        fresh = MatchStore()
        recovered = fresh.get(match_id)
        assert recovered.title == "Second Title"
        assert len(recovered.key_moments) == 2
    finally:
        _cleanup(match_id)
