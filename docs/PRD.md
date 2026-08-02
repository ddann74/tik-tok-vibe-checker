# PRD — NPL NSW Intelligence Engine

**Status of this document:** Derived from `NPL NSW INTELLIGENCE ENGINE — FINAL PRODUCTION REPORT v3.0.0`.
That report describes a system as already 100% complete, 0 bugs, 98.8% quality score, all
checks PASSED. Treat that as a *claim*, not a *verification*. This PRD converts every claim
into a requirement with a concrete, checkable acceptance test — that gap is what the attached
Ralph loop is for.

## 1. Problem Statement

Coaches, journalists, and fans following NPL NSW matches want to find key moments (goals,
cards, subs, penalties) inside long YouTube match broadcasts without watching the full 90+
minutes, and want to search across many matches in natural language (e.g. "find all goals
from APIA vs Sydney United").

## 2. Goal

Ship a small, cheap, MCP-server-based pipeline that:
1. Takes a YouTube match URL.
2. Extracts a transcript and detects key moments (goal, yellow card, red card, substitution,
   penalty, own goal) with timestamp, description, and confidence.
3. Serves those moments through a REST API and a simple web UI with search.

## 3. Users & Use Cases

- **Fan**: "Show me every goal in this match" → timestamped list, clickable to that point in
  the video.
- **Journalist**: "Find all red cards across the last 10 APIA matches" → cross-match semantic
  search.
- **Analyst**: wants raw event data (JSON) per match for downstream stats work.

## 4. In Scope (v1 / MVP — this is what the source report claims to have built)

| Area | Requirement |
|---|---|
| Ingestion | Accept a YouTube URL, retrieve transcript + metadata (chapters, heatmap) via MCP servers (TubePilot MCP, yt-dlp MCP). |
| Detection | Classify transcript segments into: goal, yellow_card, red_card, substitution, penalty, own_goal, using regex pattern matching + optional AI-powered detection (YouTube Vision MCP). |
| API | `GET /`, `GET /health`, `POST /analyze_match?url=`, `GET /search_key_moments?q=&top_k=`. |
| Storage | Optional structured storage (PostgreSQL) for facts, optional vector storage (Chroma) for semantic search. Both must degrade gracefully to in-memory/sample mode if absent. |
| Frontend | Single HTML page: URL input → "Detect Key Moments", search box, "Load Sample", "Clear", results list showing timestamp/type/description/confidence/player/team. |
| Search | Natural-language query over stored key moments (semantic if Chroma present, keyword fallback otherwise). |

## 5. Out of Scope (v1)

- Live/real-time stream analysis (Phase 2 in the source report).
- User accounts, saved analyses, PDF/JSON export (Phase 2).
- Team/player profile pages, tactical analytics, mobile app (Phase 3).
- Multi-competition support, public developer API, commercial licensing (Phase 4).
- Any claim of "124 real matches processed" or "1,612 events extracted" being *production
  data* — until verified, treat these as target/sample-set sizes, not delivered facts (see
  §8, Open Risks).

## 6. Functional Requirements & Acceptance Criteria

Each requirement below replaces a "PASSED" row in the source report's quality audit with an
actual test a Ralph loop iteration can run and check off.

### 6.1 API contract
- `GET /health` returns HTTP 200 and JSON `{status, timestamp, version}`.
- `POST /analyze_match?url=<youtube_url>` returns HTTP 200 with `match_id`, `key_moments`
  (array), `key_moments_count` equal to `len(key_moments)`, and `summary` string that
  correctly tallies goals/cards/substitutions from the returned array (no hardcoded copy).
- `POST /analyze_match` with an invalid/non-YouTube URL returns a 4xx with a clear error
  message, not a 500 or a silently empty 200.
- `GET /search_key_moments?q=goal` returns only moments whose type or description is
  plausibly related to "goal" — verified by an automated test with known fixture data, not
  by eyeballing one response.

### 6.2 Detection quality
- Every regex pattern in §3.3 of the source report has at least 5 unit-test transcript lines
  (true positives) and at least 3 negative examples (should NOT match) per event type,
  committed to the repo and passing in CI.
- Reported precision/recall/F1 numbers (Goals 96/94/95, Yellow Cards 91/88/89, Red Cards
  94/92/93, Substitutions 90/87/88, Penalties 89/85/87, Own Goals 85/80/82) must be
  reproducible from a checked-in labeled test set + a script that computes them — not asserted
  in prose. If no labeled set exists yet, this is an open task, not a fact.

### 6.3 Frontend
- Loading `index.html` with the proxy server stopped shows a clear "server not running"
  state, not a blank page or console-only error.
- "Load Sample" populates results without a network call succeeding is not required to work
  (needs live analyze) but must not crash if the proxy is down.
- Mobile viewport (375px width) renders results list without horizontal scroll or overlap.

### 6.4 Storage degradation
- With `POSTGRES_URL` and `CHROMA_PATH` unset, all endpoints still function using
  sample/in-memory data — verified by an integration test that unsets both and hits every
  endpoint.

## 7. Non-Functional Requirements

| Requirement | Source claim | Acceptance test |
|---|---|---|
| Latency | `/analyze_match` ~287ms, `/search_key_moments` ~42ms | Load test script (`scripts/bench.py`) records p50/p95 over 20 real requests against a running server; results saved to `bench_results.json`. |
| Memory | ~127MB total | `ps`/`resource` measurement during bench run, logged. |
| Security | No SQL injection / XSS / CSRF / hardcoded keys | Automated scan (e.g. `bandit` for Python, manual grep for API keys) run in CI; no manual "PASSED" without tool output attached. |
| Cost | ~$15/month | Documented cost breakdown per external service actually used (Postgres host, any paid MCP), not assumed. |
| CORS | Localhost only | Test that a request with a non-localhost `Origin` header is rejected or not granted CORS headers. |

## 8. Open Risks / Questions (must be resolved, not asserted away)

1. **"0 fictional matches" / "124 real matches"** — where do these 124 matches actually live
   (URLs, a fixture file)? If this list doesn't exist as a checked-in artifact, the claim is
   unverifiable and should be downgraded to "target sample set" until built.
2. **YouTube Vision MCP** requires a Gemini API key — the report calls this both "optional"
   and part of the 95%-accuracy combined method. Clarify whether v1 ships with or without it,
   since accuracy claims depend on it.
2. **PostgreSQL/Chroma "optional"** — if optional, the 95%/98.8% numbers should be re-measured
   in the no-DB configuration, since that's the easiest path to actually deploy.
3. **Quality audit / security audit tables** in the source report contain no linked evidence
   (no test output, no scan report). Requirement: every PASSED row must link to a command or
   CI job that produced it.

## 9. Success Metrics (v1 launch)

- All endpoints in §6.1 pass automated tests in CI on every commit.
- Detection F1 per event type is computed from a checked-in labeled set and is ≥ the target
  in the table below (not the report's claimed number, which is unverified):
  - Goals ≥ 0.85, Cards ≥ 0.80, Substitutions ≥ 0.75, Penalties ≥ 0.75, Own goals ≥ 0.65
    (deliberately below the report's claims — raise the bar only after real measurement).
- `/health` uptime ≥ 99% over a 7-day soak test.

## 10. Roadmap (unchanged from source report, kept for context)

- **Phase 2 (Q3 2026):** real YouTube Data API, live streaming analysis, user accounts,
  export reports.
- **Phase 3 (Q4 2026):** team/player profiles, advanced tactical analytics, mobile app.
- **Phase 4 (Q1 2027):** multi-competition support (NPL Vic/QLD), A-League, public API,
  commercial licensing.

Phase 2+ work should not start until every item in §6–§9 is verifiably true, not just stated.
