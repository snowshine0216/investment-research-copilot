# Design — Monitor per-stock valuation + capital-flow drill-down → grounded bias

**Date:** 2026-06-18
**Status:** Approved (brainstorming) — pending spec review
**Surface:** `irc monitor`
**Supersedes/extends:** builds on #166 (valuation + heat factors) and ADR 0017 (monitor evidence isolation), ADR 0018 (weights in `profiles.py`).

## 1. Problem

`irc monitor` produces a per-fund directional bias (`ADD_BIAS` / `NEUTRAL` / `REDUCE_BIAS`) from a 5-factor composite. Two gaps:

1. **No per-stock analysis is surfaced.** The valuation factor already loads per-constituent PE/PB (cached `stock_valuation_history` via `_stock_series_by_code`) but *collapses* it into one fund-level percentile and throws the per-stock detail away. The user cannot see *which* holdings make a fund cheap/expensive.
2. **No capital-flow signal exists.** The only "crowding" input is the restriction leg (`fund_purchase_em`). There is no stock-level capital-flow data anywhere in the codebase.

**Goal:** ground each fund's bias in the *bottom-up* facts — the top holdings' valuation (PB/PE) **and** main-money net inflow — and make that drill-down legible in a report, so that `ADD_BIAS` reads as a better-justified "buy lean" (cheap + inflow) and `REDUCE_BIAS` as a "sell lean" (expensive + outflow). The #156 framing ("a research lean, not a buy/sell order") is **retained** — we strengthen the grounding, not the claim.

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|---|
| D1 | **Both surfaces.** Flow + per-stock valuation (a) drive the bias *and* (b) render a per-fund drill-down report. Plus an eval. |
| D2 | **Drive the bias** by adding a dedicated `flow` factor — NOT folded into `heat` (heat/crowding is *bearish* on inflow; flow must be *bullish* on inflow — opposite sign). |
| D3 | **Flow signal = 主力净流入净占比** (main-money net-inflow % of turnover), 5d & 20d windows, via `ak.stock_individual_fund_flow`. A-share only. |
| D4 | **Report = per-fund drill-down** (top-5 holdings board + roll-up to bias), embedded in the brief *and* written as a standalone `drilldown.html`. |
| D5 | **Aggregation = holding-weight-weighted, renormalized over covered top holdings**: `flow_value = Σ(wᵢ·sᵢ) / Σ(wᵢ)`. Bigger positions dominate; result stays on the full [−1,+1] scale. |
| D6 | **Coverage floor 0.50.** If covered top-holding weight / total top-holding weight < 0.50 → `flow_no_coverage` (honest N/A), mirroring the valuation factor's 0.50 covered-NAV gate. |
| D7 | **Flow thresholds (净占比 → score):** `≥ +3% → +1.0`, `+1…+3% → +0.5`, `−1…+1% → 0.0`, `−3…−1% → −0.5`, `≤ −3% → −1.0`. |
| D8 | **Weights (`active_cn_equity`):** trend `.25`, valuation `.20`, **flow `.15`**, heat `.10`, macro_tilt `.15`, constituent `.15`. Other profiles unchanged. |

## 3. Scope

- **In:** the 7 `active_cn_equity` funds (519069, 260112, 006533, 000083, 519770, 018132, 161903). Flow + per-stock board apply to these (look-through holdings are A-shares).
- **Out (N/A by profile):** gold (008986), qdii_global (270023), qdii_china_us_internet (009225) — no A-share constituents → `flow` is `profile_ineligible` (no weight allocated, no board). Their weight vectors and biases are untouched.
- **Out of scope:** Northbound (北向) flow (stock-level daily disclosure discontinued by exchanges Aug 2024); per-fund AUM-Δ (still no live QoQ source — unchanged from #166); intraday flow.

## 4. Architecture

```
ActiveFundSnapshot (cached)  ─┐
  top-5 holdings by weight    │
stock_valuation_history (DB) ─┼─▶ holding_metrics.py (PURE)
  PE/PB per code              │     per-stock HoldingMetric[] (PE/PB/pct + flow windows + flow score)
fund_flow/<date>.json (cache)─┘     + FlowAggregate (Σwᵢsᵢ/Σwᵢ over covered, coverage gate)
        ▲                                   │
flow_fetch.py (EDGE, one fetch/run,         ├─▶ factors._flow → FactorScore → compute_signal → bias
  cached per day; never raises)             ├─▶ render_drilldown.py → board + roll-up (card + drilldown.html)
                                            └─▶ eval/trace.py → holding_metrics block (schema 3) → determinism + coverage + reconciliation evals
```

The pure core (`holding_metrics`, `factor_maps.flow_score`, `factors._flow`, renderers) takes already-loaded inputs. The only effects are `flow_fetch` (network, edge) and the cached DuckDB reads the valuation path already does.

## 5. Components

### 5.A `flow_fetch.py` (EDGE + pure parse) — Slice 1
Mirrors `heat_fetch.py`'s contract: never raises, degrades to None.

- `fetch_flow_series(symbols, *, cache_dir, today, fetch=None) -> dict[str, pd.DataFrame|None]`
  - For each unique 6-digit A-share symbol: load from per-day cache `data/monitor/fund_flow/<today>.json` if present; else `ak.stock_individual_fund_flow(stock=symbol, market=_market_of(symbol))`, parse to a `{date, main_net_pct}` series, cache it. CN endpoint stays **DIRECT** (no `IRC_HTTPS_PROXY`) per the project proxy rule.
  - `_market_of(symbol)`: `6*`→`sh`, `0*/3*`→`sz`, `8*/4*`→`bj`. Non-A-share symbols (HK/US lines) are skipped → never fetched → no series → uncovered.
  - One `try/except` per symbol → miss yields `None` (→ `flow_no_data` for that stock). A whole-market akshare outage degrades every stock to N/A, never a wrong number.
- `parse_main_net_pct(df) -> tuple[tuple[str, float], ...]`: pure; extracts `(date, 主力净流入-净占比)` rows, column-name-tolerant (unexpected shape → empty → N/A, never a fabricated value).

Caching is **idempotent within a day** so `--resume` and the standalone `drilldown.html` re-render never re-fetch. ~15–25 unique symbols/run (deduped across the 7 funds). Free endpoint → no spend-gate impact.

### 5.B `holding_metrics.py` (PURE) — Slice 1
- `HoldingMetric` (frozen): `symbol, name, weight_pct, pe, pb, pe_percentile, valuation_state, flow_pct_5d, flow_pct_20d, flow_score, flow_reason`.
- `FlowAggregate` (frozen): `value: float|None, reason: str|None, covered_weight_ratio: float`.
- `per_stock_metrics(top_holdings, series_by_code, flow_series_by_code) -> tuple[HoldingMetric, ...]`:
  - PE/PB/percentile/state per code reuse the opportunity `MetricSeries` already loaded for valuation — **no new valuation fetch**.
  - `flow_pct_5d` / `flow_pct_20d` = mean of the last 5 / last 20 daily 主力净占比 rows (pure). Blended `flow_pct = 0.4·5d + 0.6·20d` (steadier 20d favored; blend weights are named constants).
  - `flow_score = flow_band(flow_pct)` (D7). Missing series → `flow_score=None, flow_reason="flow_no_data"`.
- `aggregate_flow(metrics) -> FlowAggregate`: `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over holdings with a non-None `flow_score`; `covered_weight_ratio = Σ covered wᵢ / Σ all top-holding wᵢ`. **Zero covered holdings** (nothing fetched) → `value=None, reason="flow_no_data"`. **Covered but ratio < `_COVERAGE_FLOOR (0.50)`** → `value=None, reason="flow_no_coverage"`. Else `value=Σwᵢsᵢ/Σwᵢ, reason=None`. (`_flow` in §5.C maps each reason to its matching N/A.)

### 5.C Flow factor + scoring — Slice 3
- `factor_maps.flow_score(flow_pct) -> float|None`: D7 bands as a pure step function; constants `_FLOW_BANDS`.
- `factors.py`: `FactorInputs` gains `flow: FlowAggregate | None`. New `_flow(profile, inp)`:
  - `"flow" not in eligible_factors(profile)` → `_na("flow", _NA_PROFILE_INELIGIBLE)`.
  - `inp.flow is None or inp.flow.reason == "flow_no_data"` (no covered holdings had data) → `_na("flow", _NA_FLOW_NO_DATA)`.
  - `inp.flow.value is None` (below coverage floor) → `_na("flow", _NA_FLOW_NO_COVERAGE)`.
  - else `FactorScore("flow", inp.flow.value, True, "", 1.0)`.
  - Add `_NA_FLOW_NO_DATA = "flow_no_data"`, `_NA_FLOW_NO_COVERAGE = "flow_no_coverage"` to the `_NA_*` constants and `KNOWN_NA_REASONS`. `build_factor_scores` appends `_flow(...)` (6 factors now).
- `profiles.py`: add `"flow"` to `active_cn_equity.eligible`; set the D8 weight vector. **A profile never allocates weight to a factor it can't structurally fill** (invariant kept) — flow weight exists only on `active_cn_equity`.
- `signal.py`: `_FAMILY_OF["flow"] = "capital-flow"` (new family → richer `present_families`, helps clear `_MIN_FAMILIES`). Add divergence code **`valuation_flow_conflict`**: cheap valuation (`v ≥ _DIVERGE`) with outflow (`f ≤ −_DIVERGE`), or expensive (`v ≤ −_DIVERGE`) with inflow (`f ≥ _DIVERGE`) — the central honesty check on the "buy/sell" thesis.
- `render_factors.CANONICAL_FACTOR_ORDER` → `("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")`.
- `compute_signal` is **unchanged** — the new factor flows through automatically (renorm weights, composite, bands → bias).

### 5.D Report — Slice 2
- `render_drilldown.py` (PURE):
  - `holdings_board_html(metrics)`: a table — `# · symbol · name · weight% · PB · PE · PE-pct · 估值 state · 5d净占比 · 20d净占比 · flow score`. N/A cells show `—` + reason. Rows sorted by weight desc.
  - `flow_rollup_html(metrics, agg, signal)`: the reconciliation line — `flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ) = <value> (covered <ratio>%)`, then how `valuation` + `flow` contributions land in `C` → bias. This is the "dig to the bottom" methodology made explicit.
  - `drilldown_page_html(views)`: full-page wrapper for the standalone artifact (reuses the board + roll-up components, shared CSS).
- `render_types.FundView` gains `holding_metrics: tuple[HoldingMetric, ...]`.
- `render_html._card` embeds `holdings_board_html` + `flow_rollup_html` for funds that have metrics (after the factor table). Add flow badge/CSS; extend `_EXPLAINER` to name the flow leg (估值 + 资金流 → 倾向; still 非买卖指令).
- `monitor_cmd.run_monitor` writes `outputs/<date>/monitor/drilldown.html` (atomic `.tmp.{pid}→os.replace`).

### 5.E Eval — Slice 4
- `eval/trace.py`: bump `_SCHEMA_VERSION` `"2" → "3"`; add a `holding_metrics` block per fund (the board rows + `FlowAggregate`). The `flow` factor appears in `factor_scores`/`signal.contributions` automatically.
- **Determinism** (`eval/determinism.py`): flow factor + `holding_metrics` reproduce identically on cached re-run; recognize the new factor name and N/A reasons (it already imports `KNOWN_NA_REASONS`).
- **Coverage/health** (free, in `eval monitor_signal`): per-fund flow coverage % and PE/PB coverage %, plus `flow_no_data`/`flow_no_coverage` tallies — so you see exactly where the drill-down has data.
- **Reconciliation oracle** (`eval/structural.py`): assert the board's per-stock `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over covered rows equals the `flow` factor value (to 4dp) — proves the methodology is *correct*, not merely displayed.
- **Predictive** (existing M3 forward scorer): no new code — the newly-grounded bias automatically enters `forward_ledger.jsonl`; the forward scorer measures whether `ADD_BIAS`/`REDUCE_BIAS` now predict forward returns. The ultimate test of "does flow make add-bias behave like a buy signal."

### 5.F Versioning
- Bump `_ENGINE_VERSION` `"1" → "2"` in `monitor_cmd.py`: the composite/bias semantics change (new factor + reweight), so the forward scorer must not blend pre-flow and post-flow biases under one engine id. (Open for review — see §8.)

## 6. Invariants & constraints (must hold)

- **ADR 0017 evidence isolation:** flow data is the monitor's OWN cache (`data/monitor/fund_flow/`); no opportunity output files read; pure core, effects at edges.
- **Determinism + badges:** new N/A reasons (`flow_no_data`, `flow_no_coverage`) are `KNOWN_NA_REASONS` members → they do **not** trip a WARN/FAIL → `apply_eval_gate` does not caveat a fund merely for missing flow (consistent with how valuation/heat N/A behaves).
- **No silent caps:** the board logs/notes when a holding is uncovered and why; coverage-floor N/A is surfaced, never silently treated as 0.
- **Size budget:** new modules < 200 lines; functions < 20. `monitor_cmd.py` is already 672 lines — the flow-input assembly goes in `holding_metrics.py`, not inline, to avoid growing the command further.
- **Framing:** bias stays "研究参考信号，非买卖指令" (#156). The drill-down explains the lean; it does not issue orders.

## 7. Slice plan (TDD, red→green→refactor each)

1. **Data layer** — `flow_fetch.py` (edge + cache) + `holding_metrics.py` (pure metrics + aggregate + coverage gate). No bias impact. Tests: parse tolerance, window means, aggregation math, coverage floor, market-prefix routing.
2. **Report** — `render_drilldown.py` + `FundView.holding_metrics` + `monitor_cmd` wiring to build metrics and write `drilldown.html` + embed in card. *You see the data before it moves any bias.* Tests: board rows, N/A rendering, roll-up reconciliation, standalone page.
3. **Flow factor → bias** — `factor_maps.flow_score`, `factors._flow` + `FactorInputs.flow`, `profiles` eligible+weights, `signal` family + `valuation_flow_conflict`, `CANONICAL_FACTOR_ORDER`. Tests: bands, eligibility per profile, N/A reasons, renorm/composite, divergence, weight-vector sums to 1.0.
4. **Eval** — trace schema 2→3 + `holding_metrics` block, determinism recognition, coverage health, reconciliation oracle, engine_version bump. Tests: schema shape, determinism re-run, reconciliation equality.

Ship as one feature branch (matches #166's multi-slice single-PR pattern).

## 8. Open questions / for review

- **§5.F engine_version bump** — bump to `"2"` (recommended, keeps forward-eval honest) vs stay `"1"` (preserves a continuous forward-ledger series across the change). Confirm on review.
- Flow blend weights (`0.4·5d + 0.6·20d`) and the coverage floor (`0.50`) are named constants; promote to `config/monitor.yaml` only if you later want to tune them per-run.

## 9. Out of scope (YAGNI)

Northbound flow; AUM-Δ heat leg; a standalone `irc stock-screen` CLI command (the cross-fund Ranked Stock Board) — the per-fund drill-down covers the stated need; a cross-fund board can be a later spec if wanted; intraday/real-time flow; flow for non-A-share (QDII) lines.
