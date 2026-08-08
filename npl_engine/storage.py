"""In-memory match/key-moment storage, with keyword search as the primary
path and real semantic search (Chroma) layered on top when available.

The source report claimed optional PostgreSQL (structured facts) and Chroma
(semantic vector search) backends. Postgres is still not wired up here —
doing so honestly would require a live database instance this environment
doesn't have. Chroma *is* now real: its default local embedding model is
reachable from this sandbox (confirmed by actually downloading it and
running a query), so semantic search runs for real, not simulated. It's
layered as a fallback rather than the primary path: keyword search stays
exact/deterministic (existing tests depend on literal substring matches),
and semantic search kicks in for natural-language queries that keyword
search comes up empty on - which is the actual use case in PRD §3
("find all red cards across the last 10 APIA matches"). If chromadb or its
embedding model isn't available at runtime, this degrades to keyword-only
automatically; `backend_mode()` reports which actually happened, not which
was merely requested.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .detection import KeyMoment

_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "are", "be", "been", "who", "what",
    "when", "where", "which", "did", "does", "do", "by", "to", "of", "in",
    "on", "for", "and", "or", "with", "that", "this", "it", "at", "as",
}


@dataclass
class StoredMatch:
    match_id: str
    youtube_url: str
    title: str
    key_moments: list[KeyMoment]
    source: str
    transcript_segments: int


def _moment_document(moment: KeyMoment) -> str:
    return f"{moment.event_type.replace('_', ' ')}: {moment.description}"


def _init_chroma_collection():
    """Best-effort Chroma init. Returns None (not an exception) on any
    failure so callers can degrade to keyword-only search."""
    try:
        import chromadb
    except ImportError:
        return None
    try:
        chroma_path = os.environ.get("CHROMA_PATH")
        client = chromadb.PersistentClient(path=chroma_path) if chroma_path else chromadb.EphemeralClient()
        return client.get_or_create_collection("npl_key_moments")
    except Exception:
        return None


class MatchStore:
    def __init__(self) -> None:
        self._matches: dict[str, StoredMatch] = {}
        self._chroma_collection = _init_chroma_collection()

    @property
    def semantic_search_active(self) -> bool:
        return self._chroma_collection is not None

    def put(self, match: StoredMatch) -> None:
        self._matches[match.match_id] = match
        if self._chroma_collection is not None and match.key_moments:
            try:
                self._chroma_collection.upsert(
                    ids=[f"{match.match_id}:{i}" for i in range(len(match.key_moments))],
                    documents=[_moment_document(m) for m in match.key_moments],
                    metadatas=[{"match_id": match.match_id, "index": i} for i in range(len(match.key_moments))],
                )
            except Exception:  # nosec B110 - best-effort indexing, must not break analyze_match
                pass

    def get(self, match_id: str) -> StoredMatch | None:
        return self._matches.get(match_id)

    def all_moments(self) -> list[tuple[StoredMatch, KeyMoment]]:
        return [(m, mo) for m in self._matches.values() for mo in m.key_moments]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        # Without this filter, common words in a natural-language query
        # (e.g. "who was cautioned by the referee") spuriously match "the"/
        # "was"/etc. against ordinary commentary text, so keyword search
        # never comes up empty and semantic search never gets a chance to
        # run - defeating the point of the hybrid design.
        terms = [t for t in query.split() if t not in _STOPWORDS and len(t) > 2]
        scored: list[tuple[int, StoredMatch, KeyMoment]] = []
        for match, moment in self.all_moments():
            haystack = f"{moment.event_type} {moment.description} {moment.player or ''}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, match, moment))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            self._format_result(match, moment, score=score, match_type="keyword")
            for score, match, moment in scored[:top_k]
        ]

    def _semantic_search(self, query: str, top_k: int) -> list[dict]:
        if self._chroma_collection is None or not self._matches:
            return []
        try:
            result = self._chroma_collection.query(query_texts=[query], n_results=top_k)
        except Exception:
            return []
        results = []
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0] if result.get("distances") else [None] * len(ids)
        for doc_id, distance in zip(ids, distances):
            match_id, _, index_str = doc_id.partition(":")
            match = self._matches.get(match_id)
            if match is None:
                continue
            try:
                moment = match.key_moments[int(index_str)]
            except (ValueError, IndexError):
                continue
            similarity = round(1 - distance, 4) if distance is not None else None
            # Conservative absolute cutoff, not a relative top-k one: with
            # this small local embedding model and a small corpus, absolute
            # cosine similarities run low and unevenly (e.g. a genuine
            # near-synonym like "sent off" for "red card" can still score
            # negative). A relative cutoff would return junk for nonsense
            # queries just because it's the "least bad" match; this errs
            # toward returning nothing over returning noise, at the cost of
            # missing some legitimate weak matches - see README.
            if similarity is None or similarity <= 0:
                continue
            results.append(self._format_result(match, moment, score=similarity, match_type="semantic"))
        return results

    def _format_result(self, match: StoredMatch, moment: KeyMoment, score, match_type: str) -> dict:
        return {
            "match_id": match.match_id,
            "youtube_url": match.youtube_url,
            "timestamp": moment.timestamp,
            "event_type": moment.event_type,
            "description": moment.description,
            "confidence": moment.confidence,
            "player": moment.player,
            "team": moment.team,
            "score": score,
            "match_type": match_type,
        }

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        query = (query or "").strip().lower()
        if not query:
            return []
        keyword_results = self._keyword_search(query, top_k)
        if keyword_results:
            return keyword_results
        # No literal keyword hits - fall back to real semantic search for
        # natural-language queries, if it's available.
        return self._semantic_search(query, top_k)


def backend_mode() -> dict:
    """Reports what storage backends were *requested* via env vars vs what's
    actually active. Never claims a backend is live unless it truly is."""
    return {
        "postgres_requested": bool(os.environ.get("POSTGRES_URL")),
        "postgres_active": False,
        "chroma_requested": bool(os.environ.get("CHROMA_PATH")),
        "chroma_active": store.semantic_search_active,
        "active_backend": "keyword_search+chroma_semantic_fallback" if store.semantic_search_active else "keyword_search_only",
    }


store = MatchStore()
