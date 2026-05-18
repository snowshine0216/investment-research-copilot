# Item 010 — Allow same-class gold proxy without `tracked_index` match

## What

`config/universe/gold.yaml:3-5` defines `cmb_paper_gold` (CMB internal paper gold) with `venue_required: [cmb_gold]` and no `tracked_index`. The user's account has `cmb_gold` in `available_venues`.

When the allocator targets the gold ETFs (518880, 159934) — which require `cn_brokerage` and are unreachable from the user's account — `src/irc/trades/venue_check.py:_proxy_for` should find `cmb_paper_gold` as a same-class proxy. But the function requires `(i.tracked_index or "").strip() == target_index` and the paper-gold instrument has no index. Match fails, the ETFs report `blocked_no_proxy`, and the trade plan ships 20% of the portfolio in an unexecutable position.

## Files to touch

- `src/irc/trades/venue_check.py` — narrow exception to the `tracked_index` rule, gated on asset_class.
- `tests/trades/test_venue_check.py` — add the regression test.

## Acceptance criteria

- For `target.asset_class == "gold"` and `cross_class is False` (which it is for gold today), `_proxy_for` matches a candidate when the candidate's asset_class is `gold` and its `venue_required` intersects `available_venues`. The `tracked_index` equality check is skipped *only* for gold.
- For every other asset class (`cn_etf`, `cn_equity_fund`, `cn_bond_fund`, `us_etf`, `hk_etf`), today's strict `tracked_index` matching is preserved.
- A new regression test: target = `518880`, available_venues = `["cmb_gold"]`, universe contains `cmb_paper_gold` — `check_venue` returns `(compatible=False, proxy_id="cmb_paper_gold", note=...)`.
- The note should read: `"venue mismatch; proxy via cmb_paper_gold (招商银行账户金) [gold]"`.
- A new negative test: target = `510300` (cn_etf, tracked_index = "沪深300"), with a candidate that lacks a tracked_index, still returns no proxy. Asserts the gold relaxation does not bleed into other classes.
- The full suite is green.

## Implementation hint

The cleanest shape: inside `_proxy_for`, after computing `allowed_classes`, set a local flag `require_index_match = (target.asset_class != "gold")`. In the loop, gate the `(i.tracked_index or "").strip() != target_index` check on that flag.

Don't touch the cross-class substitution dict — gold isn't there, and we don't want it there.

## Coordination

- Item 008 derived `venue_status` for in-universe instruments. After this item lands, the gold ETFs go from `blocked_no_proxy` to `proxy_available`, which is what the user's `decision_report.md` should show going forward.

## Out of scope

- Re-routing the *allocation* to the proxy. The trade plan already routes to `proxy_id` when set (`pipeline.py:40`). The current run shipped weight on the ETF because no proxy was found; with this fix the proxy gets the weight. No allocation-side change needed.
- Expanding the index-free relaxation to other asset classes.
