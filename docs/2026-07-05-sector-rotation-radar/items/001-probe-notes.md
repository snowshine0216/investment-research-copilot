# AC1 probe notes — EM board field codes (item 001, Task 1)

**Date:** 2026-07-05
**Script:** `scripts/rotation_probe.py`

## Transport decision

Raw `push2.eastmoney.com` / `push2his.eastmoney.com` interfaces via `requests`
(NEVER curl-through-proxy — trap T2), routed through `IRC_CN_PROXY` at the edge
when set (`irc.http_proxy.resolve_cn_proxy()`), same posture as
`em_raw.fetch_board_pe_frame` / `flow_batch_fetch.fetch_flow_today_batch`.

We did **not** use the akshare `stock_board_industry_*` wrappers, because:

1. They hit the *same* `push2` host but add a pandas-parse layer that has
   historically drifted silently (this is exactly why `em_raw` exists — to own
   raw-JSON parsing directly, after the F4/F5 scars).
2. The monitor's geo-throttle-aware posture (batch-first call shape,
   `cached_fetch` breaker, `IRC_CN_PROXY`) only applies to the raw path, not to
   an akshare-wrapped call.

Snapshot endpoint: `clist/get` with `fs=m:90+t:2` (all industry boards, one
paginated call — same interface `em_raw.fetch_board_pe_frame` already uses).
Board history endpoint: `push2his.eastmoney.com/api/qt/stock/kline/get` per
board `secid=90.<BKcode>` with daily klines (what `stock_board_industry_hist_em`
wraps).

## Live probe outcome — partial success, geo-throttle observed

`IRC_CN_PROXY` is **not set** in this environment/session (`.env` has a value
but it is not exported into the shell used for the probe run, per the task's
stated setup). Running `scripts/rotation_probe.py` with direct egress:

- **First invocation succeeded** (single attempt, no retry) and returned a real
  SPOT row + 3 real HIST klines — see raw capture below.
- **A second, unrelated ad-hoc probe request immediately afterward failed**
  with `ConnectionError: Remote end closed connection without response`
  (the connection was aborted mid-handshake — consistent with an
  intermittent/geo-throttled EastMoney data-plane, the same class of failure
  documented in the flow-coverage-recurrence memory: bursty CN-plane access
  from this host is not reliably repeatable call-to-call).

Per the plan's script contract, the probe is **single-attempt, no
retry/hammer** (trap T3 — the breaker/probe posture is protective, never
self-extending). We did not re-run it to "confirm" a stable multi-call
sequence, because doing so would itself violate the never-hammer-live-EM rule
this ADR is scarred from. Treat the one successful capture below as a
confirming data point for field codes, but **not** as proof of stable,
repeatable live access — that remains a documented follow-up.

### Confirmed real capture (single successful call, 2026-07-05)

```
SPOT diff[0]: {"f2": 4149.53, "f3": -0.22, "f8": 0.79, "f9": 30.27, "f12": "BK0420", "f14": "航空机场", "f184": -4.39}
HIST klines[:3]:
  "2026-07-01,4082.64,4196.03,4203.31,4062.53,11307638,5200784715.00,3.44"
  "2026-07-02,4228.61,4158.78,4254.00,4141.86,9632885,4386444542.00,2.67"
  "2026-07-03,4162.12,4149.53,4198.39,4122.95,8399733,3858445826.00,1.81"
```

This single row **confirms** the akshare-known field-code mapping documented
below for `clist/get` and `kline/get` on this interface (board code, name,
change%, turnover%, PE, main-inflow%, price all landed in the expected
positions with plausible values — 市盈率=30.27 for 航空机场/airport-aviation is
a sane PE; the kline CSV parses into 8 comma-separated numeric fields matching
date/open/close/high/low/volume/amount/amplitude).

### Field codes (akshare-known, cross-checked against the live capture)

**Snapshot (`clist/get`, `fs=m:90+t:2`):**

| Field | Meaning | Notes |
|---|---|---|
| `f12` | 板块代码 (board code, e.g. `BK0420`) | primary key |
| `f14` | 板块名称 (board name) | display |
| `f3`  | 涨跌幅 (change %) | float |
| `f8`  | 换手率 (turnover %) | float |
| `f9`  | 市盈率 (board PE) | **same field `em_raw.parse_clist_boards` already reads** — PE comes inline at zero extra call cost. Tolerant: missing / `"-"` / non-numeric → `None` (some boards genuinely have no meaningful aggregate PE, e.g. loss-making board composites). |
| `f184`| 主力净流入净占比 (main-inflow net %) | expected on this board interface (akshare board wrappers surface 主力净流入 from it); degrade to `None` only if genuinely absent at runtime |
| `f2`  | 最新价 (latest index-like price) | not persisted in `BoardDay` (chg_pct is derived independently) |

**History (`kline/get`, `secid=90.<BKcode>`, `klt=101` daily):**

Each kline row is a comma-separated string: `f51,f52,f53,f54,f55,f56,f57,f58`.

| Position | Field | Meaning |
|---|---|---|
| 0 | `f51` | 日期 (date, `YYYY-MM-DD`) |
| 1 | `f52` | 开盘 (open) |
| 2 | `f53` | 收盘 (close) |
| 3 | `f54` | 最高 (high) |
| 4 | `f55` | 最低 (low) |
| 5 | `f56` | 成交量 (volume) |
| 6 | `f57` | 成交额 (amount) |
| 7 | `f58` | 振幅 (amplitude %) |

The kline interface carries **no PE field** — board PE is only available from
the snapshot (`f9`); this is why `BoardDay.board_pe` is populated on
`source="snapshot"` rows and always `None` on `source="backfill"` rows.

## Fixtures

Given the intermittent/geo-throttled live access documented above, and per
the plan's explicit fixture requirements (≥3 boards, at least one with a
missing/non-numeric `f9` to exercise the `None` path; ≥25 daily klines), the
fixtures are **hand-authored, synthetic-pending-live-confirmation**, shaped
to match the confirmed real `data.diff` / `data.klines` envelope and field
codes above (not simply copy-pasted from the one successful live row, so the
missing-PE and multi-board cases are actually exercised):

- `tests/rotation/fixtures/board_spot_sample.json` — 4 boards in `data.diff`
  list form, one (`BK0459`) with `f9: "-"` to exercise the None path, one
  (`BK0420`) with `f9` matching the real captured value (`30.27`) for realism.
- `tests/rotation/fixtures/board_hist_sample.json` — 25 ascending daily klines
  for `BK0475` (semiconductor board), same 8-field CSV-row shape as the real
  capture above.

**Live field-code confirmation beyond this single successful call is a
documented follow-up** (mirrors the f127→f100 Saturday-probe lesson — field
codes are interface-specific and should ultimately be reconfirmed against a
larger, stable live sample once CN egress from this host is verified
reliable/repeatable, not just single-shot). Parsers in
`src/irc/rotation/board_fetch.py` are built defensively (tolerant coercion,
never fabricate a row, never crash on blank/malformed payloads) against these
akshare-known + live-spot-checked field codes, and are pinned against the
fixtures above via regression tests.

## Addendum 2026-07-05 (post-merge) — F7 turnover probe: `f61` CONFIRMED

AC1-style live probe for follow-up **F7** (board-kline turnover), run after
PR #206 merged. Transport: `kline/get` via `IRC_CN_PROXY` tunnel
(`resolve_cn_proxy()`, requests — T2), **2/2 calls succeeded** (production
`fields2=f51..f58` + extended `fields2=f51..f61`, `secid=90.BK0475`, `lmt=5`).
This also partially discharges the "reconfirm against a stable live sample"
follow-up above for the kline interface: 3/3 successful kline calls total
across both probe sessions, all field positions consistent.

Extended request returns **11-column** kline CSV rows. Real capture:

```
production (f51-f58), 8 cols:
  2026-07-02,3843.00,3880.50,3918.97,3828.06,39091339,29054997866.00,2.37
  2026-07-03,3878.87,3880.94,3921.46,3847.28,33636435,24419122450.00,1.91
probe (f51-f61), 11 cols:
  2026-07-02,3843.00,3880.50,3918.97,3828.06,39091339,29054997866.00,2.37,1.20,46.11,0.29
  2026-07-03,3878.87,3880.94,3921.46,3847.28,33636435,24419122450.00,1.91,0.01,0.44,0.25
```

| Position | Field | Meaning | Verification against the capture itself |
|---|---|---|---|
| 8 | `f59` | 涨跌幅 (change %) | 3880.94/3880.50 − 1 = +0.011% → `0.01` ✓ |
| 9 | `f60` | 涨跌额 (change amt) | 3880.94 − 3880.50 = `0.44` exact ✓ |
| 10 | `f61` | **换手率 (turnover %)** | 0.25/0.29 — correct percent scale for a bank board; same unit as snapshot `f8` ✓ |

So `parse_board_hist` can source `turnover_pct` from position 10 once
`fields2` is extended — **F7 is probe-cleared, ready to build**. Ordering
matters: land F7 **before** the first `irc rotation seed`, because seed's
resumability (AC2) skips boards already in the series store — backfill rows
written with `turnover_pct=None` are never re-fetched, so a post-seed F7 only
helps re-seeds/new boards while the turn leg waits ~20 live snapshot days.
`f59` incidentally matches the derived `chg_pct` computation; keep deriving
(don't switch tested logic), it's a free cross-check at most.

Correction (cosmetic): live `data.name` for `BK0475` is **银行Ⅱ** (banks),
not 半导体 as the fixture note above and the spec §5 example row label it
(半导体 is a different BK code). No production impact — board codes are
opaque keys joined from live payloads, names are display-only from the same
payload — but don't "verify" future probes against the mislabel.

Session caveat for future probes: a Claude Code sandboxed shell RESETS both
direct push2his connections and the proxy CONNECT (baidu control succeeds) —
probe from an unsandboxed shell before concluding anything about EM egress.

## Addendum 2026-07-05 (later, same day) — ⚠️ F7 "probe-cleared" is SUPERSEDED by F8

**The "F7 is probe-cleared, ready to build" conclusion above (2/2 kline calls via
`IRC_CN_PROXY`) was NOT reproducible.** A structured 2-run diagnosis matrix
(`scripts/rotation_f8_diagnose.py`, unsandboxed, `requests` — T2) run after the
first seed attempt failed shows the board endpoints are **unreachable from this
host** — the earlier 2/2 caught a transient EM-allowed proxy exit, not a stable
path. Do **not** treat F7 as ready-to-verify-live until a working CN egress is
confirmed. The field-code table above (incl. `f61` = 换手率 at kline position 10)
remains the best-known mapping and F7 can be **built + fixture-tested offline**
against it, but its live reconfirmation is a real open follow-up, not done.

### Diagnosis matrix (2 runs, ~minutes apart, unsandboxed)

**Run 1 — proxy tunnel DOWN:**

| Endpoint | via `IRC_CN_PROXY` | direct |
|---|---|---|
| baidu (tunnel liveness) | ProxyError 15s ✗ | — |
| ulist.np (flow control) | ProxyError 15s ✗ | **200, real data ✓** (`600519 白酒Ⅱ f184=-5.3`) |
| clist/get (board snapshot) | ProxyError 15s ✗ | RemoteDisconnected 0.03s ✗ |
| push2his kline | ProxyError 15s ✗ | RemoteDisconnected 0.04s ✗ |

**Run 2 — proxy restarted (tunnel UP, EM exit BLOCKED):**

| Endpoint | via `IRC_CN_PROXY` | direct |
|---|---|---|
| baidu (tunnel liveness) | **200, 0.1s ✓** | — |
| ulist.np (flow control) | ProxyError 1.1s ✗ | 502 ✗ (was 200 in run 1 — burst-throttled) |
| clist/get (board snapshot) | ProxyError 1.1s ✗ | 502 ✗ |
| push2his kline | ProxyError 1.1s ✗ | RemoteDisconnected ✗ |

### Interpretation (this is F8)

Two independent, egress-level problems — neither fixable in code:

1. **Proxy exit IP is EM-blocked even when the tunnel is up.** Run 2: baidu-via-proxy
   succeeds (0.1s) but every EM host fails fast (~1.1s ProxyError) — the proxy
   opens the CONNECT, EM refuses the proxy's **exit IP**. Restarting the tunnel
   revives liveness but not EM access (Kuaidaili datacenter exits are flagged by
   EM). The tunnel occasionally rotates to an EM-allowed exit — that transient
   window is what produced the "2/2" above and the 2026-07-02 `ulist.np 6/6`.
2. **Direct egress is geo-throttled + board-plane-refused.** Direct `ulist.np`
   went 200×3 → 502×3 across the two runs (the documented "~5-burst then block"
   on this host's US-datacenter IP); `clist/get`/`push2his` are refused outright
   (502 / RemoteDisconnected) on the *same host* while `ulist.np` (in-burst) works
   — i.e. the block is endpoint- **and** IP-specific, not a wholesale host geo-block.

**Fix = a working CN egress** (CN-residential / EM-allowed proxy exit, a CN VPS,
or a paid CN data source), per the flow-coverage-recurrence conclusion. Until
then: `irc rotation seed` fails (`boards={'done':0}`), the daily run `abstain`s,
and the monitor's board-PE (dual-track valuation *industry* leg, same `clist/get`)
stays DARK — same root cause, dark since 2026-06-30. Consolidated fix plan:
[`../F8-DIAGNOSIS-FIX-PLAN.md`](../F8-DIAGNOSIS-FIX-PLAN.md).
