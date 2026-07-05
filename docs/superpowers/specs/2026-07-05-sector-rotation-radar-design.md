# Sector rotation radar (板块轮动雷达) — design spec

**Date:** 2026-07-05 · **Status:** grilled + locked, ready for autodev (not built)
**ADR:** [0023 — sector rotation radar](../../docs/adr/0023-sector-rotation-radar.md)
**Origin:** screening-process review 2026-07-05 — the only sector-driven fund-finding path today
is `irc narrative` (manual, 3 hand-written YAMLs); nothing detects a hot sector, so 板块轮动
candidates are found late. All measurement plumbing already exists in the monitor vertical.

## 1. Goal

A **daily, deterministic, zero-LLM** radar that (L1) ranks EastMoney industry boards by a
rotation composite and assigns each a `rotation_state`, and (L2) resolves *emerging/hot* boards
to concrete CN funds by holdings look-through, so candidate funds surface **days-to-weeks earlier**
than the weekly pipeline or a hand-written narrative would find them.

**Advisory only.** Output is a research lead. It never gates buys, never emits a
`portfolio_action`, `DirectionalBias`, or `opportunity_state`, and never feeds discovery/scoring
in v1 (ADR 0023 D2).

## 2. Non-goals (v1)

- No memo / monitor-brief / discovery / scoring integration (follow-up F2).
- No dynamic `hot_sector` research query — touches ADR 0007's static theme mapping (follow-up F3).
- No auto-generated narrative baskets — contradicts the frozen "Narrative selector" concept in
  CONTEXT.md; needs its own grill (follow-up F4).
- No `irc eval rotation_forward` command yet — ledger accumulates from day 1, eval ships once
  ~4–6 weeks of rows exist (follow-up F1).
- No new LLM or paid-search calls anywhere → the spend/balance gate is **not involved**.

## 3. Locked decisions (grill 2026-07-05)

| # | Decision |
|---|----------|
| D1 | Surface: standalone `irc rotation` command; daily post-close, chained into the **flow-capture** wrapper (15:45), NOT the 12:15 monitor wrapper — midday capture would append half-day rows into a close-based series (see §9). |
| D2 | Canonical sector unit: **EastMoney industry board** (~86, keyed by board code `BK…`). SW industries / CSIndex 17 / universe `theme` are display or follow-up vocabularies, never the measurement unit. |
| D3 | History: one-time paced backfill (~86 board-history calls, resumable) + steady-state **1 board-snapshot call/day** appended to a local series store. |
| D4 | Composite: cross-sectional percentile blend `0.5·pct(mom20) + 0.3·pct(flow5) + 0.2·pct(turnΔ)` (initial weights, tunable only via forward eval). Board-PE percentile is a 追高-risk **annotation**, never a score input. |
| D5 | `rotation_state ∈ {emerging, hot, fading, quiet}` with p80-entry / p70-exit hysteresis; `emerging` = crossed above p80 within the last 5 trading days (the early-detection deliverable). Recomputed **purely from the series store** every run — no incremental state file. |
| D6 | Degradation: total fetch failure → **abstain stub**, states do not advance; partial (flow leg absent) → drop the flow leg for **all** boards that day, renormalize, tag `degraded: flow_dark`. Never per-board mixing; never carry-forward. |
| D7 | L2 join: **fund×board exposure matrix** = cached top-10 holdings (shared `data/narrative_holdings/`) × stock→board map (extended `industry_map_store`). No curated board→theme mapping; covers all ~500 universe CN funds incl. the 262 theme-untagged. |
| D8 | Outputs: `outputs/<date>/rotation/rotation_radar.{md,json}`; json is source of truth, md is display. Zero `[ref:]` citations — pure market data, fully outside citation/SAME-3/H3 machinery. |
| D9 | Eval: append `data/rotation/forward_ledger.jsonl` from day 1; eval command deferred (F1). |
| D10 | Layer 3 hooks out of scope (F3/F4). |
| D11 | `irc rotation seed` = explicit one-time seeding (backfill + holdings + stock→board map); daily run is cache-only + bounded top-up (≤50 calls, env-overridable). |
| D12 | New `src/irc/rotation/` package importing monitor transport/cache edges (`cached_fetch`, `em_raw` parsers, `trading_calendar`); `industry_map_store` extended in place. Shared-package extraction deferred (rule of three). |

## 4. Architecture

```
src/irc/rotation/
  __init__.py
  types.py            # frozen dataclasses: BoardDay, BoardState, ExposureRow, RadarReport
  board_fetch.py      # EDGE: daily board snapshot (1 call) + backfill fetch (paced)
  series_store.py     # board series persistence (mirror flow_series_store patterns:
                      #   trading-day pruning, once-per-day idempotency, atomic write)
  composite.py        # PURE: per-day cross-sectional percentiles → composite score
  states.py           # PURE: series → rotation_state per board (hysteresis, days-in-state)
  exposure.py         # PURE: holdings × stock→board map → fund×board exposure matrix
  candidates.py       # PURE: emerging/hot boards × exposure matrix → ranked RotationCandidates
  report.py           # PURE: render md + json projections
  ledger.py           # forward-ledger row builder + append
src/irc/commands/rotation_cmd.py   # thin: `irc rotation` (daily) + `irc rotation seed`
```

Data flow, daily run:

```
board snapshot (1 call) ──append──▶ data/rotation/board_series.jsonl
                                        │ (pure)
        board_pe cache (monitor) ──▶ composite.py ──▶ states.py
                                        │
data/narrative_holdings/ (cached) ──▶ exposure.py ──▶ candidates.py
data/monitor/industry_map (ext.)        │
                                        ▼
                outputs/<date>/rotation/rotation_radar.{md,json}
                data/rotation/forward_ledger.jsonl   (append)
```

`irc rotation seed` (manual, once; resumable — skips anything already cached):
1. Board-history backfill: per-board daily close series ≥60 trading days (~86 paced calls,
   `cached_fetch` 3-outcome + breaker; partial completion is fine and reported).
2. Holdings seed: `fetch_top_holdings` for every universe CN fund missing from
   `data/narrative_holdings/` (paced; the narrative screen already does this fan-out routinely).
3. Stock→board map: chunked `ulist.np` batch over all held stocks (~2–3k symbols) reading the
   **行业 field for that interface** (f100 in `ulist.np` — NOT f127; see §13-T1), written through
   the extended `industry_map_store` (30-day cache semantics preserved).

## 5. Data contracts

**Series store** — `data/rotation/board_series.jsonl`-style store under `data/rotation/`
(implementation mirrors `flow_series_store.py`: keep-window pruning by trading days, per-day
idempotency — a rerun on the same date must not double-append). Row (conceptual):

```json
{"date": "2026-07-06", "board_code": "BK0475", "board_name": "半导体",
 "chg_pct": 2.31, "main_inflow_ratio": 1.84, "turnover_pct": 3.9, "source": "snapshot|backfill"}
```

**Report** — `rotation_radar.json`: `schema_version: 1`, `radar_version: 1` (composite formula
version; bump on any change to weights/windows/hysteresis — forward-eval segmentation depends on
it, same lesson as the monitor `_ENGINE_VERSION`), `data_status ∈ {ok, degraded_flow_dark,
abstain}`, board rows (code, name, state, days_in_state, composite_pctl, mom20, flow5, turn_delta,
pe_pctl?, chase_risk: bool), candidate rows (see below), diagnostics (immature boards excluded,
unmapped stocks, holdings-cache coverage %).

**Candidates** — per `emerging`/`hot` board: top 10 funds by `exposure_pct` (Σ top-10 holding
weight mapped to that board), threshold ≥10 %. Global `new_candidates` rollup = candidate funds on
NO existing surface. Every row annotates: `on_discovered_watchlist` / `in_monitor_set` / `held`
(from account.yaml when present) + `holdings_as_of` quarter (staleness is stated, never hidden).

**Forward ledger** — one row per (date × board) with state ≠ quiet: date, board_code, state,
composite_pctl, chg_pct, radar_version. Append-only, atomic.

## 6. Signal definitions (initial values — tunable ONLY via forward eval, never silently)

- `mom20` = 20-trading-day cumulative `chg_pct` minus the cross-board median of the same.
- `flow5` = mean of `main_inflow_ratio` over last 5 trading days.
- `turnΔ` = (5-day mean turnover) / (20-day mean turnover) − 1.
- Percentiles are cross-sectional over boards **with ≥20 trading days of history**; boards below
  that are excluded from states and listed in diagnostics ("no silent caps").
- Composite = 0.5/0.3/0.2 blend (D4). `chase_risk = state ∈ {emerging, hot} AND pe_pctl > 0.90`
  (board PE from the monitor's board-PE cache, stale-tolerated per its own freshness rules;
  missing PE → no flag, noted in diagnostics).
- States (D5), evaluated over the composite-percentile series, all trading-day indexed:
  `emerging` = first day above 0.80 was ≤5 trading days ago; `hot` = above band >5 days
  (band exit only below 0.70); `fading` = fell below 0.70 within the last 5 trading days after
  being hot/emerging; `quiet` = otherwise.

## 7. Degradation policy (D6)

| Condition | Behaviour |
|---|---|
| Snapshot call dead/transient after retries | Abstain: write stub report (`data_status: abstain`, failure named), no series append, no ledger rows, exit 0 (advisory — never pages). |
| Price present, flow fields absent | Drop flow leg for ALL boards, renormalize to 0.71·mom/0.29·turn, `data_status: degraded_flow_dark`. |
| Holidays/weekends | Wrapper already skips (holiday guard in flow-capture wrapper). |
| Holdings cache cold (seed never run) | L1 renders normally; candidates section renders a single actionable line pointing at `irc rotation seed`. Never fetches the full fan-out inline. |

## 8. Budget & pacing

Daily run: 1 snapshot call + ≤50 top-up calls (`IRC_ROTATION_TOPUP_BUDGET`, default 50) for
holdings/board-map cache misses, through `cached_fetch` (breaker stop-after-5 preserved — the
breaker is protective, never retry while blocking). Seed: paced with backoff, resumable,
partial-tolerant. No LLM, no paid search → no spend-gate preflight.

## 9. Scheduling & ops

Chain `uv run irc rotation` into `ops/launchd/run-flow-capture.sh` **after** the flow-capture
step (same 15:45 agent, post-close, holiday-guarded, protective-only: radar failure logs, never
pages, never affects the flow-capture exit path). No new launchd agent. Update
`docs/monitor/README.md` ops manual + `ops/launchd/README.md` (agent count/description) in the
same item — ops docs move with ops changes (established convention).

## 10. Terminology

CONTEXT.md gains a "Sector rotation radar" section (added 2026-07-05, marked **SPEC'd, not
built** — the shipping item flips the marker). Canonical terms: *sector rotation radar*,
*EM industry board*, *rotation_state*, *rotation candidate*, *board exposure*, *radar abstain*.
Forbidden collisions: never `heat`/`crowded`/`overheated` (fund-level `heat_state` vocabulary),
never `watchlist` for radar output, never `action`/`bias` for candidate semantics.

## 11. Acceptance criteria

- AC1 **Live probe first** (mirrors the f100/f127 lesson): before any parser is written, a
  spike/probe verifies the board snapshot + board history endpoints' actual field codes on the
  live CN egress, recorded in the item notes. Field codes are interface-specific; never assume.
- AC2 `irc rotation seed` is resumable: rerun after interrupt skips completed boards/funds/chunks;
  partial completion prints a coverage summary and exits 0.
- AC3 Daily run determinism: two same-day runs over the same series store produce byte-identical
  `rotation_radar.json` (given the once-per-day append idempotency).
- AC4 State machine unit-tested as pure functions: hysteresis (no flap on p79↔p81 oscillation),
  emerging→hot promotion at day 6, fading on band exit, quiet default; property test: states are
  a total function of the series slice.
- AC5 Degradation: abstain stub written on total failure (no series mutation, exit 0); flow-dark
  day renormalizes globally and tags `data_status`; a carry-forward of stale flow values is
  test-asserted NOT to occur.
- AC6 Exposure join: fund with 3 top-10 holdings in one board sums their weights; unmapped stocks
  reduce coverage % and appear in diagnostics, never silently dropped.
- AC7 Candidate annotations correct against fixtures for discovered-watchlist / monitor-set /
  held membership; `holdings_as_of` rendered on every candidate row.
- AC8 Report md suppresses nothing the json has except formatting — json is the additive source
  of truth (narrative-report pattern); md contains NO `[ref:` marker (grep test).
- AC9 Ledger rows append-only, atomic, carry `radar_version`; same-day rerun does not duplicate.
- AC10 Wrapper chaining: flow-capture wrapper runs the radar after capture; a radar non-zero exit
  does not page and does not mark flow-capture failed (shell-level test or manual verification
  documented).
- AC11 No import from `irc.rotation` into `irc.monitor`, `irc.discovery`, `irc.scoring`,
  `irc.memo`, `irc.opportunity` (one-way dependency, enforced by a grep/import test).
- AC12 `tests/` mirrors `src/irc/rotation/` one-for-one; `tests/commands/test_rotation_cmd.py`
  runs green **per-file** (the tests/commands whole-dir hang is a known suite-ordering issue).

## 12. Named follow-ups (out of scope, do not build)

- **F1** `irc eval rotation_forward`: do emerging boards beat the board median over the next
  10/20 trading days? Needs ~4–6 weeks of ledger. Segment by `radar_version`.
- **F2** Surface integration: one-line 轮动雷达 pointer in the weekly memo and/or monitor brief
  (touches locked memo pillars / monitor schema — separate items).
- **F3** Dynamic `hot_sector` research query from radar top boards (`build_holdings_query`
  pattern; interacts with ADR 0007 static theme mapping — grill before building).
- **F4** Auto-generated narrative baskets from emerging-board constituents (contradicts the
  frozen "Narrative selector" domain decision — needs a CONTEXT.md amendment grill).
- **F5** `tracked_index` precision join for ETFs (board → CSIndex mapping) + CSIndex momentum
  corroboration overlay.

## 13. Traps for the implementer (scar tissue, verified 2026-07-05)

- **T1** EastMoney field codes are **interface-specific**: 行业 is `f100` in `ulist.np` but
  `f127` in `stock/get`/`clist`. AC1 exists because of this. See `flow_batch_fetch.py` module
  docstring.
- **T2** Never test EM endpoints through curl-through-proxy — it false-fails; use `requests`
  (2026-07-02 finding).
- **T3** The breaker in `cached_fetch` is protective. A blocked run must never self-extend by
  retrying (>40 min self-DoS incident, ADR 0019 history).
- **T4** Midday capture corrupts a close-based series (why D1 chains at 15:45, not 12:15).
- **T5** `pytest tests/commands/` whole-dir hangs (suite ordering) — run per-file in CI steps.
- **T6** Changing any function signature: run every test dir that exercises it (grep callers in
  `tests/`), not just the mirror dir.
