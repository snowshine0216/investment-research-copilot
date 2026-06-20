# Design — Monitor forward-eval engine-drop WARN (Follow-up 1)

**Date:** 2026-06-19
**Status:** Approved (brainstorming + spec grill 2026-06-20) — ready to implement
**Surface:** `irc eval monitor_forward`
**Builds on:** #168 (per-stock flow drill-down + engine-version isolation), ADR 0019 D3 (engine-version isolation), the #168 spec §5.E.
**Origin:** #168 ship review finding 6 ([items/001-ship-blocked.md:26](../../2026-06-19-monitor-flow-stock-drilldown/items/001-ship-blocked.md), [items/001-review.md:18](../../2026-06-19-monitor-flow-stock-drilldown/items/001-review.md)) — *"Forward ledger low-n on engine-'2' day 1"*, classified non-blocking/deferred.

## 1. Problem

`irc monitor`'s forward eval isolates the comparable population by engine version: `_filter_engine` keeps only rows whose `manifest_versions.engine` equals the max engine present (`target_engine`), dropping prior-engine rows under `engine_mismatch`. The `forward_ledger.jsonl` is **append-only**, so right after an `_ENGINE_VERSION` bump the ledger is dominated by prior-engine rows that get stranded, leaving a tiny *matured* target-engine population.

That drop count **is** recorded (non-silent) in `details.json.excluded_by_engine`, and the forward metrics already WARN at low-n (`raw_composite_directional` / `publishable_bias_directional` go `state="insufficient_data"` + `status="WARN"` at `effective_n < N_MIN_BLOCKS`; `rank_ic` WARNs below `MIN_DEFINED_DAYS`). So after a bump the stage **already shows `overall=WARN`** — the operator is *not* fooled into reading a thin headline as trustworthy.

**What's missing is attribution.** The operator can see the eval is thin, but cannot tell *"thin because of the engine reset"* from *"thin because the signal is generally young / sparse."* This feature adds exactly that one bit: an **attribution label**. It is **informational only — it never changes `overall` or `rc`** (see D3). The #168 review explicitly flagged surfacing this as *"a future enhancement, not a blocker."*

This is now doubly relevant: Spec B (dual-track valuation) bumps the engine again `"2"→"3"`, so the same transition recurs and this attribution covers it.

## 2. Decisions locked (brainstorming 2026-06-19; sharpened in spec grill 2026-06-20)

| # | Decision |
|---|---|
| D1 | **One new diagnostic row** — `engine_population` — emitted as a 4th `MetricReport`. It is a **diagnostic/attribution row, NOT a 4th predictive-validity metric** (the three predictive rows stay `raw_composite_directional`, `publishable_bias_directional`, `rank_ic`; retro stays a `details.retro` sub-block). It scores nothing — it reports population health. No change to `score_forward`'s scoring; it reads counts already in scope (`target_engine`, `engine_mismatch`, `len(ledger)`, `effective_n(forward_rows)`). |
| D2 | **Trigger keys on `publishable_bias_directional.state` ONLY** (`== "insufficient_data"`), read from the per-metric `details` dict returned by `build_metric_reports` (`details["publishable_bias_directional"]["state"]` — NOT a field on the `MetricReport` object). **`rank_ic` is deliberately EXCLUDED from the trigger** (grill 2026-06-20). Rationale: `rank_ic` flaps into `"undefined"` whenever a run-date has `< MIN_CROSS` (4) defined funds — with a 7-fund monitor set that is ordinary cross-sectional sparsity, **unrelated to the engine bump**, and can recur months later. Because `engine_mismatch > 0` is permanent (append-only ledger), keying on `rank_ic` would resurrect the permanent / false-attribution WARN that D4 exists to prevent. Keying on the hit-rate headline loses nothing at the *real* transition (right after a bump the matured target-engine population is ≈ 0, so `publishable_bias_directional` is *also* `insufficient_data` and fires correctly), and it **clears monotonically** as blocks accrue. `publishable_bias_directional` is chosen over `raw_composite_directional` because it is the *published* signal operators act on and it matches the existing review-trigger (`_headline_random_delta`). |
| D3 | **Tri-state, never FAIL — and attribution-only, never gating.** WARN when the engine drop is the proximate cause of headline low-n; PASS otherwise. **It can never change `overall`/`rc`:** its WARN trigger *requires* `publishable_bias_directional` to already be `insufficient_data`, which already carries `status="WARN"`, so `worst_status` has already lifted the stage to WARN. The row adds the `state="engine_transition"` *attribution*, not a status bit. `monitor_forward` is `active` / out-of-`--all` / never-gating (`rc 0/1/2`), so this is purely informational. |
| D4 | **Self-clearing, transition-scoped.** Because prior-engine rows stay in the append-only ledger forever, the WARN keys on whether the **headline metric is still `insufficient_data`** — not on `engine_mismatch > 0` alone. Keying on the *hit-rate* headline (D2) makes the clear durable: its block floor clears monotonically and stays clear, so the WARN does not re-fire on later cross-sectional sparsity. |
| D5 | **No new schema field.** The signal rides existing `MetricReport` fields + the `details.json` block. `MetricReport` / `PredictiveMetricView` have **no free-text message field** ([report_schema.py](../../../evals/_shared/report_schema.py); [predictive_panel.py](../../../src/irc/monitor/eval/predictive_panel.py) renders a `state` column, not prose) — so the rationale is a short `state` code + the details block. Two **mandatory** details keys: `ci_low: None` and `ci_high: None` (see §4 "Rendering" — without them the panel fakes a `[+v, +v]` interval) and `threshold = {}` (matching `_HIT_TH`/`_IC_TH`, never `fail_below`). |

## 3. Scope

- **In:** a new `engine_population` diagnostic row in the `monitor_forward` stage report; its pure status logic; its `details.json` block (incl. mandatory `ci_low/ci_high = None`); the four linked tests.
- **Out:** any change to `score_forward`, `_filter_engine`, `_target_engine`, the maturity join, or the three existing forward/retro metrics. No gating-behavior change. No new fetch, LLM, or spend surface. No panel-renderer change (the existing `state`/CI/Δ columns already carry everything).

## 4. Design

A new `MetricReport` appended in `evals/monitor_forward/runner.py` after `build_metric_reports`, where the headline metric details, `target_engine`, `_excl["engine_mismatch"]`, and `len(ledger)` are all already in scope. **Append in the runner, not in `build_metric_reports`** — that keeps `build_metric_reports` returning exactly the three predictive metrics (its direct test stays green) and isolates the diagnostic row to the edge.

**Inputs (all already computed in `runner.run`):**
- `n_excluded_engine = _excl.get("engine_mismatch", 0)`.
- `headline_state = details["publishable_bias_directional"]["state"]` — **direct indexing** (a missing headline is an invariant break in `build_metric_reports`; it should fail loudly during eval development, never silently suppress the WARN to a false PASS).
- `len(ledger)` (raw parsed rows) and `effective_n(forward_rows)` (matured target-engine block span).

**Pure status logic** (`evals/monitor_forward/metrics.py`):

```python
def engine_population_status(*, n_excluded_engine: int, headline_state: str) -> tuple[str, str]:
    """PURE. Returns (status, state_code). headline_state is
    publishable_bias_directional's state from build_metric_reports' details dict."""
    if n_excluded_engine == 0:
        return "PASS", "ok"           # single-engine ledger; no transition in progress
    if headline_state == "insufficient_data":
        return "WARN", "engine_transition"   # drop is material AND headline is itself thin
    return "PASS", "ok"               # the drop happened, but the headline is already sufficient
```

**`value` and `n_observations` describe two different (both real) populations:**
- `value` = **raw-ledger target-engine share** = `(len(ledger) − n_excluded_engine) / len(ledger)` — a 0..1 transition-progress meter (the panel's `+.3f` renders it sensibly). **Empty-ledger guard:** `0.0` when `ledger == []` (and `n_excluded == 0` there → PASS / `"ok"`, no division).
- `n_observations` = `effective_n(forward_rows)` — the **matured** target-engine block span (statistical support).

The two are intentionally over different populations (raw vs matured); the `details` block labels each so no one "fixes" the apparent mismatch.

**`details["engine_population"]` block (name-keyed so the panel's `state` column renders the code — `_metric_view` sources `state` from `details[m.name]["state"]`, defaulting to `"ok"` if the key is absent):**

```python
details["engine_population"] = {
    "state": state_code,                       # "engine_transition" | "ok"
    "ci_low": None, "ci_high": None,           # MANDATORY — see "Rendering" below
    "headline_low_n": headline_state == "insufficient_data",
    "headline_metric": "publishable_bias_directional",
    "headline_state": headline_state,
    "n_excluded": n_excluded_engine,
    "n_total_raw": len(ledger),
    "n_target_raw": len(ledger) - n_excluded_engine,
    "value_population": "raw_ledger_target_engine_share",
    "n_observations_population": "matured_target_engine_effective_n_blocks",
    "n_min_blocks": N_MIN_BLOCKS,              # provenance only (not a threshold on value)
}
# unchanged: details["excluded_by_engine"] = {"target_engine", "engine_mismatch"}
```

**Rendering (the one latent bug to avoid).** `_metric_view` (monitor_cmd.py:529) does `ci_low=md.get("ci_low", m.value)`. `dict.get(k, default)` returns the *stored* value when the key is present — so an **explicit** `ci_low: None` flows through to `None`, and `_ci_cell` prints **"CI pending"** (predictive_panel.py:12-17). **Omitting** the key would default to `m.value` (the share) and render a faked `[+0.500, +0.500]` interval — exactly the anti-pattern predictive_panel.py:11-13 forbids. Hence `ci_low/ci_high = None` are mandatory. The Δ cells render `"n/a"` automatically (no `baseline_deltas` ⇒ `_metric_view._d()` returns `None`).

**Surfacing.** The `engine_population` `MetricReport` uses only existing fields: `status = WARN|PASS`, `value = the 0..1 share`, `n_observations = effective_n(forward_rows)`, `threshold = {}`, `details_ref`. The appended report auto-appears as a panel row (`_predictive_panel_model` iterates `StageReport.metrics`); its `state` column shows `engine_transition`/`ok` because the name-keyed details entry exists.

**Never FAIL; never gates.** `overall = worst_status([...])` already reflects the headline WARN; this row only ensures the *attribution* travels with it. The permanent, only-growing historical excluded count never alone trips the WARN (D4).

## 5. Components

- `evals/monitor_forward/metrics.py`: the pure `engine_population_status(*, n_excluded_engine, headline_state) -> (status, state_code)` above. No I/O; trivially unit-tested as a 4-cell truth table.
- `evals/monitor_forward/runner.py`: after `build_metric_reports` (returns `(reports, details)`), read `headline_state = details["publishable_bias_directional"]["state"]` (direct index), call the helper, build the `engine_population` `MetricReport` (`threshold={}`, value=guarded share, `n_observations=effective_n(forward_rows)`), **append it to `reports`**, write the name-keyed `details["engine_population"]` block (incl. `ci_low/ci_high = None`), and keep `details["excluded_by_engine"]` raw counts.
- **No schema change** — `MetricReport` / `StageReport` / `PredictiveMetricView` and the panel renderer are untouched (D5). No other module changes.

## 6. Invariants & constraints

- **Never gates the brief; never changes `rc`.** `monitor_forward` stays `active`, out of `--all`, `rc 0/1/2`. The row's WARN can only co-occur with a headline WARN that already set the stage status — it is attribution, not gating (D3).
- **Pure metric.** No filesystem/network/LLM; reads counts already computed.
- **Back-compat.** Single-engine ledgers (`engine_mismatch == 0`) and pre-bump runs stay PASS / `"ok"`. A genuinely empty/young single-engine ledger remains the domain of the existing `insufficient_data` metric — this row is silent (PASS) there.
- **No silent caps.** The row *surfaces* an already-recorded drop; `details.json.excluded_by_engine` continues to carry the raw counts.
- **Size budget.** One small pure function + one `MetricReport`; no module exceeds the budget.

## 7. Slice plan (TDD, red→green→refactor)

One slice, one feature branch, small PR (code+tests). The diagram overlay lands separately (§8).

**Tests:**

1. **Pure helper truth table** (`tests/evals/test_monitor_forward_metrics.py`) — the 4 cells of `n_excluded_engine ∈ {0, >0} × headline_state ∈ {"insufficient_data", "ok"}`: only `(>0, "insufficient_data")` → `("WARN", "engine_transition")`; the other three → `("PASS", "ok")`.
2. **Runner integration** (`tests/evals/test_monitor_forward_runner.py`) — a ledger with `engine_mismatch > 0` AND a thin `publishable_bias_directional` → the `engine_population` report has `status="WARN"`; `details["engine_population"]["state"] == "engine_transition"`; **`details["engine_population"]["ci_low"] is None` and `ci_high is None`** (producer side of the CI contract); `run()` returns `rc 1`.
3. **Update existing count assertion** (`tests/evals/test_monitor_forward_runner.py:214`) — `len(report["metrics"]) == 3` → `== 4`, and assert `"engine_population"` is present. (`test_monitor_forward_metrics.py:172`'s `len(reports) == 3` stays as-is — `build_metric_reports` is unchanged.)
4. **Empty-ledger guard** (runner test) — empty ledger: the `engine_population` **row** is `status="PASS"`, `value == 0.0`, `details state "ok"`, `n_target_raw == 0`, no crash. Do **not** assert whole-stage PASS — empty `forward_rows` still makes the headline metrics WARN.
5. **Command-edge CI-None preservation** (`tests/commands/test_monitor_cmd_predictive_panel.py`) — persisted `report.json` + `details.json` carrying `engine_population` with explicit `null` CIs → through **`_predictive_panel_model(...)`** (the public boundary, not `_metric_view`) → the `engine_population` view has `ci_low is None`. Pins the soft link where the bug lived.
6. **Pure renderer** (`tests/monitor/eval/test_predictive_panel.py`) — `PredictiveMetricView(name="engine_population", value=0.5, status="WARN", state="engine_transition", ci_low=None, ci_high=None, random_delta=None, momentum_delta=None, buy_hold_delta=None, n_observations=3)` → HTML contains `"engine_population"`, `"CI pending"`, and enough `"n/a"` to cover all three baseline cells.
7. **DELETE** the old planned `rank_ic state == "undefined" → WARN` test — after D2 it would encode the bug.

**Verification discipline:** run the *whole* `tests/evals/`, `tests/monitor/`, and `tests/commands/` dirs (not just the mirror) before claiming green — the runner output feeds all three, and a prior signature-change regression hid in `tests/commands/` while `tests/monitor/` was green.

## 8. Diagram deliverable (sequenced)

1. **Standalone as-built doc-sync PR** (shared #168 doc-debt, **not** FU1-owned): bring `evals/docs/monitor-eval-workflow.html` to current shipped reality (node `schema_v1` → `"3"`; depict the engine-isolation path `target_engine` filter + `excluded_by_engine`), and `docs/diagrams/monitor-workflow.html` (add the `flow` factor + `drilldown.html`, fix the stale "v2.0: valuation/heat → N/A" wording). Lands first; prerequisite for **both** FU1 and FU2 (Spec B).
2. **FU1 code + tests** (§7) proceed **in parallel** — they do not depend on the diagram.
3. **FU1 diagram overlay waits for step 1**: add a dashed "planned" `engine_population` box to the `monitor_forward` node (informational / never-gating), promoted to solid at ship time (mirrors the existing dashed M4 box). Waiting avoids a mixed stale/planned artifact and avoids bundling shared doc-debt into the FU1 PR.

## 9. CONTEXT.md pre-draft (paste at ship, not before)

CONTEXT.md describes *shipped* reality; these edits land **with the FU1 merge**, not now. Pre-drafted here so the implementation has exact language ready.

- **Amend the "Predictive metrics & baselines" line** (currently "three `MetricReport` rows … never as a 4th row"): clarify that there are **three predictive-validity metric rows** (`raw_composite_directional`, `publishable_bias_directional`, `rank_ic`) plus, after FU1, **one diagnostic/attribution row** (`engine_population`) — a different species. Retro remains a `details.retro` sub-block; it is correctly *not* a row because it would be a would-be 4th *predictive* metric and is not comparable. `engine_population` is legitimately a row because it scores population health, not signal skill.
- **New glossary entry:**
  > **`engine_population` (diagnostic row)** — a 4th `monitor_forward` `MetricReport`, **not** a predictive metric. `value` = raw-ledger share of rows on the current engine (`target_engine`); `n_observations` = `effective_n` of the matured target-engine forward rows; `state` = `engine_transition` | `ok`. **Attribution-only, never gating** (`rc` is unchanged — it WARNs only when `publishable_bias_directional` is already `insufficient_data`). Surfaces *why* a post-`_ENGINE_VERSION`-bump forward eval is thin (engine reset) vs general youth. `rank_ic` is deliberately excluded from its trigger (cross-sectional `"undefined"` flapping is not an engine signal). See ADR 0019 / this spec.
- **Amend the "Predictive-validity panel" row-state vocabulary** (currently "normal / `insufficient_data` / `undefined` / stale / review-trigger") to add **`engine_transition`**.

## 10. Out of scope

- Any change to the engine-isolation filter, the maturity join, or the scorer.
- Promoting `monitor_forward` into `--all` or making it gate.
- A configurable WARN threshold (the trigger is a state check + `engine_mismatch > 0`, not a numeric floor on `value`; add a knob only if later needed).
