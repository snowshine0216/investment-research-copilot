# Fundamental-Grounded Valuation (Risk Inherits It) — Design

**Date:** 2026-06-03
**Status:** Approved (brainstorm) → pending implementation plan
**Author:** pairing session (valuation-grounding review)

## Context

Today the equity "expensive / cheap" verdict (`valuation_state`) is decided by a
**price/NAV self-history percentile** — *where does today's NAV rank within its own
trailing series* (`classify_valuation` → `_percentile` → `self_history_percentile`,
`src/irc/opportunity/states.py:194`, `src/irc/opportunity/returns.py:59`). That is a
price-level / momentum signal, not a fundamental valuation. The classifier's own comment
concedes *"Drawdown alone is NEVER evidence of cheapness"* — but its positive signal is the
same family (price relative to its own past).

The architecture already anticipated fundamentals, but **every fundamental hook is inert in
production**:

| Hook | File | Why it is dead today |
|---|---|---|
| `earnings_yield − real_yield_10y` sanity anchor | `states.py:149` `expected_real_return_positive` | `earnings_yield` never populated → always `None` |
| `consensus_upside_pct` (analyst target vs price) | `valuation_fundamental.py:26` | `None` in prod — EastMoney feed has no target prices (ADR 0009) |
| `pe_ttm` / `pb` | `valuation_fundamental.py:46` `_pe_pb_fragment` | **reason-only** — annotates Chinese text, never changes state; fetched for broad indices only, and only the **latest** row (`akshare_index_valuation.py:57` `_extract_latest_value` discards the history) |

Risk inherits the limitation: `derive_position_risk_level`
(`src/irc/narrative/risk.py:52`) is a severity accumulator whose `valuation` driver is the
NAV-percentile verdict above. Grounding valuation therefore grounds risk for free.

This design makes the equity valuation verdict **fundamental-led** (PE/PB in historical
percentile context), keeping the NAV percentile as a fallback and a divergence signal. It is
phased: **Phase 1 top-down index-valuation percentile** (mostly reactivating data the code
already fetches and throws away), **Phase 2 bottom-up holdings look-through** (sketched here,
its own spec later).

## 1. Goals

- Make `valuation_state` for equity vehicles **decided by a fundamental-valuation percentile**
  (index PE-TTM historical percentile) when available, not the NAV price percentile.
- Keep the NAV self-history percentile as (a) the **fallback** when no fundamental data, and
  (b) a **divergence signal** when price-trend and fundamentals disagree.
- **Light up** the existing earnings-yield-vs-real-yield anchor by feeding it real data.
- Let **risk inherit** the grounded valuation with no change to the risk algorithm.
- Preserve every existing project invariant: pure classifiers, effects at the edges,
  `irc opportunity` reads **cached** evidence (no live fetch), determinism, TDD.

## 2. Non-goals

- **Not** changing `classify_product_quality` — the `weak`/`strong` judgment stays
  cost/scale/tenure (expense ratio, AUM, tracking error, manager tenure). PE/PB do not measure
  operational product quality. (The `aum_stability_pct` floor was already removed in F-1,
  commit `6b2ac48`.)
- **Not** changing the bond valuation path — `classify_bond_valuation` already uses a
  fundamental anchor (10Y CGB yield percentile).
- **Not** grounding QDII (Nasdaq/S&P/HK) valuation in Phase 1 — legulegu's index PE/PB endpoints
  are A-share-only; QDII keeps NAV percentile + the existing premium-to-NAV signal until a US/HK
  index-valuation source is added (deferred; see §8).
- **Not** implementing Phase 2 look-through here (sketch only; separate spec).
- **Not** introducing live network I/O into the `opportunity` stage.

## 3. Resolved decisions (from brainstorm)

| # | Decision | Resolution |
|---|---|---|
| Q1 | Divergence trigger | **Either** a band-tier crossing **or** `|pct_gap| ≥ 0.25` fires the divergence advisory. |
| Q2 | `real_yield_10y` source | Use an existing real-yield macro series if present; **else compute** `10Y nominal − latest CPI YoY` at ingest. |
| Q3 | QDII fundamental valuation | **Defer** — QDII keeps NAV + premium in Phase 1. |
| Q4 | Risk divergence driver | **Out of Phase 1** — risk purely inherits the grounded valuation. |
| Q5 | PB's role | **Corroboration-note-only** in Phase 1 — PB percentile annotates the reason / flags cyclical earnings; it never notches the state. |

## 4. Phase 1 — index-valuation-percentile anchor (top-down)

### 4.0 Coverage (which funds get grounded vs. fall back)

The fundamental anchor is gated on `tracked_index ∈ _BROAD_INDEX_KEYS` (the same gate
`_index_valuation_metrics` already uses). This means Phase 1 grounds **broad-index CN ETFs /
index funds** (沪深300, 中证500/1000, A500, 上证50, 科创50, 创业板, 中证红利, 红利低波).
Everything else falls back to the NAV percentile, **by design and for free**:

- **QDII** (`us_etf`/`hk_etf`/`qdii_global`) — their `tracked_index` lives in `_QDII_US_KEYS` /
  `_QDII_HK_KEYS`, not `_BROAD_INDEX_KEYS`, so the gate already excludes them (Q3 deferral needs
  no extra code; legulegu is A-share-only anyway).
- **Sector-theme CN ETFs** (半导体, 医药, 新能源, …) — these carry a `theme`, not a broad
  `tracked_index`, so they also fall back. Extending coverage to sector indices (adding their
  legulegu names) is a follow-on, not part of Phase 1.
- **Active funds** (`cn_equity_fund`) — no `tracked_index`; covered by Phase 2 look-through.

So Phase 1 changes the verdict for broad-index vehicles and leaves all other vehicles exactly as
they classify today. This bounds the blast radius and makes the regression suite the proof.

### 4.1 Data layer (effects at the edge)

The `opportunity` stage must read **cached** evidence, so all fetching happens upstream in the
ingest/fundamentals layer and lands in DuckDB.

- **New fetch** `fetch_cn_index_valuation_history(index_key: str) -> IndexValuationHistory | None`
  in `src/irc/fundamentals/akshare_index_valuation.py`. Same legulegu endpoints
  (`stock_index_pe_lg`, `stock_index_pb_lg`) as `fetch_cn_index_valuation`, but **keeps the full
  time series** instead of `_extract_latest_value`'s last row. Degrade-to-`None` contract
  unchanged (unknown key / adapter failure / empty frame → `None`, never raises). The forbidden
  `基金概况` indicator is never used (existing acceptance test still passes).
  - `IndexValuationHistory` (new frozen type in `index_valuation_types.py`):
    `(index_key: str, rows: tuple[IndexValuationPoint, ...])` where
    `IndexValuationPoint = (date_iso: str, pe_ttm: float | None, pb: float | None, dividend_yield: float | None)`.
- **New DuckDB table** `index_valuation_history(index_key TEXT, date DATE, pe_ttm DOUBLE,
  pb DOUBLE, dividend_yield DOUBLE)`, registered in `data/duckdb_helper.py::EXPECTED_TABLES`.
  Populated by an **ingest-stage** writer (one row per index per date), keyed by
  `(index_key, date)`. Refreshed on `irc run --from ingest` like other market data.
- **Macro series for the anchor**: ensure `real_yield_10y` is available as a macro series
  (`cn_10y_real_yield`) — read if a series exists, otherwise compute
  `cn_10y_yield − cpi_yoy` at ingest and persist it as a derived series. `earnings_yield` is
  **not** stored; it is derived in `populate_inputs` as `1.0 / pe_ttm` (when `pe_ttm > 0`).

### 4.2 New `OpportunityInput` fields

Added to the frozen dataclass (`src/irc/opportunity/types.py`), all defaulting to `None` so
every existing construction site and cached row stays valid:

- `valuation_percentile_fundamental: float | None` — PE-TTM historical percentile. **Primary
  anchor.** Direction matches price percentile: high = expensive.
- `valuation_percentile_fundamental_pb: float | None` — PB historical percentile.
  Corroboration only.

`earnings_yield` and `real_yield_10y` already exist on the type (lines 113–114); they simply
get populated now.

### 4.3 `populate_inputs` wiring (`src/irc/opportunity/inputs_loader.py`)

- Resolve the fund → index via the existing `skeleton.tracked_index` + `_BROAD_INDEX_KEYS`
  (same gate `_index_valuation_metrics` already uses).
- Read the index PE/PB **history** from the new DuckDB table (a pure `_index_valuation_series`
  reader mirroring `_price_series`). Compute `self_history_percentile` over the PE series and the
  PB series → `valuation_percentile_fundamental` / `valuation_percentile_fundamental_pb`. Reuse
  `self_history_percentile` verbatim (≥30 points, rank-inclusive — already battle-tested);
  fewer than 30 points → `None` (clean fallback to NAV).
- Set `earnings_yield = 1.0 / pe_ttm` when `pe_ttm` present and `> 0`; read `real_yield_10y`
  from `macro_series`.
- Keep the existing `pe_ttm`/`pb`/`dividend_yield` latest-value population for the reason text.

### 4.4 `classify_valuation` algorithm change (`src/irc/opportunity/states.py:194`)

Equity asset classes only (`_EQUITY_ASSET_CLASSES`); bonds and unknown classes are untouched.

1. **Fundamental decides.** `fund_pct = inp.valuation_percentile_fundamental`. If present, band on
   it using the **existing** thresholds (cheap `<.20`, reasonable_low `<.40`, fair `<.70`,
   expensive `<.90`, very_expensive `≥.90`). The reason string names the PE percentile.
2. **Fallback.** If `fund_pct is None`, band on `valuation_percentile_self` (today's behavior,
   byte-for-byte unchanged) → guarantees the NAV-only regression suite stays green.
3. **Divergence advisory.** If both `fund_pct` and `valuation_percentile_self` are present and
   they (a) fall in different band-tiers **or** (b) differ by `≥ 0.25`, append a reason note and
   add `valuation_price_fundamental_divergence` to `advisory_gaps`. (Price near highs but PE
   percentile low ⇒ earnings outran price ⇒ genuinely *not* expensive; the reverse ⇒ a warning.)
   The code is a new entry in `ADVISORY_GAP_CODES` (`src/irc/opportunity/states.py`) so H3's
   partition is unaffected (advisory ≠ blocking).
4. **PB corroboration note.** If PB percentile sharply disagrees with the PE verdict (e.g. PE-band
   cheap but PB percentile `≥ .70`), append a cyclical/earnings-quality caveat to the reason.
   **No state change** in Phase 1 (Q5).
5. **Earnings-yield anchor.** The existing `expected_real_return_positive` branch
   (`states.py:224–238`) is unchanged — it now fires because `earnings_yield`/`real_yield_10y`
   carry data, appending the long-horizon-DCA caveat for expensive/very_expensive equities.

The `valuation_fundamental_signal` (consensus-upside) branch stays as-is — still `None` in prod,
still corroboration-only. The new fundamental percentile is a **separate, now-live** anchor that
supersedes the NAV percentile as the band input.

`compose_opportunity_state` and the contributing-dimensions logic need **no change** — they
consume `valuation_state`, whose vocabulary is unchanged.

### 4.5 Advisory surface

`valuation_price_fundamental_divergence` is an `advisory_gaps` code (row stays publishable). It
appears on publishable rows by design and can co-exist with other advisories (e.g.
`top_holdings_broker_thin`), exactly like the existing advisory machinery (CONTEXT.md
"`advisory_gaps`"). The `robots_report.md` / discipline legends gain a one-line note explaining
the divergence flag.

## 5. Phase 2 — holdings look-through (bottom-up, active funds) — sketch

For `cn_equity_fund` (always routes to `active_fund`, no `tracked_index`):

- New per-stock valuation fetch (`stock_a_indicator_lg` or Tushare `daily_basic`) → per-holding
  `pe_ttm`/`pb`/`dividend_yield` (+ history), cached under
  `data/fundamentals/<quarter>/stock_valuation/`.
- Weight each top-N holding's PE/PB by `FundHolding.weight_pct` → fund-level weighted PE/PB →
  percentile, feeding the **same** `valuation_percentile_fundamental` slot.
- **Open method question (resolve in Phase 2 spec):** percentile of the fund's *constructed
  weighted-PE history* vs. a *percentile-of-percentiles* of constituents; and how to handle the
  top-10 truncation and HK/US holdings with no A-share indicator coverage.

Phase 2 is intentionally not designed in full here; it gets its own spec once Phase 1 ships and
the index-percentile anchor is validated against real output.

## 6. Risk inheritance

`derive_position_risk_level` is **unchanged**. Its `valuation_state` driver (expensive /
very_expensive → `+2` severity) now reflects fundamentals. The Phase-1 `+1` mean-reversion
driver for divergence is explicitly **deferred** (Q4).

## 7. Determinism, purity, and invariants

- Classifiers (`classify_valuation`, `populate_inputs`'s pure helpers) stay side-effect-free and
  unit-testable without mocks; all network I/O is in the new ingest fetcher.
- `irc opportunity` reads the new table from DuckDB — **no live fetch** (CLAUDE.md rule).
- Percentile is deterministic (`self_history_percentile`, rank-inclusive, `<30` → `None`).
- `advisory_gaps` (not `evidence_gaps`) ⇒ H3 partition and SAME-3 citation invariants untouched.
- Citation-ID, Policy B, dual-coverage gate: all unaffected (valuation is a classifier verdict,
  not an evidence record).

## 8. Test strategy (TDD)

Red → green, test file mirrors source.

- **Pure unit (`tests/opportunity/test_states.py` additions):**
  - fundamental-decides path lands each band from a synthetic `valuation_percentile_fundamental`.
  - fallback path: `valuation_percentile_fundamental=None` reproduces today's NAV verdict
    exactly (regression lock).
  - divergence: both percentiles present, band-tier crossing **and** the `≥0.25` gap each emit
    `valuation_price_fundamental_divergence`; agreement emits nothing.
  - PB corroboration note appears (and does **not** change state).
  - earnings-yield anchor fires once `earnings_yield`/`real_yield_10y` are set.
- **Pure unit (`tests/opportunity/test_inputs_loader.py`):** percentile computed from a DuckDB
  fixture; `earnings_yield = 1/pe_ttm`; missing index → fields `None`.
- **Adapter (`tests/fundamentals/test_akshare_index_valuation.py`):**
  `fetch_cn_index_valuation_history` extracts the full series from a DataFrame fixture; failure
  → `None`. A `live_akshare`-gated smoke test (double-gated per the Live-test gate).
- **Regression:** existing valuation tests pass unchanged for funds with no fundamental data.

## 9. Phasing / rollout

- **1a — data:** new fetch, `index_valuation_history` table + ingest writer, real-yield macro
  series.
- **1b — classifier:** `OpportunityInput` fields, `populate_inputs` wiring, `classify_valuation`
  fundamental-decides + divergence + PB note + lit earnings-yield anchor, new advisory code,
  legend note.
- **(Phase 2 — look-through):** separate spec.

Each sub-phase is independently shippable: 1a lands inert data; 1b activates the verdict change.
