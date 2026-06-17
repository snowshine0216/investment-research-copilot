# 003 — Heat factor, restriction leg (slice 3)

> Vertical slice 3 of `docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`.
> Independent of the valuation slices (001/002). Excerpt scoped to this slice.

## Goal

Light up the **heat (crowding) factor** for all 10 monitor funds on the **restriction leg**
(限购 / 申购状态) via a single market-wide AkShare call per `irc monitor` run. The AUM-Δ leg is
**deferred** (no per-fund live QoQ source). Heat ships on the restriction leg alone.

## Acceptance criteria

1. New module `src/irc/monitor/heat_fetch.py` (edge + pure parse), following the
   `src/irc/fundamentals/akshare_*.py` house pattern (local `import akshare as ak`, pure parse
   helpers separated from the one network call):
   ```python
   def fetch_purchase_table(fetch=ak.fund_purchase_em) -> pd.DataFrame | None   # edge: ONE call per run
   def parse_purchase_status(table, fund_id) -> bool | None                     # pure → restricted
   def heat_inputs_for(fund_id, *, purchase_table) -> tuple[bool | None, float | None]  # (restricted, None)
   ```
2. **Restriction rule** (pure): `restricted = True` when 申购状态 ∉ {`开放申购`} **or**
   日累计限定金额 < `_RESTRICTION_CAP_THRESHOLD` (`1e8`). Fund absent from the table /
   unparseable row → `None` (→ `heat_no_data`, surfaced — not fabricated).
3. `heat_inputs_for` returns `(parse_purchase_status(table, fund_id), None)` —
   `aum_delta_pct` is `None` until the AUM-history source lands.
4. **One AkShare call per run.** `fetch_purchase_table` returns the market-wide table once;
   per-fund parsing is pure against that table. CN endpoint stays **direct** (no `IRC_HTTPS_PROXY`),
   per the project http-proxy rule.
5. **Availability contract (no silent failure):** `fetch_purchase_table` returns `None`
   (does NOT raise) if the one AkShare call fails; every per-fund `parse_purchase_status` then
   yields `None` → honest `heat_no_data` in `eval_trace.json`, with a structured log line
   recording the miss. Never a fabricated score.
6. Wire at `monitor_cmd.py:578`: fetch the purchase table once before the per-fund loop, then per
   fund set `restricted, aum_delta_pct = heat_inputs_for(fund_id, purchase_table=table)` →
   `FactorInputs(..., restricted=restricted, aum_delta_pct=aum_delta_pct)`.
7. **No scoring change.** `heat_score(restricted=..., aum_delta_pct=...)` already exists
   (`factor_maps.py:15`); with `aum_delta_pct=None` it reduces to: `restricted` → `−0.5`
   (crowded), else `+0.3` (calm), `None` restriction → `None` (N/A). The existing function
   already handles the AUM-`None` case.
8. After this slice: heat lights for all 10 funds (when the table is reachable & the id parses);
   AUM-Δ sharpening (`−1.0`) explicitly deferred.

## AUM-Δ deferral (§5, known gap, not a risk)

`ak.fund_scale_change_em()` is an *aggregate-market* table (基金家数 / total 期末净资产), not
per-fund; per-fund AUM is a single latest point with no QoQ series. So `aum_delta_pct` ships
`None` and the overheated `−1.0` tier cannot fire yet. Out of scope for this slice.

## Invariants preserved (§6)

- Heat stays behind `eligible_factors(profile)`.
- `heat_no_data` is in `KNOWN_NA_REASONS` → recompute matches; no `caveated`/`gated` regression.
- Determinism: for a given purchase table, parsing is pure → identical heat scores.

## Tests (TDD, §8)

- **Pure (no mocks):** `parse_purchase_status` — 开放申购 → not restricted; 暂停/限购 状态 or
  cap < 1e8 → restricted; fund absent / unparseable row → `None`. `heat_inputs_for` always
  returns `aum_delta_pct=None`. Column-name tolerance: unexpected shape degrades to `None`
  (→ `heat_no_data`), never a wrong score.
- **Integration (cached fixtures):** monitor run over fixture DuckDB + a **fixture purchase
  table** → expected `heat` FactorScores per profile; a `None` table → `heat_no_data` for all.
- **Live (double-gated, `live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`):** one `ak.fund_purchase_em()`
  call — asserts the table is reachable and the 10 ids parse; asserts graceful `None` on a
  missing id.
- **Determinism:** eval recompute over produced `eval_trace.json` still PASS.

## Risk (spec §10)

`fund_purchase_em` schema drift — parsing is column-name-tolerant and degrades to `None`
(→ `heat_no_data`) on an unexpected shape, never a wrong score.

## Module layout

```
src/irc/monitor/heat_fetch.py   # NEW edge: fetch_purchase_table (1 akshare call) + pure parse_purchase_status / heat_inputs_for
src/irc/commands/monitor_cmd.py # EDIT ~578: fetch table once + feed restricted/aum_delta_pct per fund
```
