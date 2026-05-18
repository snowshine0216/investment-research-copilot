# Item 011 — Collapse `decision_report.md` markdown to 3 reader-first blocks

## What

`outputs/2026-05-18/decision_report.md` has 103 rows in one big table. 86 of them read `watch_only / med / 0.83 / unknown / Keep on watchlist and rerun after new data.` — wallpaper that buries the 4 actionable buys and the 12 fixable blockers.

Restructure the markdown into three sections:

1. **Actionable buys** (decision_status == `actionable_buy`) — the full table for these rows.
2. **Blocked — fixable today** (decision_status == `blocked`) — grouped by `blocking_reasons[0]`, with a one-line remediation hint per group.
3. **Watch (no trade)** — render a count summary by `watch_reason` (the field item 007 introduces) and a collapsed `<details>` block listing each instrument id.

JSON (`decision_report.json`) is unchanged — it's the contract for downstream tools.

## Files to touch

- `src/irc/decision/report.py` — replace the single-table renderer with the three-section renderer. Keep the JSON producer unchanged.
- `tests/decision/test_report.py` — update the markdown assertions to the new shape.

## Acceptance criteria

- Renderer produces three top-level `## Actionable buys`, `## Blocked — fixable today`, `## Watch (no trade)` sections in that order.
- Actionable buys: same column shape as today's table, just filtered.
- Blocked: rows grouped by first blocking_reason. For each group, render `### Blocked by: {reason}` (with a human-readable label) followed by a small table, and a one-line remediation hint at the end of the group. Hint mapping:
  - `data_incomplete` → "Repair the required financial metrics in the data layer and rerun scoring."
  - `venue_blocked` → "Add a compatible account venue, register a proxy, or accept the position is not reachable."
  - `target_weights_invalid` → "Fix allocation normalization before using target weights."
  - `pipeline_halted` → "Fix the halted stage and rerun the pipeline."
  - `memo_narrative_only` → "Improve memo traceability before treating narrative claims as evidence."
  - `score_avoid` → "Scoring action is avoid — review the underlying factor scores."
- Watch (no trade): a top summary line (`{count} 个标的暂未触发交易决策。`), then 3 small sub-tallies (`未被配置选中`, `打分仅 watch`, `渠道未知`) corresponding to the `watch_reason` field. Then a collapsible `<details><summary>展开所有 watch 标的</summary> … </details>` containing just `instrument_id | name_cn | score_action | conviction | data_completeness | venue_status | watch_reason`.
- The JSON file produced alongside is byte-equivalent to today's (modulo new `watch_reason` field from item 007).
- An updated test asserts presence of the three section headers and that the row count in Watch (no trade) equals 86 on today's fixture.
- The full suite is green.

## Coordination

- Item 007 introduced `watch_reason`. Required input.
- Item 008 reduced the number of `venue_unknown` rows. Required input.

## Out of scope

- Restructuring the JSON output. Stays as-is.
- Changing what triggers `actionable_buy` / `blocked` / `watch_only` classifications. Renderer-only.
- Adding pagination or sortable headers. Markdown is for humans, not tools.
