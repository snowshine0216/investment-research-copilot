# Dependency scan — funding-analysis backlog

Sonnet dispatch, reviewed and **amended** by the orchestrator.

## Hard dependency edges (must-respect)

- **002 → 001**: item 002's `valuation_state` classifier consumes the `pe_ttm`/`pb` and consensus-upside that item 001 wires into `OpportunityInput`. The only hard edge in the backlog.

## Soft / independent

- **004** consumes only existing `FilingDigest.gross_margin` (+ may add its own balance-sheet fetches). No hard dep on any item.
- **003** is a refactor: a provider-agnostic CN fetch interface that can wrap whatever fetchers exist at the time. No hard dep — it can run before or after 001/004.
- **005** is purely additive (a new `thesis_defend` LLM task behind a flag). Depends on nothing, blocks nothing.

## Sonnet proposal

`003 → 004 → 001 → 002 → 005` — treats 003 (pluggable data layer) as the foundation so 001's new `stock_a_indicator_lg`/`stock_individual_info_em` calls slot into a clean interface.

## Orchestrator decision — AMENDED to `001 → 002 → 004 → 003 → 005`

Rationale for overriding the 003-first proposal:

1. **Validate the loop on the smallest item.** 001 is the review's #1 priority and explicitly "few hours" — the right item to prove the spec→…→merge pipeline on. 003 is the largest item.
2. **Credential risk.** 003 is the only item with an external dependency (a paid Tushare token). Front-loading it risks an environmental stall before any value lands.
3. **Concrete over speculative.** Running 003 *after* 001/004 gives the provider abstraction real CN fetch call-sites (`target_price`, `pe`, `pb`, ratio inputs) to wrap, rather than designing the interface speculatively. 003's plan will include an explicit "migrate 001/004 fetchers behind the provider interface" step — visible, scoped rework, not hidden churn.
4. **Coherent valuation thread.** Keeping 001 (fetch valuation data) → 002 (classify + gate) contiguous makes the grill/plan agents' context tighter.

The amendment honors the single hard edge (001 before 002) and is otherwise free to optimize for loop-validation + risk.
