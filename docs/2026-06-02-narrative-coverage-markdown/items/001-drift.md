Verdict: PASS

Subagent: sonnet
Plan checklist items: 10 tasks / ~46 steps (Tasks 1–10)
Verified present in diff: all 10 tasks, all key steps

---

## Per-task verification

### Task 1: Kill-switch reader (AC4 partial)
Status: OK
- `_narrative_autobuild_on()` present at `narrative_autobuild.py:26-28` — exact match to plan body.
- Tests `test_autobuild_on_default_true` + `test_autobuild_off_when_env_zero` at `test_narrative_autobuild.py:6-13`.
- Module created at `src/irc/commands/narrative_autobuild.py`.

### Task 2: Eligibility + look-through target builder (AC1)
Status: OK
- `_is_eligible` at `narrative_autobuild.py:34-36`; `_target_for_row` at `:39-45`.
- `_ACTIVE_ASSET_CLASS = "cn_equity_fund"` at `:32`.
- Tests `test_eligible_only_for_cn_equity_fund` + `test_target_for_row_matches_active_fund_shape` present.

### Task 3: Per-fund build + cache-write helper (AC5, AC6 partial)
Status: OK
- `_build_and_cache_one` at `narrative_autobuild.py:48-76` — matches plan body exactly:
  - `replace(snap, cache_probed_at=today_iso)` immutable stamp at `:70`.
  - Empty `source_report_quarter` guard at `:65-68`.
  - Exception swallowed via `except Exception as exc` at `:57`; disk-error degrades via `sys.stderr.write` at `:73-76`.
- Three tests: `test_build_one_writes_cache_with_probed_at`, `test_build_one_skips_write_on_empty_quarter`, `test_build_one_swallows_builder_exception`.

### Task 4: Batch driver — cache-presence gate + budget guard (AC1, AC2, AC4, AC7)
Status: OK
- `_eligible_missing` at `narrative_autobuild.py:80-91` — uses `load_active_fund_cache(row.instrument_id, quarter, data_dir)` (resolved quarter, not `_load_latest_active_fund_cached`).
- `autobuild_active_funds` at `:93-120` — kill-switch first, `_eligible_missing`, `FetchPlan`/`_fetch_budget` budget guard raises `FetchBudgetExceeded` pre-build at `:108-110`.
- Four new tests: `test_skips_etf_rows_builds_only_active`, `test_skips_when_resolved_quarter_cache_present`, `test_kill_switch_disables_build`, `test_budget_guard_raises_before_any_build`.
- Module at 120 lines — within 200-line budget.

### Task 5: Wire autobuild into `_run_analyze` (AC3, AC11 wiring)
Status: OK
- Import `from irc.commands.narrative_autobuild import autobuild_active_funds` added at `narrative_cmd.py:15`.
- `autobuild_active_funds(shortlist, provider=provider, quarter=resolved_quarter, data_dir=root / "data", today_iso=_today())` at `:95-99` — before the `for row in shortlist:` loop, using `resolved_quarter`.
- `test_analyze_invokes_autobuild_with_resolved_quarter` at `test_narrative_cmd.py:331`.
- No-op autobuild stubs added to the two pre-existing analyze tests at lines 115-116 and 249-250 — matches plan Step 5 exactly (the intentional deviation the implementer flagged: proactively added to keep existing tests network-free; this IS the prescribed behaviour in plan Task 5 Step 5).

### Task 6: Correct the misleading error string (AC9)
Status: OK
- Error block at `narrative_cmd.py:162-169` replaced: "run `irc ingest`", "snapshot quarter under data/fundamentals/", "auto-built during a successful --analyze", "set IRC_NARRATIVE_AUTOBUILD=0 to disable", "run `irc opportunity` once or re-run --analyze online" — no "fundamentals snapshot" present.
- Test `test_analyze_missing_db_error_string_is_corrected` at `test_narrative_cmd.py:304` verifies all required strings and absence of "fundamentals snapshot".

### Task 7: Idempotence test (AC8)
Status: OK
- `test_analyze_idempotent_second_run_zero_builds` at `test_narrative_cmd.py:376`.
- Stubs only the `build_snapshot` edge inside the real autobuild module; exercises cache write/read end-to-end against `tmp_path`.
- Asserts `build_count["n"] == 1` after two runs and `first == second`.

### Task 8: Behavioural recovery (AC11)
Status: OK
- `test_analyze_recovers_active_fund_with_real_thesis` at `test_narrative_cmd.py:431`.
- `_fake_build` returns a non-empty `ActiveFundSnapshot` with a `ConstituentAnalysis`; `_fake_row` asserts `snapshot is not None`.
- `_row` helper added at `test_narrative_cmd.py:43-57`.
- Missing import in plan (`from irc.fundamentals.types import ActiveFundSnapshot` inside `_fake_build`) — the diff does NOT import `ActiveFundSnapshot` at module top in `test_narrative_cmd.py`; it is imported locally inside the test function at line 449 (matches the plan's inline import form). OK.

### Task 9: Forbidden-indicator + sentinel guards (AC10)
Status: OK
- `test_module_has_no_forbidden_indicator` + `test_module_never_writes_budget_exhausted_sentinel` at `test_narrative_autobuild.py:159-166`.
- Neither `基金概況` nor `fetch_budget_exhausted` appear in `narrative_autobuild.py` (confirmed by grep returning no output).

### Task 10: Full-suite verification + lint
Status: implicitly verified (no drift step requires a diff hunk; this was a verification-only task).

---

## Spec/grill invariant checks

- **`analyze_fund` stayed READ-ONLY:** `src/irc/narrative/analyze.py` shows zero diff — untouched. All fetch/build/cache-write lives in `narrative_autobuild.py` and `_run_analyze` in `narrative_cmd.py`. OK.
- **No `基金概況` in production fetch code:** grep on `narrative_autobuild.py` + `narrative_cmd.py` returns nothing. OK.
- **`fetch_budget_exhausted` sentinel NOT written into any row's evidence_gaps:** grep returns nothing; budget breach raises `FetchBudgetExceeded` exception before any build. OK.
- **No `evaluate_policy_b` / rule-2.5 stamping:** grep returns nothing. Policy-B-free posture confirmed. OK.
- **`_load_latest_active_fund_cached` NOT imported (Q-G7):** grep returns nothing; module uses `load_active_fund_cache` (the public read). OK.
- **Corrected error string no longer instructs `fundamentals snapshot`:** grep on production `narrative_cmd.py` returns nothing; test asserts `"fundamentals snapshot" not in err`. OK.

---

## Drift findings

None.

---

## Scope-creep assessment

- `docs/2026-06-02-narrative-coverage-markdown/PROGRESS.md` updated (tracking row + log entry for plan commit). Incidental housekeeping — accepted.
- No functional scope creep.

---

## Plan amendments

None required. All plan steps verified against actual diff lines.
