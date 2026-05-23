# Item 007 `/code-review` verdict

**Verdict:** PASS-WITH-NITS (after fix-round-1)
**Tool:** `/code-review` skill at `effort high` → 5 finder angles × ≤8 candidates each → 1-vote verifier → sweep
**Date:** 2026-05-23
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/61

## Surfaces

5 parallel Sonnet finder subagents:

| Angle | Focus | Findings |
|-------|-------|---------:|
| A | line-by-line diff scan | 4 |
| B | removed-behavior auditor | 6 |
| C | cross-file tracer | 4 actionable + 1 confirmed-safe |
| D | Python pitfall specialist | 3 |
| E | wrapper/proxy + invariant correctness | 4 |

Dedup + verifier pass left **7 actionable** items.

## Actionable findings — ALL CLOSED in fix-round-1 commit

1. **Production-breaking — `_instrument_alias_keys` adds shared lookthrough keys** (Angle E1; verified by running `build_alias_maps` locally on two CSI 300 ETF rows). Cardinality: 4+ CSI 300 ETFs, 5+ gold ETFs in the universe → every normal `irc memo` run hits `InstrumentAliasCollisionError` once item 006 publishes >1 fund per index.
2. **`_APPENDIX_LINE_RE` missing `re.MULTILINE`** (Angle D1). Item 009's bulk-document scan would silent-no-op on every run.
3. **`_APPENDIX_LINE_RE` `sym` pattern `[0-9A-Z]{4,6}`** (Angle A1). Rejects `BRK.B` (S&P 500 top-10 in any QDII US fund) and `BF.B`.
4. **`_format_inline_constituent_line` audit_errors precedence inverted vs appendix** (Angle A2, E3). Inline silently dropped audit signals when failure_reasons also present.
5. **`_format_inline_constituent_line` drops failure_reasons when both evidence + failure_reasons** (Angle A3). Partial-failure constituents appeared clean in inline; only visible in appendix.
6. **`InstrumentAliasCollisionError` unhandled in `run_memo`** (Angle C1). Python traceback to CLI; no clean error message.
7. **`find_uncited_conclusions` raises on legitimate all-gapped runs** (Angle A4). Empty publishable set is a valid pipeline state.

Each closed by a production-code edit AND a regression test. Item 007 scope post-fix: 751 passed / 12 skipped / 0 failed.

## Deferred (P2 / theoretical / by-design)

These were noted but not blocking — defer to a future hygiene pass or item 009/010:

- **Snapshot-cache swallows `ValueError` from `ThesisEvidence.from_dict`** (Angle C3, E2). `_active_fund_from_dict` / `_fund_level_from_dict` catch `(KeyError, TypeError, ValueError)` and return `None` (cache miss → refetch). Defeats tamper-detection but is benign in practice. Future: narrow the catch to `(KeyError, TypeError)` only.
- **`_reconstruct_opportunity_rows` drops `expected_omissions`, `contributing_dimensions`, `fetch_types_attempted`** (Angle B2). Harmless for the alias-builder consumer (item 007's only use); a future consumer might silently get empty values. Document with a TODO when item 009 lands.
- **`_order_publishable_rows_for_appendix` doesn't dedupe `pick_order_iids`** (Angle B3). Duplicate `target` in `trade_plan.yaml` produces duplicate appendix subsections. Real `trade_plan.yaml` never duplicates; defer.
- **`verdict.audit_errors` top-level field never rendered** (Angle B4). Dead code; consider removing in a future hygiene pass.
- **`_format_inline_constituent_line` double-space artifact when evidence==() AND audit_errors!=() AND failure_reasons==()** (Angle B1). Closed implicitly by fix #4 above.
- **`yaml.safe_load(...) or {}` masks falsy roots** (Angle D3). Theoretical (`trade_plan.yaml` root is a dict). Defer.
- **`float('nan')` weight_pct bypasses `< 0` guard** (Angle D2). Theoretical (snapshot never emits NaN). Defer; covered by item 005's deferred-hygiene `math.isfinite` filter.
- **Cycle-fix shim only re-exports `select_citations`** (Angle A E-final). Future symbol additions to `irc.opportunity.citation_selector` won't appear in the memo shim — but that produces a loud `ImportError` at runtime, which is the correct behavior. Documented in the shim docstring.
- **`_build_pick_rows` propagates `ValueError` from `from_dict` mismatch as uncaught exception** (Angle C4). The desired tamper-detection behavior; an enclosing `try/except` would mask it. Acceptable.

## Recommendation

**PASS-WITH-NITS.** All 7 actionable findings closed pre-merge with regression tests. Deferred items are P2/theoretical or by-design. Pre-merge gate is satisfied — all four verdicts (drift, ship-inline-review, verify, this pr-review) are PASS or PASS-WITH-NITS. Ready for `gh pr merge`.
