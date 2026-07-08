Verdict: PASS

Subagent: sonnet
Source: /verify (invoked — repo has no dedicated `verifier-*`/`run-*` skill for
this vertical; the skill's own guidance to prefer a live CLI/socket surface was
weighed against this item's spec (AC6: "documented, re-runnable proof against
live artifacts... EM egress NOT required") and against not wanting to mutate
real production state — see "Entry point" note below). Fallback used: direct
entry-point exercise per the dispatch's steps 2a-2c (independent offline
replay + production `resolve_candidates()` entry point + warning-log check).

Entry point exercised: an offline replay script, reconstructed independently
in this dispatch (not copy-pasted verbatim from 004-plan.md Task 5, though
structurally equivalent) at
`/private/tmp/claude-501/.../scratchpad/replay_004_verify.py` (run then
deleted — scratchpad only, per spec's "no committed heavy fixture" rule),
executed via `uv run python <script>` from the repo root against the REAL
on-disk artifacts:
- `data/rotation/board_series.json` (2.9MB, 200 boards)
- `data/monitor/stock_industry_map.json` (699 symbols, 103 行业 names)
- `data/narrative_holdings/` (479 cached fund files)

pinned `today = "2026-07-07"`, no network calls. The script drives the real
`_build_states` (from `irc.commands.rotation_cmd`) to get real `BoardState`s
from the real board series, then calls the production
`irc.rotation._cmd_helpers.resolve_candidates()` (the exact function
`run_rotation` calls at `rotation_cmd.py` line
`candidates, new_ids, cand_diag = resolve_candidates(root, states, membership, today=_today)`)
— i.e. the actual CLI-invoked entry point, not a lower-level helper — plus a
hand-rolled pre-fix/post-fix comparison via `build_exposure`/`rank_candidates`
directly, to reproduce the two-sided (pre-fix vs post-fix) invariant check
mandated by AC6. Did NOT run `uv run irc rotation` itself: that orchestrator
(a) requires a live `fetch_board_spot` network call the spec explicitly waives
for this proof ("EM egress NOT required"), and (b) calls `append_snapshot` on
the real `data/rotation/board_series.json`, mutating production state — out of
scope for a smoke test. `resolve_candidates()` is the same production function
the CLI calls, fed 100% real data, which is the closest offline-safe
approximation of the real entry point.

Observed behavior (raw script output, exit code 0):

```
active_boards=21 funds=446 seen_syms=699 unresolved_names=0
PRE-FIX  candidates=0 coverage=67.8016 unmapped=331
POST-FIX candidates=38 raw_pre_cap=111 coverage=67.8016 unmapped=331
per_board(raw active >=10%)={'BK1036': 69, 'BK0465': 19, 'BK0727': 15, 'BK0474': 3, 'BK1044': 3, 'BK0473': 1, 'BK1259': 1}
ALL INVARIANTS PASS (independent reconstruction)
resolve_candidates() via prod entry point: candidates=38 diag={'holdings_cache': 'ok', 'holdings_coverage_pct': 67.8016, 'unmapped_syms': (...331 symbols incl. '00700'...)}
captured WARNING log output: ''
NO FALSE-ALARM WARNING ON HEALTHY DATA -- CONFIRMED
```

This reproduces (not merely repeats) the numbers recorded in
`docs/2026-07-07-review-followup/items/004-notes.md` (candidates=38,
raw_pre_cap=111, identical per-board breakdown) run independently in this
dispatch on the same date — the drift the spec warned about (96/34 →
108-111/35-38) has stabilized at today's snapshot; no further drift observed
between the recorded evidence and this re-run.

- AC1 (translate at join) — observed: `src/irc/rotation/_cmd_helpers.py:121-125`
  builds `name_to_code = {b.board_name: b.board_code for b in states}` and
  `stock_to_code = {sym: name_to_code[nm] for sym, nm in stock_to_name.items() if nm in name_to_code}`
  before `build_exposure(funds, stock_to_code)` (line 126). Replay confirms every
  `per_board` key is BK-prefixed (`BK1036`, `BK0465`, ...) and the committed test
  `test_resolve_candidates_translates_name_to_board_code` asserts
  `all(c.board_code.startswith("BK") for c in candidates)` — PASSED.
- AC2 (dead param removed) — observed: `src/irc/rotation/exposure.py:17-20`
  signature is `build_exposure(funds: Iterable[Fund], stock_to_board: Mapping[str, str])`
  (2-arg). `grep -rn "board_names" src/ tests/` → no output (dead param fully gone).
- AC3 (false docstring corrected) — observed:
  `src/irc/monitor/industry_map_store.py:16-22` now reads "the SAME store holds
  东财行业 NAMES (f100) in the `industry` slot for BOTH consumers... never board
  codes. The radar translates 行业 name → EM board code at its OWN join
  (`rotation._cmd_helpers.resolve_candidates`...)" — no residual "codes stored
  in industry slot" claim.
- AC4 (production-shaped integration test, TDD red-first) — observed:
  `tests/rotation/test_resolve_candidates.py::test_resolve_candidates_translates_name_to_board_code`
  PASSED (non-empty, code-keyed candidates) and
  `::test_prefix_names_as_codes_yield_zero_candidates` PASSED (pre-fix shape →
  0 candidates, the regression guard). Both use production-shaped
  `{"industry": "白酒", "seen_at": ...}` rows via `record_seen`/`load_store`.
- AC5 (`test_exposure.py` → 2-arg) — observed via `git diff main...HEAD --
  tests/rotation/test_exposure.py`: all 3 `build_exposure(...)` call sites
  dropped the dead third positional arg; `s2b` values unchanged (already BK
  codes). `uv run pytest tests/rotation/test_exposure.py -v` → 3 passed.
- AC6 (offline replay runtime proof, invariant-gated) — observed (this
  dispatch's independent re-run, see full output above): `len(cands_pre) == 0`,
  `len(cands) == 38 > 0`, `raw_pre_cap == 111 >= 38`, `max(per_board.values())
  == 69 > CAND_TOP_N(10)`, `unresolved_names == 0` — every invariant gate in
  the spec's corrected AC6/Q2 held; process exited 0 with "ALL INVARIANTS
  PASS" printed.
- AC7 (unmapped/HK degrade unchanged; coverage byte-identical pre/post) —
  observed: `diag_pre["coverage_pct"] == diag["coverage_pct"] == 67.8016`
  and `unmapped == 331` both sides, byte-identical as the spec requires (G2/G4);
  `'00700'` (HK ticker) present in `unmapped_syms` from the production
  `resolve_candidates()` call, confirmed by the committed test's
  `assert "00700" in diag["unmapped_syms"]` — PASSED.
- AC8 (no version bump) — observed: `grep -n "RADAR_VERSION\|SCHEMA_VERSION"
  src/irc/rotation/report.py` → `SCHEMA_VERSION = 1`, `RADAR_VERSION = 1`
  (unchanged); `cat VERSION` → `0.9.3` (unchanged); CHANGELOG accumulates
  under `[Unreleased] > Fixed`, no version-file diff.
- AC9 (TDD + budgets; per-file pytest only) — observed:
  `uv run pytest tests/rotation/test_exposure.py tests/rotation/test_candidates.py
  tests/rotation/test_resolve_candidates.py tests/rotation/test_seed.py
  tests/monitor/test_industry_map_store.py -v` → **26 passed** (0 failed, 0
  skipped) in 0.36s, run per-file per FACTS.md's documented `tests/commands/`
  whole-dir hang trap (never invoked here). `uv run ruff check src/irc/rotation
  tests/rotation src/irc/monitor/industry_map_store.py` → `All checks passed!`.
  File sizes: `_cmd_helpers.py` 134 lines, `exposure.py` 48 lines,
  `industry_map_store.py` 105 lines — all well under the 200-line budget.
  `resolve_candidates()`'s own body (excluding the extracted
  `_translation_warnings` helper) is ~17 lines — slightly over the spec's
  original "~2 lines added" estimate because the accepted post-review addendum
  (b37bc4cb, warn on dropped/duplicate translations) added one call line plus
  a separate `_translation_warnings` helper (kept under ~15 lines, its own
  function) — not a budget violation, both functions individually stay under
  the ~20-line ideal.
- Additional check (dispatch step 2c, warning behavior) — observed: with the
  real, healthy 07-07 data (`unresolved_names=0`, no duplicate board names in
  the real 200-board set), the captured `irc.rotation._cmd_helpers` logger
  WARNING output was the empty string `''` — confirms `_translation_warnings`
  does NOT fire false alarms on healthy production data, matching the two
  targeted unit tests (`test_resolve_candidates_warns_on_dropped_name_translation`,
  `test_resolve_candidates_warns_on_duplicate_board_name`) which PASSED using
  synthetic unhealthy fixtures instead.

Findings (verify-skill style — noticed while driving the replay, not gating):
- 🔍 Probed the "no live CLI" boundary deliberately: confirmed `run_rotation`
  (`rotation_cmd.py`) requires a `fetch_spot` callable (defaults to the live
  `fetch_board_spot`) and unconditionally calls `append_snapshot` on the real
  `data/rotation/board_series.json` — running the actual `irc rotation`
  command would both need network (waived by spec) and mutate production
  state (undesirable for a verify pass). Confirms the dispatch's chosen
  offline-replay-via-`resolve_candidates()` entry point is the correct
  smoke-test surface for this item, not a corner cut.
- The independent re-run's numbers (38/111) matched 004-notes.md's recorded
  numbers (38/111) exactly on 2026-07-07 — no further drift since the
  original replay was recorded earlier the same day; this is expected, not a
  finding of concern (both runs read the identical on-disk artifacts).
- `resolve_candidates()`'s `unmapped_syms` diagnostic (from the production
  entry point) contains a very long tail of HK/US tickers (roughly 330
  symbols) — expected per AC7 (the fix targets *candidates*, never the
  unmapped/coverage diagnostic), consistent with the git-tracked
  `outputs/2026-07-06/rotation/rotation_radar.json`.
- No regressions found in adjacent test files (`test_seed.py`,
  `test_industry_map_store.py`) — all pass, confirming the store-side (Q5:
  "no change to seed/series_store/monitor") locked decision held.

Failures: none.
