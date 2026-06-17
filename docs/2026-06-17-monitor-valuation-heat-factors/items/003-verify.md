Verdict: PASS

## Subagent
claude-sonnet-4-6

## Source
Branch: `claude/monitor-valuation-heat-factors-003`
Commit: current HEAD on branch (post-implementation, pre-push)

## Entry point exercised
- Direct `uv run python -c "..."` driving `parse_purchase_status`, `heat_inputs_for`, `fetch_purchase_table` with in-process fixture DataFrames (no network).
- Offline pytest: `tests/monitor/test_heat_fetch.py`, `tests/commands/test_monitor_cmd_heat.py`, `tests/commands/test_monitor_cmd_eval_wiring.py` (39 tests).
- Determinism guard: `tests/evals/test_monitor_signal_runner.py`, `tests/evals/test_monitor_signal_metrics.py` (8 tests).
- Live test file confirmed skipped (double-gated; `IRC_RUN_LIVE_AKSHARE` not set): 2 skipped.
- Import smoke: `from irc.monitor.heat_fetch import ...` + `from irc.commands.monitor_cmd import run_monitor, _process_fund` — OK.

## Observed behavior (per AC)

**AC1 — Module exists with required public surface:**
`src/irc/monitor/heat_fetch.py` present. All three functions are defined with the exact signatures specified: `fetch_purchase_table(fetch=None)`, `parse_purchase_status(table, fund_id)`, `heat_inputs_for(fund_id, *, purchase_table)`. House pattern confirmed: `import akshare as ak` is local inside `fetch_purchase_table`, not at module top.

**AC2 — Restriction rule (pure):**
Direct exercise output:
```
001234 (开放申购, cap=1e9): restricted=False  — expected False   ✓
002345 (暂停申购, cap=nan): restricted=True   — expected True    ✓
003456 (开放申购, cap=5e7): restricted=True   — expected True    ✓ (cap < 1e8 fires)
999999 (absent): restricted=None             — expected None    ✓
None table: restricted=None                  — expected None    ✓
```
Multiple non-open statuses (暂停申购 / 限大额 / 场内交易 / 封闭期 / 认购期 / empty) all return `True` per parametrized test suite (6 status variants, all PASS).

**AC3 — `heat_inputs_for` returns `aum_delta_pct=None`:**
```
heat_inputs_for 001234: (False, None)   ✓
heat_inputs_for 002345: (True, None)    ✓
heat_inputs_for 999999: (None, None)    ✓
```

**AC4 — One AkShare call per run:**
`grep monitor_cmd.py` confirms `fetch_purchase_table()` at line 633 (before `for fund in funds:` loop at line 640). Each per-fund `_process_fund` receives `purchase_table=purchase_table` (pre-fetched). No AkShare call inside the loop. CN endpoint is direct (no `IRC_HTTPS_PROXY` applied — `heat_fetch.py` has no proxy wiring, consistent with the project http-proxy rule for CN domains).

**AC5 — Availability contract (no silent failure):**
```
fetch raises RuntimeError:              result=None  ✓  (logged warning, never raised)
fetch returns schema-drift df:          result=None  ✓  (missing 申购状态 logged, returns None)
fetch returns valid df:                 type=DataFrame  ✓
```
Both failure paths log structured WARNING lines (confirmed in output). `heat_no_data` in `KNOWN_NA_REASONS` (confirmed in `factors.py` line 28).

**AC6 — Wire at `monitor_cmd.py:578` (approximately; actual line 633):**
`fetch_purchase_table()` called once; `heat_inputs_for(fund.id, purchase_table=purchase_table)` feeds `restricted` and `aum_delta_pct` into `FactorInputs(...)` at lines 587–595. Confirmed by grep of `monitor_cmd.py`.

**AC7 — No scoring change:**
`heat_score` in `factor_maps.py` is unchanged (not in the diff for this slice). Tests `test_restricted_true_yields_eligible_crowded_heat` (→ `−0.5`), `test_restricted_false_yields_eligible_calm_heat` (→ `+0.3`), `test_restricted_none_yields_heat_no_data` all PASS.

**AC8 — Heat lights for all funds when table reachable:**
Integration tests in `test_monitor_cmd_heat.py`: restricted fund → crowded heat; open fund → calm heat; no table → `heat_no_data` for all. All 3 PASS.

**§6 invariants:**
- `heat_no_data` ∈ `KNOWN_NA_REASONS` ✓ (factors.py line 28)
- Heat behind `eligible_factors(profile)` — test `test_gold_profile_heat_still_eligible_when_restricted` PASS ✓
- Determinism: eval determinism suite 8/8 PASS ✓

**§5.3 availability contract:**
`fetch_purchase_table` never raises: both error paths (exception + schema drift) return `None` with a structured log. Confirmed by direct exercise above.

## Test counts
- `tests/monitor/test_heat_fetch.py`: 31 PASS
- `tests/commands/test_monitor_cmd_heat.py`: 3 PASS
- `tests/commands/test_monitor_cmd_eval_wiring.py`: 4 PASS (eval wiring untouched by this slice — no regression)
- `tests/evals/test_monitor_signal_runner.py` + `test_monitor_signal_metrics.py`: 8 PASS
- `tests/monitor/test_heat_fetch_live.py`: 2 SKIPPED (double-gated, correct)
- **Total offline: 47 PASS, 0 FAIL, 2 SKIPPED**

## Failures
None.
