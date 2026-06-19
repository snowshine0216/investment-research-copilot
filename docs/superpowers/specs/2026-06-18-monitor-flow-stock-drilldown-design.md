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
| D3 | **Flow signal = 主力净流入净占比** (main-money net-inflow % of turnover), 5d & 20d windows, via `ak.stock_individual_fund_flow`. A-share only. **Unit = percent-points** (akshare parses the EastMoney column via `pd.to_numeric` with NO `/100`; `12.34` means 12.34%). All flow_pct fields, bands, and tests are in percent-points — never ratio. |
| D4 | **Report = per-fund drill-down** (top-5 holdings board + roll-up to bias), embedded in the brief *and* written as a standalone `drilldown.html`. |
| D5 | **Aggregation = holding-weight-weighted, renormalized over covered top holdings**: `flow_value = Σ(wᵢ·sᵢ) / Σ(wᵢ)`. Bigger positions dominate; result stays on the full [−1,+1] scale. |
| D6 | **Coverage floor 0.50.** If covered top-holding weight / total top-holding weight < 0.50 → `flow_no_coverage` (honest N/A), mirroring the valuation factor's 0.50 covered-NAV gate. |
| D7 | **Flow thresholds (净占比 → score), percent-point units:** `flow_pct ≥ 3.0 → +1.0`, `1.0…3.0 → +0.5`, `−1.0…1.0 → 0.0`, `−3.0…−1.0 → −0.5`, `≤ −3.0 → −1.0`. (A ratio-unit value like `0.03` lands in the `−1.0…1.0` deadband → `0.0`, the canary for a 100× inversion.) |
| D8 | **Weights (`active_cn_equity`):** trend `.25`, valuation `.20`, **flow `.15`**, heat `.10`, macro_tilt `.15`, constituent `.15`. Other profiles unchanged. |

## 3. Scope

- **In:** the 7 `active_cn_equity` funds (519069, 260112, 006533, 000083, 519770, 018132, 161903). Flow + per-stock board apply to these (look-through holdings are A-shares). **Note `018132`** (博时中证有色金属矿业主题指数A) is an *index-tracking* product on the `active_cn_equity` profile: its valuation resolves via the index branch (`_resolve_index`), and its look-through holdings may be absent/partial → flow legitimately degrades to `flow_no_coverage`/`flow_no_data` (honest N/A, not a bug). Index-profiled active funds showing flow N/A is expected.
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
flow_fetch.py (EDGE, ~15-25 calls/run        ├─▶ factors._flow → FactorScore → compute_signal → bias
  = one call/A-share symbol, cached/day;     ├─▶ render_drilldown.py → board + roll-up (card + drilldown.html)
  never raises)                              └─▶ eval/trace.py → holding_metrics block (schema 3) → determinism + coverage + reconciliation evals
```

The pure core (`holding_metrics`, `factor_maps.flow_score`, `factors._flow`, renderers) takes already-loaded inputs. The only effects are `flow_fetch` (network, edge) and the cached DuckDB reads the valuation path already does. **Fetch cost** (corrects the diagram vs. `heat_fetch`): unlike `fund_purchase_em` (one market-wide call), `stock_individual_fund_flow` has no batch variant — flow is ~15-25 **sequential** per-symbol CN calls/run (deduped, cached per day). Free endpoint (no spend gate), but add light pacing between calls given prior akshare/CN rate-limit exposure (cf. legulegu rate-limiting in project history); a rate-limited symbol degrades to `flow_no_data`, never a crash.

## 5. Components

### 5.A `flow_fetch.py` (EDGE + pure parse) — Slice 1
Mirrors `heat_fetch.py`'s contract: never raises, degrades to None. The in-memory type is **parsed rows, never a DataFrame** (so the on-disk form is byte-stable).

- `FlowSeries` = `tuple[tuple[str, float], ...]` — `(date_iso, main_net_pct)` rows, **percent-point units** (D3), sorted ascending by date.
- `fetch_flow_series(symbols, *, cache_dir, today, fetch=None) -> dict[str, FlowSeries | None]`
  - For each unique 6-digit A-share symbol: load from the per-day cache if present; else `ak.stock_individual_fund_flow(stock=symbol, market=_market_of(symbol))`, run `parse_main_net_pct`, then write the cache. CN endpoint stays **DIRECT** (no `IRC_HTTPS_PROXY`) per the project proxy rule.
  - `_market_of(symbol)`: `6*`→`sh`, `0*/3*`→`sz`, `8*/4*`→`bj`. Non-A-share symbols (HK/US lines) are skipped → never fetched → `None` → uncovered.
  - One `try/except` per symbol → fetch failure yields `None` (→ `flow_no_data`). A whole-market akshare outage degrades every stock to N/A, never a wrong number.
- `parse_main_net_pct(df) -> FlowSeries`: pure; extracts `(date, 主力净流入-净占比)` rows, column-name-tolerant; rows with a non-numeric/NaN 净占比 are dropped (unexpected shape → empty → N/A, never a fabricated value). No `/100` (units are already percent-points).
- **Cache schema** (`data/monitor/fund_flow/<today>.json`) — explicit, deterministic, miss-recording:
  ```json
  {
    "<symbol>": {"status": "ok",   "rows": [{"date": "2026-06-17", "main_net_pct": 1.23}, ...]},
    "<symbol>": {"status": "miss", "rows": []}
  }
  ```
  Symbols sorted; each `rows` array sorted ascending by `date`; `main_net_pct` rounded to 4dp. `status:"miss"` records a confirmed fetch failure so a re-run does not re-hit a dead symbol (and re-renders are stable). The loader maps `"ok"`→`FlowSeries`, `"miss"`→`None`.

Caching is **idempotent within a day** so `--resume` and the standalone `drilldown.html` re-render never re-fetch. ~15–25 unique symbols/run (deduped across the 7 funds). Free endpoint → no spend-gate impact.

### 5.B `holding_metrics.py` (PURE) — Slice 1
- `HoldingMetric` (frozen): `symbol, name, weight_pct, pe, pb, pe_percentile, valuation_state, valuation_reason, flow_pct_5d, flow_pct_20d, flow_score, flow_reason`. (`valuation_reason` ∈ {`None`, `pe_not_positive`, `pe_immature`, `no_series`}; `flow_reason` ∈ {`None`, `flow_no_data`}.)
- `FlowAggregate` (frozen): `value: float|None, reason: str|None, covered_weight_ratio: float`.
- `per_stock_metrics(top_holdings, series_by_code, flow_series_by_code) -> tuple[HoldingMetric, ...]`:
  - **Valuation (per-stock — a NEW computation, distinct from the fund aggregate).** `fund_valuation_percentile` returns only fund-level `MetricCoverage`; it does NOT expose per-stock percentile/state. So `per_stock_valuation(code, MetricSeries)` is defined here, reusing the *same primitives* the fund path uses (no new fetch — it consumes the `MetricSeries.points` already loaded for the valuation factor):
    - `pe` / `pb` = the **latest** point's value (most recent date with a non-null value for that metric), shown raw even when negative/zero.
    - `pe_percentile` = `self_history_percentile` over the code's own **strictly-positive** PE sub-series, gated by `_pe_series_is_mature` (the 120/180-day maturity gate). Immature history OR no positive PE point → `pe_percentile=None`.
    - `valuation_state` = `percentile_to_valuation_state(pe_percentile)` → `None` when percentile is `None`. **Negative/zero PE** ⇒ no positive metric ⇒ percentile `None` ⇒ state `None` (board shows the raw negative PE with state `—`, reason `pe_not_positive` / `pe_immature`). PB is reported raw (no percentile) as context only.
    - This per-stock percentile is each stock vs. **its own** history — it is NOT and need not equal the fund-aggregate percentile (which is a portfolio-earnings-yield series); the two answer different questions and both appear in the report.
  - `flow_pct_5d` / `flow_pct_20d` = mean of the last 5 / last 20 daily 主力净占比 rows, **percent-points** (pure). Blended `flow_pct = 0.4·5d + 0.6·20d` (steadier 20d favored; blend weights are named constants). A series with <5 (resp. <20) rows uses what it has; an empty series → `None`.
  - `flow_score = flow_band(flow_pct)` (D7, percent-point bands). `None` series → `flow_score=None, flow_reason="flow_no_data"`.
- `aggregate_flow(metrics) -> FlowAggregate`: `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over holdings with a non-None `flow_score`; `covered_weight_ratio = Σ covered wᵢ / Σ all top-holding wᵢ`. **Zero covered holdings** (nothing fetched) → `value=None, reason="flow_no_data"`. **Covered but ratio < `_COVERAGE_FLOOR (0.50)`** → `value=None, reason="flow_no_coverage"`. Else `value=Σwᵢsᵢ/Σwᵢ, reason=None`. (`_flow` in §5.C maps each reason to its matching N/A.)

### 5.C Flow factor + scoring — Slice 3
- `factor_maps.flow_score(flow_pct) -> float|None`: D7 bands as a pure step function; constants `_FLOW_BANDS`.
- `factors.py`: `FactorInputs` gains **`flow: FlowAggregate | None = None`** — trailing AND defaulted. This is mandatory: `FactorInputs` is constructed without a flow leg in production at `eval/backtest.py:33` (the M0 evidence-free composite — retro backtest has no flow data and must stay flow-N/A) and in 4 test sites; a non-defaulted field breaks them. New `_flow(profile, inp)`:
  - `"flow" not in eligible_factors(profile)` → `_na("flow", _NA_PROFILE_INELIGIBLE)`.
  - `inp.flow is None or inp.flow.reason == "flow_no_data"` (no covered holdings had data) → `_na("flow", _NA_FLOW_NO_DATA)`.
  - `inp.flow.value is None` (below coverage floor) → `_na("flow", _NA_FLOW_NO_COVERAGE)`.
  - else `FactorScore("flow", inp.flow.value, True, "", 1.0)`.
  - Add `_NA_FLOW_NO_DATA = "flow_no_data"`, `_NA_FLOW_NO_COVERAGE = "flow_no_coverage"` to the `_NA_*` constants and `KNOWN_NA_REASONS`. `build_factor_scores` appends `_flow(...)` (6 factors now).
- `profiles.py`: add `"flow"` to `active_cn_equity.eligible`; set the D8 weight vector. **A profile never allocates weight to a factor it can't structurally fill** (invariant kept) — flow weight exists only on `active_cn_equity`.
- `signal.py`: `_FAMILY_OF["flow"] = "capital-flow"` (new family → richer `present_families`, helps clear `_MIN_FAMILIES`). Add divergence code **`valuation_flow_conflict`**: cheap valuation (`v ≥ _DIVERGE`) with outflow (`f ≤ −_DIVERGE`), or expensive (`v ≤ −_DIVERGE`) with inflow (`f ≥ _DIVERGE`) — the central honesty check on the "buy/sell" thesis. **Also update the parallel test oracle `tests/monitor/_oracle.py:13` `_FAMILY_OF`** (a second copy; `gate_predicate_ok` does a bare `_FAMILY_OF[name]` lookup → `KeyError` on a present flow factor if not updated — the project's "test-scope on signature changes" trap).
- `render_factors.CANONICAL_FACTOR_ORDER` → `("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")`.
- `compute_signal` is **unchanged** — the new factor flows through automatically (renorm weights, composite, bands → bias).

### 5.D Report — Slice 2
- `render_drilldown.py` (PURE):
  - `holdings_board_html(metrics)`: a table — `# · symbol · name · weight% · PB · PE · PE-pct · 估值 state · 5d净占比 · 20d净占比 · flow score`. N/A cells show `—` + reason. Rows sorted by weight desc.
  - `flow_rollup_html(metrics, agg, signal)`: the reconciliation line — `flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ) = <value> (covered <ratio>%)`, then how `valuation` + `flow` contributions land in `C` → bias. This is the "dig to the bottom" methodology made explicit.
  - `drilldown_page_html(views)`: full-page wrapper for the standalone artifact (reuses the board + roll-up components, shared CSS).
- `render_factors._DIVERGENCE_CAVEATS` gains `"valuation_flow_conflict": "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入"` — without it `divergence_caveat` falls through to `escape(code)` and the user sees the raw English code, inconsistent with the other three caveats and the "legible methodology" goal.
- `render_types.FundView` gains `holding_metrics: tuple[HoldingMetric, ...]`.
- `render_html._card` embeds `holdings_board_html` + `flow_rollup_html` for funds that have metrics (after the factor table). Add flow badge/CSS; extend `_EXPLAINER` to name the flow leg (估值 + 资金流 → 倾向; still 非买卖指令).
- `monitor_cmd.run_monitor` writes `outputs/<date>/monitor/drilldown.html` (atomic `.tmp.{pid}→os.replace`).

### 5.E Eval — Slice 4
- `eval/trace.py`: bump `_SCHEMA_VERSION` `"2" → "3"`; add a `holding_metrics` block per fund (the board rows + `FlowAggregate`). The `flow` factor appears in `factor_scores`/`signal.contributions` automatically.
- **Determinism** (`eval/determinism.py`): flow factor + `holding_metrics` reproduce identically on cached re-run; recognize the new factor name and N/A reasons (it already imports `KNOWN_NA_REASONS`).
- **Coverage/health** (free, in `eval monitor_signal`): per-fund flow coverage % and PE/PB coverage %, plus `flow_no_data`/`flow_no_coverage` tallies — so you see exactly where the drill-down has data.
- **Reconciliation oracle** (`eval/structural.py`): assert the board's per-stock `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over covered rows equals the `flow` factor value (to 4dp) — proves the methodology is *correct*, not merely displayed.
- **Predictive — forward-eval population isolation (REQUIRED, not free).** The new factor + reweight change the bias semantics, so v1 (pre-flow) and v2 (post-flow) ledger rows must NOT be pooled into one metric. Today nothing reads `manifest_versions.engine`: `runner.py` passes every parsed ledger row to `score_forward`, and `score_forward`/`prefilter_ledger` ignore the field. The engine bump (§5.F) is **necessary but not sufficient**; this contract makes it effective:
  - `score_forward(..., target_engine: str | None = None)`: when `target_engine` is set, a row whose `manifest_versions.engine != target_engine` is excluded **before** the maturity join and counted under a new exclusion reason `engine_mismatch` in the returned `excl` dict. (Rows missing the field count as a sentinel `"0"`/legacy engine — also excluded when a target is set.)
  - `runner.py`: compute `target_engine = _target_engine(ledger)` = the **max engine version present** in the ledger — compared **numerically** (`max(versions, key=int)`), NOT lexicographically, so a future `"10"` beats `"9"` (harmless at `"1"→"2"` but a latent trap if string-compared). Deterministic, self-configuring — no external config; a deliberate rollback is out of scope. Pass it to `score_forward`, and write the per-engine excluded counts into `details.json` alongside the existing `forward_excluded` key (new `excluded_by_engine`). Headline metrics are then computed on the target-engine population only.
  - **Tests:** a ledger mixing engine `"1"` and `"2"` rows → only `"2"` rows reach `forward_rows`; `excl["engine_mismatch"]` equals the `"1"`-row count; `details.json.excluded_by_engine` reports it. A single-engine ledger is unaffected (back-compat: `target_engine=None` preserves today's no-filter behavior).
  - Once isolated, the forward scorer measures whether v2 `ADD_BIAS`/`REDUCE_BIAS` predict forward returns — the ultimate test of "does flow make add-bias behave like a buy signal."

### 5.F Versioning
- Bump `_ENGINE_VERSION` `"1" → "2"` in `monitor_cmd.py` (**mandatory**): the composite/bias semantics change (new factor + reweight). This tags new ledger rows so the §5.E `target_engine` filter can isolate them. The bump **alone is not sufficient** — without the §5.E reader/runner filter, the tag is never read and populations still pool. Both ship together in Slice 4.

## 6. Invariants & constraints (must hold)

- **ADR 0017 evidence isolation:** flow data is the monitor's OWN cache (`data/monitor/fund_flow/`); no opportunity output files read; pure core, effects at edges.
- **Determinism + badges:** new N/A reasons (`flow_no_data`, `flow_no_coverage`) are `KNOWN_NA_REASONS` members → they do **not** trip a WARN/FAIL → `apply_eval_gate` does not caveat a fund merely for missing flow (consistent with how valuation/heat N/A behaves).
- **No silent caps:** the board logs/notes when a holding is uncovered and why; coverage-floor N/A is surfaced, never silently treated as 0.
- **Size budget:** new modules < 200 lines; functions < 20. `monitor_cmd.py` is already 672 lines — the flow-input assembly goes in `holding_metrics.py`, not inline, to avoid growing the command further.
- **Framing:** bias stays "研究参考信号，非买卖指令" (#156). The drill-down explains the lean; it does not issue orders.

## 7. Slice plan (TDD, red→green→refactor each)

1. **Data layer** — `flow_fetch.py` (edge + cache, parsed-row JSON schema §5.A) + `holding_metrics.py` (pure: per-stock valuation §5.B + flow windows + aggregate + coverage gate). No bias impact. Tests: parse tolerance, **flow-unit boundaries at `1.0`, `3.0`, `0.01`, `0.03`** (percent-point vs ratio canary), cache round-trip (ok + miss records, sorted/4dp), window means with short series, per-stock percentile maturity gate + negative/zero-PE → state `None`, aggregation math, coverage floor, market-prefix routing.
2. **Report** — `render_drilldown.py` + `FundView.holding_metrics` + `monitor_cmd` wiring to build metrics and write `drilldown.html` + embed in card. *You see the data before it moves any bias.* Tests: board rows, N/A rendering (incl. `pe_not_positive`/`pe_immature`), roll-up reconciliation, standalone page.
3. **Flow factor → bias** — `factor_maps.flow_score`, `factors._flow` + `FactorInputs.flow`, `profiles` eligible+weights, `signal` family + `valuation_flow_conflict`, `CANONICAL_FACTOR_ORDER`. Tests: bands (percent-point), eligibility per profile, N/A reasons (`flow_no_data` vs `flow_no_coverage`), renorm/composite, divergence, weight-vector sums to 1.0.
4. **Eval + versioning** — trace schema 2→3 + `holding_metrics` block, determinism recognition, coverage health, reconciliation oracle, **engine_version bump `1→2` + `score_forward(target_engine=…)` filter + `runner._target_engine` + `details.json.excluded_by_engine` (§5.E/§5.F)**. Tests: schema shape, determinism re-run, reconciliation equality, **mixed-engine ledger → only target-engine rows scored + `engine_mismatch` count correct + single-engine back-compat**.

Ship as one feature branch (matches #166's multi-slice single-PR pattern).

### 7.1 Locked tests that MUST be updated (exact-equality assertions — review #2, P0)

Adding the `flow` factor, two N/A reasons, and the schema bump trips these locked tests. Under TDD each is a deliberate red→green update — naming them prevents an implementer from "preserving" an assertion that is supposed to change:

| Test | Asserts today | Update (slice) |
|---|---|---|
| `tests/monitor/test_known_na_reasons.py` (`_EXPECTED` + the "eight codes" test) | `KNOWN_NA_REASONS` == exactly 8 codes | add `flow_no_data`, `flow_no_coverage` → 10 (slice 3) |
| `tests/monitor/test_profiles.py::test_active_cn_equity_full_vector` | eligible == exactly the 5 | add `flow` → 6 (slice 3) |
| `tests/monitor/test_render_factors.py::test_canonical_order_is_locked` | `CANONICAL_FACTOR_ORDER` == the 5-tuple | insert `flow` after `valuation` → 6-tuple (slice 3) |
| `tests/monitor/_oracle.py::_FAMILY_OF` (test oracle, not a test but consumed by oracle tests) | 5 factor→family entries | add `flow → capital-flow` (slice 3) |
| `tests/monitor/test_acceptance_eval.py:79` | `trace["schema_version"] == "2"` | → `"3"` (slice 4) |
| `tests/monitor/eval/test_trace.py::test_schema_version_is_2` | `== "2"` | → `"3"` (rename + value, slice 4) |

Plus regression-check (no change expected, but run them): the 5 `FactorInputs(` construction sites (`eval/backtest.py`, `tests/monitor/test_factors.py`, `test_heat_fetch.py`, `test_factors_property.py`, `test_valuation_wiring.py`) stay green **because** `flow` defaults to `None` (§5.C). Per the project "test scope on signature changes" rule, run `tests/monitor/`, `tests/monitor/eval/`, and `tests/commands/` — not just the mirror dir.

## 8. Open questions / for review

- **Engine bump + isolation — DECIDED (review #1, P0).** `_ENGINE_VERSION → "2"` is mandatory AND paired with the §5.E `target_engine` reader/runner filter; the bump alone does not isolate populations because nothing reads `manifest_versions.engine` today. The deliberate alternative of keeping `"1"` for a continuous series is rejected — it would pool incomparable pre/post-flow biases into one metric.
- **Target-engine policy** — the runner targets the max engine version present in the ledger (self-configuring, no config). A deliberate engine *rollback* is out of scope; if ever needed, add an explicit `--engine` override then.
- Flow blend weights (`0.4·5d + 0.6·20d`) and the coverage floor (`0.50`) are named constants; promote to `config/monitor.yaml` only if you later want to tune them per-run.

## 9. Out of scope (YAGNI)

Northbound flow; AUM-Δ heat leg; a standalone `irc stock-screen` CLI command (the cross-fund Ranked Stock Board) — the per-fund drill-down covers the stated need; a cross-fund board can be a later spec if wanted; intraday/real-time flow; flow for non-A-share (QDII) lines.
