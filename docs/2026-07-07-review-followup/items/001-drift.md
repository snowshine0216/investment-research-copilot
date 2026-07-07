Verdict: PASS

Subagent: sonnet
Plan checklist items: 57
Verified present in diff: 57

## Method

Read `001-plan.md` (7 tasks, 57 `- [ ]` steps) and `001-notes.md` (5 pre-triaged
deviations) in full, read spec §3/§4/§5/§9 (`docs/superpowers/specs/2026-07-07-data-health-notify-design.md`),
then diffed `autodev/review-followup-feature...claude/review-followup-001` in full
(29 files, +4409/-21) and checked every plan code block / test / doc edit against
actual diff lines. Re-ran the full notify/ops suite (`158 passed`), ruff
feature-scope (`All checks passed!`), the CLI smoke test, and live-reran the
AC1 runtime-proof command against real `outputs/2026-07-07/` — output matches
`001-runtime-proof.md` verbatim.

## Task-by-task

- **Task 1** (`health.py` types + `recent_trading_days` + `monitor_health`) — OK.
  `src/irc/notify/calendar.py`, `src/irc/notify/health.py` match plan code blocks
  verbatim; 6 fixtures created as specified. Commit `821d28f6`.
- **Task 2** (`rotation_health`/`detect_rotation_recovery`/`weekly_health`) — OK,
  verbatim match. Commit `24014c6a`.
- **Task 3** (classifier `degraded` + `RunOutcome.health`/`force_notify`) — OK,
  verbatim match. Commit `e04956a6`.
- **Task 4** (edge wiring `notify_health.py` + `notify_cmd.py` + CLI choice) — OK,
  verbatim match plus one review-fix round. Commits `6ebab493`, `4c8b739c`.
- **Task 5** (`run-flow-capture.sh` notify tail + wrapper test) — OK, verbatim
  match. Commit `d9a77969`.
- **Task 6** (ADR 0016 amendment + doc syncs + CHANGELOG + TODOS) — OK, verbatim
  match plus one review-fix round. Commits `47eeba54`, `8976b484`.
- **Task 7** (AC1–AC5 runtime proof) — OK. `001-runtime-proof.md` captures all
  5 ACs + full regression + ruff; AC1 independently re-executed live in this
  review, output identical. Commit `57b41fe2`.

Commit map: 6 task commits (1,2,3,4,5,6) + 1 Task-7 proof commit + 2 review-fix
commits = 9, matching "7 tasks + 2 review-fix rounds." A 10th commit
(`90df2b0e`, `001-notes.md`) is process documentation of this same review-followup
item, not a plan step — no functional content, not scope creep.

## Deviations (independently re-judged against locked spec §9, not just notes' triage)

1. **T1 — `_flow_items` `at_newest < total` guard** (`health.py`). The plan's
   literal code would fire `flow_symbol_stale` even when ALL symbols are
   uniformly stale (no minority outlier), contradicting its own
   `test_monitor_health_run_level_lag_is_warn` (uniform staleness must render
   `flow_stale`, not `flow_symbol_stale`) and G-Q5→B's rationale text ("any
   store symbol whose newest row >3 td old"... but locked *specifically to
   catch a minority outlier missed by the run-level rule* — spec §3.1 table row
   "any store symbol's newest row > 3 trading days old" is stated as an
   addition alongside, not a replacement for, the run-level rule). Verified:
   the added guard makes both directions correct per G-Q5→B's own dual-check
   design. **Accepted**, spec-faithful — cites §9 G-Q5→B + §3.1 table.
2. **T3 — `HealthDigest` import in top import group** (`types.py`). Cosmetic
   placement (ruff import-order convention) vs. the plan's brief mid-file
   suggestion. **Accepted**, no functional effect.
3. **T4 — fixture enrichment (`test_monitor_run_kind.py`,
   `test_run_kind_promotions.py`) + weekly cold-machine fix** (`4c8b739c`).
   Spec §3.3 mandates `_build_outcome` unconditionally attach health for
   monitor/weekly (not gated on artifact presence); 3 pre-existing tests staged
   `monitor.json`/`decision_report.json` without the newly-required
   `eval_trace.json`/`gold_regime.json`, so they naturally degrade to
   `health_unknown` → `degraded`. The chosen fix enriches fixtures to the
   real co-present-artifact shape (matches how `monitor_cmd`/`gold` stages
   actually write) rather than weakening the always-on wiring §3.3 requires.
   The follow-up cold-machine fix closes the same gap for weekly's "no
   `outputs/<date>/` at all" branch, symmetric with monitor/flow-capture.
   Re-verified live: `test_weekly_cold_machine_attaches_health_unknown` passes;
   severity stays `failed` (today_dir_exists precedence unaffected).
   **Accepted** — spec §3.3 over §4's aspirational "keep passing with
   `health=None`" bullet, which described intent for direct-`RunOutcome`
   classify tests, not `_build_outcome`-mediated edge tests.
4. **T6 — ops/launchd/README.md rotation-timeout row correction beyond the
   literal edit list** (`8976b484` + the same-commit rotation-step row edit in
   `47eeba54`). Plan Task 6 Step 2 only specified the flow-capture schedule row
   + a new timeout-table row; the adjacent rotation-step timeout row said
   "does NOT page," which the new missing-`rotation_radar.json`-sentinel path
   makes false (a rotation kill before the sentinel is written now yields
   `today_dir_exists=False` → severity `failed`, confirmed by reading
   `_decide()` in `classify.py`). Leaving it uncorrected would self-contradict
   the same table. **Accepted** — factual correction, verified true against
   `_flow_capture_outcome`/`_decide`.
5. **T7 — AC1 "clean" → "degraded" reconciliation**. Spec §5 AC1 literally says
   severity "stays `clean`"; G-Q5→B (§9) is locked using the exact 688072@
   2026-06-26 case as its motivating example, and it is LAW over the AC's
   parenthetical. Plan's Global Constraints section documents this
   reconciliation before Task 7 runs; runtime-proof Step 1 asserts `degraded`
   and both required substrings. **Accepted**, spec §9 outranks §5's example
   text.

All 5 deviations independently confirmed correct against the diff and the
locked spec — no amendment needed beyond what the implementer already recorded
in `001-notes.md`.

## Scope check

Diff files beyond the plan's explicit File Structure list: `tests/notify/test_monitor_run_kind.py`,
`tests/notify/test_run_kind_promotions.py` (both T4 fixture-enrichment, functional
necessity — see above) and `tests/notify/fixtures/rotation_radar_abstain_0705.json`
(created per the plan's own Task-1 Step-1 script; unreferenced by any test — a
dead but harmless fixture, not an implementer addition). No functional scope
creep found.

## Runtime-proof file

`docs/2026-07-07-review-followup/items/001-runtime-proof.md` exists, covers
AC1–AC5 + full regression (158 passed) + ruff (feature-scope clean); AC1 was
re-executed live in this review and matches verbatim.
