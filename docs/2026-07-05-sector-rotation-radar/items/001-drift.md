Verdict: PASS

```
Subagent: sonnet
Plan tasks: 18
Verified present in diff: 18
Drift findings:
  - Task 1 (AC1 probe) — present-and-matches
    Evidence: scripts/rotation_probe.py (new, 54 lines, matches plan verbatim);
      docs/2026-07-05-sector-rotation-radar/items/001-probe-notes.md (new, 126
      lines: transport decision, single successful live capture
      "SPOT diff[0]: ...f12: BK0420... f9: 30.27...", documented intermittent
      geo-throttle, akshare-derived field-code table, fixtures rationale);
      tests/rotation/fixtures/board_spot_sample.json (4 boards, one f9:"-",
      one f9:null — exercises both None paths); board_hist_sample.json (25
      ascending klines).
    Action: accepted

  - Task 2 (frozen types) — present-and-matches
    Evidence: src/irc/rotation/types.py (63 lines): BoardDay/BoardState/
      ExposureRow/RotationCandidate/RotationReport all frozen dataclasses,
      board_pe: float|None on BoardDay, pe_pctl/chase_risk on BoardState
      matching plan exactly. tests/rotation/test_types.py (51 lines, 5 tests
      incl. an extra test_exposure_row_and_candidate_are_frozen beyond the
      plan's 4 — added in commit 976630a1 "exercise ExposureRow/
      RotationCandidate to satisfy ruff unused-import"; incidental/defensive,
      not scope-creep).
    Action: accepted

  - Task 3 (board parsers + edge fetchers) — present-and-matches
    Evidence: src/irc/rotation/board_fetch.py (124 lines): parse_board_spot,
      parse_board_hist, fetch_board_spot, fetch_board_hist all present with
      the exact field-code handling (f12/f14/f3/f8/f9/f184) specified in the
      plan. tests/rotation/test_board_fetch.py (46 lines, 5 tests) matches
      plan verbatim including the board_pe None-path test.
    Action: accepted

  - Task 4 (board series store) — present-and-matches
    Evidence: src/irc/rotation/series_store.py (90 lines): load_store,
      append_snapshot, seed_backfill, idempotent same-day overwrite, prune,
      byte-stable atomic write — matches plan implementation near-verbatim.
      tests/rotation/test_series_store.py (50 lines, 5 tests) all present
      (roundtrip, same-day no-dup, prune, byte-stability, missing-store).
    Action: accepted

  - Task 5 (composite scoring) — present-and-matches + accepted-improvement
    Evidence: src/irc/rotation/composite.py (95 lines): board_signals,
      cross_sectional, pe_percentiles all present with W_MOM/W_FLOW/W_TURN/
      MIN_TD constants matching plan. ADDITIONALLY: flow_leg_dark(signals)
      (composite.py:1308-1316 per pre-commit numbering; function present in
      final file) — added in commit ac517d07 "flow5-aware flow_dark
      eliminates fabricated-0 dark factor (D6)". This is the documented
      KNOWN DIVERGENCE #2. Tested: test_flow_leg_dark_prevents_fabricated_
      zero_flow, test_flow_leg_kept_when_all_boards_have_flow5 (both in
      tests/rotation/test_composite.py), plus an end-to-end partial-flow-gap
      integration test test_partial_flow_gap_triggers_global_flow_dark and
      test_flow_dark_tags_data_status_and_never_fabricates_zero_flow (both
      in tests/commands/test_rotation_cmd.py) — confirms it is present +
      thoroughly tested, consistent with D6 "never per-board mixing".
    Action: accepted-improvement (tested, consistent with D6; fixes a real
      dark-factor bug class the plan's simpler "all main_inflow_ratio is
      None" gate would have missed post-seed)

  - Task 6 (state machine) — present-and-matches
    Evidence: src/irc/rotation/states.py (67 lines): classify_board,
      P_ENTER=0.80/P_EXIT=0.70/EMERGING_WINDOW=5, hysteresis logic matches
      plan verbatim. tests/rotation/test_states.py (49 lines, 7 tests incl.
      the AC4 property test with itertools.product) — all present.
    Action: accepted

  - Task 7 (exposure matrix) — present-and-matches
    Evidence: src/irc/rotation/exposure.py (49 lines): build_exposure with
      coverage_diag shape {total_holding_syms, mapped_syms, unmapped_syms,
      coverage_pct} matches plan exactly. tests/rotation/test_exposure.py
      (35 lines, 3 tests) all present.
    Action: accepted

  - Task 8 (candidate ranking) — present-and-matches
    Evidence: src/irc/rotation/candidates.py (46 lines): rank_candidates
      with MIN_EXPOSURE_PCT=10.0, CAND_TOP_N=10, new_candidates rollup —
      matches plan verbatim. tests/rotation/test_candidates.py (42 lines,
      3 tests) all present.
    Action: accepted

  - Task 9 (report projections) — present-and-matches (extended, non-divergent)
    Evidence: src/irc/rotation/report.py (90 lines): to_json, to_md,
      abstain_report, cold_holdings_note all present. to_md additionally
      renders a full "## 诊断" diagnostics section (_diagnostics_section,
      _diag_line, _diag_value_str) added in commit 3f2be6da "to_md renders
      json diagnostics on ok path (AC8) + strengthen subset test" — this
      is a genuine AC8 strengthening (md was previously suppressing
      diagnostics fields that json carries; now the "additive subset"
      contract is actually enforced) with 3 new tests
      (test_md_renders_all_json_diagnostics, test_md_renders_pe_coverage_
      and_unmapped_diagnostics) beyond the plan's 6. This is scope-tightening
      in service of the plan's own AC8 intent, not scope-creep.
    Action: accepted

  - Task 10 (forward ledger) — present-and-matches
    Evidence: src/irc/rotation/ledger.py (60 lines): build_ledger_rows,
      append_rows, dedup-by-(date,board_code) — matches plan verbatim.
      tests/rotation/test_ledger.py (33 lines, 3 tests) all present.
    Action: accepted

  - Task 11 (import isolation test, AC11) — present-and-matches
    Evidence: tests/rotation/test_import_isolation.py (16 lines):
      test_no_upstream_imports_rotation checks monitor/discovery/scoring/
      memo/opportunity for "irc.rotation" or "from irc import rotation" —
      matches plan verbatim. Verified PASS at HEAD (1 passed).
    Action: accepted

  - Task 12 (industry_map_store extension) — present-and-matches
    Evidence: src/irc/monitor/industry_map_store.py module docstring gained
      the exact D7 paragraph the plan specified ("Also serves the sector
      rotation radar (ADR 0023 D7)..."). No new function added (plan's
      "prefer the smaller change" branch taken — existing merge_seen/
      fresh_slice suffice). tests/monitor/test_industry_map_store.py +8
      lines: test_merge_seen_stores_board_codes_as_industry matches plan
      verbatim. Verified PASS (11 passed, full file).
    Action: accepted

  - Task 13 (seed orchestration, AC2) — present-and-matches
    Evidence: src/irc/rotation/seed.py (93 lines): seed_boards,
      seed_holdings, seed_stock_board_map all present, resumable/skip-cached/
      partial-tolerant semantics matching plan. tests/rotation/test_seed.py
      (128 lines, 5 tests) — plan specified 2 tests; impl adds 3 more
      (test_seed_boards_partial_tolerant_on_fetch_error,
      test_seed_stock_board_map_skips_fresh_and_chunks,
      test_seed_stock_board_map_chunk_failure_is_tolerated) covering the
      seed_stock_board_map function the plan's own step 3 code included but
      whose test the plan excerpt omitted. Strengthening, not scope-creep.
    Action: accepted

  - Task 14 (run_rotation daily command) — present-and-matches + accepted-divergence (F6)
    Evidence: src/irc/commands/rotation_cmd.py (245 lines) implements
      run_rotation, run_rotation_seed, _build_states, _resolve_trading_days,
      abstain/flow-dark/cold-holdings degradation exactly as specified.
      DIVERGENCE #1 (F6 deferral): the plan's own Task 14 code and commit
      8e1d0f9a "wire IRC_ROTATION_TOPUP_BUDGET into seed's stock-board map
      fetch" show the daily run_rotation() does NOT perform an in-run
      top-up fetch loop — IRC_ROTATION_TOPUP_BUDGET only bounds seed's
      chunk_size (rotation_cmd.py:836-840 _topup_budget(), used at
      rotation_cmd.py:874 chunk_size=_topup_budget() inside
      run_rotation_seed, never inside run_rotation). This matches the task
      prompt's description of the orchestrator decision. VERIFIED
      documented as F6 in FOUR places: (1) rotation_cmd.py module docstring
      line ~669 "The §8/D11 in-run bounded top-up for incremental misses
      between seeds is a named follow-up (F6)"; (2) spec §12 follow-ups list
      "F6 Daily in-run bounded top-up (§8/D11)..." (design doc diff);
      (3) CONTEXT.md "Sector rotation radar" section, new bullet "§12
      follow-up F6 — daily in-run bounded top-up (§8/D11)..."; (4) ADR 0023
      Consequences section, new bullet "F6 — daily in-run bounded top-up
      (§8/D11)...". All four say the same thing consistently (cache-only v1,
      cold cache renders L1 + seed-pointer line). Test coverage:
      tests/commands/test_rotation_cmd.py (230 lines, 10 tests) — abstain,
      byte-identical rerun, flow-dark (2 variants), diagnostics population,
      chase_risk/pe_coverage, cold-holdings note, CLI registration — all
      present, all passing (10 passed).
    Action: accepted (F6 genuinely documented in all 4 required places —
      module docstring, spec §12, CONTEXT.md, ADR 0023)

  - Task 14 size budget — divergent (minor, unflagged)
    Evidence: src/irc/commands/rotation_cmd.py is 245 lines. Plan's global
      constraint says "files < 200 lines (ideal)" and Task 18 step 8 says
      "If rotation_cmd.py exceeds, extract _resolve_candidates/
      _load_membership into src/irc/rotation/_cmd_helpers.py ... and
      re-run." The extraction WAS done (_cmd_helpers.py, 111 lines, holds
      load_membership + resolve_candidates), but rotation_cmd.py still sits
      at 245 lines post-extraction — over the 200-line ideal budget, and
      the plan's re-run contingency implicitly expected the extraction to
      bring it under. No PROGRESS.md/commit note flags this residual
      overage as accepted.
    Action: routed to triage (cosmetic size-budget miss, not a functional
      or test-coverage defect; all tests pass and file is still well under
      any hard limit; low priority)

  - Task 15 (CLI registration) — present-and-matches
    Evidence: src/irc/cli.py +18 lines: `rotation` group (invoke_without_
      command=True) + `rotation.command("seed")` registered right after the
      monitor flow-capture command, matching plan's insertion point and
      code verbatim. test_cli_rotation_registered present in
      tests/commands/test_rotation_cmd.py, passing.
    Action: accepted

  - Task 16 (15:45 wrapper chaining, AC10) — present-and-matches
    Evidence: ops/launchd/run-flow-capture.sh +8 lines: radar_rc=0 /
      run_with_watchdog .../ echo / positioned after "flow-capture rc=$rc"
      echo and before "exit \"$rc\"" — matches plan verbatim.
      tests/ops/test_flow_capture_wrapper.sh (17 lines) matches plan
      verbatim; verified PASS ("PASS: AC10 wrapper chaining").
    Action: accepted

  - Task 17 (docs/CONTEXT/CHANGELOG/ADR) — present-and-matches
    Evidence: docs/monitor/README.md 15:45 row appends the exact radar
      sentence from the plan; ops/launchd/README.md flow-capture row +
      failure-mode table row both added verbatim; CONTEXT.md "Sector
      rotation radar" marker flipped "SPEC'd 2026-07-05, not built" →
      "built 2026-07-05" plus the F6 bullet; CHANGELOG.md [Unreleased] gained
      the "Added — sector rotation radar (2026-07-05)" block; docs/adr/
      0023-sector-rotation-radar.md Status flipped "Proposed" →
      "Accepted (built 2026-07-05)" plus the F6 consequence bullet.
    Action: accepted

  - Task 18 (verification sweep) — present-and-matches
    Evidence: re-ran all Task 18 commands independently at HEAD:
      `pytest tests/rotation/ -q` → 53 passed; `pytest tests/commands/
      test_rotation_cmd.py -q` → 10 passed; `pytest tests/monitor/
      test_industry_map_store.py -q` → 11 passed; `pytest tests/rotation/
      test_import_isolation.py -q` → 1 passed; `bash tests/ops/
      test_flow_capture_wrapper.sh` → PASS; `ruff check src/irc/rotation
      src/irc/commands/rotation_cmd.py tests/rotation` → All checks passed.
      AC8 literal grep (`grep -rn '\[ref:' src/irc/rotation/report.py`)
      matches 2 lines, but both are docstring PROSE quoting the literal
      string "[ref:]" as documentation ("NO [ref:] markers" x2), not actual
      emitted markers — to_md()'s real output has zero `[ref:` occurrences,
      confirmed by test_md_has_no_ref_marker (passing) and by reading
      report.py's to_md/_state_line/_cand_line/_diag_line bodies (no
      f-string or literal containing "[ref:" outside the two docstrings).
      The plan's literal Task 18 grep command would technically exit 1 here
      (false positive from its own docstring), a plan-authoring nit, not an
      AC8 violation.
    Action: accepted (grep false-positive is on plan's own doc-comment
      wording, not a real citation-marker leak; the intent — no [ref:] in
      rendered output — is correctly satisfied and tested)
```
