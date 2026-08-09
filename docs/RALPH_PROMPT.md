# RALPH_PROMPT.md — NPL NSW Intelligence Engine

You have no memory of previous iterations. Everything you know about this
project's state must come from the repo itself — read `docs/PRD_v2.md`
section 3 ("Open items") and the actual code/tests, not from anything you
"remember."

## Your task this iteration

1. Run `pytest tests/ -v` and `python scripts/compute_detection_metrics.py`
   to confirm current state actually matches what PRD_v2.md §3 claims. If
   it doesn't match, fix the PRD, not reality — do not paper over a
   regression.
2. Pick the **single highest-priority open item** from PRD_v2.md §3 that
   you can make real, verifiable progress on *without* asking a human for
   something only they can provide (API keys, transcripts, database
   credentials, product decisions). If every remaining open item needs
   human input, say so explicitly and stop — do not invent scope to fill
   the iteration.
3. Implement the smallest change that makes real progress on that one item.
4. Verify it: run the actual tests/scripts that prove it, not just "it
   looks right." If you can't verify something (e.g. it needs live
   internet this sandbox doesn't have), say that explicitly instead of
   claiming success.
5. Update PRD_v2.md §3 to reflect the new real state — move the item,
   narrow it, or close it, with the evidence (test name, command output)
   that justifies the change.
6. Commit with a message that states what changed and how it was verified.
   Do not write "implemented X" without also stating how you know it works.

## Hard rules

- Never mark something done because it "should work" — only because a
  command you ran proved it.
- Never soften or remove an honest limitation from the README/PRD to make
  progress look bigger. Removing a caveat requires a verification that
  disproves it, not just discomfort with admitting it.
- If you find a bug while validating something else (this has happened
  twice already — a false positive and a stopword-filtering bug were both
  found this way), fix it in this iteration rather than filing it away,
  as long as it's small. If it's large, note it as a new item in PRD_v2.md
  §3 instead of scope-creeping the current task.
- One concrete unit of work per iteration. Do not try to close multiple
  open items in one pass — the next iteration exists for that.
- Stop and end your turn once steps 1-6 are done. Do not keep going onto a
  second item in the same iteration.
