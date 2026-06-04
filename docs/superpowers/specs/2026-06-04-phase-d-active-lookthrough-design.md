# Phase D — active-fund holdings look-through (design spec)

**Status:** Draft for review (2026-06-04)
**Roadmap:** [`docs/2026-06-04-valuation-coverage-roadmap/ROADMAP.md`](../../2026-06-04-valuation-coverage-roadmap/ROADMAP.md) §Phase D.
**Builds on:** [ADR 0012 — fundamental-led equity valuation](../../adr/0012-fundamental-led-equity-valuation.md) (the `valuation_percentile_fundamental` seam, `self_history_percentile`, the 120/180 maturity gate, PB corroborate-only, the divergence advisory), [ADR 0009 — consensus-upside degrade-to-None](../../adr/0009-consensus-upside-degrade-to-none.md) (degrade-to-None discipline), valuation-grounding item 001 §5 (the original sketch this supersedes).
**Goal:** Populate `valuation_percentile_fundamental` for active CN equity funds (no `tracked_index`) by looking through to their disclosed top-N A-share holdings, so the largest block of the universe (383 funds, 58%) moves off the NAV momentum proxy and onto a PE/PB anchor.

---

## 1. What it does (one sentence)

For each active CN equity fund, reconstruct a **current-basket PE (and PB) series** from its cached top-N A-share holdings' per-stock valuation history, take the `self_history_percentile` of the latest value, and — behind a default-off config flag — feed it into the **existing** `valuation_percentile_fundamental` slot that `classify_valuation` already consumes.

## 2. Why this shape

The index-valuation pipeline (ADR 0012) already proves the seam end-to-end: `fetch history → ingest to a DuckDB table → inputs_loader reads cached → self_history_percentile → valuation_percentile_fundamental → classify_valuation`. Phase D adds a **per-stock sibling** of that fetch/ingest path plus **one new pure aggregation module** that rolls constituents up into the fund-level series. No new classifier logic, no new advisory, no change to the slot's meaning — an active fund's fundamental percentile is the same numeric input an index fund's already is.

The 58% active block is both the **bulk** and the **hardest** piece (roadmap §2): it has no index, so look-through is the only path, and it is the largest blast radius. Hence the rollout is deliberately split into shadow-compute (this spec's PR1) and flag-flip (PR2), gated by a human output review.

## 3. Decisions (locked)

All five load-bearing decisions and six review amendments are settled. This section is the contract.

### 3.1 Roll-up method — constructed current-basket PE series (harmonic / earnings-yield)
Build a synthetic series for the fund's **current** disclosed top-N A-share basket, then percentile its latest value. Aggregation is **earnings-yield (harmonic)**, the mathematically correct portfolio PE:

```
EY_fund(t) = Σ_i  w̃_i(t) · (1 / PE_i(t))         PE_fund(t) = 1 / EY_fund(t)
```

where `w̃_i(t)` are the **current** top-N weights, renormalized over the holdings that have a PE point on date `t` (per-date renormalization — §3.4). The latest value's percentile is `self_history_percentile(PE_fund_series)`.

**Naming (review P1):** this is a **current-basket** series — current weights applied to *past* per-stock PE. It is **not** the fund's true historical PE through time (that would need historical holdings, which we do not store). The honest name is used throughout, and the caveat is surfaced in the diff report (§8).

PB runs the **identical harmonic aggregation** on book yield (`1/PB`): `PB_fund(t) = 1 / Σ w̃_i(t)·(1/PB_i(t))`, into `valuation_percentile_fundamental_pb`, corroborate-only.

Rejected: *percentile-of-percentiles* (weight-averaging each stock's own percentile) — a mean of percentiles is not a percentile, loses the absolute-level signal, and is not comparable to the index-path semantics.

### 3.2 Coverage rule — renormalize over covered A-shares + configurable floor
- **Covered set:** the fund's current top-N holdings that are (a) A-share (6-digit numeric ticker, matched by `^\d{6}$` with **no** surrounding whitespace — §6.1), and (b) have a usable PE (positive; §3.6).
- **Coverage ratio (review P0 — units are load-bearing):**

```
coverage = Σ_{i ∈ covered} weight_pct_i / 100.0          # ratio of NAV, NOT raw percent sum
```

  `fund_holdings.weight_pct` is stored in **percent units 0..100** (`fund_holdings_ingestor.py:43`, validated `0.0 ≤ weight_pct ≤ 100.0`). The `/100.0` is mandatory: summing raw `weight_pct` against a `0.50` floor would pass virtually every fund incorrectly.
- **Floor:** if `coverage < coverage_floor` (default `0.50`, config §6.2) → emit `None` → NAV fallback (byte-identical to today). Otherwise renormalize the covered weights to sum to 1 and aggregate.
- The EY weighting renormalizes the covered weights, so the aggregation itself is **unit-invariant** (the `/100` cancels). Only the floor comparison depends on units — that is the one place to get right.

### 3.3 Maturity gate (review P2 — explicit, asymmetric, matching the index path)
- **PE:** require the surviving `PE_fund` series to clear the index path's bar — `≥ MIN_PE_POINTS (120)` non-null points **AND** `≥ MIN_PE_DAYS (180)` calendar-day span (`inputs_loader._pe_series_is_mature`) — plus the inherent `<30 → None` floor in `self_history_percentile`.
- **PB:** gated **only** by `self_history_percentile`'s `<30 → None` floor — **not** the 120/180 gate. This matches the index path exactly (`inputs_loader.py:186–191`: index PB also uses the bare percentile). Exposed as `pb_uses_pe_gate: false` so the looser gate is a deliberate, flippable call. Rationale: preserves index/active-fund symmetry, and PB is corroborate-only (ADR 0012 §5) so the looser gate carries no decision risk.

### 3.4 Per-date renormalization (anachronism bound)
On each historical date `t`, aggregate only over the current-basket holdings that have a PE point at `t`, renormalizing their weights by the weight present at `t`. Drop dates where present weight `< coverage_floor` (so a date covered by one mega-cap doesn't masquerade as the whole basket). This bounds the current-weights × past-PE anachronism naturally: the series only reaches as far back as the *current* basket actually has data, and every surviving point is internally consistent.

### 3.5 Source — hybrid (EastMoney primary, Tushare fallback)
**Endpoint correction (review P0):** legulegu's per-stock sibling `stock_a_indicator_lg` is **not present in the locked AkShare 1.18.60** (`hasattr(ak, "stock_a_indicator_lg") == False`) — verified in this checkout. The index path's `stock_index_pe_lg` is index-only; there is no legulegu per-stock endpoint to mirror. Primary is therefore EastMoney.
- **Primary:** AkShare `stock_value_em(symbol="<6-digit>")` (EastMoney) — **one call returns the full daily history** (~2000+ trading days, ample for the 120/180 gate) with columns `数据日期` (date), `PE(TTM)`, `市净率` (PB), plus `总市值`/PEG/etc. Free, no token, A-share only, CN-direct AkShare call (no `IRC_HTTPS_PROXY` — it is a CN domain). The fetcher extracts `(date, pe_ttm=PE(TTM), pb=市净率)`. *Exact columns must be re-confirmed by the gate-#4 live test in PR1.*
- **Fallback:** Tushare `daily_basic` per-stock, fired only on a `stock_value_em` miss/empty. Token-gated (reuses the existing `tushare_provider` token plumbing); absent token ⇒ EastMoney-only, misses just shrink coverage (floor catches it), **no hard failure**.
- **Comparability note:** EastMoney and Tushare PE definitions differ slightly, and both differ from the index path's legulegu. This matters **less** than it first appears: Phase D percentiles each fund against **its own** constructed series (`self_history_percentile`), and the divergence advisory compares the fund's PE-percentile vs **its own** NAV-percentile — both self-referential. No cross-source *absolute* PE comparison is made. Internal consistency of a fund's series is the requirement; mixed-source funds are still `_source`-flagged in the diff report (§8) so the risk is visible.
- **Single-source-per-stock rule:** to keep each stock's history internally consistent, a given `stock_code` is sourced wholly from EastMoney **or** wholly from Tushare (fallback is per-stock, not per-date); "mixed source" in the diff report means *different stocks in one fund came from different providers*, never one stock's series spliced across providers.

### 3.6 Negative / zero / None PE
Exclude that holding from the covered set (do **not** cap or floor it). Coverage shrinks honestly and the floor governs. (A negative-earnings name has no meaningful PE percentile; including it would corrupt the harmonic sum.) Same treatment for non-positive PB.

### 3.7 Fetch placement — dedicated command, own cadence
A new `irc fundamentals stock-valuation` command (§6.1) owns the heavy per-stock history refresh. It is **not** part of `irc run` (≈1000–1500 unique A-shares is far too heavy for a weekly run / fetch budget). `irc opportunity` reads the cached `stock_valuation_history` table only — the CLAUDE.md cached-evidence invariant is preserved.

### 3.8 Rollout — shadow-mode behind a config flag
- **PR1 (flag default OFF):** full pipeline computes and the diff report runs, but `inputs_loader` does **not** populate the slot for active funds while the flag is off. Prod is byte-identical to today.
- **Human reviews the diff** on real cached data (exit gate #5).
- **PR2 (flip flag ON):** `enabled: true`; active funds now use the PE anchor; the divergence advisory begins firing for them (intended — it surfaces NAV-vs-PE disagreement). ADR 0012 addendum + CHANGELOG + CONTEXT.md updated; real before/after output diff recorded.

The flag gates **slot population** (not just the classifier read), so shadow mode is truly inert: no divergence noise, the all-`None` dormancy lock holds, H3 / SAME-3 unaffected.

## 4. Architecture — mirror the index path, add a pure core

| Layer | Index path (existing) | Phase D (new) |
|---|---|---|
| Fetch | `fundamentals/akshare_index_valuation.py` | `fundamentals/akshare_stock_valuation.py` (EastMoney `stock_value_em`) + `fundamentals/tushare_stock_valuation.py` (fallback) |
| Table | `index_valuation_history` | `stock_valuation_history(stock_code, date, pe_ttm, pb, dividend_yield, <provenance>)` |
| Ingest | `data/index_valuation_ingestor.py` | `data/stock_valuation_ingestor.py` |
| Command | (part of `irc run` ingest) | `@fundamentals.command("stock-valuation")` → `commands/fundamentals_cmd.py:run_stock_valuation_refresh` |
| Aggregation | (none — index fetched whole) | `opportunity/lookthrough_valuation.py` (pure core) |
| Read → slot | `inputs_loader._index_valuation_metrics` | `inputs_loader` active-fund branch (flag-gated) |

Effects stay at the edges (the two fetchers + the command + DuckDB writes). `lookthrough_valuation.py` is **pure** and unit-testable without mocks. Every new file is < 200 lines, functions < 20 lines (extract helpers).

## 5. Data flow

```
irc fundamentals stock-valuation     (own cadence, heavy — NOT in irc run)
  SELECT DISTINCT holding_ticker FROM fund_holdings
    -> keep A-share shapes (^\d{6}$, no surrounding space); dedup across all funds
  for each code (skip if fresh within threshold_days unless --force):
      eastmoney stock_value_em(code) ; on miss -> tushare daily_basic(code)
  -> upsert stock_valuation_history   (per (stock_code, date), _source recorded)

irc run / irc opportunity            (cached-only; invariant preserved)
  inputs_loader, active-fund branch (asset_class == cn_equity_fund):
      latest-quarter holdings (fund_holdings) + stock_valuation_history
      -> lookthrough_valuation.fund_valuation_percentile(holdings, series_by_code, floor)
      -> IF flag.enabled: write valuation_percentile_fundamental[_pb]
         ELSE: leave None  (NAV fallback, byte-identical to today)
```

`fund_holdings` is already populated by `irc run` ingest (`ingest_cmd.py:643`, `ingest_fund_holdings`, best-effort, threshold 30 days). The new command consumes it; it does not re-fetch holdings.

**Refresh order (README update):** `irc run` (populates `fund_holdings`) → `irc fundamentals stock-valuation` (populates `stock_valuation_history`) → `irc opportunity` (reads both cached).

## 6. Component detail

### 6.1 Command — `irc fundamentals stock-valuation`
- Wiring: a new `@fundamentals.command("stock-valuation")` under the **existing** `fundamentals` group (`cli.py:228`), alongside `snapshot`.
- Signature: `run_stock_valuation_refresh(repo_root, *, force=False, threshold_days=30) -> int`.
- **Discovery source:** `SELECT DISTINCT holding_ticker FROM fund_holdings`, filtered to A-shares by **ticker shape** `^\d{6}$` (6-digit numeric, no surrounding whitespace; HK 5-digit / US-alpha / unknown shapes are skipped — they are uncoverable and the floor accounts for them). No reliance on a persisted exchange column (the `fund_holdings` table has none; `FundHolding.exchange` lives only on the in-memory dataclass). On the current DB this matches **393 distinct A-share tickers**.
- **Staleness:** per `stock_code`, skip when `stock_valuation_history` has a latest `date` fresh within `threshold_days`; `--force` refetches all. Mirrors `fund_holdings_ingestor.is_stale`. Idempotent on same-day reruns.
- **Failure isolation:** per-stock failures are captured, never raised (mirror `ingest_many`); the command returns 0 on a completed run (even with per-stock gaps), non-zero only on a structural error (e.g. cannot open DuckDB). Failed stocks logged at WARN with code + reason.
- Effects confined here + the ingestor; pure parsing in the fetchers.

### 6.2 Config — extend `config/valuation_buckets.yaml`
No `config/opportunity.yaml` exists (`config_loader._FILENAME_TO_SCHEMA` is a fixed registry). Extend the **already-registered** valuation config (`ValuationBucketsConfig`, `irc/schemas/valuation.py`) with:

```yaml
active_fund_lookthrough:
  enabled: false          # shadow mode default; PR2 flips to true
  coverage_floor: 0.50    # ratio of NAV; covered A-share weight must meet this
  pb_uses_pe_gate: false  # PB stays on the <30 floor, not 120/180 (§3.3)
```

Real schema + bundle field (validated by `irc config validate`), default-off, and semantically the right home (it is valuation config). An env override is explicitly **out of scope** (one source of truth).

**Config threading (review P1 — name the signatures; no hidden reads).** Today `_build_input` calls `populate_inputs(con, skeleton, holding_entry_date=..., provider=...)` with **no** config (`inputs_build.py:14,63`), and `run_opportunity` loads `bundle.valuation_buckets` but does **not** pass it into `_build_rows` (`opportunity_cmd.py:1490`). The flag/floor must be threaded **explicitly** down this chain — module-level/global config reads are forbidden (FP rules):
1. `run_opportunity` already has `bundle.valuation_buckets`; pass `bundle.valuation_buckets.active_fund_lookthrough` into `_build_rows(...)`.
2. `_build_rows` forwards it to `_build_input(...)`.
3. `_build_input` forwards it to `populate_inputs(con, skeleton, *, holding_entry_date, provider, lookthrough_cfg)` as a new keyword-only param (default a disabled config so existing call sites/tests stay valid).
A focused test asserts the value reaches `populate_inputs` (no global lookup).

### 6.3 Aggregation core — `opportunity/lookthrough_valuation.py`
Pure. Public surface:
- `fund_valuation_percentile(holdings, series_by_code, *, coverage_floor, pb_uses_pe_gate) -> FundValuationResult`.
- **`FundValuationResult` carries per-metric coverage (review P2).** PE and PB exclude holdings **independently** — a name can have a usable PE but a missing/non-positive PB, or vice-versa (§3.6) — so a single `coverage_ratio`/`covered_codes`/`source_mix` would misstate PB provenance even though PB is corroborate-only. The result is therefore split per metric:
  ```
  FundValuationResult(
    pe=MetricCoverage(percentile|None, coverage_ratio, covered_codes, source_mix),
    pb=MetricCoverage(percentile|None, coverage_ratio, covered_codes, source_mix),
  )
  ```
  `MetricCoverage` is a frozen dataclass; `source_mix` is the provider set over **that metric's** covered codes.
- Internal helpers: covered-set selection (§3.2/§3.6, run once per metric), per-date renormalized harmonic aggregation (§3.1/§3.4), maturity gate (§3.3, reusing `_pe_series_is_mature` semantics for PE; bare `<30` floor for PB), percentile via `self_history_percentile`.
- Returns per-metric coverage + source so the diff report (§8) and `inputs_loader` record/flag them accurately for PE and PB separately.

### 6.4 Fetchers + ingestor + table
- `akshare_stock_valuation.py` — mirror `akshare_index_valuation.py`: thin `stock_value_em` call + pure column extraction `数据日期→date`, `PE(TTM)→pe_ttm`, `市净率→pb` (EastMoney exposes no per-stock dividend yield, so `dividend_yield` is left `None` — the column stays nullable, consistent with the index table). Degrade-to-None on empty/raise.
- `tushare_stock_valuation.py` — `daily_basic` per-stock via the existing token plumbing; map `pe_ttm`/`pb` (and `dv_ratio→dividend_yield` when present); degrade-to-None when no token / empty.
- `data/stock_valuation_ingestor.py` — mirror `index_valuation_ingestor.py`: atomic `INSERT OR REPLACE` into `stock_valuation_history`, `_source` per row, BEGIN/COMMIT/ROLLBACK.
- `data/duckdb_helper.py` — add the `stock_valuation_history` DDL (PK `(stock_code, date)`, provenance cols), beside `index_valuation_history`.

### 6.5 `inputs_loader` wiring
Add an active-fund branch (`asset_class == "cn_equity_fund"`): load latest-quarter holdings + the per-code series from `stock_valuation_history`, call `fund_valuation_percentile`, and **iff** `active_fund_lookthrough.enabled` write the result into `valuation_percentile_fundamental[_pb]`. No live fetch (R3). Index-fund path untouched.

## 7. Error handling / degradation (degrade-to-None discipline)

- No holdings / stale holdings / `coverage < floor` / series fails maturity → `None` → NAV fallback (today's behaviour).
- Tushare token absent → EastMoney-only; misses shrink coverage, floor catches it. No hard failure.
- Non-positive PE/PB names excluded → coverage shrinks honestly (§3.6).
- Mixed-source series → `_source`-flagged, surfaced in the diff report (§3.5/§8).
- Flag off → every active-fund slot `None` → outputs byte-identical → H3 / SAME-3 / divergence advisory all inert (the all-`None` dormancy lock of ADR 0012).
- `valuation_percentile_fundamental[_pb]` are plain numeric inputs (no `ThesisEvidence`, no `[ref:...]`), so the dual-coverage gate, citation selector, SAME-3, H3 partition, 16-hex citation id (ADR 0001), and Policy B / `thesis_state` ownership (ADR 0003) are structurally unaffected — exactly as for the index path. `valuation_state` is a separate axis from `thesis_state` and never leaks into Policy B.

## 8. Diff report (exit-gate #5 artifact)

A report (command output / written artifact) listing, per active fund:
- would-flip band (NAV-derived `valuation_state` vs PE-derived), and **Δpercentile** (PE vs NAV);
- **per-metric covered-weight ratio** and **source mix** (EastMoney / Tushare / mixed) — reported **separately for PE and PB** (§6.3), since their covered sets can differ;
- the **current-basket caveat** (current weights × past PE);
- a **coverage-floor sensitivity table** at `0.40 / 0.50 / 0.60` showing grounded-fund count at each, so precision-vs-coverage is visible before the flag flips.

This is what the human reviews at gate #5. It runs independently of the flag (computes regardless of `enabled`).

## 9. Testing (TDD, test mirrors source)

- **Aggregation core (rich unit tests, no mocks):** worked harmonic example; coverage-floor pass/fail with the `/100` unit boundary; non-positive-PE exclusion; per-date renormalization (holdings with shorter history); PE maturity gate (120/180) vs PB `<30` floor; degrade-to-None on every gap path.
- **Unit-boundary test (P0 regression):** a fund whose raw `Σ weight_pct ≈ 55` but covered ratio `0.55` — assert the floor compares the ratio, not the percent sum.
- **Fetchers:** pure column extraction unit tests; **live-gated** test (`IRC_RUN_LIVE_AKSHARE=1` + marker) confirming `stock_value_em` returns real rows with the expected `数据日期`/`PE(TTM)`/`市净率` columns for a known A-share, and that the column→`(date, pe_ttm, pb)` extraction holds — no silently-guessed strings (gate #4). A parallel live-gated Tushare `daily_basic` test when a token is present.
- **Ingestor + table:** integration test (atomic upsert, `_source`, idempotent rerun).
- **`inputs_loader`:** flag-off ⇒ active-fund slot `None`; flag-on ⇒ populated; index path unchanged.
- **Flag-off byte-identical regression (P1):** a fixture run asserting active-fund opportunity outputs are byte-identical with the flag off (dormancy lock).
- **Invariants:** H3 universal gapped-row + SAME-3 citation-set equality unaffected with the flag both off and on.
- Lint: `uv run ruff check src tests` clean.

## 10. Rollout & exit gates (per the roadmap)

**PR1 — shadow compute (flag OFF):** fetchers + ingestor + table + command + aggregation core + flag-gated `inputs_loader` population + diff report. Must pass: tests green (gate #1), invariants intact (gate #2), grounded-fund count **measured** via a real `irc fundamentals stock-valuation` + `irc opportunity` (gate #3 — do **not** assert 383; report the real count and the floor-sensitivity table), live-symbol confirmation (gate #4), docs synced (gate #6). Produces the gate-#5 artifact. Prod byte-identical.

**Human review (gate #5, non-negotiable):** the user reviews the diff report on real cached data and signs off.

**PR2 — flip the flag (flag ON):** set `enabled: true`; record the real before/after `memo.md` / `opportunity` / `narrative` valuation-bucket diff; ADR 0012 addendum (active-fund look-through now populates the slot) + CHANGELOG `[Unreleased]` + CONTEXT.md "Valuation inputs".

Per the roadmap §6, Phase D is `brainstorming → spec (this doc) → plan → autodev the plan` — with the live-verify and human output review treated as hard gates. PR1's code+tests are autodev-able; gates #4 and #5 are not, and must stop the loop.

## 11. Reach (honesty note)

Phase D's ceiling is **funds that clear the coverage floor**, not all 383. Measured on the current `data/local.duckdb` (131 funds in the latest `fund_holdings`), applying the **A-share-only covered-set rule of §3.2** (not all top-N holdings):

| Floor | A-share-only (§3.2 rule) | All-holdings (wrong, for contrast) |
|---|---:|---:|
| ≥ 0.50 | **58** | 73 |
| ≥ 0.40 | **93** | 103 |

The A-share-only figures (58 / 93) are the honest upper bound; the earlier 73 / 103 counted every holding including HK/US and so over-stated reach. **And even 58 is an upper bound on *grounded* funds** — a fund also needs each covered stock's PE history to clear the maturity gate (§3.3), which only the real `stock_value_em` ingest can confirm. The roadmap and any "most funds" claim must be read against the **measured grounded count** gate #3 produces after a real ingest, not against 383. The diff report's sensitivity table sizes the precision-vs-coverage trade; the floor is config-tunable.

## 12. Out of scope

- HK/US per-stock valuation sources (those holdings stay uncovered → floor). A future enhancement.
- A lightweight "latest-PE-only" freshness probe piggybacking on `irc run` (the heavy history refresh stays in the dedicated command for now).
- Changing `derive_position_risk_level` (ADR 0012 Q4 deferral stands).
- Any change to the index/sector/QDII phases (A/B/C) — independent, additive.
