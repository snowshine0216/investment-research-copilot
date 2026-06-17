# 002 — Look-through valuation (slice 2)

> Vertical slice 2 of `docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`.
> Builds on item 001's `valuation.py` (fills in the look-through branch). Excerpt scoped to this slice.

## Goal

Light up the **look-through valuation factor** for the 6 pure active funds
(`active_cn_equity` with `tracked_index is None`: `519069`, `260112`, `006533`, `000083`,
`519770`, `161903`), by **reusing the opportunity layer's pure Phase-D look-through derivation**
on monitor-loaded **cached** holdings + cached stock-valuation histories. No new network calls.
This is the heaviest slice (cached-coverage dependent).

## Acceptance criteria

1. Extend `resolve_valuation_state` in `src/irc/monitor/valuation.py` (from item 001): the
   **look-through branch** (`tracked_index is None`, `active_cn_equity`) now:
   - Assembles the cached look-through inputs from the monitor's already-loaded active-fund
     snapshot holdings — the same `load_latest_active_fund_cached` / `build_constituent_pool`
     the constituent factor uses (`monitor_cmd.py:561–576`) — plus cached stock-valuation
     histories.
   - Reuses the **pure** opportunity module `opportunity/lookthrough_valuation`:
     `fund_valuation_percentile` (`lookthrough_valuation.py:193`) with its `HoldingWeight` (`:37`)
     and `MetricSeries` (`:43`) value types → fund-level percentile.
   - `percentile_to_valuation_state(pct)` (the shared helper from item 001) → state.
   - **Coverage gate fails** (too few priced holdings) → `(None, False, "valuation_no_anchor")`.
2. This is pure valuation-math reuse, **not** a pipeline dependency. Per ADR 0017 (monitor
   evidence isolation): call the opportunity layer's *pure functions* on monitor-loaded cached
   data; do NOT depend on the opportunity *pipeline* having run, and do NOT read opportunity
   *output files*. Shared dependency is the cached fundamentals tables (constituent snapshots,
   stock valuations) that the monitor already consumes for the constituent factor.
3. After this slice: the 6 pure active funds show a real look-through `valuation` factor when
   cached stock-valuation coverage is sufficient; thin coverage → `valuation_no_anchor`
   (surfaced, not fabricated). `009225` (index path from 001) unchanged.
   `gold`/`qdii_global` stay `profile_ineligible`.

## Reuse boundary (§4.1 look-through bullet)

`fund_valuation_percentile` + `HoldingWeight`/`MetricSeries` are **pure**. The monitor loads the
cached holdings (already done for the constituent factor) and the cached stock-valuation series,
constructs the value types, calls the pure percentile function. No opportunity output files, no
pipeline run.

## Invariants preserved (§6)

- Eligibility unchanged; `gold`/`qdii_global` stay `profile_ineligible`.
- N/A reason on coverage miss is `valuation_no_anchor` (in `KNOWN_NA_REASONS`) → recompute
  matches; no `caveated`/`gated` regression.
- Determinism: same cached artifacts → identical fund percentile → identical signal.

## Tests (TDD, §8)

- **Pure (no mocks):** `resolve_valuation_state` look-through dispatch (`tracked_index is None`
  → look-through path); fund-percentile → state via `percentile_to_valuation_state` at band
  boundaries; **coverage-gate-fail → N/A** (too few priced holdings). Assert the look-through
  branch constructs `HoldingWeight`/`MetricSeries` correctly from cached rows (unit, using
  in-memory fixtures, no opportunity pipeline).
- **Integration (cached fixtures):** monitor run over fixture DuckDB + snapshot with sufficient
  stock-valuation coverage → expected look-through `valuation` FactorScore for an active fund;
  a thin-coverage fixture → `valuation_no_anchor`.
- **Determinism:** eval recompute over produced `eval_trace.json` still PASS.

## Risk (spec §10, primary)

Look-through needs cached stock-valuation histories for held names; thin coverage → N/A
(surfaced), not an error. Refreshed by the existing quarterly `irc monitor snapshot` /
`fundamentals snapshot` jobs. The look-through branch must degrade honestly, never fabricate.

## Module layout

```
src/irc/monitor/valuation.py   # EDIT: fill in the look-through branch (reuse lookthrough_valuation)
```
