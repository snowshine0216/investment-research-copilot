Verdict: PASS-WITH-NITS

Source: /code-review on PR #205 (round 2, post-fix re-review)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/205#issuecomment-4885306457
Findings: 3 (all pre-existing nits, re-triaged; no new issues)
  - src/irc/rotation/types.py (ExposureRow/RotationCandidate display fields), src/irc/rotation/report.py:39 — nit — duplicated fund_id/name_cn display fields across two frozen dataclasses. Cosmetic duplication, not a bug. Unchanged by the b23b1291 fix.
  - src/irc/rotation/types.py:64 (RotationReport.diagnostics) — nit — `field(default_factory=dict)` is a mutable-typed field on an otherwise-frozen dataclass. No mutation call site found (constructed once, never mutated post-construction); immutability smell vs. CLAUDE.md FP conventions, not an active bug. Unchanged by the b23b1291 fix.
  - src/irc/rotation/seed.py (seed_boards/seed_stock_board_map) — nit — one full read-modify-write of board_series.json per board rather than one batched write. Atomic and resumability-safe; efficiency-only. Unchanged by the b23b1291 fix.

Prior blocker (round 1) — CONFIRMED RESOLVED:
  - Round-1 FAIL: src/irc/rotation/board_fetch.py:81 `parse_board_hist` read turnover via `_f(parts[8]) if len(parts) > 8 else None`, which was always False (fields2 requests exactly 8 fields, indices 0-7) — every backfill-sourced BoardDay.turnover_pct silently defaulted to 0.0 via `_tail_mean`, while a board with real live turnover could score non-zero: fabricated-0 per-board-mixing dark-factor bug (D6), unflagged by any data_status/diagnostics signal.
  - Fix (b23b1291) verified in the diff:
    - board_fetch.py:59-90 `parse_board_hist` — dead `parts[8]` read removed; `turnover_pct=None` now explicit with a comment documenting the kline field-code reality (fields2 = f51..f58, no turnover field) and deferring a real fetch to follow-up F7 (needs an AC1-style live probe, per this codebase's T1/f100-f127 scar — correctly not guessed blind).
    - composite.py:46 `board_signals` — `turn_delta` now falls back to `None` (never fabricated `0.0`) when the trailing turnover window is all-None.
    - composite.py:80-89 — new `turn_leg_dark()` mirrors `flow_leg_dark()`: True iff no boards or any board lacks a computable `turn_delta`.
    - composite.py:92-110 `cross_sectional` — rewritten to a generalized per-leg renorm: mom always kept; flow and turn each independently dropped GLOBALLY (never per-board) when their `*_leg_dark` fires. When a leg is kept, every value in it is guaranteed non-None.
    - rotation_cmd.py:179-190 `run_rotation` — computes `sig` once, derives `flow_dark`/`turn_dark`, threads both through `_build_states`/`_pctl_series_by_day`/`_one_state`; reports `data_status` as one of `ok|degraded_flow_dark|degraded_turn_dark|degraded_flow_turn_dark` plus a `diagnostics.dark_legs` list — the fix is now honestly flagged, closing the "unflagged" gap from round 1.
  - Confirmed via new targeted tests (all passing): tests/rotation/test_composite.py::test_turn_leg_dark_prevents_fabricated_zero_turn, test_turn_leg_kept_when_all_boards_have_turn_delta, test_cross_sectional_both_legs_dark_is_mom_only; tests/commands/test_rotation_cmd.py::test_turn_dark_when_board_missing_from_snapshot (board present in series but absent from today's snapshot -> degraded_turn_dark, turn_delta None for every board, never fabricated), test_flow_only_dark_still_reports_degraded_flow_dark (regression guard on the pre-existing status literal).
  - The turn leg can no longer be silently fabricated to 0.0 while another board scores a real turn value: confirmed via code trace + the generalized renorm + the 6 new tests. Round-1 blocker is resolved.

New issues from the fix itself: none found. Specifically checked:
  - report.py to_md/to_json: `_state_line` never renders turn_delta at all (only mom/pe reach markdown), so the None-vs-0.0 distinction never had a markdown rendering path to break; to_json uses dataclasses.asdict + stdlib json.dumps, which serializes None -> null natively. New data_status literals render fine in the existing header f-string.
  - rotation_cmd.py:180-181 — flow_dark keeps its pre-existing extra `all(b.main_inflow_ratio is None for b in snapshot)` clause; turn_dark intentionally omits the analogous check since turn_leg_dark(sig) alone subsumes it — confirmed intentional and tested (test_turn_dark_when_board_missing_from_snapshot exercises exactly the case a snapshot-only gate would miss), not an asymmetry defect.
  - _one_state (rotation_cmd.py:88-102) rounds turn_delta only when both `not turn_dark` and the value is non-None — no `round(None, 4)` crash path.

Verification: `uv run pytest tests/rotation/ tests/commands/test_rotation_cmd.py tests/monitor/test_industry_map_store.py -q` -> 83 passed. `uv run ruff check src/irc/rotation src/irc/commands/rotation_cmd.py tests/rotation tests/commands/test_rotation_cmd.py` -> All checks passed.
