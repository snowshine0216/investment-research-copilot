# Phase 3 — cross-cutting validation

## Test suite

- Focused suite (`tests/scoring tests/research tests/opportunity
  tests/allocation tests/memo tests/decision tests/trades`) —
  **607 passed, 0 failed**.
- Two pre-existing e2e failures (`test_e2e_irc_run_only_stage`,
  `test_e2e_irc_run_from_stage` in `tests/test_e2e_plan3_full_pipeline.py`)
  require live web research providers — 4 EN themes returned "no
  sources to synthesize from" because Tavily/Brave timed out. Not
  caused by this branch (the same failure reproduces on `main`).

## Acceptance criteria (from MASTER-SPEC.md)

| # | Acceptance | Verified | Evidence |
|---|---|---|---|
| 1 | `data/research/holdings_sector.md` cites only sources whose entities intersect user holdings | ✅ via filter | `build_holdings_query(('黄金','沪深300','标普500','医疗保健'))` injects concrete hooks; `filter_relevant_citations` drops non-matches at run time. |
| 2 | `thesis_cards.yaml` does not mark `intact` when only republisher-tier evidence | ✅ | `_thesis_from_theme_report` requires ≥1 PAPER-or-better citation; tested in `test_thesis_relevance_gate.py`. |
| 3 | `proposed_allocation.yaml`: at most one S&P500 and one Nasdaq100 instrument | ✅ | `drop_duplicate_index_trackers` keeps highest-weight per `(asset_class, tracked_index)`; 4-row sp500+ndx fixture → 2 kept. |
| 4 | `gold_regime.json` includes `drivers_score`, `drivers_tilt`, `drivers_availability` | ✅ | `gold_cmd.run_gold` writes all four (drivers_score, drivers_tilt, drivers_availability, drivers_unavailable, combined tilt). |
| 5 | `memo.md` Section 1/2 names failed role buckets | ✅ | `compose_role_bucket_banner` prepended to risk_notes; live demo shows `"发现层覆盖警告：2/3 角色桶本期未召回..."`. |
| 6 | `memo.md` carries execution-drift alert when ≥5pp residual | ✅ | `compose_execution_drift_lines` emits 3-line block; verified with residual=0.15 / target=0.05 → "10.0pp" copy lands. |
| 7 | `memo_audit.txt` says 审核通过, else publish exits non-zero | ✅ | `audit_blocks_publish` blocks on 审核未通过 OR P-tier `^\| P\d+` row; `memo_cmd` writes `memo_blocked.md` and returns rc=2. Verified against the actual 2026-05-19 audit text. |
| 8 | bond rows use yield-curve anchor, not NAV percentile | ✅ | `classify_valuation` dispatches `cn_bond_fund` to `classify_bond_valuation`; yield_pct=0.05 → very_expensive even when NAV_pct=0.14 would say cheap. |
| 9 | `valuation_cost ≥ 0.25`, `thesis_news ≤ 0.10`, `weights_version` bumped | ✅ | Live config: `valuation_cost=0.30, thesis_news=0.10, weights_version=2026-05-19-v2`. Sum = 1.00. Guarded by `test_weights_sum.py`. |
| 10 | trade plan triggers `trim_review` on very_expensive holdings | ✅ | `derive_risk_action` returns `trim_review` for `(very_expensive, is_holding=True)` — covered by `test_trim_triggers.py`. |

## Items merged into feature branch

| ID | Commit | Title |
|---|---|---|
| 011 | `fd9f836` | fix(scoring): rebalance weights for long-horizon DCA |
| 015 | `8887ba6` | fix(allocation): cap satellite-role QDII at 5% NAV |
| 008 | `7cb1401` | fix(allocation): dedupe rows tracking the same index |
| 005 | `ee9baf1` | fix(opportunity): bond valuation uses yield-percentile anchor |
| 007 | `fe7ed52` | fix(opportunity): equity earnings-yield real-rate anchor |
| 004 | `32ab259` | feat(research): source-tier classifier |
| 001 | `b0c3a45` | fix(research): holdings-keywords gate on theme query + citations |
| 002 | `8fbbc82` | fix(opportunity): thesis intact requires trusted-tier citation |
| 003 | `0108714` | fix(research): WARN when ≥2 critical themes degraded |
| 006 | `574eb23` | fix(gold): honest tilt combination of regime × drivers |
| 012 | `a3eb258` | fix(discipline): symmetric trim-side triggers fire on holdings |
| 013 | `bca2fb9` | fix(memo): execution-drift alert when cash residual exceeds target |
| 014 | `98b7daa` | fix(memo): FX/QDII exposure diagnostic when QDII weight ≥ 20% |
| 010 | `df3081b` | fix(memo): banner for failed role buckets |
| 009 | `e8a0afc` | fix(memo): audit becomes a publish-blocking gate |

## Skipped (with reason — see SKIPPED.md)

- §I — preserve list (no fix needed)
- §D trigger-threshold tuning — needs back-test infra
- §D macro_view.active toggle — redirected into 011
- §H 000176 self-proxy → caught at audit gate (item 009)
- §E data-completeness in fundamentals adapters — out of scope

## Why the new pipeline addresses the review's "one paragraph bottom line"

> "The system is well-architected but its signal layer is unreliable in
> ways the report layer hides. A user reading today's memo would not
> realize that the thesis evidence is irrelevant, half the role buckets
> failed, the gold model isn't using its drivers, and 10pp of NAV
> drifted into cash because of an unhandled venue gap. Those are the
> four things that most need to be loud."

After this branch:

1. **Thesis evidence is irrelevant** — items 001, 002, 003, 004 close
   the loop: query construction uses holdings, results are
   relevance-filtered, intact requires a trusted-tier citation, and the
   quality gate WARNs when critical themes are degraded.
2. **Half the role buckets failed** — item 010 puts a banner naming
   each failed role at the top of the memo's risk-notes section.
3. **Gold model isn't using its drivers** — item 006 makes
   drivers_score / drivers_availability first-class fields in
   gold_regime.json and combines them with the regime for the final
   tilt.
4. **10pp of NAV drifted into cash** — item 013 emits a 3-line
   execution-drift alert (drift header, named affected instruments,
   remediation options) when residual exceeds target by ≥5pp.

Plus:
- Bond NAV-percentile (§B1) replaced with yield anchor (item 005).
- Equity sanity anchor (§B3) added (item 007).
- Two-S&P500 duplicate (§C1) deterministically deduped (item 008).
- 8.8% sector-QDII (§C2) capped at 5% (item 015).
- Scoring weights (§G) rebalanced for DCA (item 011).
- Audit becomes a publish-blocker (§H, item 009).
- Trim-side discipline (§F) added (item 012).
- FX/QDII diagnostic (§C4+§C5) added (item 014).
