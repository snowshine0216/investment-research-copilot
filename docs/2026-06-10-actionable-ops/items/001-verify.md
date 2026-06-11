Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point exercise (verify skill not invoked)
Entry points exercised:
  - `uv run irc --help` (exit 0)
  - `uv run irc decision` (exit 0, reads outputs/2026-06-08/)
  - `uv run pytest tests/decision/ tests/opportunity/ -q` (814 passed, 3 skipped)
  - `uv run pytest tests/opportunity/test_report_appendix.py tests/opportunity/test_policy_b.py -q` (69 passed, 1 skipped)
  - `uv run ruff check src/irc/decision/ src/irc/opportunity/report.py src/irc/commands/opportunity_cmd.py src/irc/commands/decision_cmd.py` (all checks passed)

Observed behavior:
  - AC1 — opportunity report rows: `_row_to_dict` in `src/irc/opportunity/report.py` emits `risk_action`, `dca_action`, `portfolio_weight`, `is_holding` via `discipline_by_id` lookup; 6 passing tests in `tests/opportunity/test_report.py` (discipline-keyed).
  - AC2 — `PortfolioAction = Literal["no_trade", "buy", "trim_review", "exit_review", "review"]`; `DecisionStatus` includes `"review_sell_later"`; Phase-3 TODO removed. `test_portfolio_action_members` + `test_decision_status_includes_review_sell_later` both PASS.
  - AC3 — `map_portfolio_action` is pure, precedence correct: sell-side first (even with blockers), `is_holding` gate enforced. 14 truth-table tests in `test_portfolio_action.py` all PASS, including blocked-held-exit, blocked-non-held, non-held short-circuit.
  - AC4 — `weight_delta(current, target)` returns `current - target`; `None` treated as 0.0 (P1-1 explicit check). 4 unit tests PASS (`test_weight_delta_*`).
  - AC5 — `decision_report.json` summary carries `trim_count`, `exit_count`, `review_count` (no `sell_count`); `actionable_buy_count`/`watch_count`/`avoid_count`/`blocked_count` preserved. Current artifact (pre-001 stale) shows all three as `null` — correct per ADR 0015 Addendum. `test_summary_counts_sell_actions` PASS.
  - AC6 — `decision_report.md` contains `## 持仓行动 / Sell · Trim · Review` exactly once (line 128). Current artifact renders stale-warning (pre-001 artifact) instead of empty-state line — correct per ADR 0015 Addendum null-counts semantics. Renderer tests (`test_holdings_action_section_renders_held_sell_rows`, `test_holdings_action_section_empty_state`, `test_markdown_contains_holdings_section_above_blocked`) all PASS.
  - AC7 — non-held instrument with `risk_action=exit_review/trim_review/review_required` maps to `no_trade`; `test_non_held_overheated_does_not_get_sell_action` + `test_sell_branches_require_is_holding` PASS; `test_holdings_action_section_excludes_non_holdings` PASS.
  - AC8 — back-compat: `test_legacy_call_without_sell_params_is_no_trade` PASS (defaults `risk_action="none"`, `is_holding=False`, `portfolio_weight=None` → `no_trade`); `test_compose_report_stale_signals_null_counts` PASS.
  - AC9 — `test_held_exit_review_maps_to_exit_review_and_review_sell_later` PASS; `test_blocked_held_exit_review_decision_status_is_blocked_but_action_is_exit` PASS (precedence boundary correct).
  - AC10 — `uv run irc decision` exits 0; `outputs/2026-06-08/decision_report.json` summary carries `trim_count`/`exit_count`/`review_count` (null — stale, correct); rows carry `portfolio_action` and `is_holding` keys.
  - AC11 — `ruff check` on all touched files: all checks passed. New `portfolio_action.py` is 61 lines (within budget). Pre-existing `report.py` (803L) and `gates.py` (343L) exceed ideal but are pre-existing; no new files exceed budget.

Failures: none
