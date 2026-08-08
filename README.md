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

- **Match-report calibration**: `POST /calibrate?match_id=X` compares a
  match's detected key moments against an official match report's events
  (event type + minute or half), reporting matches/misses and any
  timestamp correction the report's precision supports. Kickoff and
  half-time are detected via regex over the transcript at analyze time and
  stored as two numbers (never the transcript text itself); video
  timestamps are converted to estimated match minutes relative to
  kickoff. Validated against a real match: a detected penalty at video
  timestamp 5590s calibrated to match minute 74, correctly landing in the
  second half per that match's real report - see `npl_engine/calibration.py`
  for the full honesty notes (kickoff detection can return "not found," a
  narrative report without minute markers only supports coarse half-level
  matching, etc). Matching is type + timing only, not identity: since
  detected `KeyMoment.team` is almost always `null` (detection.py never
  guesses team from commentary text - see below), the algorithm can't
  usually tell a home-team goal from an away-team goal on the video side.
  It skips a candidate when both the video and the report *do* have team
  data and they disagree, and every `matched[]` entry carries a
  `team_verified` flag (`true` only when both sides had team data to check
  - `false`, the common case, means the match is type+timing only and
  should not be read as a confirmed same-team identity match).

- **Match-week browser**: `GET /match_weeks` serves a dropdown-friendly list
  of games grouped by upload-date proximity into "estimated match weeks."
  This is a real, working feature, but the week numbers are **not** the
  league's official round numbers — confirmed by actually listing the real
  YouTube playlist's video titles, which don't include round info at all,
  only team names. Populated by `scripts/refresh_playlist_cache.py`, which
  needs `pip install yt-dlp` and real internet access to youtube.com (this
  sandbox blocks that, same as transcript fetching — the script is written
  but only verified against real playlist data pasted in by hand, not run
  end-to-end from here). With no cache generated yet, the endpoint returns
  an empty `weeks` list rather than erroring, and the frontend degrades to
  the plain URL input. **Refreshing is incremental by default**: games
  already in the cache keep their known date without being re-fetched
  (the slow part - one page load per video); only new games get the full
  fetch. `python scripts/refresh_playlist_cache.py --full` forces a
  complete re-fetch from scratch if ever needed.
- **Detection**: regex pattern matching only (`npl_engine/detection.py`).
  No AI-powered / "YouTube Vision MCP" tier — that MCP server isn't
  available in this environment, so it's not implemented, not simulated.
- **Transcript source**: `youtube-transcript-api` (no API key). If a video
  has no captions or is unreachable, the API falls back to a labeled sample
  transcript rather than erroring — response includes `"source":
  "live"` or `"source": "sample_fallback"` so callers always know which.
- **Storage**: in-memory cache backed by real, optional persistence. Set
  `POSTGRES_URL` and matches/key moments are actually written and reloaded
  on restart (`npl_engine/pg_storage.py`) — proven by
  `tests/test_pg_storage.py`, which restarts a fresh store against the same
  database and checks the data survived, run against a real local
  PostgreSQL 16 instance and continuously verified in CI via a
  `postgres:16` service container. Unset, it's in-memory only, same as
  before. Chroma *is* also real: its default local embedding model is
  reachable in this environment and semantic search runs for real. Keyword
  search is the primary path
  (exact, deterministic); when it finds nothing, natural-language queries
  fall back to semantic search, filtered to a conservative similarity
  threshold (see `npl_engine/storage.py`'s `search()` docstring for why a
  relative top-k cutoff was rejected in favor of an absolute one). With this
  small model and small corpus, plenty of legitimate-sounding queries still
  come back empty rather than noisy — that's intentional, not a bug.
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

# Same, plus real Postgres persistence tests (skipped above without this)
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/npl_engine_test PYTHONPATH=. pytest tests/ -v

# Security scan
bandit -r npl_engine

# Latency/memory bench (needs the server already running)
python scripts/bench.py --base-url http://127.0.0.1:8000 --server-pid <uvicorn pid>
```

All of the above also run in CI (`.github/workflows/ci.yml`) on every push.

### Real-match validation (not just self-authored fixtures)

The checked-in fixtures score a perfect 1.00 F1 on every bucket — expected,
since they were written alongside the patterns. To get an honest read, the
patterns were also run line-by-line against a real NPL NSW match transcript
(Southerntherland Sharks vs Sydney FC) supplied outside this repo. That
transcript isn't checked in here (broadcast commentary is copyrighted), but
the outcome is: goals 2/2 caught, yellow cards 5/5, substitutions 3/4, no
false positives on red cards/penalties/own goals (none occurred in that
match). The substitution/yellow-card patterns were widened afterward based
on real phrasing gaps this run exposed (e.g. "into the book" beyond just
"goes into the book"; "comes in for" and "entered the fray for" beyond
"comes on for"). This is one match, not a statistically meaningful sample —
treat it as a sanity check that closed an obvious gap, not proof the F1
targets in §9 hold in general.

A second real match (St. George City vs Rockdale Illawarra, also not checked
in here) was run the same way and caught two real bugs the first match
happened not to exercise:

- **False positive**: the goal pattern matched the bare word "score" (e.g.
  "the final score, St. George City 1, Rockdale nil"), because `scores?`
  also matches singular "score". Fixed to require "scores"/"scored".
- **Recall miss**: a real goal call ("...there's the opening goal of the
  match... puts the home side in front") used none of the existing trigger
  verbs. Added a pattern for "opening/equalising/winning/late goal" phrasing.

Re-run after the fix: goal 1/1 (was 0/1, plus the false positive is gone),
yellow cards 4/4, substitutions 2/4. No penalty, red card, or own goal
occurred in this match either — those three event types have still never
been checked against real commentary, only self-authored fixtures.

A third real match (Wollongong Wolves vs Rockdale Illawarra, also not
checked in here) had an own goal and a yellow card - the first real
exercise of the own-goal pattern - plus more goal/substitution phrasing
gaps:

- Own goal: caught, but only via a half-time recap sentence that
  literally said "own goal" - the live call ("the deflection off [player]
  who needed to make the intervention...") used none of the existing
  triggers and was missed. Not fixed - "a deflection off a player" is too
  generic a phrase to safely trigger on without risking false positives on
  ordinary deflected shots that aren't own goals.
- Goal: a bare "...and it's a goal" call was missed (only qualified goals
  like "opening goal" were covered). Added a pattern for "it's a goal" /
  "that's a goal".
- Substitution: 0/5 caught. Real commentary phrases substitutions as
  "[player] coming off... [player] on", "set to come on in place of
  [player]", "[player] coming off, [player]" - none of which matched
  "comes on for" style patterns. Added "coming on" / "coming off" / "set
  to come on" as triggers.
- Yellow card: 1/1 caught, no changes needed.
- Red card, penalty: still zero real-match exercise - this match had
  neither (a hand-ball shout drew no penalty, correctly not flagged).

Re-run after the fix: substitutions 5/5 (was 0/5), goals 2/3 (was 1/3 -
the recap-only own-goal miss stands, undecided whether to chase it).

A fourth real match (Wollongong Wolves vs SD Raiders, also not checked in
here) had a real red card - the first exercise of that pattern - plus more
goal/substitution gaps:

- Red card: caught cleanly, no pattern change needed.
- Goal: "buried it" (a common finishing verb - "he's buried it") was
  missed. Added. Two goal calls remain missed and unfixed as too risky to
  generalize: a noun-phrase call ("...with the finish", no verb) and
  "clipped in goal" (a fairly common but ambiguous construction - "in
  goal" also appears in unrelated phrases like "the keeper collects it in
  goal").
- Substitution: simple-present "comes off"/"comes on" (as opposed to the
  gerund "coming off"/"coming on" already covered) and bare "replaced by"
  without a leading "is" were both missed. Added. One substitution call
  ("James Letter... going to have to take his leave... Thomas Santa Rossa
  who's on") remains missed and unfixed - too idiosyncratic to generalize
  from a single example without risking false positives on unrelated
  "who's on" phrasing.
- Penalty: two hand-ball shouts in this match, neither resulted in an
  actual penalty being awarded, and neither triggered a false positive -
  a genuine, if narrow, validation that the conservative penalty pattern
  behaves correctly on real "almost but not quite" commentary.

A fifth real match (UNSW FC vs Wollongong Wolves, also not checked in
here) had a real penalty awarded and converted, closing the last event
type with zero real-world exercise:

- The live penalty award ("...went over and that's a penalty") was
  missed - only a later recap phrase ("broken from the spot") was caught.
  Added "that's a penalty" / "it's a penalty" and "12 yards" / "12-yard"
  (standard penalty-spot terminology).
- Deliberately NOT fixed: a bare-noun recap ("it was the [player] penalty
  that did it") was also missed. Adding bare "penalty" as a trigger would
  fix that, but it would also flip a real true-negative from the 4th
  match ("that almost resulted in a penalty", correctly unflagged) into a
  false positive. Chose precision over recall here rather than silently
  trading one for the other.
- Substitution: "have both come off" (base verb form, as opposed to
  "comes off"/"coming off") was missed. Added bare "come off"/"come on".

Running tally across all five validated matches: goals 9/13, yellow cards
20/20, substitutions 15/19, red card 1/1, penalty 3/4, own goal 1/1
(recap only). **Every event type has now been exercised against real
commentary, not just self-authored fixtures** - the gap that mattered
most (§9's success metrics being measured only against patterns' own
authors) is closed, even though recall on several event types is still
short of the checked-in fixtures' inflated 1.00.

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
- Postgres and Chroma semantic search are both real now (see above), not
  gaps. Postgres is only verified against local/CI PostgreSQL 16 — a
  managed production instance (connection pooling, network latency, TLS)
  may behave differently; not assumed identical.
- Detection F1 targets in `tests/test_detection.py` are measured against
  fixtures written alongside the patterns, not an independently labeled,
  held-out set — real-world accuracy on unseen broadcasts is unverified.
- No 7-day `/health` uptime soak test (PRD §9) — not something a single
  session can produce.
- `player` extraction is a best-effort capitalized-phrase heuristic, not
  NER; `team` is intentionally always `null` (no reliable way to infer it
  from commentary text alone without a roster).
