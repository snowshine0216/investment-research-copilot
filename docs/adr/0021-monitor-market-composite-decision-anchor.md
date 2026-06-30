# ADR 0021 — Monitor Report v2: Market-Composite Decision Anchor + News Overlay

**Status:** Accepted  
**Date:** 2026-06-30  
**Deciders:** Xue Yin

---

## Context

The monitor report's single composite score (完整C) blends four market factors
(trend, valuation, flow, heat) **and** two news factors (macro_tilt, constituent).
News factors are highly volatile, often flipping the displayed directional bias
between same-day re-runs while market factors remain byte-identical (see
MEMORY.md → "Monitor macro_tilt instability").

Users need a stable, auditable decision anchor for position-sizing — one that
separates the volatile news overlay from the more persistent market signal.

## Decision

### 1. Market-Composite (市场面综合分)

Computed **at render time** from `signal.contributions`:

- Filter contributions to the "market" family (trend / valuation / flow / heat).
- Renormalize surviving weights to sum to 1 (per-fund, per-run).
- The resulting composite drives `_bias()` using the same buy=+0.40 / sell=−0.40
  band thresholds as the full composite.

This is a **render-derived value** — it does NOT change `SignalRecord`, the
engine computation, `_ENGINE_VERSION`, or any existing output contracts.

### 2. News Overlay (新闻叠加)

```
news_delta = full_C − market_composite
```

Displayed alongside the market anchor with an 易变 (volatile) label.

### 3. Honesty Caveat

All decision-anchor displays include the plain-language caveat:
> 市场面综合分 前瞻验证累积中 · 目前仅趋势单因子有历史命中 ~0.54

This is unconditional — it does not disappear once the forward eval matures.

### 4. Forward Ledger Schema Extension

`ledger_row` gains two additive, back-compat keyword arguments:

| Field | Type | Notes |
|---|---|---|
| `market_composite` | `float \| None` | None for legacy rows |
| `market_bias` | `str \| None` | None for legacy rows |

These propagate to `ForwardRow` and are consumed by
`build_metric_reports` to emit a non-gating
`market_composite_directional` details block (present only when rows
carry the field; absent for legacy runs — no panel breakage).

### 5. What does NOT change

- `_ENGINE_VERSION` stays "3"
- `SignalRecord.composite` is unchanged
- `signal.bias` / `published_state` / gate logic untouched
- No new network calls or LLM calls

## Consequences

- Every fund card in the monitor report now shows a market-composite anchor with
  a diverging contribution-bar SVG and a bias-history timeline.
- The forward eval can eventually surface whether the market-composite leads the
  full composite in predictive accuracy.
- Runs on hosts with geo-blocked EastMoney (flow DARK) will show
  `eligible_market_factors=2` or fewer without breaking the render.
