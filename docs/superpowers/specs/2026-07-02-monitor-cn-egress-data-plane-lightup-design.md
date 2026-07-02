# Design — Monitor data-plane light-up: `IRC_CN_PROXY` egress, batch-first flow (B2 un-shelved), industry-leg raw fetchers, valuation backfill

**Date:** 2026-07-02
**Status:** Spec — grilled 2026-07-02 (user decisions §9 locked); ready for implementation in a fresh session
**Surface:** `irc monitor` (+ one `irc fundamentals` op step, one new launchd job)
**Un-shelves:** [Option B2 — rank-snapshot accumulation](2026-06-25-monitor-flow-rank-snapshot-accumulation-design.md) (its D-B0..B7 stand; §3 records only the deltas). [Option A — cross-day reuse](2026-06-25-monitor-flow-coverage-cross-day-reuse-design.md) **stays shelved** (superseded by the D6 capture job).
**Amends:** [ADR 0019](../../adr/0019-monitor-capital-flow-factor.md) (best-effort/DARK addendum — its "conditional future fix" trigger has fired), [ADR 0020](../../adr/0020-monitor-dual-track-valuation.md) (D3 industry-leg transport; root-cause correction).

## 1. Problem

Three degraded legs in the daily brief, all visible in the 2026-07-01 report:

1. **flow** — N/A for 5/7 `active_cn_equity` funds (`flow_cover` 0.0 everywhere except 006533 = 0.84; 519770 = 0.47 < the 0.50 floor).
2. **industry valuation leg** — `industry_cover` **0.0 for every fund**: the dual-track valuation (ADR 0020) silently runs self-history-only, and the four industry columns (行业/行业PE/r/行业分) render as dead dashes in every holdings table.
3. **per-stock PE/PB series** — `nav_cover` only 0.34–0.54; several holdings show `no_series` (e.g. 600690 海尔智家, 600233 圆通速递).

The 2026-06-26 resolution (ADR 0019 addendum) accepted flow as best-effort/DARK because the binding constraint was believed to be **host geography with no CN egress available**. The 2026-07-02 measurements below overturn the availability premise (a CN egress now exists) and **correct the industry-leg diagnosis entirely** (it was never geo).

## 2. Empirical findings (2026-07-02, live probes from the monitor host)

| # | Probe | Result |
|---|---|---|
| F1 | `IRC_CN_PROXY` (static CN residential IP, Henan Unicom `42.51.40.10:16816`, IP-whitelist auth, already in `.env`) → EastMoney | **Works on both planes via python `requests`**: `push2` `ulist.np` batch 3/3 OK with valid `f184`; `push2` `stock/get` `f127` OK (`白色家电` for 600690); `datacenter` `stock_value_em` full 2,059-row series OK. |
| F2 | Direct (no proxy) from the host | Currently egresses a **CN Telecom IP** (`220.191.185.154`) and `ulist.np` succeeds direct — the geo situation is **dynamic** (2026-06-25 measured US datacenter `199.255.81.250`). Motivates the always-proxy posture (D2). |
| F3 | `curl` through either proxy vs EastMoney | **False-fails** ("Empty reply from server") while python `requests` succeeds on the same URL. **Never diagnose EastMoney reachability with curl.** |
| F4 | `ak.stock_board_industry_name_em` (akshare 1.18.60) | Succeeds but **no longer returns a `市盈率` column** (12 columns, none PE) → `parse_industry_pe` → `{}` → **cached `{}` for the day** (confirmed: `data/monitor/industry_pe/2026-06-29.json` and `-30.json` are both `{}`). |
| F5 | `ak.stock_individual_info_em` | **Raises `ValueError: Length mismatch`** on every call, direct AND proxied (EastMoney added `dlmkts`/`dsc` top-level keys the fixed-key parser can't handle) → every symbol TRANSIENT → no cache file written since 06-23. On 06-21/22 (pre-drift) it produced **all-"miss"** caches. Net: **the industry leg has NEVER produced data in production** — every engine-"3" ledger row to date is self-only valuation. |
| F6 | Raw replacements | `clist/get` `fs=m:90+t:2&fields=f12,f14,f9` → board PE (100 rows/page, ~496 boards total, sane values e.g. 黄金 18.46; 16/100 non-positive → dropped by existing `_coerce_positive`). `stock/get` `fields=f57,f58,f127` → per-stock 东财行业. Both verified through the proxy. |
| F7 | `ak.stock_value_em` for the report's `no_series` stocks | Full 2,059-row PE/PB series for 600690 and 600233 → the DuckDB `stock_valuation_history` gaps are **refetchable transient failures**, not missing data. |

## 3. Decisions locked

| # | Decision |
|---|---|
| D1 | **Proxy contract.** `IRC_CN_PROXY` in `.env` holds the CN egress (URL or bare `host:port`, normalized to `http://host:port`); optional `IRC_CN_PROXY_MODE` ∈ `on\|off` toggle, **default `on`** when the URL is present. New `resolve_cn_proxy()` + the `proxy_env()` context manager (extracted from `akshare_client._proxy_env`, single source of truth) live in `src/irc/http_proxy.py`. Direction is the **opposite** of `IRC_HTTPS_PROXY` (which routes non-CN destinations); the two never mix. Secrets/endpoints stay in `.env` only. |
| D2 | **Always-proxy posture at the EastMoney data-plane edges** when enabled: flow batch (`ulist.np`), board PE (`clist/get`), stock→industry (`stock/get`), per-stock series (`stock_value_em`). **No direct fallback** — deterministic egress regardless of the host's dynamic geo (F2), protects the host IP from the self-extending block (ADR 0019), and a proxy outage degrades through the existing transient/DARK machinery. The **fund plane stays DIRECT** (`fund_purchase_em` heat, NAV history — never throttled; avoid a needless single point of failure). |
| D3 | **Industry-leg re-transport, contract-preserving.** New `src/irc/monitor/em_raw.py` provides raw fetchers slotted into the **existing injectable `fetch` params** of `industry_valuation.fetch_industry_pe` / `fetch_stock_industry_map`: `fetch_board_pe_frame()` (paginated `clist/get` `f9`, pz=100, ≤10 pages, existing 0.3s pacing) returns a frame with the `板块名称`/`市盈率` columns the existing pure parser expects; `fetch_stock_info_frame(symbol=…)` (one `stock/get` call) returns the `(item,value)` frame shape the existing `parse_stock_industry`/`_is_blank_info_frame`/3-outcome classification consume unchanged. **Do not reintroduce the akshare wrappers** — em_raw owns its raw-JSON parsing so upstream response-shape drift (F4/F5) can't recur silently. One contract fix: `fetch_industry_pe` **no longer caches an empty parse** (`{}` → returned but NOT written, treated like a raised fetch) — kills the "{} frozen for the day" wart (F4). |
| D4 | **No `_ENGINE_VERSION` bump for the industry light-up.** The dual-track methodology (0.60·self + 0.40·industry + clamp) IS engine "3"; the leg never produced data (F5), so no value stream is being redefined — this is **data availability returning**, the same class as flow DARK→FRESH which ADR 0019 explicitly ships without a bump. `f9` (市盈率-动) as the board denominator is sanity-gated in Slice 0 (hand-check ~3 boards vs the EastMoney web UI + range sanity); ADR 0020 D3's denominator-robustness risk note stands unchanged. |
| D5 | **B2 batch-first flow un-shelved as specified** — D-B0 (ulist.np transport), D-B1 (single-day f184 only), D-B2 (math/store byte-identical), D-B3 (no engine bump gated on 4dp same-day equivalence), D-B5 (pruned market-wide store), D-B6 (FRESH/STALE-N ≤3td/DARK), D-B7 (spike gate) all stand. Deltas: transport goes through D1/D2; D-B1b run timing resolved by D6; D-B4 warm-up resolved by D7; the Tier-0 spike re-runs **through the proxy**. |
| D6 | **Hybrid schedule (resolves D-B1b).** The **12:15 brief is unchanged** — it exists to support same-day orders (a CN fund order before 15:00 fills at today's close NAV). A **new 15:45 Asia/Shanghai launchd job — `irc monitor flow-capture`** — makes ONE `ulist.np` batch call for the monitor-set union symbols and appends the now-final `f184` to the series store (idempotent same-day, completed-day-only, prune to ~25 td): no LLM, no report, no ledger row. Wrapper reuses `ops/launchd/lib-run.sh` (`acquire_lock` + `run_with_watchdog`); sentinel = the store file's appended date. The 12:15 brief MAY display today's morning-session `f184` as a **盘中提示/provisional annotation only** — never persisted, never in factor math (the factor consumes the store, whose newest row is yesterday's completed day at 12:15). |
| D7 | **Seed-then-organic warm-up (resolves D-B4).** One-time seed at rollout: merge existing `data/monitor/fund_flow/*.json` `ok` series into the store, then a **one-shot paced per-symbol `daykline` sweep via the proxy** for symbols still missing depth (breaker on, ~30 calls, run once after close). Thereafter the 15:45 capture is the only writer and depth accumulates organically. |
| D8 | **Valuation backfill op (F7).** Post-merge: `uv run irc fundamentals stock-valuation --force` (its `fetch_stock_valuation_history` edge now routed per D2) refills `stock_valuation_history`; verify `nav_cover` recovers in the next brief. Quarterly cadence unchanged. |
| D9 | **Eval:** one eval-trace `_SCHEMA_VERSION` bump + `flow_source` marker (`batch_today` \| `per_symbol_seed`) per B2 §5.E; `flow_reconciliation` and the composite stay byte-identical (D-B2). Coverage health gains the warm-up (rows-per-symbol) curve. |
| D10 | **Per-symbol flow path retired from the run path at implementation** (monitor_cmd consumes the store; `fetch_flow_series` no longer called per fund). The per-symbol `daykline` fetcher stays as library code for the D7 seed and Tier-2 equivalence spot-checks. Option A's cross-day machinery is never built. |

## 4. Scope

- **In:** everything in §3; ADR 0019/0020 addenda; CONTEXT.md *Flow freshness state* rewrite **at implementation** (STALE-N becomes buildable; describe as-built states only).
- **Out:** report-v3 readability overhaul (own spec); the "not-heated" fund scout (own spec); full-basket flow coverage; TTL cross-day industry-map caching (follow-up note — per-day is ~20 proxied calls/run, acceptable); routing the fund plane or legulegu through the proxy; any weight/band change.

## 5. Slice plan (TDD, red→green→refactor; mirror test files per slice)

0. **Spike re-run (gate for slices 3–5, NOT for 1–2):** extend `scripts/phase0_flow_batch_spike.py` with `IRC_CN_PROXY` support. GATE 1 reachability through the proxy after close; GATE 2 next-day same-day `f184 ≈ daykline.净占比` 4dp equivalence (decides D-B3's no-bump claim); plus the D4 board-PE `f9` sanity check. Findings appended to this spec.
1. **`http_proxy`:** `resolve_cn_proxy()` (bare host:port normalization, MODE toggle, unset/off → None) + `proxy_env()` extraction; `akshare_client` dedupes to the shared impl. `tests/test_http_proxy.py`.
2. **Industry light-up:** `em_raw.py` pure parsers (`parse_clist_boards`, `parse_stock_info`: fixture payloads incl. `dlmkts`/`dsc` keys, `data:null`, missing `f127` → frame-without-行业-row so the DEAD path still works) + edge fetchers (pagination stop, injected `http_get` recording `proxies=`); `industry_valuation` default-fetch swap + empty-parse-not-cached; `akshare_stock_valuation._fetch_frame` wrapped in `proxy_env` when enabled. Existing `tests/monitor/test_industry_valuation.py` must stay green untouched (contract preservation proof).
3. **Flow batch + store:** `flow_batch_fetch.py` + `flow_series_store.py` per B2 §5.B/§5.C (secid build, 3-outcome blank→TRANSIENT, idempotent completed-day append, prune, corrupt-store degrade, byte-stable writes) + D7 seed helpers.
4. **Capture job + swap:** `irc monitor flow-capture` subcommand; `monitor_cmd` swap to store-consumption (B2 §5.D); 12:15 provisional annotation render; `ops/launchd/` capture wrapper + plist + `install.sh` templating; per-day `fund_flow` fetch removed from the run path (D10).
5. **Eval + docs:** schema bump + `flow_source` + warm-up curve (B2 §5.E); CONTEXT.md *Flow freshness state* as-built rewrite; README ops table (new job + backfill op).

**Post-merge op steps (in order):** install the 15:45 job → run the D7 seed once after close → `irc fundamentals stock-valuation --force` → next 12:15 brief: verify Tier-2.

## 6. Locked tests that MUST be updated

| Test | Asserts today | Update (slice) |
|---|---|---|
| `tests/monitor/eval/test_trace.py` schema assert | current `_SCHEMA_VERSION` | single bump (slice 5) |
| `fetch_flow_series` callers in `tests/commands/` | per-fund per-symbol path | store-fed path (slice 4) — **run per-file; the whole dir hangs** |
| `tests/monitor/test_industry_valuation.py` | injectable-fetch contract | unchanged (must stay green) + new default-fetch identity test (slice 2) |
| `tests/ops/test_launchd_monitor.py` | 12:15 single job | + capture job plist/wrapper (slice 4) |

## 7. Exit gates

- **Tier 0 (spike, flow only):** proxy reachability at 15:45 across ≥3 days; 4dp equivalence on ≥5 overlapping symbols (fail → engine-bump escalation per D-B3, do not silently ship); `f9` sanity.
- **Tier 1 (pre-merge):** slice tests green; `flow_reconciliation` 4dp byte-identical on fixture inputs; industry aggregate equals hand-computed dual-track on a fixture fund; `_ENGINE_VERSION` untouched; one schema bump.
- **Tier 2 (post-merge, real runs):** flow Σ renders for **≥5/7** active funds on day 1 (seeded); `industry_cover > 0` for every fund above the 0.40 NAV floor; `nav_cover ≥ ~0.8` after D8; the 06-25 symptom (set-wide 回退 banner) does not recur for a week; breaker trips ≈ 0 steady-state; no provisional value ever appears in the store (spot-check dates).

## 8. Traps for the implementer (measured, do not relearn)

- **Never probe EastMoney with curl through a proxy** — false "Empty reply" (F3); use python `requests`.
- **Never retry an EastMoney endpoint while it is blocking** — the block self-extends >40 min (ADR 0019). The breaker (stop after 5) is protective; keep it on every path including the D7 seed sweep.
- `pytest tests/commands/` **whole-dir hangs** — run per-file.
- A provisional (pre-close) `f184` must **never** be persisted (D6) — the append API takes only completed days; the 12:15 path has no write access to the store.
- akshare wrapper drift caused F4/F5 — `em_raw` parses raw JSON itself; treat any future akshare re-introduction as a regression.
- A reference implementation of Slice 1 existed briefly on branch `worktree-monitor-cn-proxy-industry-fix` (reverted; spec-only). Re-derive via TDD — do not hunt for it.

## 9. Resolved decisions (user, 2026-07-02)

1. **Run timing:** hybrid 12:15 brief + 15:45 capture (D6) — chosen for same-day order support ("whether to invest more money today"; pre-15:00 orders fill at today's NAV).
2. **Warm-up:** one-time seed sweep, then organic accumulation (D7).
3. **Proxy:** toggleable, **default ON via proxy** when `IRC_CN_PROXY` is set (D1/D2).
4. **Spec landing:** spec-only PR to main (this document + ADR addenda), implementation in a fresh session.

## 10. Out of scope / follow-ups

- Report v3 readability (今日速览 header, citation dedup + dates + source tiers, Chinese narrative + relevance guard, dark-data rendering, stale-eval badges) — next spec.
- "Promising, not-yet-heated" fund scout (`irc scout` staged funnel over the ~380-fund universe) — next spec; depends on this one only for the flow/valuation data quality.
- TTL cross-day caching for the (essentially static) stock→industry map — note only; revisit if ~20 proxied calls/run ever matters.
- Retiring the per-symbol `daykline` library code — after B2 proves out (D10 keeps it for seed/spot-checks).

## Tier-0 findings

**GATE-1 (reachability) — PASS at plan authoring (2026-07-02 12:05 CST).** Live probes through `IRC_CN_PROXY` from the planning session returned three clean results, none retried:

- `ulist.np` batch: one call returned valid numeric `f184` for all probed symbols.
- `clist/get` (`f9`, board PE): 100 boards returned, sane PE range on hand-inspection — the D4 range-sanity check.
- `stock/get` (`f127`, stock→industry): `600690` → `白色家电`, correct against the EastMoney web UI.

Full command transcripts live outside this doc (`.superpowers/sdd/gate1-evidence.md`, not committed to docs/); this appendix records only the verdict and the three checks, per the "no secrets in docs" rule (proxy host/port never printed).

**Implementation-session re-confirmation (2026-07-02 ~13:00 CST) — DEFERRED, not a regression.** Re-running the same two probes (GATE-1 reachability + D4 f9 range-sanity) through the proxy from the implementation session both hit `RemoteDisconnected: Remote end closed connection without response` — the documented EastMoney `push2*` burst-then-block pattern (ADR 0019). Per ADR 0019's explicit rule, **no retry was attempted** (retries extend the ban); total live HTTP calls this session: 2, both within the ≤3 budget. The proxy path itself was confirmed live and reaching egress (`proxy_used=True` was logged before the remote reset the connection) — the block is at EastMoney's edge, not in `resolve_cn_proxy()` / `proxy_env()` wiring. This DEFERRED result does not invalidate the authoring-session PASS above; it reflects a transient rested-IP-state block at the specific re-confirmation time, consistent with "wait until the IP is fully rested (overnight), retry once at ~15:45 CN."

**GATE-2 (4dp same-day `f184` ≈ `daykline.净占比` equivalence) — OPEN (deferred post-merge).** Reason: GATE-2 requires a post-close capture compared against the *same completed day's* daykline series the next day — structurally not completable inside a single plan/implementation session that ends before the 15:00 CN close. **Escalation path (D-B3):**

1. Run the spike post-close (`uv run python -m scripts.phase0_flow_batch_spike --use-cn-proxy`) to capture today's batch `f184`.
2. The next day, run `uv run python -m scripts.phase0_flow_batch_spike --use-cn-proxy --equiv-against <capture>` to compare against the completed day's per-symbol daykline series.
3. If `max|Δ| ≤ 4dp` across the compared symbols → keep `_ENGINE_VERSION="3"` (no bump; the batch and per-symbol paths are numerically equivalent at the digits that matter).
4. If a material (>4dp) gap surfaces → escalate to an `_ENGINE_VERSION` bump **and** a fresh ADR 0019 addendum **before** trusting the flow factor's forward metrics — do not ship the batch path's values into the forward ledger as if they were engine-"3"-equivalent without this check passing.

See the README "GATE-2 post-merge ops step" for the exact commands to run this check in production, and ADR 0019's 2026-07-02 addendum for the BUILT/gated summary.

### Tier-0 addendum — post-merge ops day 1 (2026-07-02, operator session)

- **Install:** all 3 launchd jobs registered (12:15 monitor / 15:45 flow-capture / quarterly snapshot); install.sh cold-start snapshot ran.
- **D7 seed:** completed — 30 symbols, 21–24 rows depth. First attempt seeded 30 EMPTY series: `seed_from_per_symbol` anchored its prune window at `max(trading_days)` and the cached calendar extends to 2026-12-31 → all-future keep-window. Op completed with the calendar clamped ≤ today; library fix landed separately (PR #191).
- **D8 backfill:** `irc fundamentals stock-valuation --force` → 397/397 A-shares, 715,477 rows, ALL through IRC_CN_PROXY (datacenter plane) — the proxy transport itself is healthy.
- **First 15:45 capture fire:** job fired on schedule, degraded rc=0 as designed — `ProxyError(RemoteDisconnected)` on the ulist.np CONNECT. **New discriminator measured:** the tunnel proxy passes datacenter-web CONNECTs (400 calls fine 15:0x–16:1x) but has refused push2.eastmoney.com CONNECTs since ~12:31 (authoring probes at 12:05 succeeded). Direct (CN Telecom egress) ulist.np succeeded 3/3 at 16:1x → push2 itself healthy; the proxy↔push2 tunnel leg is the failing piece. D2's no-direct-fallback stance means captures keep degrading until the tunnel recovers or D2 is amended (operator decision, not code).
- **Capture completed via operator action:** one direct ulist.np batch (spike script, injection seam) → 29/30 finals; appended to the store as 2026-07-02 (after_close=true). Store now 30 symbols × ≤25 td ending today.
- **GATE-2:** attempted same-evening (5 symbols, direct, paced) — ABORTED on symbol 1 (`ConnectionError` on daykline; direct IP warm from the day's probes; no retry per ADR 0019). **Status: OPEN.** Re-run once on a rested IP: `uv run python -m scripts.phase0_flow_batch_spike --equiv-against data/monitor/phase0_flow_spike/2026-07-02.json --equiv-n 5` (~15:45 next trading day). Escalation unchanged: >4dp → engine bump + ADR 0019 addendum before trusting flow forward metrics.
