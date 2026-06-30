# Design — Monitor flow-factor coverage: cross-day reuse + consolidated fetch + freshness/Δ (Option A, Phase 1)

**Date:** 2026-06-25
**Status:** Draft — brainstorming captured 2026-06-25; pending spec review
**Surface:** `irc monitor`
**Supersedes/extends:** [ADR 0019](../../adr/0019-monitor-capital-flow-factor.md) + its 2026-06-22 transient-resilient addendum; the [2026-06-18 flow drill-down spec](2026-06-18-monitor-flow-stock-drilldown-design.md). Companion: [Option B2 — rank-snapshot accumulation](2026-06-25-monitor-flow-rank-snapshot-accumulation-design.md) (the durable Phase 2 that may make this obsolete).

## 1. Problem

The `irc monitor` capital-flow factor has been **N/A for all 7 `active_cn_equity` funds for ≥3 consecutive trading days** (2026-06-23 → 2026-06-25). The report shows the set-wide banner *"⚠ 资金流数据今日不可用——倾向回退至五因子"* every day; the 0.15 flow weight silently renormalizes onto the other factors, and the bottom-up flow grounding ADR 0019 introduced is absent.

**This is a coverage failure, not a fetch outage.** The data is fetchable and current — today's cache (`data/monitor/fund_flow/2026-06-25.json`) holds rows up to 2026-06-24 — but only **5 of ~30** needed top-5 symbols got cached, so **0/7 funds clear the `_COVERAGE_FLOOR = 0.50`** gate in `aggregate_flow`.

Evidence (per-day `fund_flow/<date>.json`):

| Day | symbols cached | `ok` (with rows) | newest row | result |
|---|---|---|---|---|
| 06-21 (pre-fix) | 30 | 5 | 2026-06-18 | 1 fund worked |
| 06-22 | 30 | 0 | — | all N/A (poisoned) |
| 06-24 | 3 | 3 | 2026-06-23 | all N/A |
| 06-25 | 5 | 5 | 2026-06-24 | all N/A (5×`flow_no_data`, 2×`flow_no_coverage`) |

**Root cause — three compounding causes:**

1. **EastMoney `stock_individual_fund_flow` throttles after ~3-5 calls/run** (the documented burst-then-block, ADR 0014/0019). This is the substrate constraint; empirically verified again 2026-06-25 (per-symbol → `ConnectionError`/`RemoteDisconnected`, blank-200 after the morning burst).
2. **The circuit-breaker resets per fund.** `fetch_flow_series` is called *once per fund* (`monitor_cmd._build_full_basket_metrics`, line 246), each with only that fund's 5 symbols. `cached_fetch.cache_first_fetch`'s `consecutive_transient` breaker is local to each call → it gives the first fund its ~5 and every later fund then hammers an already-blocked endpoint with no shared visibility.
3. **The cache is strictly per-day** (`{today}.json`, `cached_fetch._cache_path`) with **no cross-day fallback.** A symbol settled `ok` yesterday is not reused today. Each run starts cold, lands ~5, and never accumulates.

**Why the 06-22 fix didn't resolve it:** the transient-resilience work (ADR 0019 addendum, PRs #176/#177) correctly stopped *poisoning* (transients are no longer cached as confirmed misses) and promised "retried on the next run." But the next run is a **new calendar day with a fresh empty cache**, which re-hits the same throttle. The ADR's "~15-25 sequential calls/run" premise is the real defect: EastMoney's per-run ceiling is ~5.

**Goal:** restore a working flow factor on the **proven** per-symbol substrate by (a) making the breaker see the whole run and (b) accumulating coverage across days within a bounded staleness, and surface three operator asks: **(#1)** an indicator of how fresh the flow data is, **(#2)** a today-vs-prior-trading-day comparison, **(#3)** an explicit ≤3-trading-day acceptance window with that comparison shown. The factor's economic meaning, math, and weight are **unchanged** — we fix data availability and make staleness visible.

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|---|
| A1 | **Consolidate to ONE run-level flow fetch.** Dedup the union of all flow-eligible funds' top-5 symbols into a single `fetch_flow_series` call so the breaker has true cross-fund visibility (kills cause #2). The per-fund `_build_full_basket_metrics` consumes a run-level `dict[symbol → FlowSeries|None]` instead of fetching itself. |
| A2 | **Cross-day cache reuse.** On read, for a symbol not settled `ok` today, fall back to the most recent prior-day `fund_flow/<date>.json` that holds an `ok` entry for it (cause #3). |
| A3 | **Coverage staleness cap = 5 trading days.** Reuse a symbol's series **iff** its newest row date is within 5 *trading* days of `today` (via `trading_calendar.load_trading_days`). Older → treated as cache-absent → eligible for refetch, counts as uncovered until refreshed. 5 (not 3) maximizes coverage under the ~5/run refresh ceiling (3-td would leave funds flapping the 0.50 floor — see §9). |
| A4 | **Refetch-priority = stalest/missing first.** Each run orders the fetch queue so the symbols with the oldest (or no) cached series are fetched first within the throttle budget, so coverage rotates and self-heals rather than always retrying the same head-of-list symbols. |
| A5 | **Preserve the factor exactly → NO `_ENGINE_VERSION` bump.** `0.4·5d + 0.6·20d`, the D7 bands, and the 0.50 coverage floor are unchanged. Cross-day reuse changes *data freshness/availability*, not the factor's economic definition or the bias semantics, so the forward-eval population is NOT reset (contrast ADR 0019 D3, which bumped because the *factor set* changed). |
| A6 | **Freshness display threshold = 3 trading days**, distinct from the A3 coverage cap. A covered symbol/fund is shown **FRESH** when its newest row ≤3 td old, else **STALE** with `滞后 N 个交易日 (as of <date>)`. This honors requirement #3's "within 3 trading days" as a *display* contract without re-introducing the coverage flapping a hard 3-td *coverage* cap would cause. |
| A7 | **Only `ok` is reusable across days.** `miss` (confirmed dead) and transients are never carried forward as covered (extends the ADR 0019 2026-06-22 contract: no re-poisoning across days, just as within a day). |
| A8 | **Today-vs-prior-trading-day comparison is pure and series-derived.** Both the per-stock Δ (`今日净占比 vs 前一交易日`) and the per-fund flow-factor Δ are computed from the (reused) daily series, NOT by reading yesterday's output files — deterministic and dependency-free. |

## 2.1 Transport & reachability (probed 2026-06-25)

The recurring N/A is a *throttle*, so the transport is in scope. Empirical probes settle which mechanism is feasible:

| Probe | Result | Conclusion |
|---|---|---|
| `ak.stock_individual_fund_flow('000651')` retried with spacing | **works** (120 rows, newest 2026-06-24) | the block is **transient IP rate-limiting**, not an outage — the per-symbol endpoint is fine at low volume |
| raw `push2his.eastmoney.com/.../fflow/daykline/get`, **bare vs browser headers** | **byte-identical** HTTP 200 JSON | the block is **NOT** UA/client/header based |
| Playwright import | `ModuleNotFoundError` | not installed |
| akshare rank wrapper | internally paginates (`0/53`) | the rank *wrapper* is ~53 calls — more exposed, not less |
| raw `clist/get` with `pz=8000` | **capped at 100 rows/page** (total 5290) | can't fetch the market in one call |
| raw `push2.eastmoney.com/api/qt/ulist.np/get?secids=<list>&fields=f12,f14,f184` | **1 call → all requested secids' 今日净占比** (000/300/600/688 boards) | ✅ batching our ~30 secids into ONE call is feasible |

| # | Decision |
|---|---|
| A9 | **Root of the throttle = request *volume*, not client type.** Confirmed: bare and browser-headed raw calls behave identically; akshare works at low volume. The fix is to *reduce calls*, not to look more like a browser. |
| A10 | **Browser transport (Playwright / Chrome MCP) REJECTED — recorded so it is not re-proposed.** (a) No benefit: same IP → same rate-limit (A9). (b) Playwright is a heavyweight uninstalled dep. (c) "Reuse the existing Chrome session" is **infeasible under `launchd`** — the scheduled run is headless cron with no extension/logged-in browser. A browser would only ever be a manual-run crutch that *still* wouldn't beat the IP limit. |
| A11 | **Primary transport stays the per-symbol `daykline` endpoint** (timing-robust: returns the last *completed* trading day + full history). Cross-day accumulation (A2–A4) is precisely what keeps per-run volume under the limit (~5 fresh fetches/run). **Add an optional `ulist.np` multi-secid batch call** (`fetch_flow_today_batch(secids)`, ONE request for all monitored symbols) as a same-day coverage *booster* / fallback — caveat: its `f184` is **今日/intraday**, authoritative only after CN close, so at the ~09:19 run it supplements rather than replaces the daykline series. |
| A12 | **Chronic-throttle escape hatch = a network-path change (proxy), NOT a browser.** If batching+pacing still trips the limit, route the flow leg through a proxy (cf. `http_proxy.IRC_HTTPS_PROXY`); note the ADR 0017 "CN endpoints stay DIRECT" tension and decide explicitly then. |

## 3. Scope

- **In:** the 7 `active_cn_equity` funds (519069, 260112, 006533, 000083, 519770, 018132, 161903) — flow-eligible, A-share look-through. `018132` (index-tracking) may still legitimately degrade to `flow_no_coverage` (unchanged from ADR 0019). The fix is to the *fetch/cache/freshness* layer; the factor pure core is untouched except for threading `as_of`.
- **Out (N/A by profile):** gold (008986), qdii_global (270023), qdii_china_us_internet (009225) — `profile_ineligible`, untouched.
- **Out of scope:** the rank-endpoint migration (Option B2, its own spec); seeding/back-filling history; tuning the blend/floor; any change to the bias math or weights.

## 4. Architecture

```
flow-eligible funds ─┐  union(top-5 symbols), deduped, stalest-first
                     ▼
        flow_fetch.fetch_flow_series  (ONE run-level call — A1)
                     │
        cached_fetch (3-outcome + breaker, now run-scoped — A1)
                     │  read order:  today.json[ok]  →  recent prior-day .json[ok] within 5 td (A2/A3/A7)
                     ▼
   dict[symbol → (FlowSeries|None, as_of_date, freshness_state)]   ← carries staleness (A6)
                     │
        holding_metrics (PURE, math UNCHANGED — A5) + as_of/Δ threading (A8)
                     ├─▶ factors._flow → FactorScore → compute_signal → bias   (no engine bump)
                     ├─▶ render: freshness badge (#1) + today-vs-prior Δ (#2/#3)
                     └─▶ eval: coverage health gains reuse/staleness counts
```

The only new effect is reading prior-day cache files (still the monitor's own `data/monitor/fund_flow/`, ADR 0017 isolation preserved). The factor core stays pure; staleness is data threaded through, not a side effect.

## 5. Components

### 5.A `cached_fetch.py` (EDGE) — cross-day read + run-scoped breaker — Slice 1
- New read path: `_read_with_fallback(cache_dir, today, deserialize, *, trading_days, max_stale_td)` — start from `today.json`; for symbols absent there, scan prior `<date>.json` files newest-first, accepting the first `ok` entry whose **newest row date** is within `max_stale_td` trading days of `today`. Returns `dict[symbol → (payload|None, as_of_date|None)]`. Unreadable/corrupt prior files are skipped (degrade, never crash — existing `_read` guard contract).
- `cache_first_fetch` gains the staleness-window inputs and an optional `priority(symbols) -> ordered symbols` hook (A4: stalest/missing first). The breaker is unchanged in mechanism but now sees the whole run because there is a single call (A1).
- **No change to the write contract** — only `ok`/`dead` for *today* are persisted to `today.json`; reused entries are not rewritten (they already live in their own day's file). `miss`/transient never reused (A7).

### 5.B `flow_fetch.py` (EDGE) — run-level signature — Slice 1
- `fetch_flow_series(symbols, *, cache_dir, today, trading_days, fetch=None) -> dict[str, FlowDatum]` where `FlowDatum = (series: FlowSeries|None, as_of: str|None, fresh_td: int|None)`. `trading_days` is the `frozenset[date]` from `load_trading_days` (caller passes it; flow degrades gracefully to a calendar-day count if `None`, mirroring nav_quality's fallback).
- Helpers: `_newest_row_date(series)`, `_trading_days_between(as_of, today, trading_days)` (reused from / shared with `trading_calendar`).
- **Optional batch booster (A11):** `fetch_flow_today_batch(secids, *, fetch=None) -> dict[str, float|None]` — ONE `ulist.np` multi-secid call returning every monitored symbol's `f184` (今日净占比). Pure `parse_ulist(j)` extracts `{f12 → f184}` (percent-points, column-tolerant, blank→`{}`). Used to append a *same-day* row to any covered series whose daykline lacks today (post-close runs) — never the sole source given the intraday caveat. Same 3-outcome classification + DIRECT CN endpoint.

### 5.C `monitor_cmd.py` (EDGE) — hoist the fetch out of the per-fund loop — Slice 1
- Build `flow_by_symbol = fetch_flow_series(union_top5, …)` **once** before the per-fund loop; pass the relevant slice into `_build_full_basket_metrics` (which no longer calls `fetch_flow_series`). This is the structural fix for cause #2 and is independently valuable.
- Thread the run's `trading_days` (already loaded for nav_quality) into the call.

### 5.D `holding_metrics.py` (PURE) — `as_of` + Δ threading, math unchanged — Slice 2
- `HoldingMetric` gains `flow_as_of: str|None` and `flow_fresh_td: int|None` (trailing-defaulted, back-compat). The 5d/20d means, blend, `flow_band`, `aggregate_flow`, and the 0.50 floor are **byte-identical** (A5).
- `FlowAggregate` gains `as_of: str|None` (the **oldest** covered-stock `as_of` → the fund's flow is only as fresh as its stalest covered top-5 member) and `fresh_td: int|None`.
- New pure helpers (A8):
  - `flow_factor_as_of(series_by_code, top_holdings, as_of_trading_day) -> FlowAggregate` — recompute the aggregate truncating each series to rows ≤ `as_of_trading_day`. Used to get "yesterday's" factor value.
  - `flow_delta(today_agg, prior_agg) -> float|None` and per-stock `flow_pct_delta(series, prior_trading_day)` — the Δ for #2.

### 5.E Render — freshness badge (#1) + today-vs-prior Δ (#2/#3) — Slice 3
- **Reuse the existing `factor_freshness: dict[str, str]`** (`render_types.FundView`, `render_factors.factor_table_html`). Today every factor maps to `"fresh"`; extend the `"flow"` value to one of `fresh` / `滞后 N 交易日 (as of <date>)` driven by `FlowAggregate.fresh_td`/`as_of`. No new plumbing for #1 — extend the value space.
- `render_drilldown.holdings_board_html`: add a `Δ vs 前一交易日` column (per-stock `今日净占比` and its Δ); STALE rows show the `as of <date>` and the `滞后` marker. `flow_rollup_html`: append the per-fund `资金流因子 Δ vs 前一交易日 = …` line.
- `render_html._flow_outage_banner` (currently fires only on *set-wide collapse*): keep that contract; add a **softer** run-level note when the set is covered-but-all-STALE (e.g. *"资金流数据为滞后口径（最新 as of <date>）"*) so a uniformly-stale day is not silently presented as fresh. Pure, computed from view states (no side effect; consistent with the `KNOWN_NA_REASONS` non-caveat rule — staleness is informational, never gating).

### 5.F Eval — coverage health gains reuse/staleness, reconciliation unchanged — Slice 4
- `eval/trace.py`: bump `_SCHEMA_VERSION` `"4" → "5"`; record per-fund `flow_as_of`, `flow_fresh_td`, and per-stock `as_of`/Δ in the `holding_metrics` block.
- `eval/structural.py::flow_reconciliation`: **unchanged** math (Σwᵢsᵢ/Σwᵢ == factor value to 4dp) — reused/stale data still must reconcile. Add no new FAIL classes.
- Coverage/health (free, in `eval monitor_signal`): report `flow_covered`, `flow_reused_from_prior`, and the staleness histogram (how many covered symbols are 0/1/…/5 td old) so an operator sees the warm-up curve and whether the rotation is keeping up.
- **No forward-eval / engine change** (A5).

### 5.G Versioning
- `_ENGINE_VERSION` **unchanged** ("3"). Only the eval-trace `_SCHEMA_VERSION` bumps (4→5) for the new fields.

## 6. Invariants & constraints (must hold)

- **No re-poisoning across days (A7):** only `ok` entries reused; `miss`/transient never served as covered. A throttle day still degrades to N/A, never a frozen wrong value.
- **No silent stale (A6/§5.E):** any reused/stale flow is visibly marked (`as of <date>` + `滞后 N`); the factor never presents stale data as today's.
- **Math/bias unchanged (A5):** `flow_reconciliation` and the renorm composite are byte-identical on fresh data; a cached re-run on the same day reuses deterministically (determinism eval).
- **ADR 0017 isolation:** all reads stay within `data/monitor/fund_flow/`; no opportunity files; pure core, effects at edges.
- **Framing (ADR 0015):** unchanged — lean, not order.
- **Size budget:** cross-day logic lives in `cached_fetch.py`/`flow_fetch.py`; comparison helpers in `holding_metrics.py`; `monitor_cmd` shrinks (fetch hoisted out of the loop), not grows.

## 7. Slice plan (TDD, red→green→refactor each)

1. **Fetch/cache** — run-scoped breaker (A1) + cross-day read with 5-td staleness window + stalest-first priority (A2/A3/A4/A7). Tests: prior-day `ok` reused within window; `>5 td` not reused; `miss`/transient never reused; corrupt prior file skipped; priority order; single shared breaker across the whole symbol set; idempotent same-day re-run.
2. **`monitor_cmd` hoist** — one run-level fetch feeding the per-fund loop. Tests: per-fund metrics identical to today's behavior on all-fresh data (regression); only one `fetch_flow_series` invocation.
3. **as_of/Δ + render** — `HoldingMetric`/`FlowAggregate` as_of fields, `flow_factor_as_of`/`flow_delta`, freshness badge value, board Δ column, rollup Δ line, stale-but-covered note. Tests: as_of = oldest covered member; Δ vs prior trading day (incl. first-run `—`, weekend/holiday prior); badge states at 3-td boundary; stale note fires only when covered-and-all-stale.
4. **Eval** — schema 4→5 + reuse/staleness health; reconciliation unchanged on reused data; determinism re-run. Tests: schema shape, staleness histogram counts, reconciliation equality on a reused series, deterministic re-run.

Ship as one feature branch (matches the multi-slice single-PR pattern).

### 7.1 Locked tests that MUST be updated
| Test | Asserts today | Update (slice) |
|---|---|---|
| `tests/monitor/eval/test_trace.py` schema test | `schema_version == "4"` | → `"5"` (slice 4) |
| `tests/monitor/test_acceptance_eval.py` schema assert | `"4"` | → `"5"` (slice 4) |
| any `fetch_flow_series` signature test | per-fund call shape | run-level signature + `trading_days` arg (slice 1) |

Regression (no change expected, run anyway per the "test scope on signature changes" rule): `tests/monitor/`, `tests/monitor/eval/`, **`tests/commands/`** (the `_process_fund`/`_build_full_basket_metrics` callers — run per-file, the whole-dir run is known to hang).

## 8. Exit gate / verification

**Key property: Option A cannot be verified in a single run** — its mechanism is *accumulate coverage across days and self-heal*, so correctness and outcome are separate gates. Tier 1 proves it is **correct** (and lets you merge); Tier 2 proves it **works** (the true exit gate, ~a week of runs because that is the warm-up curve).

### Tier 1 — Pre-merge correctness (deterministic, fast)
- All §7 slice tests green, plus a **fund-level acceptance test** (`tests/monitor/test_flow_coverage_acceptance.py`) that seeds a synthetic multi-day cache and asserts the *assembled* result:
  - prior-day `ok` series at 1/3/5 td old → **reused**; at 6 td → **not reused** (uncovered);
  - given a realistic mix, **≥N funds clear the 0.50 floor** (the broken symptom);
  - freshness badge **FRESH ≤3 td, STALE 4–5 td** (exact boundary, A6);
  - per-stock/per-fund **Δ vs the correct prior *trading* day** (weekend/holiday handled, A8);
  - `miss`/transient **never reused** (no re-poisoning, A7);
  - **deterministic re-run** (same-day re-run / `--resume` / drilldown re-render reuse identically, no refetch).
- **Regression invariants (must NOT move):** `eval/structural.flow_reconciliation` equals the factor value to 4dp (math unchanged, A5); `_ENGINE_VERSION` **unchanged** (no forward-eval reset); only `_SCHEMA_VERSION` 4→5.
- **One fetch, not seven:** assert exactly one run-level `fetch_flow_series` call (cause #2 gone).

### Tier 2 — Post-merge outcome (real runs, the true gate)
Instrument off `eval_trace.json` + `irc eval monitor_signal` (coverage health gains `flow_covered` / `flow_reused_from_prior` / staleness histogram, §5.F):
- **Day 0 (smoke):** `irc monitor` completes, no crash; `eval monitor_signal` PASSES (reconciliation + determinism); banner state matches that day's actual coverage.
- **Warm-up (~5–7 trading days):** `flow_covered` **climbs** day over day and stabilizes; by ~day 5–6 the set-wide *"资金流数据今日不可用——回退至五因子"* banner **stops firing on normal days**, and **≥5 of the 6 non-index active funds** show a real `Σ(wᵢ·sᵢ)/Σ(wᵢ)` (recall `018132` is index-tracking → may legitimately stay N/A, §3).
- **Staleness bounded:** the histogram does not pile up at the 5-td tail — the stalest-first rotation (A4) keeps pace with the throttle.
- **Resilience:** on a throttle day, the factor degrades to **STALE badges, not a set-wide collapse**, and recovers next good run.

### Headline pass/fail
The original symptom does **not recur** — no ≥3-consecutive-day stretch of banner + all-funds-N/A over the observation window — **and** every shown flow value is honestly freshness-marked (never stale-presented-as-today).

## 9. Open questions / for review

- **5-td coverage cap vs 3-td display (A3/A6) — DECIDED.** Rationale: with the ~5/run refresh ceiling and ~30 symbols, a hard 3-td *coverage* cap can only hold ~50-60% covered at steady state → funds flap the 0.50 floor day to day; a 5-td cap maximizes coverage, and the 3-td *display* threshold keeps the staleness honest. Revisit if the rotation empirically keeps everything ≤3 td.
- **Fund-level freshness = oldest covered top-5 member (conservative) — confirm** vs weight-weighted average staleness.
- **Steady-state ceiling is real:** even fully warmed, A serves flow up to 5 td lagged and the 5d leg degrades toward the 20d leg. This is *why* Option B2 exists — A is the proven bridge, not the end state.

## 10. Out of scope (YAGNI) / staged follow-ups

- **Option B2 (rank-snapshot accumulation)** — the durable same-day-full-coverage upgrade; its own spec. Decide whether A is still needed after B2 ships.
- Seeding the cross-day store from historical fetches; tuning blend/floor to config; cross-fund ranked stock board; northbound/AUM-Δ/intraday flow.
