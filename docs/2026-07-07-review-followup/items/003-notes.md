# Item 003 — implementation notes

- **2026-07-07 follow-up (review-driven rewording, meaning unchanged):** two independent
  reviewers proved three wording loopholes in the rules landed by this item, fixed on
  `claude/review-followup-003` in one commit. (1) Production-shaped fixtures bullet —
  "integration fixtures" collided with the repo's reserved `-m integration` pytest marker
  (a cold reader could exempt plain unit tests, the exact class that produced R-1), and the
  absolute "never hand-crafted" outlawed legitimate deliberately-adversarial edge-case
  fixtures (e.g. `tests/rotation/test_resolve_candidates.py`, `tests/notify/test_health.py`);
  reworded to scope by purpose (normal-shape fixtures, any tier) with an explicit exemption
  for adversarial fixtures, R-1 "BK1" citation kept verbatim. (2) Assembly assertion
  bullet — added a clause cross-referencing the FACTS.md known trap that
  `tests/commands/` hangs as a whole directory, so new wiring tests must be invoked
  per-file. (3) FACTS.md preamble — the "currently set/unset env var" category had entries
  (`IRC_HTTPS_PROXY`, `MINIMAX_MODEL`) with no cited verify command; added the generic
  `grep -oE '^NAME=' .env` recipe directly to the preamble sentence so every entry in that
  category has a runnable command by construction. No rule's locked meaning changed.

Both tasks executed exactly per `003-plan.md`: three CLAUDE.md Conventions bullets
(production-shaped fixtures / assembly assertion per feature / contract sentences name
their test) inserted verbatim directly after the TDD bullet, and the FACTS.md preamble
live-incident rule appended verbatim as a `>` paragraph before `## Services & endpoints`.

Anchors matched the plan's expectations on first read (no re-anchoring needed — item 002
had left both target regions unchanged as documented). All three CLAUDE.md citations
(R-1 "BK1" fixture at `tests/rotation/test_seed.py:88`, the M3 "under-wired runner/metrics
ASSEMBLY" lesson, M-1 prose-only flow-freshness contract) and the FACTS.md F8
"stale within 2 days" citation were spot-verified against
`docs/2026-07-07-workflow-review.md` before committing and are accurate.

Verification greps from the plan matched expected output exactly (Task 1: 3 lines inside
Conventions, bullet count 10; Task 2: rule line 8, first `## ` section header line 17).
`uv run pytest tests/docs/test_version_sync.py -q` stayed green (8 passed) — CLAUDE.md/
FACTS.md are not guarded surfaces but no accidental damage occurred.
