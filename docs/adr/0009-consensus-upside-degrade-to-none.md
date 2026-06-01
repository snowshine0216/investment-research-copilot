# ADR 0009 — Wire consensus-upside end-to-end, degrade to `None` rather than fabricate a target price

**Status:** Accepted (2026-05-31, funding-analysis item 001).
**Supersedes:** none. Builds on [ADR 0001 — citation data model](0001-citation-data-model.md) (citation invariants left untouched).
**Spec:** `docs/2026-05-31-funding-analysis/items/001-spec.md`.

## Context

IRC declares `OpportunityInput.pe_ttm` / `pb` / `dividend_yield` but never populates them, and `BrokerReport.target_price` is hardcoded `None` because the only wired broker feed — AkShare's `stock_research_report_em` (EastMoney) — **drops its 目标价 column upstream** (`indvAimPriceT`/`indvAimPriceL` renamed to `"-"` and discarded; verified against installed AkShare source and locked by `tests/fundamentals/test_akshare_fundamentals.py`). Item 001 adds a price-vs-target valuation metric, `consensus_upside_pct = median(non-None target_price) / latest_close − 1`. With no target prices available today, three positions were possible.

## Decision

**Wire the consensus-upside metric end-to-end (pure helper → `OpportunityInput` field → `populate_inputs`), but let it evaluate to `None` in production.** `fetch_cn_broker_reports` is NOT changed to invent a target price; `BrokerReport.target_price` stays honestly `None` on the EastMoney path. The metric activates automatically — zero further wiring — the moment a target-price-bearing source (Tushare, deferred to a later item) lands.

## Considered options

- **(a) Fabricate a target** from forward-EPS × forward-PE (both present in the EastMoney feed). **Rejected:** a synthesised "target" is not a broker consensus; it would corrupt the metric's meaning and break the existing `target_price is None` assertion.
- **(b) Drop the metric entirely** until a data source exists. **Rejected:** the consumer (`consensus_upside_pct` + its `OpportunityInput` field) is cheap, pure, and fully testable offline now; deferring it would re-open the wiring later for no saving.
- **(c) Wire-but-degrade-to-`None`** (chosen). Honest, zero-cost, and self-activating.

## Consequences

A future reader will see `consensus_upside_pct` plumbed through the whole stage yet always `None` in production and may "helpfully" stub a `target_price`. **Do not.** The `None` is the contract: the honesty constraint (never invent a target) is load-bearing. The metric is a plain numeric input — not `ThesisEvidence` — so it touches none of the ADR 0001 citation invariants (scope, dual-coverage gate, citation selector, SAME-3, H3, Policy B). This ADR exists so that "why build a metric that never fires?" has a recorded answer.
