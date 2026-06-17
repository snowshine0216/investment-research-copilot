# 001 — Index-path valuation + vocabulary unification (slice 1)

> Vertical slice 1 of `docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`.
> Excerpt scoped to this slice; shared sections (§3 eligibility, §4.3 vocab, §6 invariants) reproduced verbatim.

## Goal

Light up the **index-anchored valuation factor** in `irc monitor` for the profiles whose
`tracked_index` resolves to a real index anchor (`qdii_china_us_internet` → `009225`; and
`active_cn_equity` sector-index funds like `018132` when their sector slug is activated), using
**cached** evidence — no new valuation network calls. Also **unify the monitor valuation
vocabulary** onto the opportunity layer's five states. This slice proves the wiring + the map
end-to-end (smallest, no network).

## Acceptance criteria

1. New pure module `src/irc/monitor/valuation.py` exists with:
   - `resolve_valuation_state(fund, *, con, root) -> ValuationResolution` (frozen result
     `(state: str | None, cached: bool, reason: str | None)`), dispatching by `tracked_index`.
   - **Index-anchored branch** (`tracked_index` present): call `_index_valuation_metrics(con, tracked_index)`
     → `pe_percentile`; map percentile → band via the shared `_VALUATION_BANDS` / `_band`
     (`states.py:160–173`). Miss / immature history → `(None, False, "valuation_no_anchor")`.
   - **Look-through branch** (`tracked_index is None`): returns honest N/A placeholder
     `(None, False, "valuation_no_anchor")` — **filled in by item 002**. Leave a clear marker.
   - Pure helper `percentile_to_valuation_state(pct) -> str | None` applying the shared band
     thresholds (`cheap<0.20, reasonable_low<0.40, fair<0.70, expensive<0.90, very_expensive≥0.90`
     — `states._VALUATION_BANDS`), keeping boundaries DRY with the opportunity layer.
     `None`/NaN percentile → `None` (→ N/A).
2. `tracked_index` is resolved via the **same** `_tracked_index_for` / instrument-metadata
   mechanism the universe/opportunity layer uses (`inputs_loader.py:319–325`), so monitor and
   opportunity agree. `018132` (sector index) follows the index path but is subject to the
   existing `activated_sector_slugs` allowlist — `_index_valuation_metrics` short-circuits to N/A
   for an un-activated sector slug (acceptable: N/A, surfaced).
3. **Vocabulary unified** (§4.3, DECIDED): extend `_VALUATION_MAP` (`factor_maps.py:3`) to the
   opportunity layer's actual five states:
   ```python
   _VALUATION_MAP = {
       "cheap": 1.0, "reasonable_low": 0.5, "fair": 0.0,
       "expensive": -0.5, "very_expensive": -1.0,
   }
   ```
   `valuation_state_score` returns `None` for any unrecognized state → `valuation_unknown_state`
   (already a known N/A reason); contract unchanged for unexpected inputs.
4. Wire at `monitor_cmd.py:578`: replace `valuation_state=None, valuation_cached=False` with
   `val = resolve_valuation_state(fund, con=con, root=root)` →
   `valuation_state=val.state, valuation_cached=val.cached`.
5. After this slice: a fund whose `tracked_index` is a real `_INDEX_VALUATION_KEYS` member
   (e.g. `csi300`) shows a real valuation factor (when cache present); look-through active funds
   still show `valuation_no_anchor` (filled by 002); `gold`/`qdii_global` stay
   `profile_ineligible`.
   - ~~`009225` shows a real valuation factor (when cache present)~~ — **corrected at plan time
     (grounding):** `009225`'s tracked index `china_internet` is NOT in `_INDEX_VALUATION_KEYS`
     (it's a QDII-US display name, not a recognized index-valuation key), so `009225` honestly
     ships `valuation_no_anchor` even with cache. This is consistent with spec §4.1's
     "Miss / immature history → N/A" path and the non-goal "no new valuation fetch path." The
     wiring+map is proven end-to-end via `csi300`; a regression test
     (`test_china_internet_anchor_is_na_documented_gap`) locks the gap. Lighting `009225`
     specifically is a documented follow-up (add `china_internet` to the index-valuation key set
     with a data source) — out of scope for slice 1.

## Reuse boundary (§4)

Call the opportunity layer's **pure functions** (`_index_valuation_metrics`, the shared
`_VALUATION_BANDS`/`_band` in `states.py`) on monitor-loaded cached data. Do NOT depend on the
opportunity *pipeline* having run, and do NOT read opportunity *output files* (ADR 0017 monitor
evidence isolation). Shared dependency is the cached fundamentals tables only.

## Invariants preserved (§6)

- `gold`/`qdii_global` valuation remains `profile_ineligible` (behind `eligible_factors(profile)`),
  NOT `valuation_no_anchor`.
- All emitted N/A reasons remain in `KNOWN_NA_REASONS` → `monitor_signal` recompute still matches,
  `apply_eval_gate` unaffected. No regression to `caveated`/`gated`.
- Determinism: same cached artifacts → identical signal.

## Tests (TDD, §8)

- **Pure (no mocks):** `_VALUATION_MAP` unified vocabulary table-driven (every state +
  unrecognized→None); `percentile_to_valuation_state` at each band boundary
  (`0.20/0.40/0.70/0.90`, plus `None`/NaN → None); `resolve_valuation_state` index-anchored
  dispatch (present `tracked_index` → index path); coverage-miss → N/A; sector-allowlist
  short-circuit → N/A.
- **Integration (cached fixtures):** monitor run over fixture DuckDB → expected index-path
  `valuation` FactorScore for `009225`; `gold`/`qdii_global` stay `profile_ineligible`.
- **Determinism:** eval recompute over produced `eval_trace.json` still PASS.

## Module layout

```
src/irc/monitor/valuation.py   # NEW (index path + percentile_to_valuation_state; look-through = N/A stub)
src/irc/monitor/factor_maps.py # EDIT _VALUATION_MAP → unified 5-state vocab
src/irc/commands/monitor_cmd.py # EDIT ~578: feed valuation_state/valuation_cached
```
