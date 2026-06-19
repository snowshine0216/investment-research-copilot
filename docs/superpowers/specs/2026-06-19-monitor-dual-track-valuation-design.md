# Design — Monitor dual-track per-stock valuation + False-Cheap clamp (Follow-up 2)

**Date:** 2026-06-19
**Status:** Approved (brainstorming) — pending spec review
**Surface:** `irc monitor`
**Builds on:** #168 (per-stock drill-down + `flow` factor + per-stock self-history valuation), ADR 0017 (evidence isolation), ADR 0018 (weight/scoring governance), ADR 0019 D4 (this work was explicitly deferred there).
**Origin:** #168 spec §9 *"Out of scope (YAGNI) / staged follow-ups"* and ADR 0019 D4 — the dual-track valuation + False-Cheap clamp, classified evidence-**independent** and built now (the conflict-suppression and flow-reversal guards remain evidence-gated and are NOT in this spec — see §10).

## 1. Problem

The bias-driving **valuation factor** is fund-level: `valuation.py::resolve_valuation_state` returns a *state* via either the index branch (`_resolve_index`, for index-tracking funds) or a look-through branch that aggregates constituents into one *portfolio earnings-yield series* and takes its self-history percentile. Separately, #168 added a **per-stock board valuation** (`holding_metrics.per_stock_valuation`) that is **display-only** — each stock vs its own PE history, with **no aggregation into the factor**.

Two gaps:

1. **Self-history only is value-trap-blind.** A stock cheap vs *its own* (possibly de-rated) history can be expensive vs *its peers* — a classic value trap. The factor cannot see this; nothing compares a holding to its industry.
2. **The per-stock board doesn't drive the bias.** The legible per-stock detail #168 surfaced is decorative; the factor still rides a single fund-aggregate series, so the board and the factor can disagree.

**Goal (ADR 0019 D4, evidence-independent leg).** Re-base the look-through valuation factor as a **bottom-up, per-stock dual-track score** — self-history percentile **and** industry-relative richness — with a **False-Cheap clamp** that neutralizes value traps. All score-level, flowing through the existing linear composite (§9 lock: *"a per-stock score adjustment that flows through the existing linear composite, NOT a fund-level veto"*). The #156/ADR 0015 framing is **retained** — a better-*reasoned* lean, never an order.

## 2. Decisions locked (brainstorming 2026-06-19)

| # | Decision |
|---|---|
| D1 | **Two-tier model.** Valuation guards are **score-level** (inside the linear composite). The post-composite *veto* tier (honesty gates) is separate and **deferred** (§10). This spec touches only the score-level tier. |
| D2 | **Re-base the factor bottom-up.** Add `aggregate_valuation()`: per-stock dual-track score → weight-weighted over covered holdings → the **valuation factor value for look-through active funds**. The aggregation *value* follows `aggregate_flow`'s shape (`Σwᵢvᵢ/Σwᵢ` over covered), but the **coverage gate uses the NAV denominator** (D10), NOT flow's. Index-tracking funds keep `_resolve_index` (no per-stock look-through). |
| D3 | **Dual-track blend = 0.60·self-history + 0.40·industry-richness** (your Layer-1 weights). Both legs in `[-1,+1]`, cheap → positive (bullish), matching the existing valuation sign convention. |
| D4 | **Industry leg = Option A.** "stock PE vs **industry-average** PE" from **cacheable market-wide tables** (a stock→industry map + an industry-average-PE table) — NOT a per-peer percentile (Option B, rejected: heavy per-peer fetch, ADR 0014 rate-limit exposure) and NOT a sector-blind absolute ceiling (Option D, rejected). |
| D5 | **False-Cheap clamp.** `self_score > 0` (cheap vs own history) **AND** richness `r = stock_pe/industry_avg_pe ≥ _FALSE_CHEAP_RICHNESS` (≈1.2, rich vs peers) → clamp that stock's `val_score = 0.0` (NEUTRAL), `false_cheap=True`. Clamp to **0, not negative** — the guard removes a false bullish signal, it does not assert bearishness (§9: "clamp to 0/NEUTRAL"). |
| D6 | **No PEG/DCF.** §9's drop stands; monitor computes neither and the dormant fund-level `valuation_fundamental_signal` (ADR 0012/0009) cannot serve. The industry leg + clamp **is** the False-Cheap mechanism (the table's Layer 1 and Layer 2 merge). |
| D7 | **Valuation weight unchanged** (`.20` on `active_cn_equity`). We re-base the factor's *value*, not its *weight* — no profile/weight-vector change. |
| D8 | **Engine bump `"2"→"3"`** (bias semantics change). Forward-eval isolation targets `"3"`; Follow-up 1's `engine_population` WARN covers the transition. |
| D9 | **Priors as named constants**, documented in ADR 0020 (not auto-tuned, ADR 0018): blend `0.60/0.40`, coverage floor `0.50`, `_FALSE_CHEAP_RICHNESS ≈ 1.2`, industry_score banding. Promote to `config/monitor.yaml` only if later tuned. |
| D10 | **Coverage = fraction of fund NAV — match the factor being replaced.** `covered_weight_ratio = Σ covered weight_pct / 100.0` (ratio of NAV; the `/100` is load-bearing — same as `lookthrough_valuation._coverage_ratio`), **NOT** `aggregate_flow`'s covered/top-holdings denominator. Floor `0.50` = ≥50% of *fund NAV*; `>=` accepts exactly-at-floor (matches `_meets_floor`). (Review fix: flow's denominator could pass 50% "coverage" while covering far less than 50% of fund NAV — wrong for a factor that gates on covered NAV.) |

## 3. Scope

- **In:** the look-through `active_cn_equity` funds (per-stock A-share holdings exist). Dual-track + clamp + bottom-up valuation factor apply to these.
- **Index-tracking active funds** (e.g. 018132 有色金属指数A): resolve via `_resolve_index` — **no per-stock look-through → keep the index branch.** The dual-track does not apply; their valuation factor is unchanged (honest asymmetry: index funds have an index-level valuation, not per-stock).
- **Out (N/A by profile):** gold / qdii_global / qdii_china_us_internet — valuation stays `profile_ineligible` (unchanged).
- **Out of scope:** the entire post-composite veto tier (conflict hard-suppression, flow-reversal guard) — deferred, evidence-gated (§10); Amihud tradability veto (dropped from monitor — a decision-layer concern, ADR 0015); per-peer true-percentile industry comparison (Option B); PEG/DCF (D6).

## 4. Architecture

```
top-5 holdings (cached ActiveFundSnapshot) ─┐
stock_valuation_history (cached DuckDB) ─────┼─▶ holding_metrics.py (PURE)
  per-stock self-history PE percentile       │     per-stock StockValuation (self_score)
industry_pe / stock_industry (cache) ────────┘     + industry_score + dual-track val_score + False-Cheap clamp
        ▲                                              │
industry_valuation.py (EDGE, cached/day,               ├─▶ aggregate_valuation → ValuationAggregate (Σwᵢvᵢ/Σwᵢ, coverage gate)
  market-wide tables, never raises)                    ├─▶ factors._valuation (look-through: numeric aggregate; index: state) → composite → bias
                                                        ├─▶ render_drilldown.py → board gains industry + value-trap badge
                                                        └─▶ eval/trace.py → holding_metrics block (schema 4) → determinism + coverage + reconciliation
```

Pure core (`holding_metrics`, `aggregate_valuation`, the dual-track scoring) consumes already-loaded inputs. The only new effect is `industry_valuation` (cached market-wide reads), plus the DuckDB reads the valuation path already does.

## 5. Components

### 5.A `industry_valuation.py` (EDGE + pure parse) — Slice 1
Mirrors `flow_fetch.py`'s contract: never raises, degrades to None/empty, parsed rows (no DataFrame on disk), per-day JSON cache with `ok`/`miss` status, **direct** CN endpoint (no `IRC_HTTPS_PROXY`), light pacing (ADR 0014).
- `fetch_industry_pe(*, cache_dir, today, fetch=None) -> dict[str, float]` — industry → average PE, from a **market-wide** industry-PE table (few calls, cached/day).
- `fetch_stock_industry_map(symbols, *, cache_dir, today, fetch=None) -> dict[str, str]` — symbol → industry, from a **single market-wide classification table** (Option A: cacheable tables, **not** per-symbol calls — avoids the rate-limit exposure §9/ADR 0014 flagged). Non-A-share lines unmapped → industry leg N/A for them.
- Exact akshare endpoints chosen at impl; cache `data/monitor/industry_pe/<today>.json` + `data/monitor/stock_industry/<today>.json`. ADR 0017: the monitor's OWN cache; no opportunity output files.

### 5.B Dual-track scoring + clamp in `holding_metrics.py` (PURE) — Slice 2
- `self_score ∈ [-1,+1]` from the existing self-history PE percentile (cheap→positive), using the same percentile→value sign as the current valuation factor (unified vocab). Self leg N/A (immature / non-positive PE, per #168) → the stock has **no `val_score`** and is excluded from the aggregate (matches #168 state-None behavior).
- `industry_score ∈ [-1,+1]` from richness `r = stock_pe / industry_avg_pe`: cheaper-than-peers → positive, banded symmetrically around `r≈1` (named constants). No industry mapping / no industry PE → `industry_no_data`.
- `val_score = 0.60·self_score + 0.40·industry_score`. **Industry leg N/A → `val_score = self_score`** (honest 1.0·self fallback; the per-stock `HoldingMetric.industry_reason = "industry_no_data"` — never a fabricated industry leg). `industry_no_data` is a **per-stock `HoldingMetric` reason** (alongside the existing `pe_not_positive`/`pe_immature`/`no_series`), NOT a factor-level N/A reason and **NOT in `KNOWN_NA_REASONS`** — the factor stays eligible on self-only.
- **False-Cheap clamp (D5):** `self_score > 0 AND r ≥ _FALSE_CHEAP_RICHNESS` → `val_score = 0.0`, `false_cheap=True`, reason `false_cheap_clamp`.
- Extend `StockValuation` / `HoldingMetric` with: `industry`, `industry_pe`, `industry_richness` (`r`), `industry_score`, `self_score`, `val_score`, `false_cheap`, and the reason.
- `aggregate_valuation(metrics) -> ValuationAggregate`: **value** = `Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ)` over holdings with a non-None `val_score` (weight-renormalized — same shape as `aggregate_flow`); **clamped stocks count as covered** (contribute 0). **Coverage uses the NAV denominator (D10):** `covered_weight_ratio = Σ covered weight_pct / 100.0` — the fraction of *fund NAV* covered, matching `lookthrough_valuation._coverage_ratio` (NOT flow's covered/top-weight). Zero covered → `valuation_no_data`; `covered_weight_ratio < 0.50` of NAV → `valuation_no_coverage`; else `value, reason=None`.

### 5.C Factor re-base + scoring — Slice 3
- `factors._valuation`: look-through active funds consume the numeric `ValuationAggregate.value`; index funds keep the state→value path. `_valuation` handles both; `FactorInputs` gains the aggregate as a **trailing, defaulted** field (back-compat with the **2 `src/` construction sites** — `monitor_cmd.py` + retro `eval/backtest.py` — plus the test sites; `backtest.py` already omits `flow=` and rides the trailing default, proving the pattern).
- **Resolver must expose its branch (review P1 — the real gap).** `resolve_valuation_state` dispatches index-vs-look-through *internally* via `_tracked_index_for_fund` and returns only a `ValuationResolution` — **the branch taken is hidden**. And `profile_spec.lookthrough == "active_fund"` is **True for index-tracking active funds too** (e.g. 018132), so it is NOT a sound proxy for "use the bottom-up aggregate." Fix: add `path: Literal["index","lookthrough"]` to `ValuationResolution` (or have `_process_fund` itself call `_tracked_index_for_fund`), and gate the numeric-aggregate feed on `path == "lookthrough"` — never on `profile_spec.lookthrough`.
- **Factor N/A reasons (reachable branches required).** The bottom-up path adds two new `_NA_*` constants emitted by *real* `_valuation` branches mapped from `ValuationAggregate.reason`: `_NA_VALUATION_NO_DATA = "valuation_no_data"` (zero covered) and `_NA_VALUATION_NO_COVERAGE = "valuation_no_coverage"` (below the NAV floor). The index path keeps `_NA_VALUATION_NO_ANCHOR`. Both new codes **must** join `KNOWN_NA_REASONS` (else `deterministic_health._bad_reasons` FAILs them) **and** be referenced from a branch (else `test_known_na_reasons` reachability fails). `industry_no_data` is NOT among these (per-stock reason — §5.B).
- **`monitor_cmd._process_fund` wiring (HIGH-RISK — the #168/valuation/heat dark-factor trap).** Feed `aggregate_valuation(holding_metrics)` into `FactorInputs` **only when `path == "lookthrough"`** (above); an index-tracking active fund builds `holding_metrics` but must keep the index state path. The integration test MUST drive the real `_process_fund` and assert (a) a look-through fund gets a **bottom-up valuation `FactorScore` (eligible)** end-to-end, AND (b) an index-tracking active fund (018132) still rides the **index state** — not merely unit-test the pure aggregate. (Memory: assert factor wiring at `_process_fund`, not just the pure fn — same bug class as flow/valuation/heat going dark.)
- **Valuation weight unchanged** (D7): no `profiles.py` weight-vector change.
- `signal.py`: **no new divergence code** — the False-Cheap is neutralized in-score (the clamped stock contributes 0), so it needs no separate caveat. Surface it instead on the board (§5.D).
- `_ENGINE_VERSION "2"→"3"` in `monitor_cmd.py` (D8). `compute_signal` is unchanged — the re-based value flows through automatically.

### 5.D Report — Slice 3 (with the factor re-base)
- `render_drilldown.py`: board gains `行业 · 行业PE · 行业相对 (r) · 行业分` columns and a **value-trap badge** on clamped rows with a 便宜(自身)/偏贵(行业)→中性 annotation. Roll-up shows the dual-track split (self vs industry legs) and which holdings were clamped.
- Optional non-gating **fund-level note** when a material-weight holding is clamped (transparency, mirroring #168's broad-outage header-note pattern). Pure: computed from the metrics, not a side effect.
- `_EXPLAINER` extended to name the dual-track (估值 = 自身历史 + 行业相对；价值陷阱→中性). Lean language only — no 买入/卖出 (ADR 0015).

### 5.E Eval — Slice 4
- `eval/trace.py`: bump `_SCHEMA_VERSION "3" → "4"`; the `holding_metrics` block gains the industry/self/blend/clamp fields. The valuation factor value is now bottom-up automatically.
- **Determinism** (`eval/determinism.py`): dual-track + clamp reproduce identically on cached re-run; recognize the new factor reasons (`industry_no_data`, `valuation_no_coverage`).
- **Coverage/health** (free, `eval monitor_signal`): industry-map coverage %, industry-PE coverage %, `false_cheap` tally per fund.
- **Reconciliation oracle** (`eval/structural.py`): assert the board's weighted dual-track `Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ)` over covered rows equals the `valuation` factor value (4dp) for look-through funds — proves the methodology, mirroring flow's reconciliation.

### 5.F Versioning
- `_ENGINE_VERSION "2"→"3"` (D8). Tags new ledger rows so the existing `score_forward(target_engine=…)` filter isolates the v3 population; Follow-up 1's `engine_population` WARN surfaces the transition.

## 6. Invariants & constraints

- **ADR 0017 isolation:** industry data is the monitor's OWN cache (`data/monitor/{industry_pe,stock_industry}/`); pure core, effects at edges; no opportunity output files.
- **Determinism + badges:** the new **factor-level** N/A reasons `valuation_no_data` + `valuation_no_coverage` join `KNOWN_NA_REASONS` (non-caveating, like flow's) with reachable `_valuation` branches. **`industry_no_data` is a per-stock `HoldingMetric` reason, NOT a factor reason** — it is not in `KNOWN_NA_REASONS` (the factor stays eligible on self-only). `false_cheap_clamp` is **not** an N/A either — the stock is covered, score 0; per-stock annotation only.
- **No silent caps:** uncovered holdings and clamped holdings are surfaced on the board with reasons; coverage-floor N/A is explicit.
- **Framing (ADR 0015 line):** still 研究参考信号，非买卖指令. The board explains *why* a stock is cheap/expensive/trap using lean language; no imperative action, no target weights, no per-instrument order.
- **Size budget:** new fetch in `industry_valuation.py`; dual-track in `holding_metrics.py`; clamp pure; `monitor_cmd` stays thin (wiring only).

## 7. Slice plan (TDD, red→green→refactor each)

1. **Data layer** — `industry_valuation.py` (fetch + cache, parsed-row JSON, `ok`/`miss`) + the cache schema. No bias impact. Tests: parse tolerance, cache round-trip (ok + miss, sorted), market-wide-table shape, never-raises per call, classification map lookup.
2. **Pure core** — dual-track score (0.60/0.40 blend), industry-richness mapping + banding, **False-Cheap clamp boundary at `r = _FALSE_CHEAP_RICHNESS`**, industry-leg-N/A → self-only fallback, self-leg-N/A → no score, `aggregate_valuation` + coverage floor (zero covered, `<0.50`, clamped-counts-as-covered). No bias wiring yet.
3. **Factor re-base → bias + report** — `ValuationResolution.path` exposure + `factors._valuation` numeric path + `FactorInputs` field (defaulted), `monitor_cmd._process_fund` **path-gated** wiring (**end-to-end integration test**), board columns + value-trap badge, `_ENGINE_VERSION "2"→"3"`. Tests: a look-through fund gets a bottom-up valuation `FactorScore` (eligible) via the real command; an **index-tracking active fund (018132) keeps the index state** (path-gated, NOT profile-gated); clamp moves the aggregate; weight-vector unchanged; `compute_signal` byte-identical given the same value.
4. **Eval + versioning** — trace schema `"3"→"4"` + holding_metrics fields, determinism recognition, coverage health, reconciliation oracle, engine `"2"→"3"` wiring. Tests: schema shape, determinism re-run, reconciliation equality for look-through funds, mixed-engine `"2"/"3"` isolation (the existing filter + Follow-up 1's WARN).

Ship as one feature branch (matches #166/#168's multi-slice single-PR pattern).

### 7.1 Locked tests that MUST be updated (exact-equality assertions)

Under TDD each is a deliberate red→green update — naming them prevents "preserving" an assertion that is supposed to change:

| Test (current assertion) | Update (slice) |
|---|---|
| `tests/monitor/test_known_na_reasons.py` (`_EXPECTED` + the `test_known_na_reasons_is_exactly_the_ten_codes` test + the "ten" prose at lines 8/16 + both reachability tests) | add **factor** codes `valuation_no_data`, `valuation_no_coverage` → 12; **rename the test/prose ten→twelve**; each new code needs a `_NA_*` constant **and** a reachable `_valuation` branch. **`industry_no_data` is NOT added** (per-stock reason, not a factor N/A). (slice 3) |
| `tests/monitor/eval/test_trace.py::test_schema_version_is_3` (**rename → `_4`**) + `tests/monitor/test_acceptance_eval.py:79` | `"3" → "4"` (slice 4) |
| engine-isolation tests (`tests/monitor/eval/test_forward_score.py`) | **no test asserts the literal `_ENGINE_VERSION`** — the isolation tests use `target_engine` as version-agnostic fixtures; the `"2"→"3"` bump needs **no test change** here, but re-run to confirm (slice 4) |
| `tests/monitor/test_render_drilldown.py` board-row/golden tests | new board columns (`行业 · 行业PE · r · 行业分` + value-trap badge) (slice 3) |

`CANONICAL_FACTOR_ORDER` (`render_factors`) is **unchanged** — `valuation` already occupies its slot; this spec re-bases its *value*, adding no factor.

Plus regression-check (no change expected, but run them per the project "test scope on signature changes" rule): the `FactorInputs(` construction sites stay green **because** the new valuation-aggregate field defaults. Run `tests/monitor/`, `tests/monitor/eval/`, and `tests/commands/test_monitor_cmd*` — not just the mirror dir.

## 8. ADR

**New ADR 0020 — Monitor dual-track valuation + False-Cheap clamp.** Records: the economic prior (self-history is mean-reversion; industry-relative is value-trap detection); why Option A (cacheable tables) over B/D; the False-Cheap clamp rationale (remove a false bullish signal, clamp to neutral not negative); the **factor re-base** (look-through valuation becomes bottom-up; index unchanged); the engine bump `"2"→"3"`; and the named-constant priors (D9). Governed surface (ADR 0018) → recorded prior, never auto-tuned.

## 9. Diagram deliverable

See the **shared diagram note** in the Follow-up 1 spec (`2026-06-19-monitor-forward-engine-drop-warn-design.md` §8): the as-built #168 correction lands first as a standalone doc-sync; each follow-up adds a dashed "planned" overlay that promotes to solid on ship.

- `docs/diagrams/monitor-workflow.html`: the **Factor scores** node — replace "v2.0: valuation/heat → N/A" with the as-built `flow` factor, then (this spec) show valuation re-based **bottom-up** (per-stock dual-track: 自身历史 + 行业相对 + 价值陷阱 clamp). Add the `industry_valuation` cache feed alongside the flow cache.
- `evals/docs/monitor-eval-workflow.html`: the node currently labels `schema_v1`; the as-built doc-sync first corrects it to `"3"`, then this spec bumps it to `"4"` and notes the dual-track fields in the `holding_metrics` block; add the valuation **reconciliation oracle** alongside flow's.

## 10. Out of scope (deferred — the evidence-gated veto tier)

Per ADR 0019 D4, the **post-composite veto tier** is judged together against forward evidence that only began accruing at engine `"2"` (and resets to `"3"` here). It is NOT built in this spec:

- **Conflict hard-suppression** — whether an open `valuation_flow_conflict` (cheap-but-being-sold / expensive-but-being-bought) should force the call to `NEUTRAL`/`NO_CALL`. Today it is an informational caveat only (#168). Build only once the forward eval (made trustworthy by Follow-up 1) shows conflicted `ADD_BIAS` calls actually underperform.
- **Flow-reversal sign-agreement guard** — whether a 5d-vs-20d flow sign split should down-weight the flow score. Today the split is *visible* on the board but does not down-weight.
- **Amihud tradability veto** — dropped from the monitor entirely: the fund is the NAV-priced tradeable instrument; constituent illiquidity is a decision-layer (ADR 0015) execution concern, not a research-lean gate.

When forward evidence justifies them, these become a separate spec implementing the two-tier weaken-only post-composite veto (composite produces a provisional bias; the veto layer can only demote `ADD → NEUTRAL`, never strengthen).
