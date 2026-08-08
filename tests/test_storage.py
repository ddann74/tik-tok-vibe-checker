"""Tests for the storage layer's real Chroma-backed semantic search.

Deliberately doesn't assert specific event types come back for a given
query - absolute embedding similarities on this small model + small corpus
are low and can shift slightly across chromadb/onnxruntime versions. What's
actually being verified: semantic search never crashes, never returns
scores below the honesty threshold, and keyword search still wins whenever
it has any hits at all (see npl_engine/storage.py's search() docstring).
"""
from npl_engine.detection import detect_key_moments
from npl_engine.storage import MatchStore, StoredMatch
from npl_engine.transcript import SAMPLE_TRANSCRIPT


def _seeded_store() -> MatchStore:
    store = MatchStore()
    moments = detect_key_moments(SAMPLE_TRANSCRIPT)
    store.put(StoredMatch("m1", "https://example.com/m1", "Sample", moments, "sample", len(SAMPLE_TRANSCRIPT)))
    return store


def test_semantic_search_never_crashes_on_nonsense_query():
    store = _seeded_store()
    results = store._semantic_search("xylophone", top_k=5)
    assert isinstance(results, list)
    assert results == []


def test_semantic_search_results_are_all_above_the_honesty_threshold():
    store = _seeded_store()
    for query in ["red card", "who scored", "player substituted", "penalty kick"]:
        for result in store._semantic_search(query, top_k=10):
            assert result["score"] > 0
            assert result["match_type"] == "semantic"


def test_keyword_search_wins_over_semantic_when_both_could_apply():
    store = _seeded_store()
    results = store.search("goal", top_k=10)
    assert results
    assert all(r["match_type"] == "keyword" for r in results)


def test_search_degrades_to_empty_not_error_with_no_matches_stored():
    store = MatchStore()
    assert store.search("goal") == []
