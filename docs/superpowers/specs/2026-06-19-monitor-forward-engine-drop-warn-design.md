# Design — Monitor forward-eval engine-drop WARN (Follow-up 1)

**Date:** 2026-06-19
**Status:** Approved (brainstorming) — pending spec review
**Surface:** `irc eval monitor_forward`
**Builds on:** #168 (per-stock flow drill-down + engine-version isolation), ADR 0019 D3 (engine-version isolation), the #168 spec §5.E.
**Origin:** #168 ship review finding 6 ([items/001-ship-blocked.md:26](../../2026-06-19-monitor-flow-stock-drilldown/items/001-ship-blocked.md), [items/001-review.md:18](../../2026-06-19-monitor-flow-stock-drilldown/items/001-review.md)) — *"Forward ledger low-n on engine-'2' day 1"*, classified non-blocking/deferred.

## 1. Problem

`irc monitor`'s forward eval isolates the comparable population by engine version: `_filter_engine` keeps only rows whose `manifest_versions.engine` equals the max engine present (`target_engine`), dropping prior-engine rows under `engine_mismatch`. The `forward_ledger.jsonl` is **append-only**, so right after an `_ENGINE_VERSION` bump the ledger is dominated by prior-engine rows that get stranded, leaving a tiny *matured* target-engine population.

That drop count **is** recorded (non-silent) in `details.json.excluded_by_engine`, and `score_forward` / the metrics already have an `insufficient_data` path for low-n. **But** the stage's `overall` status does not distinguish *"headline metrics are thin because of the engine reset"* from *"metrics are fine."* An operator reading the report after a bump can mistake a low-n headline for a trustworthy one. The #168 review explicitly flagged surfacing this as *"a future enhancement, not a blocker."*

This is now doubly relevant: Spec B (dual-track valuation) bumps the engine again `"2"→"3"`, so the same transition recurs and this WARN covers it.

## 2. Decisions locked (brainstorming 2026-06-19)

| # | Decision |
|---|---|
| D1 | **One new panel metric** — `engine_population` — emitted as a `MetricReport`. No change to `score_forward`'s scoring; it reads counts already in scope (`target_engine`, `engine_mismatch`, `len(forward_rows)`). |
| D2 | **Sufficiency is judged in the metrics' OWN units, not a row count.** The forward metrics flag low-n in **block-based** units — hit-rate via `effective_n` (H run-date *blocks*) `< N_MIN_BLOCKS`, rank-IC via *defined cross-sectional days* `< MIN_DEFINED_DAYS` — recording a low-n `state` in the **per-metric `details` dict** returned by `build_metric_reports` (`details[name]["state"]` — NOT a field on the `MetricReport` object). Low-n states are `"insufficient_data"` (hit-rate) and `"insufficient_data"` **or `"undefined"`** (rank-IC, the latter at zero defined IC days — the dominant post-bump case). The engine WARN keys off whether a **headline metric is itself low-n** (`state in {"insufficient_data","undefined"}`), NOT a recomputed `len(forward_rows)`. (Review fixes: a row-count floor would PASS while block-based metrics WARN; and the rank-IC zero-days state is `"undefined"`, which a bare `=="insufficient_data"` check would miss.) |
| D3 | **Tri-state, never FAIL.** WARN when the engine drop is the proximate cause of headline low-n; PASS otherwise. `monitor_forward` is `active` / out-of-`--all` / never-gating, so this is purely informational (`rc 1`). |
| D4 | **Self-clearing, transition-scoped.** Because prior-engine rows stay in the append-only ledger forever, the WARN keys on whether the **headline metrics are still `insufficient_data`** — not on `engine_mismatch > 0` alone — else it would WARN permanently. |
| D5 | **No new schema field.** The signal rides existing `MetricReport` fields (`status`, `n_observations`, `value`, `threshold`, `details_ref`) + the already-written `details.json.excluded_by_engine` block. `MetricReport` / `PredictiveMetricView` have **no free-text message field** ([report_schema.py](../../../evals/_shared/report_schema.py), [predictive_panel.py](../../../src/irc/monitor/eval/predictive_panel.py) renders a `state` column, not prose) — so the rationale is a short `state` code + the details block, never a message string. |

## 3. Scope

- **In:** a new `engine_population` metric in the `monitor_forward` stage report; its status logic; its human-readable message; `details.json` already carries the inputs.
- **Out:** any change to `score_forward`, `_filter_engine`, `_target_engine`, the maturity join, or the existing forward/retro metrics. No gating-behavior change. No new fetch, LLM, or spend surface.

## 4. Design

A new `MetricReport` appended in `evals/monitor_forward/runner.py` after `build_metric_reports`, where the headline metric reports, `target_engine`, and `_excl["engine_mismatch"]` are all already in scope.

**Inputs (all already computed in `runner.run`):**
- `n_excluded_engine = _excl.get("engine_mismatch", 0)`.
- `headline_low_n` = whether any hit-rate / rank-IC metric is itself low-n. The per-metric `state` lives in the **`details` dict returned by `build_metric_reports`** (its second return value — `details[name]["state"]`), **not** a field on the `MetricReport` object. A metric is low-n when `state in {"insufficient_data","undefined"}` (hit-rate emits `"insufficient_data"` at `effective_n < N_MIN_BLOCKS`; rank-IC emits `"insufficient_data"` or, at zero defined IC days, `"undefined"` — the dominant post-bump case). Read that; do **not** recompute a row count.
- `target_engine`; and `effective_n` over the target-engine forward rows — for the reported `n_observations` **only**, never the trigger.

**Status logic (pure):**

```
low = {"insufficient_data", "undefined"}
headline_low_n = any(metric_details[m.name]["state"] in low for m in forward_metrics)
if n_excluded_engine == 0:
    PASS    # single-engine ledger; no transition in progress.
elif headline_low_n:
    WARN    # a headline metric is itself low-n AND the engine drop is material
            # → attribute that insufficiency to the transition.
else:
    PASS    # the drop happened, but the headline metrics are already sufficient.
```

Keying off the metrics' own low-n verdict (in their own block units) closes the unit mismatch: a ledger with many target-engine *rows* but too few run-date *blocks* is already low-n, so the WARN tracks it; a row-count floor would not.

**Surfacing (no new schema field — D5).** The `engine_population` `MetricReport` uses only existing fields: `status = WARN|PASS`, `value = target-engine row share of the ledger` (a 0..1 ratio, so the panel's `+.3f` rendering is sensible — not a raw count), `n_observations = effective_n(target-engine rows)`, `threshold = {…the block floors…}`, `details_ref`. The daily brief's predictive panel sources each row's `state` from `details[m.name]["state"]` (`_metric_view` in `monitor_cmd`), so the runner writes a **name-keyed** `details["engine_population"] = {"state": "engine_transition"|"ok", "headline_low_n": …, "n_target": …, "n_excluded": …}` — AND keeps the raw counts in `details["excluded_by_engine"]`. (The appended report metric auto-appears as a panel row — `_predictive_panel_model` iterates the StageReport metrics — but renders `engine_transition` in the **`state` column** only because the name-keyed entry exists; without it the panel would default `state` to `"ok"`.) `MetricReport`/`PredictiveMetricView` have no free-text message field; the signal is the `state` code + the details block, never prose.

**Never FAIL** — transitional/informational only.

`overall = worst_status([m.status for m in reports])` already lifts a WARN to the stage status → `rc 1`, visible in the printed `monitor_forward eval: WARN` line, the persisted `StageReport`, and the eval-workflow diagram.

**Self-clearing:** as engine-`<target>` rows accrue enough run-date blocks, the headline metrics leave `insufficient_data`, so `headline_low_n` is false and this returns PASS — no code change; the permanent (only-growing) historical excluded count never alone trips it (D4).

## 5. Components

- `evals/monitor_forward/metrics.py`: a pure helper `engine_population_status(n_excluded_engine, forward_metrics, metric_details) -> (status, state_code)` implementing the §4 logic — it reads `metric_details[name]["state"]` (the per-metric details dict, NOT the `MetricReport` object), performs no I/O.
- `evals/monitor_forward/runner.py`: after `build_metric_reports` (which returns `(reports, details)`), compute `headline_low_n` from `details`, build the `engine_population` `MetricReport`, **append it to `reports`** (so `worst_status` includes it), write a **name-keyed** `details["engine_population"] = {state, headline_low_n, n_target, n_excluded}` (so the panel's `state` column renders the code), and keep the raw counts in `details["excluded_by_engine"]`.
- **No schema change** — `MetricReport` / `StageReport` / `PredictiveMetricView` are untouched (D5). No other module changes.

## 6. Invariants & constraints

- **Never gates the brief.** `monitor_forward` stays `active`, out of `--all`, `rc 0/1/2`; this metric can only raise the *eval* status, never the daily brief.
- **Pure metric.** No filesystem/network/LLM; reads counts already computed.
- **Back-compat.** Single-engine ledgers and pre-bump runs stay PASS. A genuinely empty/young single-engine ledger remains the domain of the existing `insufficient_data` metric — this metric is silent (PASS) there.
- **No silent caps.** The WARN is the *surfacing* of an already-recorded drop; `details.json.excluded_by_engine` continues to carry the raw counts.
- **Size budget.** One small pure function + one `MetricReport`; no module exceeds the budget.

## 7. Slice plan (TDD, red→green→refactor)

1. **`engine_population` metric** — pure status logic + wire into the stage report + extend the details block.
   Tests:
   - engine drop material (`engine_mismatch > 0`) **AND** a headline metric `state == "insufficient_data"` → **WARN**; `details["engine_population"]["state"] == "engine_transition"`; `overall` lifts to WARN; `run()` returns `rc 1`;
   - **rank-IC `state == "undefined"`** (zero defined IC days — the dominant post-bump case) + material drop → **WARN** (the case a bare `=="insufficient_data"` check would miss);
   - engine drop material but headline metrics sufficient (states all `"ok"`) → **PASS**;
   - single-engine ledger (`engine_mismatch == 0`), headline metric low-n → **not this WARN** (PASS — plain youth; the headline metric's own low-n state still owns it);
   - the row's `n_observations` is `effective_n` of target-engine rows (block-based), **not** a row count; `value` is a 0..1 ratio;
   - `details["excluded_by_engine"]` still carries `target_engine` + `engine_mismatch`; `details["engine_population"]` carries the name-keyed `state`.

Ships as one feature branch (one slice, small PR).

## 8. Diagram deliverable

`evals/docs/monitor-eval-workflow.html` (the M3 `monitor_forward` node + cards):
- **As-built first** (independent #168 doc-debt — see the shared note below): the diagram already shows `monitor_forward`; ensure the engine-isolation path (`target_engine` filter, `excluded_by_engine`) is depicted.
- **This spec:** add the `engine_population` WARN to the `monitor_forward` node (a dashed "planned" annotation that promotes to solid on ship), noting it is informational/never-gating.

> **Shared diagram note (both follow-up specs).** Both `evals/docs/monitor-eval-workflow.html` and `docs/diagrams/monitor-workflow.html` are **stale vs the #168 as-built** (no `flow` factor, no `drilldown.html`, `monitor-workflow` still says "v2.0: valuation/heat → N/A", eval-workflow labels the node `schema_v1` — *two* versions behind the real `"3"`). The **as-built correction is plain #168 doc-debt and should land first as a standalone doc-sync** (bringing the node to `"3"`), independent of A/B. Each follow-up then adds a dashed "planned" overlay box that promotes to solid when it ships (mirrors the existing dashed M4 box).

## 9. Out of scope

- Any change to the engine-isolation filter, the maturity join, or the scorer.
- Promoting `monitor_forward` into `--all` or making it gate.
- A configurable WARN threshold (reuse the existing sufficiency constant; add a knob only if later needed).
