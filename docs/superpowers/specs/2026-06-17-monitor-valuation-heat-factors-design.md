# Monitor valuation + heat factor wiring — design

**Date:** 2026-06-17
**Status:** Design (approved scope: wire BOTH valuation and heat)
**Supersedes:** the "OPEN v2.1: valuation factor" item in the Monitor vertical roadmap.
**Reconciles:** a prior abandoned attempt on stale branch `monitor-valuation-heat-factors`
(cut from `7ba7647`, pre-#162, no PR). Its concrete AkShare findings (restriction-only heat
via `fund_purchase_em`; reuse of `opportunity/lookthrough_valuation`) are folded in here; its
code is discarded (would revert the merged #162 NAV-gap calendar work).
**Related:** `docs/superpowers/specs/2026-06-15-monitor-daily-report-design.md` (§ valuation/heat factor rows 183–184, eligibility rows 199–201, open-question rows 563–568); ADR 0017 (monitor evidence isolation); ADR 0012 (valuation axis).

## 1. Problem

`irc monitor` produces a daily brief whose signal is a weighted blend of up to five factors
(`trend`, `valuation`, `heat`, `macro_tilt`, `constituent`). Today the **valuation** and
**heat** factors are dark for *every* fund whose profile makes them eligible, because the
command edge hardcodes their inputs to `None`:

```python
# src/irc/commands/monitor_cmd.py:578
inp = FactorInputs(
    acc_nav=nav.acc_series ...,
    valuation_state=None,      # ← never fetched
    valuation_cached=False,    # ←
    restricted=None,           # ← heat input
    aum_delta_pct=None,        # ← heat input
    macro_rows=macro_rows,
    constituent_rows=constituent_rows,
)
```

The factor functions therefore short-circuit to N/A:
- `_valuation` (`factors.py:60`): `not valuation_cached or valuation_state is None` → `valuation_no_anchor`.
- `_heat` (`factors.py:71`): `heat_score(None, None)` → `heat_no_data`.

These N/A reasons are *legitimate* members of `KNOWN_NA_REASONS`, so the eval gate correctly
reports `validated` — the signal is valid, it just rests on fewer factors than designed. The
intent (monitor daily-report design, rows 183–184) was always to feed real inputs; the wiring
was deferred. This spec wires it.

> **Diagnostic note (not in scope to fix here):** the displayed reasons are
> `valuation_no_anchor` / `heat_no_data`, **not** `profile_ineligible`. That confirms these
> factors are *eligible* for the fund's profile but starved of inputs — the unfinished-wiring
> case, distinct from the by-design `gold` / `qdii_global` valuation ineligibility.

## 2. Goals / non-goals

**Goals**
- Light up `valuation` for the profiles that have a real anchor (`qdii_china_us_internet`,
  `active_cn_equity`), using **cached** evidence — no new valuation network calls.
- Light up `heat` (crowding) for all profiles whose weight vector includes it, on the
  **restriction leg** (限购 / 申购状态) via a single market-wide AkShare call. The AUM-Δ leg
  is deferred (no per-fund live QoQ source — §5).
- Preserve every existing invariant: per-profile eligibility, N/A-reason determinism, eval
  badges, signal reproducibility.
- Degrade honestly to N/A (never fabricate) when data is absent, and *surface* coverage.

**Non-goals**
- No change to `gold` / `qdii_global` valuation eligibility — they stay `profile_ineligible`.
- No new valuation fetch path (the `# TODO(post-v1)` narrow index-valuation refresh in
  `fetch.py:15` stays out of scope; we read whatever is cached and ship N/A on a miss).
- No re-weighting of profile vectors.

## 3. The monitor set & per-profile factor eligibility

`config/monitor.yaml` currently lists **10 funds** (the set grew from the original 7):

| fund | profile | valuation path | heat |
|------|---------|----------------|------|
| 008986 广发上海金ETF联接A | `gold` | **N/A by design** (commodity, no anchor) | eligible |
| 270023 广发全球精选股票(QDII) | `qdii_global` | **N/A by design** (active, no anchor) | eligible |
| 009225 天弘中证美互联网QDII | `qdii_china_us_internet` | **index-anchored** | eligible |
| 018132 博时中证有色金属矿业主题指数A | `active_cn_equity` | index-anchored (sector index, allowlist-gated) | eligible |
| 519069 汇添富价值精选混合 | `active_cn_equity` | **look-through** | eligible |
| 260112 景顺长城能源基建混合A | `active_cn_equity` | look-through | eligible |
| 006533 易方达科融混合 | `active_cn_equity` | look-through | eligible |
| 000083 汇添富消费行业混合 | `active_cn_equity` | look-through | eligible |
| 519770 交银择优回报 | `active_cn_equity` | look-through | eligible |
| 161903 万家行业优选 | `active_cn_equity` | look-through | eligible |

The valuation path is decided by `tracked_index`, exactly as the opportunity layer already
does (`inputs_loader.py:319–325`): a fund with a resolved `tracked_index` uses the index-PE
path; a pure active fund (`tracked_index is None`) uses look-through. `018132` is a sector
*index* fund whose `tracked_index` resolves to a sector slug — it follows the index path but
is subject to the existing `activated_sector_slugs` allowlist (`_index_valuation_metrics`
short-circuits to N/A for an un-activated sector slug, which is acceptable: N/A, surfaced).

## 4. Valuation factor — reuse the opportunity engine

**Principle: reuse, do not reimplement.** The opportunity layer already computes a fully
coverage-gated per-fund valuation, with both an index-PE path and a Phase-D look-through path,
and it is already unit-tested. Duplicating that subtle logic inside the monitor would be a
DRY violation and a second source of truth for valuation. The monitor instead *loads the
cached inputs and calls the existing pure derivation*.

### 4.1 New module: `src/irc/monitor/valuation.py` (pure)

```
resolve_valuation_state(fund, *, con, root) -> ValuationResolution
```
returning a frozen result `(state: str | None, cached: bool, reason: str | None)` where
`state` is one of the unified vocabulary (§4.3) or `None`.

Internal dispatch by `tracked_index` (resolved via the same `_tracked_index_for` /
instrument-metadata mechanism the universe uses, so the monitor and opportunity agree):

- **Index-anchored** (`tracked_index` present): call `_index_valuation_metrics(con, tracked_index)`
  → `pe_percentile`; map percentile → band via the shared `_VALUATION_BANDS` /
  `_band` (`states.py:160–173`). Miss / immature history → `(None, False, valuation_no_anchor)`.
- **Look-through** (`tracked_index is None`, `active_cn_equity`): assemble the cached
  look-through inputs from the monitor's already-loaded active-fund snapshot holdings
  (the same `load_latest_active_fund_cached` / `build_constituent_pool` the constituent
  factor uses, `monitor_cmd.py:561–576`) plus cached stock-valuation histories, and reuse
  the **pure** `opportunity/lookthrough_valuation` module — `fund_valuation_percentile`
  (`lookthrough_valuation.py:193`) plus its `HoldingWeight` / `MetricSeries` value types
  (`:37` / `:43`) — to get a fund-level percentile, then `percentile_to_valuation_state`
  (§4.3) → state. This is pure valuation-math reuse, not a pipeline dependency. Coverage
  gate fails (too few priced holdings) → `(None, False, valuation_no_anchor)`.

> **Reuse boundary:** we call the opportunity layer's *pure functions* on monitor-loaded
> cached data. We do NOT depend on the opportunity *pipeline* having run, and we do NOT read
> opportunity *output files* — consistent with ADR 0017 monitor evidence isolation. The
> shared dependency is the cached fundamentals tables (`index_valuation_history`, stock
> valuations, constituent snapshots), which the monitor already consumes for other factors.

### 4.2 Wiring

At `monitor_cmd.py:578`, replace the two hardcoded `None`s:

```python
val = resolve_valuation_state(fund, con=con, root=root)
inp = FactorInputs(
    ...,
    valuation_state=val.state,
    valuation_cached=val.cached,
    ...
)
```

### 4.3 Vocabulary — unify on the opportunity states (DECIDED)

The opportunity layer emits `{cheap, reasonable_low, fair, expensive, very_expensive}`; the
monitor `_VALUATION_MAP` (`factor_maps.py:3`) currently keys on `{cheap, fair_cheap, fair,
fair_expensive, expensive}`. **Decision: extend the monitor map to the opportunity's actual
five states** rather than lossy-remap at the boundary. This gives one vocabulary, one source
of truth, and no information loss. New map:

```python
_VALUATION_MAP = {
    "cheap": 1.0, "reasonable_low": 0.5, "fair": 0.0,
    "expensive": -0.5, "very_expensive": -1.0,
}
```

`valuation_state_score` returns `None` for any unrecognized state → `valuation_unknown_state`
(already a known N/A reason), so the contract is unchanged for unexpected inputs.

Both valuation paths produce a *percentile* (index PE-pct, or the look-through fund
percentile), so `valuation.py` carries one pure `percentile_to_valuation_state(pct) -> str | None`
helper that applies the shared band thresholds (`cheap<0.20, reasonable_low<0.40, fair<0.70,
expensive<0.90, very_expensive≥0.90` — `states._VALUATION_BANDS`), keeping the band boundaries
DRY with the opportunity layer. `None`/NaN percentile → `None` (→ N/A).

## 5. Heat factor — restriction leg now, AUM leg deferred

Heat has no existing data source. AkShare reality (verified — `ak.fund_purchase_em` /
`ak.fund_scale_change_em` both exist on the pinned version):

- **限购 / 申购状态 — available, covers all funds in one call.** `ak.fund_purchase_em()`
  returns **one market-wide table** (申购状态 + 日累计限定金额 per fund). A single call per
  `irc monitor` run yields the restriction status for all 10 ids — no per-fund fetch, no
  availability risk. This is the heat input we ship.
- **AUM QoQ Δ — no per-fund live source. Deferred.** `ak.fund_scale_change_em()` is an
  *aggregate-market* table (基金家数 / total 期末净资产), not per-fund; per-fund AUM is only a
  single latest point with no QoQ series. So `aum_delta_pct` ships `None`, and the
  overheated `−1.0` sharpening (which requires AUM Δ ≥ 20%) is **deferred** to a future slice
  with a real per-fund AUM-history source. Heat still ships on the restriction leg alone.

This supersedes the §10 "endpoint availability" risk in the 2026-06-15 design: the restriction
endpoint is confirmed market-wide, so heat is eligible for every fund now; only the AUM
sharpening is deferred.

### 5.1 New module: `src/irc/monitor/heat_fetch.py` (edge + pure parse)

Follows the `src/irc/fundamentals/akshare_*.py` house pattern (local `import akshare as ak`,
pure parse helpers separated from the one network call):

```python
def fetch_purchase_table(fetch=ak.fund_purchase_em) -> pd.DataFrame | None   # edge: ONE call per run
def parse_purchase_status(table, fund_id) -> bool | None                     # pure → restricted
def heat_inputs_for(fund_id, *, purchase_table) -> tuple[bool | None, float | None]  # (restricted, None)
```

- **Restriction rule** (pure): `restricted = True` when 申购状态 ∉ {`开放申购`} **or**
  日累计限定金额 < `_RESTRICTION_CAP_THRESHOLD` (`1e8`). Fund absent from the table /
  unparseable row → `None` (→ `heat_no_data`, surfaced — not fabricated).
- `heat_inputs_for` returns `(parse_purchase_status(table, fund_id), None)` — `aum_delta_pct`
  is `None` until the AUM-history source lands.
- CN endpoint stays **direct** (no `IRC_HTTPS_PROXY`), per the project http-proxy rule.

### 5.2 Wiring & scoring

`heat_score(restricted=..., aum_delta_pct=...)` already exists (`factor_maps.py:15`) and with
`aum_delta_pct=None` reduces to: `restricted` → `−0.5` (crowded), else `+0.3` (calm), `None`
restriction → `None` (N/A). Wire `restricted` / `aum_delta_pct` into `FactorInputs` at
`monitor_cmd.py:578`. No scoring change — the existing `heat_score` already handles the
AUM-`None` case.

### 5.3 Availability contract (no silent failure)

`fetch_purchase_table` returns `None` (not raises) if the one AkShare call fails; every
per-fund `parse_purchase_status` then yields `None` → honest `heat_no_data` in
`eval_trace.json`, with a structured log line recording the miss. Never a fabricated score.

## 6. Invariants preserved

- **Profile eligibility unchanged.** Both factors stay behind `eligible_factors(profile)`:
  `gold` / `qdii_global` valuation remains `profile_ineligible` (NOT `valuation_no_anchor`).
- **N/A determinism.** All emitted reasons remain in `KNOWN_NA_REASONS`
  (`valuation_no_anchor`, `valuation_unknown_state`, `heat_no_data`), so the
  `monitor_signal` recompute still matches and `apply_eval_gate` is unaffected — funds simply
  light up where real data exists; nothing regresses to `caveated`/`gated` from this change.
- **Confidence.** A factor that becomes eligible gets `conf = 1.0` per the existing gate
  guarantee (design row 249); no new confidence model.
- **Determinism / reproducibility.** Same cached artifacts → identical signal.

## 7. Module layout & insertion points

```
src/irc/monitor/
  valuation.py        # NEW  pure: resolve_valuation_state + percentile_to_valuation_state (reuse lookthrough_valuation)
  heat_fetch.py       # NEW  edge: fetch_purchase_table (1 akshare call) + pure parse_purchase_status / heat_inputs_for
  factor_maps.py      # EDIT _VALUATION_MAP → unified 5-state vocabulary
  factors.py          # unchanged (already consumes the FactorInputs fields)
  fetch.py            # unchanged (cache-read; TODO post-v1 narrow refresh stays out)
src/irc/commands/
  monitor_cmd.py      # EDIT line ~578: feed valuation_state/valuation_cached + restricted/aum_delta_pct
```

## 8. Testing strategy (TDD, red→green→refactor)

- **Pure (no mocks):**
  - `_VALUATION_MAP` unified vocabulary: table-driven, every state + unrecognized→None.
  - `resolve_valuation_state` dispatch: index-anchored vs look-through selection by
    `tracked_index`; percentile→band mapping at each boundary (`0.20/0.40/0.70/0.90`);
    coverage-gate-fail → N/A; sector-allowlist short-circuit → N/A.
  - `parse_purchase_status`: 开放申购 → not restricted; 暂停/限购/cap<1e8 → restricted;
    fund absent / unparseable → `None`. `heat_inputs_for` always returns `aum_delta_pct=None`.
- **Integration (cached fixtures):** monitor run over fixture DuckDB + snapshot + a fixture
  purchase table → expected `valuation`/`heat` FactorScores per profile; gold/qdii_global
  stay `profile_ineligible`.
- **Live (double-gated, `live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`):** one `ak.fund_purchase_em()`
  call — asserts the table is reachable and the 10 ids parse; asserts graceful `None` on a
  missing id.
- **Determinism:** eval recompute over the produced `eval_trace.json` still PASS (N/A reasons
  in the known set); badge distribution unchanged except newly-lit factors.

## 9. Phasing (one spec, three vertical slices)

1. **Index-path valuation + vocab unification** — lights `009225` (and `018132` when its
   sector slug is activated). No network. Smallest, proves the wiring + map end-to-end.
2. **Look-through valuation** — the 6 pure active funds; reuse the opportunity Phase-D
   derivation on monitor-loaded cached holdings + stock valuations.
3. **Heat (restriction leg)** — `fetch_purchase_table` (one `fund_purchase_em` call) +
   `parse_purchase_status` → wire. Independent of the valuation slices; can land in parallel.
   Lights heat for all 10 funds. AUM-Δ sharpening explicitly deferred (§5).

## 10. Risks & open questions

- **Look-through cached-data coverage (primary risk).** Active-fund valuation needs cached
  stock-valuation histories for the held names; thin coverage → N/A (surfaced), not an error.
  Refreshed by the existing quarterly `irc monitor snapshot` / `fundamentals snapshot` jobs.
  This is the heaviest unit (slice 2).
- **`fund_purchase_em` schema drift.** Heat depends on AkShare's market-wide purchase table
  column names (申购状态 / 日累计限定金额). Parsing is column-name-tolerant and degrades to
  `None` (→ `heat_no_data`) on an unexpected shape, never a wrong score.
- **AUM-Δ deferred (known gap, not a risk).** No per-fund live QoQ AUM source exists
  (`fund_scale_change_em` is aggregate-only), so the overheated `−1.0` heat tier cannot fire
  yet; heat runs on the restriction leg (`−0.5` / `+0.3`). Revisit when a per-fund AUM-history
  source lands.
- **Cache staleness coupling.** Valuation reads cached `index_valuation_history` / stock
  valuations; a stale or empty cache → N/A on a miss (no live fallback in scope). Acceptable
  per Non-goals.
