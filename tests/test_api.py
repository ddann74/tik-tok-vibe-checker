"""PRD §6.1 API contract, §6.4 storage degradation, §7 CORS."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # PRD §6.4: with POSTGRES_URL / CHROMA_PATH unset, every endpoint must
    # still work off in-memory/sample data.
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    from npl_engine import storage as storage_module

    # `store` is a module-level singleton built once at import time, so
    # merely reloading server_module below re-binds names but does NOT
    # re-run MatchStore.__init__ - without rebuilding it here, this
    # fixture's env-var patching would be silently ignored and
    # postgres_active/chroma_active would keep reflecting whatever was
    # true the first time storage.py was imported in this test session.
    monkeypatch.setattr(storage_module, "store", storage_module.MatchStore())

    from npl_engine import server as server_module

    importlib.reload(server_module)
    return TestClient(server_module.app)


def test_health_returns_200_and_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body
    assert "version" in body


def test_root_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_analyze_match_key_moments_link_to_the_right_timestamp(client, monkeypatch):
    # Force the sample-fallback transcript deterministically, rather than
    # relying on this arbitrary video ID actually lacking football content.
    # A real fetch depends on network access this test can't assume: this
    # sandbox blocks outbound YouTube entirely, but a CI runner with real
    # internet fetched this video's actual (non-football) captions, found
    # zero key moments, and correctly failed the "at least one moment"
    # assertion below - that was this test's bug, not the app's.
    from npl_engine import server as server_module
    from npl_engine import transcript as transcript_module

    # server.py does `from .transcript import fetch_transcript`, binding its
    # own module-level name - patching transcript_module.fetch_transcript
    # would not affect server.py's already-resolved reference, so this
    # patches the name actually called inside analyze_match().
    monkeypatch.setattr(
        server_module, "fetch_transcript", lambda video_id: (transcript_module.SAMPLE_TRANSCRIPT, "sample_fallback")
    )
    r = client.post("/analyze_match", params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    body = r.json()
    assert body["key_moments"], "expected at least one key moment for this to be a meaningful test"
    for moment in body["key_moments"]:
        assert moment["video_url"].startswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=")
        assert moment["video_url"].endswith("s")


def test_search_key_moments_results_include_video_url(client):
    r = client.get("/search_key_moments", params={"q": "goal"})
    body = r.json()
    assert body["results"], "expected at least one result for this to be a meaningful test"
    for result in body["results"]:
        assert result["video_url"] is None or result["video_url"].startswith("https://www.youtube.com/watch?v=")


def test_analyze_match_success_shape_and_summary_matches_moments(client):
    r = client.post("/analyze_match", params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert r.status_code == 200
    body = r.json()
    assert body["match_id"]
    assert isinstance(body["key_moments"], list)
    assert body["key_moments_count"] == len(body["key_moments"])

    goals = sum(1 for m in body["key_moments"] if m["event_type"] in ("goal", "own_goal", "penalty"))
    cards = sum(1 for m in body["key_moments"] if m["event_type"] in ("yellow_card", "red_card"))
    subs = sum(1 for m in body["key_moments"] if m["event_type"] == "substitution")
    expected_summary = f"{goals} goals | {cards} cards | {subs} substitutions | {len(body['key_moments'])} total moments"
    assert body["summary"] == expected_summary


@pytest.mark.parametrize(
    "bad_url",
    ["", "not a url", "https://vimeo.com/12345678", "ftp://youtube.com/watch?v=dQw4w9WgXcQ"],
)
def test_analyze_match_rejects_invalid_url_with_4xx(client, bad_url):
    r = client.post("/analyze_match", params={"url": bad_url})
    assert 400 <= r.status_code < 500, f"expected 4xx for {bad_url!r}, got {r.status_code}"
    assert r.json().get("detail")


def test_search_key_moments_filters_by_query_against_seeded_sample_data(client):
    r = client.get("/search_key_moments", params={"q": "goal"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["results"])
    assert body["count"] > 0
    for result in body["results"]:
        haystack = f"{result['event_type']} {result['description']}".lower()
        assert "goal" in haystack


def test_search_key_moments_irrelevant_query_returns_no_false_matches(client):
    r = client.get("/search_key_moments", params={"q": "xylophone"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_every_endpoint_works_without_postgres_or_chroma_configured(client):
    """PRD §6.4 integration check: hit every endpoint with both backends unset.

    Postgres genuinely isn't implemented, so postgres_active must be False.
    Chroma is real (see npl_engine/storage.py) and runs standalone without
    needing CHROMA_PATH - CHROMA_PATH only selects on-disk persistence vs.
    an ephemeral in-memory index - so chroma_active reflects whatever this
    environment's chromadb install actually managed at startup, not a fixed
    expectation. The point of this test is that nothing 500s either way.
    """
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    analyze = client.post("/analyze_match", params={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert analyze.status_code == 200
    assert analyze.json()["storage_backend"]["postgres_active"] is False
    assert isinstance(analyze.json()["storage_backend"]["chroma_active"], bool)
    assert client.get("/search_key_moments", params={"q": "card"}).status_code == 200


def test_cors_rejects_non_localhost_origin(client):
    r = client.get("/health", headers={"Origin": "http://evil-example.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers.keys()}


def test_cors_allows_localhost_origin(client):
    r = client.get(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
