# Sector rotation radar (`irc rotation`)

A **daily, deterministic, zero-LLM** radar that ranks EastMoney industry boards by a rotation
composite and resolves *emerging / hot* boards to concrete CN funds by holdings look-through — so
sector-rotation fund candidates surface **days-to-weeks earlier** than the weekly pipeline or a
hand-written `irc narrative` would find them.

**Advisory only.** The output is a research *lead*. It never gates buys, never emits a
`portfolio_action` / `DirectionalBias` / `opportunity_state`, and does not feed discovery or scoring
(v1). It runs *outside* the citation / SAME-3 / H3 machinery — pure market data, no `[ref:]` markers.

Design: [`docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md`](../../../docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md) ·
ADR [0023](../../../docs/adr/0023-sector-rotation-radar.md) · terminology in
[`CONTEXT.md`](../../../CONTEXT.md) → "Sector rotation radar".

---

## First-time setup (do this ONCE, in order)

The daily run is **cache-only** — it reads a local board-history series + cached holdings, it does
not build them. You must seed first, and the launchd wrapper must be (re)installed to auto-run it.

1. **Seed the caches** (one-time, paced live job, ~5–15 min, resumable):
   ```bash
   uv run irc rotation seed          # needs IRC_CN_PROXY set (same CN egress as `irc monitor`)
   ```
   Builds: (a) ≥60 trading days of per-board close history → `data/rotation/board_series.json`;
   (b) top-10 holdings for every universe CN fund missing from `data/narrative_holdings/`;
   (c) the stock→东财行业 board map → `data/monitor/stock_industry_map.json`.
   Re-running `seed` after an interrupt **skips** already-cached boards/funds/chunks and prints a
   coverage summary (exit 0 even on partial completion).

2. **Install the schedule** (so the daily run fires automatically):
   ```bash
   sh ops/launchd/install.sh
   ```
   Chains `irc rotation` into the **15:45** `com.irc.flow-capture` agent, *after* the flow-capture
   step, **protective-only** (a radar failure logs but never pages and never affects the
   flow-capture exit). No separate agent. (`install.sh` also runs a one-time `irc monitor snapshot`
   cold-start — expected.)

> **AC1 — check the first live run.** The board snapshot/history endpoint field codes were
> akshare-derived and fixture-tested but **not live-probed** at build time. Eyeball the first
> `seed` output and the first `rotation_radar.json`: real board history / board states, **not**
> `data_status: "abstain"` or all-boards-immature. If the field codes are wrong for your egress,
> that is where it shows (see the f100/f127 scar, ADR 0020).

---

## Daily usage

```bash
uv run irc rotation          # 1 board-snapshot call → append series → score → write report + ledger
uv run irc rotation --help
uv run irc rotation seed      # re-run any time to top up caches (resumable, idempotent)
```

Runs automatically at 15:45 each trading day once installed (holiday-guarded by the wrapper).
Advisory: **exits 0 always**, never pages.

### Where to find the report

```
outputs/<YYYY-MM-DD>/rotation/
  rotation_radar.json     # SOURCE OF TRUTH — schema_version, radar_version, data_status,
                          #   board_states[], candidates[], diagnostics{}
  rotation_radar.md       # human display (additive subset of the json; Chinese)
```

- **`board_states[]`** — per board: `state` (emerging / hot / fading / quiet), `days_in_state`,
  `composite_pctl`, `mom20`, `flow5`, `turn_delta`, `pe_pctl`, `chase_risk` (追高 flag).
  `emerging` = crossed into the top band (p80) within the last 5 trading days — the early-detection
  signal.
- **`candidates[]`** — funds surfaced by **board exposure** (Σ top-10 holding weight mapped to an
  emerging/hot board, ≥10 %). Each row is annotated `on_discovered_watchlist` / `in_monitor_set` /
  `held` + the holdings `as_of` quarter (staleness is stated, never hidden). The global
  `new_candidates` count = funds on **no** existing surface (the actionable leads).
- **`diagnostics{}`** — `immature_boards`, `unmapped_syms`, holdings-cache coverage %,
  `pe_coverage`, `dark_legs`.

### Data stores (git-ignored, persist across runs)

```
data/rotation/board_series.json      # append-only, once-per-day, trading-day pruned (keep 60 td)
data/rotation/forward_ledger.jsonl   # one row per (date × non-quiet board) — accrues from day 1
                                     #   for a future eval (F1); carries radar_version
data/monitor/stock_industry_map.json # shared stock→board map (extended in place; ≤30-day serve)
```

Two same-day runs over the same series store produce a **byte-identical** `rotation_radar.json`
(AC3 determinism).

---

## `data_status` (degradation is honest, never silent)

| value | meaning |
|---|---|
| `ok` | all three legs (mom / flow / turn) scored |
| `degraded_flow_dark` | flow leg dropped for **all** boards (renorm) — e.g. flow data absent, or post-seed before ~5 live snapshots accrue |
| `degraded_turn_dark` | turnover leg dropped for all boards (e.g. a board in the series is absent from today's snapshot) |
| `degraded_flow_turn_dark` | both dropped → momentum-only ranking |
| `abstain` | total snapshot fetch failure → stub report, **no** series/ledger mutation, exit 0 |

The flow/turn legs are dropped **globally**, never per-board (D6 "no per-board mixing") — a board is
never scored with a fabricated `0.0` flow/turn while a peer uses real data. Expect
`degraded_*_dark` for roughly the **first ~5–20 trading days after a seed**, because backfill rows
carry price only (flow/turnover accrue from live daily snapshots) — this is by design.

---

## Environment variables

| var | default | effect |
|---|---|---|
| `IRC_CN_PROXY` | — | CN egress proxy for the board fetch (required for live data; same as `irc monitor`) |
| `IRC_ROTATION_TOPUP_BUDGET` | `50` | bounds the `seed` stock→board fetch chunk size |
| `IRC_ROTATION_TIMEOUT` | `300` | watchdog timeout (s) for the wrapper-chained daily run |

No LLM, no paid search anywhere → the spend/balance gate is **not** involved.

---

## Troubleshooting

### The seed reports `boards={'done': 0}` / the daily run writes `data_status: "abstain"`

The board **snapshot** (`push2.eastmoney.com/api/qt/clist/get?fs=m:90+t:2`) and board **history**
(`push2his.eastmoney.com/.../stock/kline/get`) live on EastMoney's **geo-throttled** data plane. Some
egress paths — notably rotating datacenter tunnels — reach `ulist.np` (the endpoint `irc monitor`
uses for capital flow) but are **blocked on `clist/get` / `push2his`**, which fail with `ProxyError` /
`Read timed out`. `clist/get` is load-bearing (it enumerates + snapshots the ~86 boards **every**
run), so when it's blocked the radar has nothing to score.

Diagnose (from the repo root, so `.env` loads):
```bash
uv run python -c "from dotenv import load_dotenv; load_dotenv(); \
from irc.rotation.board_fetch import fetch_board_spot; print(len(fetch_board_spot('2026-01-01')), 'boards')"
```
- `ProxyError` on `push2.eastmoney.com` while `irc monitor` flow works → your egress can't reach
  `clist/get` (only `ulist.np`).
- **Same root cause darkens the monitor's board-PE leg.** Check `data/monitor/industry_pe/`: if the
  newest day file is stale or empty `{}`, `clist/get` has been unreachable for a while and the
  dual-track valuation *industry* leg has been degrading to DARK (ADR 0020 tolerates this silently).

Fix: run the seed + daily job from an egress that **can** reach `clist/get` (a CN-residential IP, or a
tunnel not geo-throttled on that endpoint). Follow-up **F8** (below) tracks a code path that would
avoid `clist/get` entirely. This is the **AC1** "endpoints/field codes are interface-specific — probe
live first" risk — the build had no CN egress to catch it.

## Package layout (`src/irc/rotation/`)

Pure-core + edge split — effects (fetch, file writes) live only in `board_fetch.py`, the store
writers, `seed.py`, and `commands/rotation_cmd.py`; everything else is pure and unit-tested with
fixtures. **One-way dependency** (AC11): `irc.rotation` imports *from* `irc.monitor`, never the
reverse (enforced by `tests/rotation/test_import_isolation.py`).

| module | role |
|---|---|
| `types.py` | frozen dataclasses: `BoardDay`, `BoardState`, `ExposureRow`, `RotationCandidate`, `RotationReport` |
| `board_fetch.py` | EDGE: board snapshot (1 clist call) + paced backfill (kline) + pure parsers |
| `series_store.py` | board-series persistence (once-per-day idempotent, trading-day pruned, atomic) |
| `composite.py` | PURE: cross-sectional percentile blend + `flow_leg_dark`/`turn_leg_dark` per-leg renorm + `pe_percentiles` |
| `states.py` | PURE: composite-percentile series → `rotation_state` (p80/p70 hysteresis, days-in-state) |
| `exposure.py` | PURE: holdings × stock→board map → fund×board exposure matrix + coverage diagnostics |
| `candidates.py` | PURE: emerging/hot boards × exposure → ranked candidates + membership annotations |
| `report.py` | PURE: `RotationReport` → json + md projections |
| `ledger.py` | forward-ledger row builder (pure) + append (edge) |
| `seed.py` | EDGE: resumable one-time seed orchestration |
| `_cmd_helpers.py` | command-layer glue (membership load, candidate resolution) |
| `../commands/rotation_cmd.py` | thin `run_rotation` (daily) + `run_rotation_seed` |

Tests mirror one-for-one under `tests/rotation/` (+ `tests/commands/test_rotation_cmd.py`, run
**per-file** — `pytest tests/commands/` whole-dir hangs on suite ordering).

---

## Follow-ups (see `TODOS.md` → "Sector rotation radar")

- **F1** `irc eval rotation_forward` — do emerging boards beat the board median over the next
  10/20 td? (needs ~4–6 weeks of ledger).
- **F2** surface integration (weekly-memo / monitor-brief 轮动雷达 pointer).
- **F3** dynamic `hot_sector` research query from the top boards.
- **F4** auto-generated narrative baskets from emerging-board constituents.
- **F5** `tracked_index` precision join for ETFs (board → CSIndex).
- **F6** daily in-run bounded top-up (v1 is cache-only; the budget currently bounds `seed`).
- **F7** board-kline **turnover** fetch — **BUILT, merged `4d5af11d` (2026-07-05)**: `board_fetch.py:87,136` parses `f61` (换手率) into `turnover_pct` on backfill rows, so the turn leg now has kline history (not snapshot-only). Still goes `turn_leg_dark` for boards without enough live turnover history yet or dropped from a later snapshot — honest, never a fabricated 0.0. No `radar_version` bump (availability class).
- **F8** board fetch off **`clist/get`** — the board snapshot/history endpoints (`clist/get`,
  `push2his` kline) are **intermittently** reachable on direct egress (ok 2026-07-06, refused 07-07) and blocked on some geo-throttled egresses that still reach `ulist.np` (see
  Troubleshooting). A `ulist.np`-based board path would need (a) a way to **enumerate** the ~86 boards
  without `clist/get` (a static BK-code list, or another reachable endpoint) and (b) a reachable
  board-history source (`push2his` is also blocked on the same egress). Non-trivial; tracked for a
  dedicated session. Shares the root cause with the monitor's dark board-PE leg.
