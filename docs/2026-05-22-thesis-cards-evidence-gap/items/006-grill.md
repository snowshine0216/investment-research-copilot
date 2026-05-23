# Item 006 — Grill summary

Auto-accepted under autonomy override 2026-05-23. No human in the loop; every recommended answer locked verbatim.

## Six grill questions resolved

| # | Question | Locked answer |
|---|---|---|
| G-Q1 | `rejections.json` write timing | Atomic write-at-end via `.tmp.{pid} → os.replace`. NOT append-per-row. Empty-rejections case still writes `entries: []`. |
| G-Q2 | `audit_errors` field placement | `ConstituentAnalysis.audit_errors` only. NOT on `OpportunityRow`. Row-level effect captured by `evidence_gaps += ("incomplete_constituent_record",)`. |
| G-Q3 | V1 systematic exclusions count: who computes? | Item 006's `render_v1_systematic_exclusion_summary` computes AND renders the line. Item 007 does NOT recompute. `rejections.json` does NOT carry a pre-computed tally field. |
| G-Q4 | Policy B precedence | **1 → 2 → 3 → 4 → 5** (locked; the previous draft alternated between two orderings). Each rule short-circuits. |
| G-Q5 | `fetch_budget_exhausted` raise location | Two distinct gates: item 003's `FetchBudgetExceeded` in `_build_rows` (preflight), item 006's `RuntimeError` at the TOP of `_write_opportunity_outputs` (defence-in-depth). Different exception classes — they do not mask each other. |
| G-Q6 | Policy B applicability scope | `ActiveFundSnapshot` ONLY. `FundLevelSnapshot` (gold/bond/cn_etf/QDII sentinel) and `ConstituentSnapshot` (legacy) are NOT evaluated by Policy B; their rejection records are built with `verdict=None` via the `_decision_rule_for` fallback helper. |

## Artifacts updated

- **CONTEXT.md** — new "Failure-mode + audit policy" section (12 terms).
- **docs/adr/0003-failure-mode-policy-b.md** — new ADR (6 sections).
- **items/006-spec.md** — refined inline: precedence locked, criterion 12 prose unambiguous, `_decision_rule_for` helper added, "Grill-phase locked decisions" section before "Open questions resolved during brainstorming", grill verdict appended.

## Verdict

**PASS.** Spec is plan-ready.
