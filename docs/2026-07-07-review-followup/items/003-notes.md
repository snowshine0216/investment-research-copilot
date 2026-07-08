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

- **2026-07-07 pr-review FAIL round (`claude/review-followup-003`, this round):** independent
  `/code-review` second pass (PR #214) FAILed on 3 findings in the same three CLAUDE.md
  bullets (`:113-115`), all fixed in one commit. (1) "shipped green for weeks" was an
  invented, unverified duration — `git log` shows the rotation module + `tests/rotation/
  test_seed.py`'s masking test data were introduced together in `b1ae820f` (#206,
  2026-07-05) and the join fix landed `76359c69` (#208, item 004) on 2026-07-07: a 2-day
  window, not weeks. Reworded to "shipped green while the join was dead" — true regardless
  of elapsed time, and the actual defect (dead code path masked by unrepresentative test
  data), not a duration claim. (2) The bullet's bare word "fixture" (used 4×, incl. the
  title) collided with `CONTEXT.md:42`'s explicit instruction to avoid the bare term
  (it collides with pytest fixtures and the distinct "AkShare fixture" glossary entry at
  `CONTEXT.md:178`) — every bare occurrence replaced with "test data" ("Production-shaped
  fixtures" → "Production-shaped test data", etc.); meaning unchanged. (3) The citations
  "(review §4.4)" and "(review §4.3 / M-1)" referenced subsection numbers that don't exist
  in `docs/2026-07-07-workflow-review.md` — its "## 4." section is a plain numbered list
  (items 1-7), not headed subsections. Re-pointed to the real anchors: "(review §4, item 4)"
  for the assembly-checklist bullet and "(review §4, item 3 / M-1)" for the contract-
  sentences bullet (content mapping was already correct; only the notation was wrong).
  Verification: `grep -c fixture CLAUDE.md` → 0; Conventions bullet count still 10;
  `grep "§4\.3\|§4\.4" CLAUDE.md` → 0; `uv run pytest tests/docs/ -q` → 9 passed.

- **2026-07-07 Codex finding round (same branch, one more wording-precision fix):** the
  clause "must be copied from a real on-disk artifact (a real `data/**` store or cache
  file)" could be read as tests READING live mutable `data/**` at runtime — conflicting
  with fast/isolated/deterministic tests and effects-at-edges. Intended meaning (what this
  run's tests actually did, e.g. `tests/notify/fixtures/*.json`): commit a minimal snapshot
  DERIVED from a real artifact into the test tree; never read live `data/**` in unit/
  assembly tests. Clause tightened to: "must be a **committed snapshot copied/reduced from
  a real artifact** (e.g. a trimmed copy of the real `data/**` store or cache file, checked
  into the test tree) — tests never read live `data/**` at runtime." Everything else in the
  bullet untouched. Verification: bullet count still 10; `uv run pytest tests/docs/ -q` →
  9 passed.
