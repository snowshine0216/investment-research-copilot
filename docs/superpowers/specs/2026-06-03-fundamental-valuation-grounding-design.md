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
| Q2 | `real_yield_10y` source & units | See §3.1 R1 — must land in **ratio units**; CN CPI dependency made explicit with a nominal-gap fallback. |
| Q3 | QDII fundamental valuation | **Defer** — QDII keeps NAV + premium in Phase 1. |
| Q4 | Risk divergence driver | **Out of Phase 1** — risk purely inherits the grounded valuation. |
| Q5 | PB's role | **Corroboration-note-only** in Phase 1 — PB percentile annotates the reason / flags cyclical earnings; it never notches the state. |

## 3.1 Review findings resolved (2026-06-03 spec review)

Five findings from the written-spec review, each verified against the code and resolved here.
The body sections (§4) are written to satisfy these.

**R1 (P1) — Real-yield units must be ratio, and the CPI dependency is unmet.**
`expected_real_return_positive` (`states.py:149`) compares `earnings_yield` against `real_yield_10y`
as raw floats, and the anchor tests use **ratio units** (`real_yield_10y=0.020`,
`tests/opportunity/test_earnings_yield_anchor.py:29`). But the CN 10Y ingest emits **percent
units** (`2.45 == 2.45%`, `akshare_client.py:421`), and `earnings_yield = 1/pe_ttm` is a ratio
(PE 14 → `0.071`). A percent-unit real yield (`≈2.1`) makes `0.071 > 2.1` **always false** — the
anchor would silently never fire. Resolution:
- `real_yield_10y` is populated in **ratio units**: divide the percent-unit computation by 100.
- **Source precedence:** (a) if a CN CPI-YoY macro series exists, `real_yield_10y =
  (cn_10y_yield − cpi_yoy) / 100`; (b) **CN CPI is not ingested today** — so Phase 1's default is
  the CN-standard **equity-bond yield gap** (股债利差) using the *nominal* 10Y CGB:
  `real_yield_10y = cn_10y_yield / 100`. The anchor then reads "equity earnings yield vs the
  nominal 10Y CGB yield," a well-understood CN allocation signal that needs no new CPI ingest.
  Ingesting CN CPI to switch from nominal to real is a clean follow-on, not a Phase-1 blocker.
- **Do NOT** reuse `real_yield_10y_tips` (a **US TIPS** series, percent units) — wrong geography
  and wrong units for a CN equity anchor. The two are distinct; keep them separate.

**R2 (P1) — The divergence advisory needs an explicit thread into `advisory_gaps`.**
`classify_valuation` returns only `(state, reason)` (`states.py:194`); `build_opportunity_row`
derives advisories solely from `_partition_gaps(structural_gaps + thesis_gaps)`
(`states.py:587`). There is no path for a classifier-emitted advisory. Resolution in §4.4: a
single pure detector `valuation_divergence_code(inp) -> str | None` is the one source of truth —
`classify_valuation` calls it for the reason note, and `build_opportunity_row` calls it to fold
the code into `combined_gaps` before `_partition_gaps`. The code
`valuation_price_fundamental_divergence` is registered in `ADVISORY_GAP_CODES` so it routes to
`advisory_gaps` (never `evidence_gaps`; H3 partition untouched).

**R3 (P1) — `opportunity` must not fetch live; replace the provider call with a cached read.**
`populate_inputs` today **live-calls** `provider.fetch_index_valuation` (`inputs_loader.py:155`),
which violates the cached-evidence invariant. Resolution in §4.3: that call is **removed**.
`populate_inputs` reads the cached `index_valuation_history` table — the latest row supplies
`pe_ttm`/`pb`/`dividend_yield` (for the reason text and `earnings_yield`), the full series
supplies the percentile. No network I/O remains in the opportunity stage.

**R4 (P2) — History fetch is AkShare-only ingest infra, NOT a 4th provider method.**
`CnFundamentalsProvider` is a 3-method `Protocol` (ADR 0010, `provider.py:31`). Resolution:
`fetch_cn_index_valuation_history` is called **only by the ingest writer** (effect at the edge),
so the provider seam, ADR 0010, and provider tests are **untouched**. Consequence: with R3
removing the `populate_inputs` call, `provider.fetch_index_valuation` is no longer exercised by
the opportunity path; it remains a valid seam method (harmless, still tested) and its removal is
out of scope. Phase-1 history is AkShare-only (legulegu); a Tushare history fallback is a future
enhancement, not Phase 1.

**R5 (P2) — Consensus-upside precedence vs the PE-percentile verdict.**
`compose_opportunity_state` vetoes `core_dca` when `valuation_fundamental == "rich"` and the
valuation is cheap/reasonable_low (`states.py:451`); with this design that cheap verdict can now
come from the PE-percentile anchor. Resolution: **preserve the veto** — when the PE-percentile
anchor says cheap but the (future) consensus-upside signal says rich, the row drops to
`small_watch`, not `core_dca`. Rationale: the two are *independent fundamental lenses* (trailing
PE percentile vs forward analyst target); a genuine disagreement warrants a watch, not a
green light. `valuation_state` itself stays cheap (AC3 preserved). This needs **no change** to
`compose_opportunity_state` (it already operates on `valuation_state` regardless of derivation).
The veto is latent in production until a target-price feed lands (still `None` per ADR 0009), and
flipping the precedence later is a one-line change in the contradiction gate.

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
  `基金概况` indicator is never used (existing acceptance test still passes). **AkShare-only**:
  called **only by the ingest writer** — NOT added to the `CnFundamentalsProvider` seam, so
  ADR 0010 and the provider tests are untouched (R4).
  - `IndexValuationHistory` (new frozen type in `index_valuation_types.py`):
    `(index_key: str, rows: tuple[IndexValuationPoint, ...])` where
    `IndexValuationPoint = (date_iso: str, pe_ttm: float | None, pb: float | None, dividend_yield: float | None)`.
- **New DuckDB table** `index_valuation_history(index_key TEXT, date DATE, pe_ttm DOUBLE,
  pb DOUBLE, dividend_yield DOUBLE)`, registered in `data/duckdb_helper.py::EXPECTED_TABLES`.
  Populated by an **ingest-stage** writer (one row per index per date), keyed by
  `(index_key, date)`. Refreshed on `irc run --from ingest` like other market data. This is the
  **only** source `populate_inputs` reads for index valuation — no live provider call (R3).
- **Real-yield anchor input (ratio units — R1).** `OpportunityInput.real_yield_10y` is populated
  in **ratio units**, matching `earnings_yield = 1/pe_ttm` and the existing anchor tests:
  - Default (Phase 1, no CN CPI ingested): `real_yield_10y = cn_10y_yield / 100` — the nominal
    10Y CGB yield as a ratio (the 股债利差 equity-bond yield-gap reading).
  - If/when a CN CPI-YoY series is ingested: `real_yield_10y = (cn_10y_yield − cpi_yoy) / 100`.
  - **Never** reuse `real_yield_10y_tips` (US TIPS, percent units — wrong geography/units).
  - `earnings_yield` is **not** stored; derived in `populate_inputs` as `1.0 / pe_ttm`
    (`pe_ttm > 0`). Both sides of the anchor comparison are therefore ratios.

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

- **Remove the live provider call (R3).** Delete the `provider.fetch_index_valuation(...)` call
  inside `_index_valuation_metrics` (`inputs_loader.py:155`). `populate_inputs` no longer touches
  the network for index valuation; the `provider` parameter is retained only for the
  broker-reports / consensus path.
- Resolve the fund → index via the existing `skeleton.tracked_index` + `_BROAD_INDEX_KEYS` gate.
- Read the index PE/PB **history** from the new DuckDB table (a pure `_index_valuation_series`
  reader mirroring `_price_series`). From this single read:
  - **latest row** → `pe_ttm` / `pb` / `dividend_yield` (for the reason text and `earnings_yield`);
  - **full series** → `self_history_percentile` over PE and PB →
    `valuation_percentile_fundamental` / `valuation_percentile_fundamental_pb`. Reuse
    `self_history_percentile` verbatim (≥30 points, rank-inclusive); `<30` points → `None`
    (clean fallback to NAV).
- Set `earnings_yield = 1.0 / pe_ttm` when `pe_ttm` present and `> 0`. Set `real_yield_10y` in
  **ratio units** per §4.1 R1 (read `cn_10y_yield` from `macro_series`, `/100`; subtract CPI-YoY
  ratio if that series is present).

### 4.4 `classify_valuation` algorithm change (`src/irc/opportunity/states.py:194`)

Equity asset classes only (`_EQUITY_ASSET_CLASSES`); bonds and unknown classes are untouched.

1. **Fundamental decides.** `fund_pct = inp.valuation_percentile_fundamental`. If present, band on
   it using the **existing** thresholds (cheap `<.20`, reasonable_low `<.40`, fair `<.70`,
   expensive `<.90`, very_expensive `≥.90`). The reason string names the PE percentile.
2. **Fallback.** If `fund_pct is None`, band on `valuation_percentile_self` (today's behavior,
   byte-for-byte unchanged) → guarantees the NAV-only regression suite stays green.
3. **Divergence reason note.** If `valuation_divergence_code(inp)` (the shared detector, §4.4a)
   is non-`None`, `classify_valuation` appends a reason note. (Price near highs but PE percentile
   low ⇒ earnings outran price ⇒ genuinely *not* expensive; the reverse ⇒ a warning.) Note only
   here — the `advisory_gaps` code is folded in by `build_opportunity_row`, not by
   `classify_valuation` (R2; `classify_valuation` keeps its `(state, reason)` signature).
4. **PB corroboration note.** If PB percentile sharply disagrees with the PE verdict (e.g. PE-band
   cheap but PB percentile `≥ .70`), append a cyclical/earnings-quality caveat to the reason.
   **No state change** in Phase 1 (Q5).
5. **Earnings-yield anchor.** The existing `expected_real_return_positive` branch
   (`states.py:224–238`) is unchanged — it now fires because `earnings_yield`/`real_yield_10y`
   carry ratio-unit data (§4.1 R1), appending the long-horizon-DCA caveat for expensive states.

### 4.4a Divergence threading (R2)

One pure detector is the single source of truth, so the reason note and the advisory code can
never drift:

```python
# src/irc/opportunity/states.py
DIVERGENCE_PCT_GAP: float = 0.25
VALUATION_DIVERGENCE_CODE: str = "valuation_price_fundamental_divergence"

def valuation_divergence_code(inp: OpportunityInput) -> str | None:
    """Return the advisory code when the fundamental and NAV percentiles
    disagree (different band-tier OR |gap| >= DIVERGENCE_PCT_GAP); else None."""
    f, n = inp.valuation_percentile_fundamental, inp.valuation_percentile_self
    if f is None or n is None:
        return None
    if _band(f) != _band(n) or abs(f - n) >= DIVERGENCE_PCT_GAP:
        return VALUATION_DIVERGENCE_CODE
    return None
```

- `classify_valuation` calls it for the step-3 reason note.
- `build_opportunity_row` (`states.py:587`) folds it into the gap stream before partitioning:
  `combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps) + tuple(_divergence_gaps(inp))`,
  where `_divergence_gaps` wraps `valuation_divergence_code` into a 0/1-tuple.
- `VALUATION_DIVERGENCE_CODE` is added to `ADVISORY_GAP_CODES`, so `_partition_gaps` routes it to
  `advisory_gaps` (never `evidence_gaps`) → H3 partition and SAME-3 invariants untouched.

### 4.4b Consensus-upside precedence (R5)

`compose_opportunity_state` and `derive_contributing_dimensions` need **no change**. The existing
`fundamental_contradiction` veto (`valuation_fundamental == "rich"` while valuation is
cheap/reasonable_low → refuse `core_dca`, fall to `small_watch`) is **preserved as-is**, and now
applies even when the cheap verdict came from the PE-percentile anchor. Rationale: trailing PE
percentile and forward analyst target are independent fundamental lenses; their disagreement is a
watch signal, not a green light. `valuation_state` stays cheap (AC3). The veto is latent until a
target-price feed exists (`consensus_upside_pct` is `None` in prod, ADR 0009); flipping the
precedence later is a one-line change in the contradiction gate. The PE-percentile anchor remains
the **band input** that sets `valuation_state`; the consensus-upside signal only gates the
`core_dca` promotion — they are not in conflict over the state itself.

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
  - `valuation_divergence_code` (R2): band-tier crossing **and** the `≥0.25` gap each return
    `VALUATION_DIVERGENCE_CODE`; agreement and any `None` percentile return `None`.
  - `classify_valuation` appends the divergence reason note but its return stays `(state, reason)`
    (no signature change).
  - PB corroboration note appears (and does **not** change state).
  - earnings-yield anchor fires once `earnings_yield`/`real_yield_10y` are set.
- **Pure unit — divergence routing (R2):** `build_opportunity_row` with divergent percentiles
  puts `valuation_price_fundamental_divergence` in `row.advisory_gaps` and **not** in
  `row.evidence_gaps`; the row stays publishable (`evidence_gaps == ()`).
- **Pure unit — real-yield units (R1):** `populate_inputs` with `cn_10y_yield = 2.45` (percent)
  yields `real_yield_10y ≈ 0.0245` (ratio); combined with `pe_ttm = 14` (`earnings_yield ≈
  0.071`) the anchor reads **positive** — the explicit regression against the always-false bug.
- **Pure unit — no live fetch (R3):** `populate_inputs` is called with a provider stub whose
  `fetch_index_valuation` raises if invoked; the test passes only because the index path reads the
  cached `index_valuation_history` fixture, proving the opportunity stage performs no live index
  fetch.
- **Pure unit (`tests/opportunity/test_inputs_loader.py`):** percentile computed from a DuckDB
  fixture; latest-row `pe_ttm`/`pb`; `earnings_yield = 1/pe_ttm`; missing index → fields `None`.
- **Adapter (`tests/fundamentals/test_akshare_index_valuation.py`):**
  `fetch_cn_index_valuation_history` extracts the full series from a DataFrame fixture; failure
  → `None`. A `live_akshare`-gated smoke test (double-gated per the Live-test gate).
- **Provider seam unchanged (R4):** no new test churn — `CnFundamentalsProvider` stays 3-method;
  the existing provider tests pass untouched.
- **Regression:** existing valuation tests pass unchanged for funds with no fundamental data.

## 9. Phasing / rollout

- **1a — data:** `fetch_cn_index_valuation_history` (AkShare-only), `index_valuation_history`
  table + ingest-stage writer. `real_yield_10y` is derived from the already-ingested
  `cn_10y_yield` (ratio, §4.1 R1) — no new macro series required for Phase 1 (CN CPI ingest is a
  later refinement).
- **1b — classifier:** new `OpportunityInput` fields, `populate_inputs` wiring (cached read, live
  provider call removed — R3), `classify_valuation` fundamental-decides + divergence note + PB
  note + lit earnings-yield anchor, `valuation_divergence_code` + `build_opportunity_row`
  threading (R2), `ADVISORY_GAP_CODES` entry, legend note.
- **(Phase 2 — look-through):** separate spec.

Each sub-phase is independently shippable: 1a lands inert data; 1b activates the verdict change.
