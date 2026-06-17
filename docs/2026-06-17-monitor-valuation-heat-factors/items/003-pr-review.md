Verdict: PASS-WITH-NITS

Source: /code-review on PR #165 / https://github.com/snowshine0216/investment-research-copilot/pull/165#issuecomment-4730547078 / Findings (2): both nit

---

## Review scope

Independent second-pass review of `monitor-valuation-heat-wiring...claude/monitor-valuation-heat-factors-003`.
Files reviewed: `src/irc/monitor/heat_fetch.py`, `src/irc/commands/monitor_cmd.py`,
`tests/monitor/test_heat_fetch.py`, `tests/monitor/test_heat_fetch_live.py`,
`tests/commands/test_monitor_cmd_heat.py`, `tests/commands/test_monitor_cmd_eval_wiring.py`,
`tests/monitor/test_acceptance_eval.py`.

## Findings

| # | File | Location | Finding | Class |
|---|------|----------|---------|-------|
| 1 | PR body / PROGRESS.md | n/a | `"threaded per-fund"` language implies concurrent execution; actual impl is a sequential `for fund in funds` loop passing `purchase_table` as a read-only kwarg. Term follows plan doc's own wording ("thread it into `_process_fund`" = pass-through). No correctness impact. | nit |
| 2 | `heat_fetch.py` | line 86–88 | `_has_required_columns` checks only `_CODE_COL` / `_STATUS_COL`, not `_CAP_COL`. Correct by design — `_cap_below_threshold` degrades to `False` on missing cap column (graceful fallback). Documenting for future readers. | nit |

## Confirmed clean

- `fetch_purchase_table` truly never raises (bare except wraps only `fetch()`, logs with `exc_info=True`).
- Schema-drift observability: `_has_required_columns` + structured WARNING distinguishes drift from empty/network-fail. Pre-push fix (commit `ac5fba7`) correctly surfaced at the I/O edge; pure parser stays side-effect-free.
- `parse_purchase_status` return type is always `bool | None`: `restricted_by_status or _cap_below_threshold(row)` evaluates to `bool` in all non-None paths.
- Fetch-once pattern: shared read-only DataFrame across sequential per-fund loop — no mutation risk.
- `**kw` lambda fix in `test_monitor_cmd_eval_wiring.py` absorbs both item-001 `con=con` debt and item-003 `purchase_table` kwarg. 4 RED → GREEN.
- `aum_delta_pct` always `None` (AUM-Δ deferred) — by design, per spec §5 and PR description.
- `fetch_purchase_table` returns `None` on failure (not raises) — designed availability contract per spec §5.3.
- CN endpoint direct (no proxy), lazy akshare import — correct house patterns.
- No new N/A reason codes; `heat_score` and `factor_maps.py` unchanged; `heat_no_data` pre-existing.
- CLAUDE.md compliance: all helpers < 20 lines, `heat_fetch.py` 102 lines (< 200), pure core + effects at edge.

## Context honored (not re-flagged)

- `fetch_purchase_table` returns None on failure + logs (exc_info) — designed availability contract (§5.3).
- `parse_purchase_status` → None on absent/unparseable/missing-column — designed honest `heat_no_data`.
- `aum_delta_pct` always None — AUM-Δ leg explicitly deferred (§5).
- `**kw` lambda fix in `test_monitor_cmd_eval_wiring.py` — fixes item-001 regression.
- `场内交易` + cap=0 → restricted and negative-cap — documented P2 cosmetics, no monitor-fund impact.
