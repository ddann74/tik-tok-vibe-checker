# PRD v2 — NPL NSW Intelligence Engine

**Status of this document:** Written against the actual codebase on
`claude/npl-intelligence-engine-5c6fi9` as of this commit, not against a
claims-only report. Every line item below is either (a) already backed by a
test in this repo you can run yourself, or (b) marked open with the exact
reason it isn't closed. Nothing here is aspirational prose.

## 1. What's actually built (verify, don't trust)

| Area | Real state | How to verify |
|---|---|---|
| API | `GET /`, `/health`, `POST /analyze_match`, `GET /search_key_moments` | `pytest tests/test_api.py -v` |
| Detection | Regex only, 6 event types | `python scripts/compute_detection_metrics.py` |
| Transcript | `youtube-transcript-api`, real, but **outbound YouTube access is blocked in this sandbox** — every run here falls back to sample data | `curl -X POST /analyze_match?url=...` and check `"source"` field |
| Storage | In-memory. Postgres unwired (honest stub). Chroma **real** — embedding model confirmed reachable and downloaded | `pytest tests/test_storage.py -v` |
| Frontend | Single page, verified in a real headless browser incl. no-backend and 375px states | manual: open `static/index.html` with server down |
| Security | bandit clean | `bandit -r npl_engine` |
| CI | Green on GitHub Actions for every push so far | GitHub Actions tab |

## 2. Validated against real data (not just self-authored fixtures)

Four real NPL NSW match transcripts (user-supplied, not checked into this
repo — copyrighted broadcast commentary) were run through the detection
engine line-by-line. This found and fixed:

- A false positive (bare "score" matching the goal pattern on phrases like
  "the final score").
- Recall misses on goal calls: "opening goal... puts them in front", bare
  "...and it's a goal", and "buried it" (a common finishing verb) all
  matched no existing trigger at various points.
- Substitution-phrasing gaps: "comes in for", "entered the fray for",
  "[player] coming off... [player] on" / "set to come on in place of
  [player]" (the third match had 0/5 substitutions caught before this was
  added), and simple-present "comes off"/"comes on" plus bare "replaced
  by" without a leading "is" (the fourth match's biggest miss).
- The fourth match provided the first real red card - caught cleanly, no
  fix needed for that pattern.
- An own goal was caught, but only via a half-time recap sentence that
  literally said "own goal" - the live call used generic deflection
  language and was missed. Left unfixed: "a deflection off a player" is
  too generic a trigger to add without risking false positives on ordinary
  deflected shots.

Current real-match tally across all four matches: goals 8/11, yellow cards
18/18, substitutions 13/17, red card 1/1, own goal 1/1 (recap only, live
call missed). **Zero real-match exercise for penalty** — none of the four
validated matches had one (two had a hand-ball shout that correctly did
NOT trigger a false positive, since no penalty was actually awarded either
time). Penalty is now the only event type with no real-world exercise at
all - the last item in this gap.

## 3. Open items, ranked, with why they're open

1. ~~**Penalty/red-card real-match validation**~~ **Red card CLOSED** (4th
   match, caught cleanly, no pattern change needed). **Penalty still open**
   — blocked on getting a transcript with an actual penalty awarded (not
   just a shout that was waved away, which two of the four matches already
   had and correctly did not false-positive). Not blocked on anything
   technical.
2. **Live YouTube fetch, end-to-end** — blocked on this sandbox's egress
   policy (confirmed via live 403 at the proxy, not assumed). Needs running
   `npl_engine/transcript.py` somewhere with real internet.
3. **AI-powered detection tier** — not blocked, undecided. Requires a
   product call: is regex-only accuracy acceptable, or is a Gemini-backed
   tier worth the API cost and a required key? PRD §8 in the original
   report flagged this as unresolved; it still is.
4. ~~**Postgres backend**~~ **CLOSED.** Real persistence now wired in
   (`npl_engine/pg_storage.py`): matches + key moments are written on every
   `put()` and reloaded on startup. Proven by
   `tests/test_pg_storage.py::test_data_survives_a_simulated_restart`,
   which restarts a fresh `MatchStore` against the same database and checks
   the data survived — run against a real local PostgreSQL 16 instance, and
   CI now spins up a `postgres:16` service container so this stays
   continuously verified, not just verified once locally. Still unverified
   against anything other than local/CI Postgres (managed production
   instances - connection pooling, network latency, TLS - may behave
   differently; not assumed to be identical).
5. **Player/team extraction quality** — known-weak. The capitalized-phrase
   heuristic has no real NER behind it and provably misfires (confirmed:
   "Deflects", "That's", team names bleeding into the player field). Fixed
   the specific bugs found; the general ambiguity (a name and an ordinary
   verb are both capitalized at a sentence start) is not fixable without a
   real NER model or a squad roster to cross-reference against.
6. **Semantic search coverage** — real, but weak on this small model/small
   corpus: many legitimate natural-language queries score below the
   honesty threshold and return nothing rather than a guess. Getting more
   real key-moment data into the corpus would likely help; unverified.

## 4. Non-functional status

- Latency: real p50/p95 numbers exist (`scripts/bench.py`), not reproduced
  here since they drift run-to-run — regenerate, don't trust a pasted number.
- CORS: localhost-only, tested.
- No 7-day `/health` uptime soak test — not producible in one sitting,
  not claimed.

## 5. Explicitly out of scope for this PRD

Anything from the original report's Phase 2-4 roadmap (live streaming,
user accounts, multi-competition support, commercial licensing). Not
revisited until everything in §3 is closed, same rule as the original PRD.
