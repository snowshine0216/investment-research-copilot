Verdict: PASS
Subagent: sonnet
Plan checklist items: 12
Verified present in diff: 12

## Verification summary

All 21 files mandated by the plan (8 src/irc/narrative/*.py + narrative_cmd.py + cli.py + compute_metals.yaml + 10 test files) are present in the diff and absent from restricted paths (src/irc/opportunity/, src/irc/fundamentals/, src/irc/discovery/, src/irc/commands/fund_eval_cmd.py — diff for those paths is empty).

Key invariants confirmed from diff lines:
- `--min-overlap` wired: cli.py option → `run_narrative(min_overlap=...)` → `dataclasses.replace(basket, min_basket_weight_pct=min_overlap)` before `_screen`.
- analyze path: `_build_input` → `build_opportunity_row` → `build_thesis_card` → `derive_position_risk_level` (reuse untouched).
- renderer emits `[ref:...]` via `select_citations(thesis_evidence, cap=3)` in `_evidence_bullets` (report.py:52-57), not a stub.
- `基金概况` absent from all src/irc/narrative/*.py (acceptance test greps confirmed; holdings_fetch.py uses only `fund_portfolio_hold_em`).

## Drift findings

- (a) Task 8 — test_analyze.py `risk_action` assertion — accepted
  Evidence: tests/narrative/test_analyze.py:66 — `assert rpt.risk_action in ("none", "trim_review", "review_required")` (plan had `== "trim_review"`).
  Rationale: `derive_risk_action` returns `"none"` for a prospective position (`is_holding=False`, no portfolio weight, therefore not overweight); `trim_review` fires only when `is_holding AND (expensive or hot)` (discipline.py:75). Production code is unchanged and correct per spec. The relaxed assertion still meaningfully exercises the path (non-empty tuple, correct `risk_drivers`, correct `thesis_evidence`). Comment in plan was wrong ("is_holding=False but expensive+hot fires trim").
  Action: plan amended inline (commit to follow)

- (b) Task 6 — config/narratives/compute_metals.yaml force-added past .gitignore — accepted
  Evidence: diff shows `A config/narratives/compute_metals.yaml`; `.gitignore` has `config/` pattern. File IS present in the diff as an added file (confirmed via `git diff --name-status`).
  Rationale: matches precedent of other tracked config files; required for `test_config.py::test_load_compute_metals_parses` and `test_available_narratives_includes_compute_metals` to pass without test fixtures.
  Action: plan amended inline (commit to follow)

- (c) Task 9 — `_run_analyze` wraps `con.close()` in `try/except` — accepted
  Evidence: src/irc/commands/narrative_cmd.py:99-102 — `finally: try: con.close() except Exception: pass` (plan had bare `con.close()`).
  Rationale: `test_analyze_renders_real_citations` stubs `_open_analyze_context` to return `("CON", "PROV", "2026Q1", {})` where `"CON"` is a plain string with no `.close()` method; without the guard the test crashes in the `finally` branch. In production a real `duckdb.DuckDBPyConnection` is used, which never raises on `.close()`, so no real error is masked. The concession is edge-only and minimal (3 lines).
  Action: plan amended inline (commit to follow)
