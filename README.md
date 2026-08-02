# NPL NSW Intelligence Engine

Extracts key moments (goals, cards, substitutions, penalties, own goals) from
NPL NSW match commentary and serves them through a small REST API + web UI.

## Why this exists / how it relates to `docs/`

This repo was originally a different app (a TikTok comment "vibe checker");
that code has been removed. What's here now was built from
[`docs/PRD.md`](docs/PRD.md), which itself is a response to
[`docs/source_claim_report_v3.0.0_UNVERIFIED.txt`](docs/source_claim_report_v3.0.0_UNVERIFIED.txt) —
a "final production report" claiming 100% completion, 0 bugs, and a 98.8%
quality score for a system that didn't actually exist as checked-in code.
**That report's numbers are not reproduced anywhere in this codebase.**
Every claim below is either backed by a test you can run yourself, or
explicitly marked as not yet done.

## What's real right now

- **Detection**: regex pattern matching only (`npl_engine/detection.py`).
  No AI-powered / "YouTube Vision MCP" tier — that MCP server isn't
  available in this environment, so it's not implemented, not simulated.
- **Transcript source**: `youtube-transcript-api` (no API key). If a video
  has no captions or is unreachable, the API falls back to a labeled sample
  transcript rather than erroring — response includes `"source":
  "live"` or `"source": "sample_fallback"` so callers always know which.
- **Storage**: in-memory only. `POSTGRES_URL` / `CHROMA_PATH` are read and
  reported back (`storage_backend` field) but neither backend is wired up —
  search is keyword matching, not semantic. See PRD §8 open risk 2.
- **Frontend**: `static/index.html`, single page, no build step, no CDN
  dependencies. Verified in a real browser (Playwright): sample data loads
  with no backend running, a clear "server not running" banner shows
  instead of a blank page, and the layout doesn't overflow at 375px.

## Running it

```bash
pip install -r requirements.txt
uvicorn npl_engine.server:app --reload
```

- API root: http://127.0.0.1:8000/
- Frontend: http://127.0.0.1:8000/ui/
- Health: http://127.0.0.1:8000/health

## Verifying the claims yourself

```bash
# Detection precision/recall/F1 per event type, from a checked-in labeled set
PYTHONPATH=. python scripts/compute_detection_metrics.py

# Full test suite (detection F1 thresholds, API contract, storage degradation, CORS)
PYTHONPATH=. pytest tests/ -v

# Security scan
bandit -r npl_engine

# Latency/memory bench (needs the server already running)
python scripts/bench.py --base-url http://127.0.0.1:8000 --server-pid <uvicorn pid>
```

All of the above also run in CI (`.github/workflows/ci.yml`) on every push.

## API

| Endpoint | Method | Notes |
|---|---|---|
| `/` | GET | Service info |
| `/health` | GET | `{status, timestamp, version}` |
| `/analyze_match?url=` | POST | 400 on non-YouTube URLs. `summary` is computed from `key_moments`, never hardcoded. |
| `/search_key_moments?q=&top_k=` | GET | Keyword search over all analyzed matches (sample match pre-seeded). |

## Known gaps vs. the PRD (honestly listed, not glossed over)

- No AI-powered detection tier (needs a Gemini key + the actual YouTube
  Vision MCP server, unavailable here).
- No real PostgreSQL/Chroma backend — in-memory + keyword search only.
- Detection F1 targets in `tests/test_detection.py` are measured against
  fixtures written alongside the patterns, not an independently labeled,
  held-out set — real-world accuracy on unseen broadcasts is unverified.
- No 7-day `/health` uptime soak test (PRD §9) — not something a single
  session can produce.
- `player` extraction is a best-effort capitalized-phrase heuristic, not
  NER; `team` is intentionally always `null` (no reliable way to infer it
  from commentary text alone without a roster).
