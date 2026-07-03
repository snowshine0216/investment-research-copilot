Verdict: PASS

## Subagent

Doc-sync verification subagent, dispatched by autodev, 2026-07-03, branch
`autodev/todos-critical-fixes-feature` (base `main` @ 221a34e4).

## Items reviewed

001 (macro `attribution_strength` hardening), 002 (dual-leg thesis gate for
`ActiveFundSnapshot`), 003 (stale TODO, doc-annotation only — no grill), 004
(fund-level evidence repair probe), 005 (dead `narrative.py` deletion,
user-authored spec, no grill).

## Doc changes verified (per doc, per item)

**CONTEXT.md** (`git diff 221a34e4...HEAD -- CONTEXT.md`, 16 changed lines):
- 001: no new/changed term (below ADR bar per grill) — confirmed no term added
  for the isinstance hardening; only unrelated annotation-sync edits present
  (report-v3 "not yet built" → "shipped 2026-07-03" ×4, dual-track "not yet
  built" → "built 2026-06-21", "(ADR 0022 when written)" → "(ADR 0022.)",
  "(ADR 0017 addendum when built)" → "(ADR 0017 addendum)") — these are
  001-grill housekeeping, not item-001 functional coverage, and correctly so.
- 002: new term **"Dual-leg thesis heuristic"** added (Monitor set / dual-coverage
  gate section), covering presence-only union, empty-flattened-guard-first
  ordering, insufficient-not-under_pressure choice, and an _Avoid_ note
  distinguishing it from the dual-coverage gate. Matches grill R6.
- 004: new term **"Fund-level evidence repair (repair probe)"** added after
  "Fail-closed freshness probe", describing the 4-call fund-level-only refetch,
  leg-wise monotone merge, `foreign_heavy_fund_level_gap` predicate, and the
  `FetchPlan.active_fund_fund_level_repair` budget class. Cross-reference
  sentence appended to "Foreign-heavy fund (rule 2.5 short-circuit)" pointing
  at the repair entry. Matches grill R7.
- 005: no CONTEXT.md entry expected or made (nothing asserted the module
  existed) — confirmed no diff hunk targets narrative.py-related terms.

**docs/adr/0003-failure-mode-policy-b.md** (28 changed lines):
- Status line amended to record the 2026-07-03 amendment (item 002, §8 added).
- New **§8 "Thesis-level dual-leg union for `ActiveFundSnapshot`"**: context,
  decision (3 locked properties — union not constituent-only, presence-only,
  empty-flattened-guard-first), 3 rejected alternatives, literal-exposure note.
  Matches grill R7 (ADR bar met: hard-to-reverse / surprising / real trade-off).
- §7 "Fetch budget impact" corrected: stale "2 additional AkShare calls (~100)"
  → "4 additional AkShare calls (~200)", with an inline note explaining the
  original figure predated the three-endpoint announcement union. New §7
  addendum paragraph "Fund-level evidence repair on the cached-serve path —
  2026-07-03" describing `_maybe_fund_level_evidence_repair`, the leg-wise
  merge, no-backoff rationale, and the budget-class accounting. Matches
  grill R7/R2 (item 004) and the MASTER-SPEC's explicit expectation of "the
  corrected 4-call math."
- 001: no ADR touch expected (below bar) — confirmed absent.
- 005: no ADR touch expected — confirmed absent.

**CHANGELOG.md** (`[Unreleased]`, 77 new lines, no VERSION bump — confirmed
VERSION file unchanged at 0.9.3):
- 001: `### Fixed` entry — macro narrative non-str `attribution_strength` now
  consumes the schema-retry budget instead of degrading the whole block;
  names the guard, the retry mechanics, and that the gather-level `except`
  tuple is deliberately unchanged.
- 002: `### Fixed` entry — dual-leg check extended to the `ActiveFundSnapshot`
  branch; names the union, the empty-flattened guard, the new CONTEXT.md term,
  and the ADR 0003 §8 addendum; explicitly states no new `ThesisState` literal,
  no new gap code, no VERSION bump.
- 004: `### Fixed` entry — repair probe for foreign-heavy cached snapshots;
  names the predicate, the leg-wise merge, the budget class, the corrected
  trigger condition (rule-2.5 leg-gap mirror vs. the TODO's literal `== ()`),
  and the ADR 0003 §7 addendum / stale-count fix.
- 005: `### Removed` entry — `src/irc/monitor/narrative.py` deletion, reason
  (production-dead since report v3, latent TypeError twin of the item-001 bug
  class), and the test cleanup (mirror tests + stale monkeypatch scaffolding).

**TODOS.md** (8 changed lines):
- 001 (TODOS.md line ~15, Reliability section): `[ ]` → `[x]`, with a
  **Resolved 2026-07-03:** annotation naming the isinstance guard, the retry
  mechanics, and the new test names.
- 002 (TODOS.md line ~51): `[ ]` → `[x]`, with a **Resolved 2026-07-03:**
  annotation naming the union check, the empty-flattened guard, ADR 0003 §8,
  the CONTEXT.md term, and the new test names (including the corrected file
  location `opportunity/thesis_evidence.py`, not `states.py`).
- 004 (TODOS.md line ~21): `[ ]` → `[x]`, with a **Resolved 2026-07-03:**
  annotation naming the corrected trigger (rule-2.5 leg-gap mirror, not the
  TODO's literal `== ()`), the repair module, the merge semantics, and the
  new test names across 3 test files.
- 003 (Opportunity-filtering line): `[ ]` → `[x]`, annotated
  **Resolved 2026-07-03 (verified as-built — stale entry, no code change):**
  naming `_build_input`/`inputs_build.py`, the `opportunity_cmd.py:1497`
  wiring, PR #25's deliberate reversal of the downgrade-gate half, and the
  locking test `test_venue_incompatible_does_not_block_core_dca`.
- 005: no TODOS.md entry existed or was required (per item spec AC7 — it was
  flagged only in item-001's spec Non-goals) — confirmed no stray edit added.

**README.md**: no changes — correctly so; nothing in README.md referenced any
of the changed behaviors, the deleted module, or the corrected call counts
(grep below).

## Stale-reference sweep (step 5)

- `grep -rn "narrative\.py" README.md docs/monitor/README.md` → zero hits.
- `grep -rn "gather_narrative" README.md docs/monitor/README.md` → zero hits.
- `grep -rn "2 additional AkShare\|~100" README.md docs/monitor/README.md CONTEXT.md` →
  zero hits (the only place this claim ever lived was ADR 0003 §7, now corrected).
- `grep -rn "monitor\.narrative\b\|from irc\.monitor\.narrative" src/ tests/` →
  zero hits; all remaining `narrative_macro` references are the surviving,
  unrelated module (word-boundary-excluded per item 005 AC4).
- Historical run-dir archives under `docs/2026-06-*`/`docs/2026-07-02-*` still
  mention `narrative.py`/`gather_narrative` — these are point-in-time specs/
  plans for already-shipped work, not living documentation, so they are out
  of scope for this sync check.

## Missing coverage

None.

## Manual fix path

N/A (Verdict: PASS).
