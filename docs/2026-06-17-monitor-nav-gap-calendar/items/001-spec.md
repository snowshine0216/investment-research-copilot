# Monitor `nav_quality` — calendar-grounded NAV-gap check

**Status:** Draft for review (2026-06-17)
**Owner:** Xue Yin
**Relates to:** [ADR 0017](../../adr/0017-monitor-evidence-isolation.md) (evidence isolation / pure-types boundary) · [ADR 0018](../../adr/0018-monitor-scoring-rationale-and-governance.md) "D3" (the pragmatic fix this supersedes) · [CONTEXT.md](../../../CONTEXT.md) "Monitor set" · `src/irc/monitor/eval/{trace.py,structural.py}` · `src/irc/data/akshare_client.py`
**Supersedes (keeps as fallback):** PR #158 (`b6ff72a`) — the recent-window + `_WARN_GAP_DAYS=8` heuristic.

---

## 1. Problem

`irc monitor`'s `monitor_signal` structural-health stage caveats a fund on a NAV cadence gap.
The original check (`trace._max_gap_days`) scanned the entire acc-NAV series and WARNed on any
inter-observation gap `> 5` **calendar** days. A CN-fund year *always* contains an ~11-day Spring
Festival and National-Day-Golden-Week closure, so the check could never pass — **every fund was
permanently `caveated`**, voiding the badge.

PR #158 shipped a pragmatic fix: measure the gap only over the recent ~20 observations and tolerate
gaps `≤ 8` calendar days. It works for the common case but leans on two **magic numbers** that
*proxy* for the holiday calendar rather than knowing it, and it leaves a residual: a run within ~4
weeks **after** Spring Festival / National Day still sees the big-holiday gap inside the window and
WARNs.

**This spec replaces the calendar-day heuristic with ground truth:** a gap is benign iff every day
in it was a non-trading day; the check WARNs only when a fund missed *trading days the market was
actually open*.

## 2. Key finding — one calendar covers the whole set

The monitor set mixes profiles: 7 `active_cn_equity`, 1 `gold`, 2 QDII (`qdii_global` 270023,
`qdii_china_us_internet` 009225). The concern was that QDII funds follow *foreign* calendars.
**Empirically they do not publish on foreign calendars** — probing the real NAV series:

| date | CN/US status | 009225 QDII-US | 270023 QDII-global | 260112 CN-equity |
|---|---|---|---|---|
| 2025-11-27 (US Thanksgiving) | US closed, CN open | NAV | NAV | NAV |
| 2025-07-04 (US July 4) | US closed, CN open | NAV | NAV | NAV |
| 2026-02-16 (CN Spring Festival) | CN closed, US open | — | — | — |

Chinese QDII funds value at lagged foreign close but **publish unit NAV on every CN trading day** —
identical presence/absence to a domestic fund. Therefore a **single CN A-share trading calendar**
(SSE) is correct for all 10 funds. No per-market calendars, no QDII special-casing. (QDII NAV *value*
lag is T+1/T+2, well inside the `stale_days=7` FAIL bound — unaffected.)

## 3. Design

### 3.1 Trading calendar (I/O, edge)

- **`akshare_client.fetch_trade_calendar() -> tuple[date, ...]`** — wraps AkShare
  `tool_trade_date_hist_sina()` (SSE trade-date history), returns sorted ascending trade dates.
  Pure-ish wrapper at the existing AkShare boundary; no other module imports AkShare for this.
- **`monitor/trading_calendar.py` — `load_trading_days(today: date) -> frozenset[date] | None`**
  (thin edge). Reads `data/monitor/trade_calendar.json` (which stores `{"fetched_on": <date>,
  "dates": [...]}`); refetches via `fetch_trade_calendar` only when the cache is **missing** or its
  **`fetched_on < today`** — i.e. at most once per calendar day (the calendar is append-only at the
  tail, so intra-day refetch is pointless; a once-per-day check avoids the weekend over-fetch a
  "max-date < today" trigger would cause). Persists with the atomic `.tmp.{pid} → os.replace`
  pattern. On any fetch/parse failure, logs a warning and returns **`None`** (degrade, never crash).
  Returns a `frozenset[date]` for O(1) membership.

### 3.2 Pure metric (trace.py)

- **`_missing_trading_days(series, trading_days, *, window=_RECENT_GAP_WINDOW) -> int | None`**
  — over the last `window` observations, for each consecutive pair `(d0, d1)` count the trading
  dates **strictly between** `d0` and `d1` (`{d ∈ trading_days : d0 < d < d1}`); return the max.
  Holidays/weekends aren't in `trading_days` → contribute 0. Returns `None` when `trading_days is
  None` (calendar unavailable) so the gate can fall back. `< 2` observations → `0`.
- `_RECENT_GAP_WINDOW = 20` is **retained** but its role changes: it is now *relevance scoping*
  (don't surface an ancient 2021 outage in today's brief), not holiday-dodging. The calendar, not
  the window, provides holiday immunity.
- The trace `nav` dict gains **`missing_trading_days`**; **`max_gap_days` is retained** (display +
  fallback). `schema_version` is bumped.

### 3.3 Gate (structural.py)

`nav_quality` decides the gap sub-status as:

```
md = nav["missing_trading_days"]
if md is not None:                      # calendar available — ground truth
    WARN if md >= _MISSING_TRADING_WARN   # _MISSING_TRADING_WARN = 2
else:                                    # calendar unavailable — degraded fallback
    WARN if max_gap_days > _WARN_GAP_DAYS  # the PR #158 heuristic, unchanged
```

`_MISSING_TRADING_WARN = 2`: tolerate a single isolated missed trading day (transient AkShare /
publish glitch); WARN on ≥2 consecutive missed open days. This is the **only** remaining threshold,
and it is semantically meaningful (consecutive trading days the fund went dark), not a calendar fudge
factor. The `obs<min`, `missing NAV`, and `as_of older than stale_days` **FAIL**s are unchanged.

### 3.4 Threading (monitor_cmd.py edge)

`build_eval_trace` gains a `trading_days: frozenset[date] | None = None` parameter, passed through
`_nav` into `_missing_trading_days`. The edge calls `load_trading_days(date.today())` **once per
run** and passes the result into both `build_eval_trace` call sites (`_compute_gates` projection and
`_write_eval_artifacts`). Default `None` keeps every existing pure-test call site valid (they fall
back to `max_gap_days`).

## 4. Data flow

```
monitor_cmd (edge)
  └─ load_trading_days(today)              # cache hit, or one AkShare call; None on failure
       └─ build_eval_trace(..., trading_days)        [pure]
            └─ _nav → _missing_trading_days(series, trading_days, window=20)   [pure]
                 └─ nav["missing_trading_days"]
  └─ monitor_signal_health → nav_quality                                       [pure]
       └─ md≥2 → WARN  |  md None → fallback to max_gap_days>8 → WARN  |  else PASS
       └─ WARN → apply_eval_gate → "caveated" (fail-open; never EVAL_GATED)
```

## 5. Error handling / degrade

- **Calendar fetch fails** → `load_trading_days` returns `None` → `missing_trading_days` is `None`
  → gate falls back to the PR #158 calendar-day heuristic. The brief still renders; no regression
  vs today. A warning is logged with the cause.
- **Calendar stale but present** (network down, cache has yesterday's dates) → used as-is; the only
  risk is the very latest trading day not yet in the cache, which affects the *trailing* edge
  (staleness territory), not interior gaps.
- **Pure functions never do I/O** (ADR 0017 §3.3): `trace.py` / `structural.py` receive the calendar
  as a parameter; only `akshare_client` and `trading_calendar.py` touch the network/filesystem.

## 6. Testing (TDD)

Pure (no mocks):
- `_missing_trading_days`: holiday gap → 0; a real interior missed trading day → counts; respects the
  recent window (ancient outage ignored); `None` calendar → `None`; `<2` obs → `0`.
- `nav_quality`: `md≥2` → WARN; `md∈{0,1}` → PASS; `md=None` → falls back to `max_gap_days` path
  (both branches); FAILs unchanged.
Edge (thin, mocked I/O):
- `load_trading_days`: cache hit (no fetch); stale/missing → fetch + persist; fetch failure → `None`
  + warning; atomic write.
- `fetch_trade_calendar`: shape/parse of the AkShare frame (mocked), ascending `date` tuple.
Acceptance:
- Recompute the gate over a fixture series spanning Spring Festival → `missing_trading_days = 0` →
  `validated`, including a run dated the day after the holiday (the residual the heuristic couldn't
  close).
- Live (gated, opt-in): regenerate today → all 10 funds `validated`, panel `monitor_signal PASS`.

## 7. Out of scope / YAGNI

- Per-market calendars for genuinely foreign-publishing funds — none exist in the monitor set
  (finding §2); revisit only if such a fund is ever added.
- SGE-vs-SSE session nuances for gold — the gold fund publishes on CN trading days like the rest;
  not modelled separately.
- Trailing-edge / staleness changes — already covered by the `stale_days=7` FAIL; untouched.

## 8. Consequences

- The two big closures no longer WARN even right after the holiday — the residual is **closed**.
- One meaningful threshold (`_MISSING_TRADING_WARN=2`) remains; the calendar-day window/threshold
  survive only as the **degraded-mode fallback**, so PR #158 is not wasted.
- Adds one cached AkShare call per run (one network round-trip on cache miss; free on hit) and a new
  `data/monitor/trade_calendar.json` artifact.
- `eval_trace.json` schema gains `missing_trading_days`; `schema_version` bumped. Update ADR 0018
  "D3" to point at this calendar-grounded successor.
