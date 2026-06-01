# MASTER-SPEC — Funding (fundamentals) analysis enhancements

- **Mode:** backlog
- **Source:** `docs/funding-analysis-review.md` → `## Recommended changes` (5 points)
- **Date:** 2026-05-31
- **Feature branch:** `autodev/funding-analysis-feature` (synthesized off `main`; left open for user to land)
- **Decisions (locked at intake):** Opus authoring · PR shape A (per-item PRs) · Item 003 Tushare implemented with gated live tests + README setup docs.

## Scope classification

All 5 recommended changes are **IN scope**. No OUT items (SKIPPED.md empty).

| id | Title | Goal | IN/OUT |
|----|-------|------|--------|
| 001 | Use the data you already fetch | Populate `BrokerReport.target_price` from AkShare and derive a consensus **upside** metric; fetch `pe`/`pb` (`stock_a_indicator_lg` / `stock_individual_info_em`) and surface them into `OpportunityInput.pe_ttm`/`pb`. | IN |
| 002 | Fundamental `valuation_state` | Make `valuation_state` consume a **fundamental** valuation input (pe/pb + consensus upside), not only price percentile; gate `core_dca` on cheap-AND-intact in `opportunity/states.py`. | IN |
| 003 | Pluggable CN data layer + Tushare | Introduce a provider-agnostic CN fundamentals fetch interface with AkShare as default and **Tushare** as fallback/primary; wire the existing `tushare_token` stub; gate live Tushare tests (double-gated marker + env var); **update README** with Tushare setup. | IN |
| 004 | Dexter `key_ratios` surface | Deterministic pure `compute_ratios(financials) -> {roe, debt_equity, gross_margin, fcf_yield}` — no LLM; closes the balance-sheet / earnings-quality gap. | IN |
| 005 | Bull/bear debate | Add an optional `--adversarial` flag on the opportunity stage; add a `thesis_defend` LLM half to pair with the existing `thesis_falsify` (TradingAgents pattern). | IN |

## Context discovered at intake (grounds the per-item specs)

- `OpportunityInput` (`opportunity/types.py:69-114`) **already declares** `pe_ttm`, `pb`, `dividend_yield`, `earnings_yield`, `real_yield_10y`, plus valuation percentiles. Items 001/002 are about *populating + consuming* this scaffolding, not adding fields from scratch.
- `ValuationState` is already a defined Literal/state tuple (`cheap … very_expensive … evidence_insufficient`) and `OpportunityRow.valuation_state` exists. Item 002 wires a fundamental input into the existing classifier and the `core_dca` gate.
- `BrokerReport.target_price` exists (`fundamentals/types.py:182`) but `fetch_cn_broker_reports` hardcodes `target_price=None` (`fundamentals/akshare_filing.py:84`). Item 001 populates it.
- `tushare_token` is a declared-but-unused `SecretStr` stub (`settings.py:42`). Item 003 wires it.
- The LLM task registry routes by task name (`config/llm.yaml`); `thesis_falsify` (deepseek-reasoner) already exists. Item 005 adds `thesis_defend`.

## Hard constraints (apply to every item — from CONTEXT.md / ADRs / CLAUDE.md)

- **TDD** red→green→refactor; test file mirrors source. Files < 200 lines, functions < 20 lines (ideal).
- **Functional / immutable.** Pure cores; I/O at edges (thin wrappers + `commands/`). Frozen dataclasses; `dataclasses.replace`, never mutation.
- **Citation ID** locked at 16 hex chars (`\[ref:[0-9a-f]{16}\]`, ADR 0001). New evidence must respect the preimage contract.
- **`基金概况` indicator is forbidden** in production fetch code (acceptance test greps for it).
- **Policy B** sets publishability, never `thesis_state`; `derive_thesis_from_evidence` owns `thesis_state` (ADR 0003).
- **H3 / SAME-3 invariants** govern the opportunity partition + citation-set equality (ADR 0004).
- **Secrets in `.env` only**; YAML references env var names.
- **Live tests double-gated**: a `pytest.mark.<name>` marker AND an `IRC_*=1` env var.

## Out of scope (explicit non-goals — from the review's "Scope boundary")

Do **not** bolt trading onto IRC (signals, backtests, ML factors, transaction-cost modeling). Those live in the separate `ashare-quant` repo. None of the 5 items cross that line — they stay within fund-DCA + thesis-discipline. Item 005's debate is a *reasoning* aid, not a trading signal.
