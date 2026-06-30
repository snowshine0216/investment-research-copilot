# Design — Monitor flow factor: market-wide rank-snapshot accumulation (Option B2, durable Phase 2)

**Date:** 2026-06-25
**Status:** Draft — brainstorming captured 2026-06-25; **gated on a Phase-0 verification spike** (see §5.A); pending spec review
**Surface:** `irc monitor`
**Supersedes/extends:** [ADR 0019](../../adr/0019-monitor-capital-flow-factor.md); companion to [Option A — cross-day reuse](2026-06-25-monitor-flow-coverage-cross-day-reuse-design.md), which is the proven Phase-1 bridge. B2 may make Option A's per-symbol cross-day machinery obsolete; that decision is taken *after* B2 runs (§10).

## 1. Problem

Same root cause as Option A (per-symbol EastMoney `stock_individual_fund_flow` throttles after ~3-5 calls/run → coverage never accumulates → 0/7 funds clear the 0.50 floor → permanent 5-factor fallback). Option A *mitigates* this on the per-symbol substrate but has a hard ceiling: under the ~5/run refresh budget, coverage trades off against staleness (full coverage only at ~5-td lag; the 5d leg degrades toward the 20d leg).

**B2 removes the constraint at its source.** A raw `ulist.np` multi-secid batch call returns **all monitored holdings' flow in one request** (see §1.1) — no per-symbol throttle, no coverage/staleness tension. (The akshare *rank* wrapper was the original idea but paginates ~53 calls — rejected; "rank-snapshot" in the title is retained for continuity, but the transport is the `ulist.np` batch.)

**Goal:** drive the flow factor from one market-wide call per run while **preserving the validated factor math and the bias semantics** (no engine reset), and deliver the same three operator asks as Option A (#1 freshness indicator, #2 today-vs-prior-trading-day comparison, #3 ≤3-trading-day acceptance window + comparison).

## 1.1 Empirical findings (probe, 2026-06-25) — these shape every decision below

> **Correction (2026-06-25, second probe round):** the original "rank endpoint = 1 call/run" premise was **wrong**. See the transport findings — `stock_individual_fund_flow_rank` paginates ~53 calls, but a raw `ulist.np` multi-secid call *does* fetch exactly our symbols in **one** request. B2 is re-based on `ulist.np`, not the akshare rank wrapper.

- `stock_individual_fund_flow_rank` **exists** but the **akshare wrapper internally paginates ~53 calls** (raw `clist/get` caps at 100 rows/page; total market ≈ 5290) → it is *more* throttle-exposed than the per-symbol path, not less. **Do not use it.**
- **Only `今日 / 3日 / 5日 / 10日` are valid rank `indicator` values** — `20日` raises `KeyError` (deterministic). The current blend is `0.4·5d + 0.6·20d`; the 20d leg carries the majority of the signal (ADR 0019 D7). Reading any pre-aggregated `5日/10日` column *cannot* reproduce the factor → would force a redefinition + engine bump. **B2 avoids this** (D-B1: accumulate the single-day value).
- ✅ **The real single-call path:** raw `push2.eastmoney.com/api/qt/ulist.np/get?secids=<our list>&fields=f12,f14,f184` returns **all requested secids' `f184` (今日主力净流入净占比) in ONE call** (probed: 5/5 secids, boards 000/300/600/688). This is B2's transport.
- **The block is IP rate-limiting by *volume*, not client type** (bare and browser-headed raw calls behave identically; akshare works fine at low volume). **A browser (Playwright / Chrome MCP) gives zero benefit and is rejected** — same IP, same limit; and a Chrome session can't run under `launchd` anyway. Batching to one call is the fix.
- **Timing caveat (load-bearing):** `ulist.np`'s `f184` is **今日/intraday**, authoritative only after CN close. The per-symbol `daykline` returns the last *completed* day + full history. The monitor runs ~09:19 (near open), so a `今日` batch is provisional at run time — this drives the seed/warm-up and the run-timing decisions below.

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|---|
| D-B0 | **Transport = raw `ulist.np` multi-secid batch, NOT the akshare rank wrapper.** One request with our ~30 `secids` returns each symbol's single-day `f184` (今日净占比). The rank wrapper (~53 paginated calls) and any `clist` page (capped 100/row) are rejected. A browser transport is rejected (IP-volume throttle, not client-type — see §1.1). |
| D-B1 | **Read the single-day `今日` value (`f184`) only; do NOT use any pre-aggregated `3日/5日/10日` field.** Rationale: (a) `20日` is unavailable anyway; (b) the multi-day fields are *cumulative-window ratios*, a different definition from the factor's *mean of daily 净占比*, which would invalidate the D7 band calibration. The single-day value preserves both. |
| D-B1b | **Run-timing / intraday guard.** `f184` is intraday until CN close; the ~09:19 run would capture a provisional value. Options (decide in §9): (i) **move the scheduled run to after close** so `今日` is final; (ii) keep the morning run and append the batch's value only when it represents a *completed* day (else rely on the daykline-seeded series' last completed row). The series must never append a provisional intraday value as a completed day. |
| D-B2 | **Accumulate the daily value into our own persisted daily series** (scoped to monitored symbols), then keep `_window_mean(5/20)` + `flow_band` + the 0.50 floor **byte-identical** (the validated math). Same series shape `flow_fetch` already produces. |
| D-B3 | **NO `_ENGINE_VERSION` bump — gated on the Phase-0 spike** proving rank `今日` ≈ per-symbol `stock_individual_fund_flow` last-row value for overlapping stocks (the factor input is then provably the same number from a more reliable path). If the spike shows they diverge materially → the input definition changed → escalate to an engine-bump + ADR addendum (do not silently ship a semantics change). |
| D-B4 | **~20-trading-day warm-up accepted.** Until the series has ≥20 rows per stock, `_window_mean` uses what it has (existing graceful `<n` behavior — same as a young stock today). Optional accelerator: **seed** the store from the existing per-symbol caches (`data/monitor/fund_flow/*.json` already hold full ~6-month series for symbols previously fetched). Seeding is additive, never required. |
| D-B5 | **Store is one market-wide daily-series file, scoped + pruned.** Persist only the union of monitored funds' look-through symbols (not all 5000), pruned to the last ~25 trading days (enough for the 20d window + slack). One append per run. This is cross-day persistence — but a *single market-wide series store*, structurally distinct from Option A's per-symbol throttle-recovery cache. |
| D-B6 | **Freshness / comparison / 3-td fallback reuse Option A's contract and rendering** (#1/#2/#3). B2 makes them *simpler*: one call → the whole factor is uniformly FRESH (today landed) or uniformly STALE-N (fell back to the stored series ≤3 td old) or DARK (>3 td / never → 5-factor banner). No per-stock freshness patchwork. |
| D-B7 | **Phase 0 verification spike is a hard gate** (§5.A). Until it passes — reachable at a fresh time, expected columns, bare-6-digit 代码, board coverage incl. 688/300/8xx, and `今日`≈per-symbol equivalence — B2 is not committed and Option A remains the active fix. |

## 3. Scope

- **In:** the 7 `active_cn_equity` funds' A-share look-through holdings (flow factor input only).
- **Out:** gold/qdii profiles (`profile_ineligible`, untouched); the bias math/weights (unchanged); valuation/heat/other factors.
- **Out of scope:** using the endpoint's `3日/5日/10日` aggregate columns; expanding flow coverage to the full basket (flow stays top-5 per ADR 0019 — the rank call merely makes the top-5 reliably covered); northbound/AUM-Δ/intraday.

## 4. Architecture

```
Phase 0 (spike, no prod code) ── proves reachability + 今日≈per-symbol(same day) + columns/coverage ──┐  (gate, §5.A)
                                                                                                      ▼
   ulist.np/get?secids=<our ~30>&fields=f12,f14,f184   ── ONE batch call/run ──▶ {symbol → 今日净占比}
                                                                                                      │
                       persisted daily-series store  data/monitor/fund_flow_series.json  ◀────────────┤ append (completed-day only, D-B1b/D-B5)
                       (monitored symbols, pruned ~25 td)  ◀── optional daykline seed (D-B4)           │
                                                                                                      ▼
            today landed? ── yes → series fresh ──┐   no → fall back to stored series if newest row ≤3 td (D-B6)
                                                  ▼
                       holding_metrics (PURE, math UNCHANGED — D-B2)  ── same 5d/20d/bands/0.50 floor
                                                  ├─▶ factors._flow → bias   (no engine bump — D-B3)
                                                  ├─▶ render: freshness badge (#1) + today-vs-prior Δ (#2/#3)   [shared with Option A §5.E]
                                                  └─▶ eval: coverage health + warm-up curve
```

Single new effect: the `ulist.np` batch fetch (CN endpoint, DIRECT per ADR 0017). The factor core stays pure and unchanged. History is seeded/back-filled from the per-symbol `daykline` (Option A's transport) so the 5d/20d windows don't cold-start.

## 5. Components

### 5.A Phase 0 — verification spike (HARD GATE; no production code) — Slice 0
A throwaway script (probe already partly done 2026-06-25; this hardens it), capturing:
1. `ulist.np/get?secids=<list>&fields=f12,f14,f184` returns a row per requested secid; confirm `f12` (bare 6-digit code), `f14` (name), `f184` (今日净占比, percent-points). ✅ partly confirmed (5/5 secids, boards 000/300/600/688).
2. **8xx/BJ coverage** — do Beijing-exchange holdings (if any in the monitor set) resolve under a `0.`/`1.` secid prefix? (the per-symbol path routes `8*/4*`→bj.)
3. **Same-day value equivalence (the D-B3 gate)** — after CN close, for ≥5 overlapping stocks, `ulist.f184(今日) ≈ daykline.last_completed_day.净占比`. Must compare the **same** day (the morning probe saw 000651 `f184=11.78` for *today/intraday* vs daykline's `13.90` for the *prior* completed day — different days, so equivalence is unproven until a same-day post-close comparison). Record tolerance → no engine bump iff equal to 4dp.
4. **Reachability** at the *actual* run time, across a few days (one batch call should clear the volume throttle, but confirm).
Output: a findings note + the run-timing decision (D-B1b). **Slices 1+ do not start until §5.A passes.**

### 5.B `flow_batch_fetch.py` (EDGE + pure parse) — Slice 1
- `fetch_flow_today_batch(symbols, *, fetch=None) -> dict[str, float|None]` — build `secids` from `symbols` (`6*`→`1.`, `0*/3*`→`0.`, reuse `flow_fetch._market_of` sign), ONE `ulist.np` call; pure `parse_ulist(j)` extracts `{f12 → f184}` (percent-points, NO `/100`, key-tolerant; missing/blank → `{}` → all None, never fabricated). Classified through the 3-outcome model (blank/throttled body → TRANSIENT → no write; well-formed → OK). CN endpoint DIRECT.
- Non-A-share lines (HK/US QDII) are never in `secids` → uncovered, as today.

### 5.C `flow_series_store.py` (EDGE) — persisted daily series — Slice 1
- `append_today(store_path, today, today_by_symbol, *, keep_td, trading_days) -> dict[str, FlowSeries]` — load the store (degrade to `{}` on corrupt/missing, never crash), append today's per-symbol row **iff** today landed (idempotent: re-run on the same `today` overwrites that day's row, not duplicate), prune rows older than `keep_td` trading days, atomic byte-stable write (`.tmp.{pid}→os.replace`, sorted keys, 4dp). Returns the per-symbol `FlowSeries` for the run.
- On a non-landing run, return the stored series unchanged (the freshness layer decides ≤3-td acceptance).
- Optional `seed_from_per_symbol(store, fund_flow_dir)` (D-B4) — one-time merge of existing `fund_flow/*.json` `ok` series into the store.

### 5.D `monitor_cmd.py` (EDGE) — Slice 2
- Replace the per-fund `fetch_flow_series` calls with: one `fetch_flow_today_batch(union_symbols)` → `append_today(...)` → pass each fund its `FlowSeries` slice into `_build_full_basket_metrics` (now pure-consume, like Option A §5.C). Thread `trading_days` (already loaded).

### 5.E `holding_metrics.py` (PURE) + Render + Eval — Slice 2/3/4
- **`holding_metrics` math UNCHANGED** (D-B2). `as_of`/`fresh_td`/Δ fields and the `flow_factor_as_of`/`flow_delta` helpers are **the same ones specified in Option A §5.D** — build once; whichever ships first owns them, the other reuses. Here `as_of` = the series' newest row date (uniform across the fund since one call fed everything).
- **Render** = Option A §5.E verbatim (freshness badge via `factor_freshness`, board Δ column, rollup Δ line, stale-but-covered note, `_flow_outage_banner` on >3-td/never).
- **Eval** — `eval/trace.py` `_SCHEMA_VERSION` bump (→ "5" if not already bumped by Option A; if A shipped first, reuse "5" and add the source marker); `flow_reconciliation` **unchanged**; coverage health gains the warm-up curve (rows-per-symbol distribution) and a `flow_source` marker (`rank_today` vs `per_symbol`). **No forward-eval/engine change** (D-B3, gated on §5.A).

### 5.F Versioning
- `_ENGINE_VERSION` **unchanged** ("3") **iff** §5.A value-equivalence passes (D-B3). Eval-trace schema bump only. If equivalence fails → revisit with an explicit engine bump + ADR 0019 addendum before shipping.

## 6. Invariants & constraints (must hold)

- **§5.A gate is non-negotiable:** no production B2 code until reachability + equivalence + column/coverage are proven. A failed gate keeps Option A as the fix.
- **Math/bias unchanged (D-B2/D-B3):** `flow_reconciliation` and the composite are byte-identical to the per-symbol path on the same inputs; warm-up `<n` behavior matches today's short-series handling.
- **No silent stale (D-B6):** a fallback (≤3-td) run is visibly marked; >3-td → DARK → existing banner.
- **No re-poisoning:** a non-landing run never writes a fabricated row; it serves the prior stored series only within the 3-td window.
- **ADR 0017 isolation:** the store lives under `data/monitor/`; CN endpoint DIRECT; pure core, effects at edges.
- **Framing (ADR 0015):** unchanged — lean, not order.
- **Size budget:** `flow_batch_fetch.py` and `flow_series_store.py` each < 200 lines; `monitor_cmd` shrinks.

## 7. Slice plan (TDD, red→green→refactor each)

0. **Spike (§5.A)** — gate; produce findings + the engine-bump decision. *No code merged.*
1. **Fetch + store** — `flow_batch_fetch.parse_ulist` (unit boundaries 1.0/3.0/0.01/0.03 percent-point canary), `fetch_flow_today_batch` (secid build, 3-outcome, blank→transient), `flow_series_store.append_today` (idempotent same-day, completed-day-only per D-B1b, prune, corrupt-store degrade, byte-stable), optional daykline seed.
2. **`monitor_cmd` swap + pure consume** — one call feeds the loop; regression: per-fund metrics identical to the per-symbol path on equivalent inputs.
3. **as_of/Δ + render** — reuse Option A's helpers/rendering; tests for uniform-freshness, ≤3-td fallback, Δ vs prior trading day, warm-up (<20 rows) graceful.
4. **Eval** — schema/source marker, warm-up curve health, reconciliation unchanged, determinism re-run.

Ship as one feature branch *after* §5.A.

### 7.1 Locked tests that MUST be updated
| Test | Asserts today | Update (slice) |
|---|---|---|
| `tests/monitor/eval/test_trace.py` schema test | `schema_version == "4"` (or "5" if A shipped) | bump consistently (slice 4) |
| `fetch_flow_series` callers in `tests/commands/` | per-fund per-symbol call | run-level rank-fed path (slice 2) |

Run `tests/monitor/`, `tests/monitor/eval/`, **`tests/commands/`** per-file (whole-dir hangs).

## 8. Exit gate / verification

**How B2's gate differs from Option A's:** B2 gets **full coverage immediately** (one batch call hits every symbol), so coverage-accumulation is *not* the risk. B2's risks are instead **(a)** the §5.A spike holding in production (reachability + equivalence), **(b)** window **depth** warm-up (the 20d leg fills over ~20 td unless seeded), and **(c)** never persisting an intraday-provisional value as a completed day (D-B1b).

### Tier 0 — Spike gate (precondition, §5.A — no code until green)
Reachable at the actual run time across several days; columns/board coverage confirmed; **same-day `ulist.f184 ≈ daykline.净占比` to 4dp** (the no-engine-bump decision); run-timing decided (D-B1b). A failed spike → B2 not committed, Option A remains the fix.

### Tier 1 — Pre-merge correctness (deterministic, fast)
- §7 slice tests green, plus a **fund-level acceptance test**:
  - `parse_ulist` unit boundaries (1.0/3.0/0.01/0.03 percent-point canary); secid build (`6*`→`1.`, `0*/3*`→`0.`); blank/throttled body → TRANSIENT (not written);
  - `flow_series_store.append_today` is **idempotent same-day**, appends a **completed day only** (never an intraday value, D-B1b), prunes to `keep_td`, **degrades on a corrupt store** (never crash), byte-stable;
  - given a seeded/accumulated store, **≥N funds clear the 0.50 floor**, freshness is **uniform** (one call), **Δ vs prior trading day** correct;
  - optional **daykline seed** merges existing `fund_flow/*.json` `ok` series correctly.
- **Regression invariants (must NOT move):** `flow_reconciliation` to 4dp (math unchanged, D-B2); `_ENGINE_VERSION` **unchanged** *iff* Tier-0 equivalence passed (D-B3); `_SCHEMA_VERSION` bump consistent with Option A (one bump, + `flow_source` marker).
- **One batch call, not 53 / not per-fund.**

### Tier 2 — Post-merge outcome (real runs, the true gate)
Off `eval_trace.json` + `irc eval monitor_signal` (coverage health gains the rows-per-symbol warm-up curve + `flow_source` marker):
- **Day 0 (seeded):** coverage ~full immediately → banner gone, **≥5 of 6 non-index funds** show a real `Σ` value; `eval monitor_signal` PASSES.
- **Day 0 (cold / unseeded):** coverage is still full (one call covers all symbols) but the **20d leg is shallow** — verify the factor is **live early** (5d leg within ~5 td), values **stabilize as the window deepens** (~20 td), and the warm-up is visibly tracked (not silently thin).
- **Reachability/resilience:** the single batch call succeeds at the run time across the window; on a miss, the **≤3-td fallback** serves the stored series (STALE badge, not collapse) and recovers next run.
- **Equivalence holds in production:** periodically spot-check that B2's values **track the per-symbol baseline** (an occasional `daykline` cross-check) — the guarantee that no silent semantics drift slipped in past Tier-0.

### Headline pass/fail
The original symptom does **not recur**; every shown value is honestly freshness-marked; B2's values **track the per-symbol baseline** (equivalence preserved); and — if the morning run-timing is kept (D-B1b) — **no intraday-provisional value is ever persisted as a completed day**.

## 9. Open questions / for review

- **Run timing (D-B1b) — the biggest open decision.** `ulist.np f184` is intraday until CN close, but the monitor runs ~09:19 (near open). Either **(i)** move the scheduled run to after close (~15:30+) so `今日` is final and the batch is the clean daily driver, or **(ii)** keep the morning run and treat the batch as a *supplement* to a daykline-seeded series (append only completed-day values). Option (i) is simpler and makes B2 self-sufficient; (ii) preserves the current schedule but keeps a per-symbol dependency. Decide before Slice 1.
- **§5.A equivalence tolerance** — what Δ between `ulist.f184(今日)` and the same day's daykline `净占比` counts as "same number" (no engine bump) vs "different definition" (bump)? Propose: ≤ rounding (4dp) on the matched completed day → same; persistent material gap → escalate. (The 2026-06-25 probe compared *different* days, so this is still open.)
- **Reachability cadence** — if the single fresh call is intermittently blocked, does B2 lean on Option A's per-symbol cross-day store as its ≤3-td fallback feeder (A + B2 compose), or accept occasional DARK days? Decide after the spike.
- **Warm-up** — accept the ~20-td ramp, or seed (D-B4)? Seeding only helps the handful of symbols already in `fund_flow/*.json`; the rest ramp regardless.
- **Schema ownership** — if Option A ships first (schema "5"), B2 adds only the `flow_source` marker; sequence the two specs so the schema bump happens once.

## 10. Out of scope (YAGNI) / staged follow-ups

- **Retiring Option A** — once B2 is proven reliable, the per-symbol cross-day machinery may be removed; decide post-deployment (don't pre-delete the proven bridge).
- Full-basket flow coverage (the rank call makes it *possible* — defer; it's a coverage-denominator semantics change); cross-fund ranked stock board; using `3日/5日/10日` aggregates; northbound/AUM-Δ/intraday flow.
