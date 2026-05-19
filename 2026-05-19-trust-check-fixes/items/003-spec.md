# 003 — Collapse venue-blocked list with proxy remediation line

## Why

Trust-check A5: five A-share gold ETFs (518880, 159937, 159934,
518800, 518850) appear as `blocked_no_proxy` in `decision_report.md`.
A non-finance reader cannot tell that:

- The proxy `cmb_paper_gold` (招行账户金) *already* fills the gold
  role (`trade_plan.yaml: cmb_paper_gold @ 20% target_weight`).
- The 20% gold target is *already met*.

A layperson may panic-add a redundant position thinking gold is
uncovered.

## What changes

In `src/irc/decision/report.py`:

1. `compose_decision_report` computes `proxy_coverage`: for every
   trade in `trade_plan.trades` where `proxy_id` is non-null and
   `target_weight > 0`, record:
   `{asset_class: [{target: ..., target_weight: ..., proxy_id: ...}]}`.

2. Add `proxy_coverage` to the report dict (additive — existing keys
   unchanged).

3. In `_blocked_fixable_section`, after rendering the per-`blocking_reason`
   table, append a one-line "Role already met" banner for each
   asset_class present in the group that is also in `proxy_coverage`.

   Example output line:
   ```
   _✓ Gold role already met via cmb_paper_gold (20% target_weight) —
   the 5 blocked gold ETFs above are redundant; no action required._
   ```

## Acceptance criteria

- A blocked row whose `asset_class` matches a non-empty entry in
  `proxy_coverage` produces a remediation banner (separate from
  the row table).
- A blocked row whose `asset_class` is NOT covered produces the
  normal `_Remediation:_` line only (no false-positive banner).
- The proxy_coverage entry in the report dict is well-formed:
  `dict[asset_class, list[{target, target_weight, proxy_id}]]`.
- Existing tests pass.

## Tests to add

`tests/decision/test_three_section_markdown.py`:

- `test_blocked_section_emits_proxy_coverage_banner` — gold ETF
  blocked + a cmb_paper_gold trade present → banner appears.
- `test_blocked_section_no_banner_when_no_proxy_for_class` — bond ETF
  blocked, no proxy in same class → no banner.
- `test_proxy_coverage_in_report_dict` — `report["proxy_coverage"]`
  has the expected structure.
