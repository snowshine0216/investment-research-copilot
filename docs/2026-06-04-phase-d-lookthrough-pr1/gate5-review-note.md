# Phase D — gate #4 / gate #5 review note (PR2 sign-off)

**Date:** 2026-06-05 · **Reviewer:** user (floor decision) · driven by Claude

This is the short review note the spec (§10) asks PR2 to record — the gate outcomes, the chosen `coverage_floor`, and the recorded before/after impact. It replaces a PR2 spec (none needed; ADR 0012 addendum is the durable design-of-record).

## Gate #4 — live EastMoney column confirmation: **PASS**

```
IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare \
  tests/fundamentals/test_stock_valuation_live.py -v -s
```
Live `stock_value_em` for 600519 (贵州茅台): **2041 rows, latest PE=19.16, PB=5.85**; the `数据日期`/`PE(TTM)`/`市净率` → `(date, pe_ttm, pb)` extraction holds against the real API. No silently-guessed column strings ship.

## Gate #5 — diff report review + floor decision: **GO, floor = 0.50**

Ingest: `irc fundamentals stock-valuation` fetched **393/393 distinct A-shares** (0 failures, all EastMoney, 702,641 rows). Report: `irc lookthrough-diff` → 95 active funds (copy: `gate5-diff-report-2026-06-05.md`).

**Coverage-floor sensitivity (grounded = clears floor AND 120/180 maturity gate):**

| floor | grounded funds |
|---|---:|
| 0.40 | 71 |
| **0.50 (chosen)** | **40** |
| 0.60 | 17 |

**Decision:** `coverage_floor = 0.50` — the spec placeholder; each grounded fund is built on ≥50% of NAV (balanced precision/reach). Reach is modest and honest (spec §11): the maturity gate, not just coverage, is the binding constraint.

**Headline finding — flips are systematically one-directional:** every band flip in the report goes **NAV-momentum-expensive → PE-cheaper** (large negative Δpercentile; e.g. `001054 工银新金融` very_expensive→cheap Δ−0.85; `110022 易方达消费` fair→cheap Δ−0.53). Economically coherent: NAV near its own highs while underlying A-share holdings sit at reasonable PE percentiles. This is the intended signal — moving the active block off the NAV momentum proxy.

**Methodology check — no flaw, one data-completeness follow-up:**
- HK-holding funds (`006809`/`020397`/`501025`) correctly degrade to None (no A-share coverage → NAV fallback). ✓
- Per-metric PE/PB split works (a few funds show higher PB than PE coverage). ✓
- Several *index* products (`...指数`/`指数增强`/`LOF`) land in the active look-through because they lack a `tracked_index` mapping in `config/universe/cn_funds.generated.yaml`. Look-through still produces a valid percentile for them — **not a blocker**; a follow-up is to add their `tracked_index` mappings so they ride the cleaner index path.

## Recorded before/after (real cached data)

`irc opportunity` run twice on the 2026-06-03 watchlist (scratch dirs), flag OFF vs ON:

| | flag OFF | flag ON |
|---|---|---|
| rows / cards / rejections | 78 / 17 / 0 | 78 / 17 / 0 (**identical — H3/SAME-3 intact**) |
| instruments missing valuation | 11/126 | 8/126 |

**`valuation_state` changes (3):**
- `002258 大成国企改革` very_expensive → reasonable_low (opp unchanged)
- `003304 前海开源沪港深核心资源` evidence_insufficient → fair (opp unchanged)
- `110022 易方达消费行业` fair → **cheap** → **`opportunity_state` small_watch → core_dca**

**`opportunity_state` changes (1):** `110022 易方达消费行业` → `core_dca` (PE look-through says its holdings are cheap; combined with an intact thesis it becomes eligible for DCA where the NAV proxy had it on watch).

## PR2 changes
- `active_fund_lookthrough.enabled: true`, `coverage_floor: 0.50` (template + user-local).
- ADR 0012 addendum (2026-06-05); CONTEXT.md "Valuation inputs" (`active_fund_lookthrough` entry); CHANGELOG `[Unreleased]` Changed entry. No VERSION bump.
