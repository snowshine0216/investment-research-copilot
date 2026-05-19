# 006 — Refuse QDII actionable when premium / FX data missing

## Why

Trust-check A2 and priority #4 (highest single-trade-loss risk):

> Nowhere in `decision_report.md` does the reader see *price*,
> *historical drawdown*, *fund size*, *expense ratio*, or
> *premium-to-NAV* for the buy candidates. … QDII feeders frequently
> trade at 5–15% premium to NAV and can suspend large subscriptions.
> This is the single most likely way the report leads to real money
> loss.

The current 2026-05-19 report had 017641, 019172, 005561 as
`buy_candidate` with `data_completeness=1.00` and no premium data
collected. A non-finance reader could buy at a 10%+ premium and not
know.

## What changes

`src/irc/decision/gates.py`:

1. New constant `_QDII_ASSET_CLASSES = {"us_etf", "hk_etf"}`.
2. In `decide_row`, compute `qdii_premium_unknown` =
   `(asset_class in _QDII_ASSET_CLASSES) AND
   (score.get("qdii_premium_pct") is None) AND
   (score_action in _BUY_ACTIONS)`.
3. Pass it to `_blocking_reasons`. When true, append
   `"qdii_premium_unknown"` to the blocking reasons.

`src/irc/decision/report.py`:

- Add `qdii_premium_unknown` to `_BLOCKING_REASON_LABEL` →
  `"QDII premium-to-NAV data not collected"`.
- Add `qdii_premium_unknown` to `_BLOCKING_REMEDIATION` →
  `"Fetch real-time QDII premium / FX status before treating as
  actionable. QDII feeders frequently trade 5–15% above NAV."`.

Net effect: a `us_etf` / `hk_etf` row with `score_action=buy_candidate`
but no `qdii_premium_pct` field → `decision_status=blocked`, not
`actionable_buy`. The Blocked section surfaces the gate with a
remediation note. When premium data is later wired in, those rows
flow back to `actionable_buy` automatically.

## Acceptance criteria

- A us_etf `buy_candidate` with no `qdii_premium_pct` → `decision_status
  == "blocked"`, blocking_reasons contains `qdii_premium_unknown`.
- A us_etf `buy_candidate` with `qdii_premium_pct = 0.05` → not
  blocked by this gate (other gates may still apply).
- A cn_equity_fund `buy_candidate` with no `qdii_premium_pct` → NOT
  blocked by this gate (only QDII asset classes gated).
- A us_etf `watch` row with no `qdii_premium_pct` → NOT blocked
  (only buy actions gated).
- Existing tests pass.

## Tests to add

`tests/decision/test_gates.py` (new file or append):

- `test_qdii_buy_without_premium_blocks`
- `test_qdii_buy_with_premium_passes_qdii_gate`
- `test_non_qdii_buy_without_premium_passes`
- `test_qdii_watch_without_premium_not_blocked`
- `test_qdii_premium_unknown_renders_in_blocked_section`
