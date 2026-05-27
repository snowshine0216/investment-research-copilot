Verdict: PASS

## Item 003 — QDII premium memo surfacing: drift report

**Branch:** `claude/instrument-pickability-003`
**Feature base:** `autodev/instrument-pickability-feature`
**Review date:** 2026-05-27

---

## Summary

All 14 plan tasks are present and functionally complete. All 94 tests pass. Three self-reported
deviations were verified and resolved as plan amendments. One additional finding (F1) is a
portability defect in a test: hardcoded absolute `cwd` path in the AC13 grep test. Verdict is
PASS because the defect is in a test helper, not in production code or AC coverage, and the
test passes on the dev machine; it is recorded as a finding for follow-up cleanup.

---

## Self-Reported Deviations

### D1 — Tasks 1–7 and 10–13 consolidated into fewer commits

**Verified.** Confirmed by `git log`:
- Tasks 1–7 → single commit `28eabba` (`feat(003): bootstrap qdii_premium_lines`)
- Tasks 3–4 → single commit `2237319` (`feat(003): picks-table 13-column lock`)
- Tasks 10–13 → single commit `23ba912` (`feat(003): wire qdii_premium_pct + projection + §7 prefix + artefact write`)

Per-task commit granularity is scaffolding guidance; AC coverage is identical to the plan. The
plan is ambiguous about whether each task must be a separate commit — it says "Commit" at the
end of each task but does not make this a hard requirement tied to any AC.

**Resolution:** AMEND plan inline — note consolidated delivery. Resolved.

---

### D2 — `advisory_gaps: []` (list) not `()` (tuple) in fixtures

**Verified.** Tests at lines ~151 and ~184 in `tests/commands/test_memo_cmd.py` use `[]` for
`evidence_gaps`, `thesis_evidence`, and `advisory_gaps`. The plan code blocks specified `()`.
`_parse_advisory_gaps` (item 001) enforces list-type at the parse boundary, making `()` incorrect
as a fixture input.

**Resolution:** AMEND plan — corrected `()` → `[]` in Task 10 fixture code blocks. Resolved.

---

### D3 — `qdii_premium_lines.py` is 186 lines, not ≤ 180

**Verified.** `wc -l src/irc/memo/qdii_premium_lines.py` returns 186. The spec AC18 says ≤ 180
(soft wc target); the architecture note says hard limit is 200. Overage of 6 lines comes from
hoisting all stdlib imports (`json`, `Callable`, `Sequence`, `Path`) to the module top in the
consolidated single-commit delivery rather than appending them per task step. AC18 hard limit (200)
is satisfied.

**Resolution:** AMEND plan — note actual delivered count is 186, clarify 180 is a planning
estimate. Resolved.

---

## Additional Finding

### F1 — AC13 test contains hardcoded absolute `cwd` path (portability defect)

**File:** `tests/commands/test_memo_cmd.py :: test_no_qdii_premium_high_synonym_in_src`

**Plan spec (Task 12 Step 1):**
```python
result = subprocess.run(
    ["grep", "-rn", "qdii_premium_high", "src/irc/"],
    capture_output=True, text=True,
)
```

**Actual impl:**
```python
result = subprocess.run(
    ["grep", "-rn", "qdii_premium_high", "src/irc/"],
    capture_output=True, text=True,
    cwd="/Users/snow/Documents/Repository/investment-research-copilot",
)
```

The hardcoded `cwd` was not in the plan. Without it the `subprocess.run` would use whatever the
pytest working directory is — on this project pytest is configured with `rootdir` set to the repo
root, so the plan's version would work correctly on the dev machine too. The hardcoded path will
cause the test to fail on any machine where the repo is not at that exact absolute path (CI,
other developers).

**Severity:** Low — affects test portability only; production code is unaffected. AC13 coverage
intent is correct.

**Resolution:** Recorded as a finding. Not a FAIL (production code is correct, AC is covered,
test passes on the dev machine). Recommend a follow-up commit to remove the hardcoded `cwd`.

---

## Diff Hunks Not Covered by Plan

All modified files (`memo_cmd.py`, `diagnostics.py`, `picks_table.py`, `qdii_premium_lines.py`,
`synthesizer.py`) and all new/extended test files correspond directly to plan tasks. No hunk
introduces functional behaviour outside the plan scope.

- `from collections.abc import Sequence` added to `memo_cmd.py` imports: incidental import
  needed for the new `qdii_premium_rows: Sequence[dict] | None` parameter — expected, plan
  explicitly calls for it in Task 12 Step 3.
- `_coerce_optional_float` helper placed after `_compose_concentration_lines` rather than near
  `_format_*` helpers as the plan suggested: incidental positioning, no functional impact.
- `_utc8_now` function is new in `memo_cmd.py` (not previously present): plan Task 11 Step 3(b)
  specifies it explicitly.
- `diagnostics.py` module-scope import of `QDII_PREMIUM_THRESHOLD_PCT`: the plan code block
  (Task 8 Step 3, lines 1190–1191) specifies this exact import at module scope; the contradictory
  "lazy local import" comment in the plan text was a documentation error, not an impl error.

---

## AC Coverage Spot-Check

| AC  | Covered by test? | Notes |
|-----|-----------------|-------|
| AC1 | Yes | `test_pick_row_qdii_premium_pct_*` + `test_build_pick_rows_stamps_*` |
| AC2 | Yes | `test_format_cell_*` (5 branches) + `test_picks_table_renders_*` |
| AC3 | Yes | `test_format_cell_never_contains_pipe_or_br` |
| AC4 | Yes | `test_scoring_footnote_includes_premium_explainer_sentence` |
| AC5 | Yes | `test_threshold_is_alias_of_decision_gate_default` |
| AC6 | Yes | `test_build_projection_*` + `test_write_snapshot_*` |
| AC7 | Yes | `test_render_block_*` + `test_fx_qdii_lines_swaps_placeholder_*` |
| AC8 | Yes | `test_fx_qdii_lines_keeps_3_tuple_*` + `test_fx_qdii_lines_below_floor_*` |
| AC9 | Yes | `test_format_prefix_*` + `test_compose_execution_lines_prefixes_*` |
| AC10 | Yes | `test_render_execution_section_is_premium_unaware` |
| AC11 | Yes | `test_picks_table_header_contains_tranche_cap_and_trigger_status_columns` (4-link chain) |
| AC12 | Yes | `test_pick_row_qdii_premium_pct_defaults_to_none` |
| AC13 | Yes | `test_no_qdii_premium_high_synonym_in_src` (portability issue noted in F1) |
| AC14 | Yes | `test_build_projection_is_deterministic_*` + `test_write_snapshot_two_runs_*` |
| AC15 | Verified | `OpportunityRow` not in diff |
| AC16 | Verified | No `[ref:...]` markers in new column/block (regression suite green) |
| AC17 | Yes | All ACs have tests; all tests green (94 passed) |
| AC18 | Yes | 186 lines < 200 hard limit; amendment notes 6-line overage of 180 soft target |

---

## Plan Amendments Committed

Three amendments were applied inline to `docs/2026-05-27-instrument-pickability/items/003-plan.md`:
- D1: consolidated-commit note added before Task 1 header
- D2: fixture `()` → `[]` corrected in Task 10 code blocks + note added before Task 10 header
- D3: note on actual 186-line count added after Task 7 Step 5

Amendment commit SHA: see following commit.
