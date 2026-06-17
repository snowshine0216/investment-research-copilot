Verdict: PASS

Subagent: sonnet / Source: /verify (integrated) / Entry point exercised / Cross-item flow observed (valuation index + lookthrough + heat coexist; gold/qdii_global eligibility intact) / Failures: 0

## Branch / HEAD

- Branch: monitor-valuation-heat-wiring
- HEAD: a150b24 (docs sync commit; all 3 slice PRs squashed to main via #163/#164/#165)

## Integrated direct exercise

Single Python script seeded a tmp DuckDB with:
- `instruments` row for index fund `000300` (tracked_index='csi300') + 200-row `index_valuation_history` (PE ramps 8→60)
- `instruments` row for active fund `110011` (tracked_index=None) + `ActiveFundSnapshot` written via `write_active_fund_cache` + 200-row `stock_valuation_history` for holding `600000` (PE ramps 8→50)
- Fixture purchase table: `110011` with `申购状态=暂停申购`

### Results

**Slice 1 — index-path valuation (000300 / csi300):**
`resolve_valuation_state` → `state='very_expensive'  cached=True  reason=None`

**Slice 2 — look-through valuation (110011 / active fund):**
`resolve_valuation_state` → `state='very_expensive'  cached=True  reason=None`
(loaded snapshot from `write_active_fund_cache`, matched `600000` in `stock_valuation_history`)

**Slice 3 — heat restriction leg (110011):**
`heat_inputs_for("110011", purchase_table=df)` → `(True, None)`

**Integrated `build_factor_scores` — active_cn_equity profile:**
```
trend                ELIGIBLE  value=0.372
valuation            ELIGIBLE  value=-1.0
heat                 ELIGIBLE  value=-0.5
macro_tilt           N/A (macro_insufficient_families)
constituent          N/A (constituent_no_coverage)
```

**Eligibility gate — gold profile:**
`valuation → profile_ineligible` ✅

**Eligibility gate — qdii_global profile:**
`valuation → profile_ineligible` ✅

All assertions passed.

## Unit test surface

```
uv run pytest tests/monitor/test_valuation.py tests/monitor/test_lookthrough.py \
  tests/monitor/test_heat_fetch.py tests/commands/test_monitor_cmd_heat.py \
  tests/evals/test_monitor_signal_runner.py tests/evals/test_monitor_signal_metrics.py -q
76 passed in 0.70s
```

## CLI wiring

```
uv run irc monitor --help  →  Usage: irc monitor [OPTIONS] COMMAND [ARGS]...  ✅
integrated imports OK  ✅
```
