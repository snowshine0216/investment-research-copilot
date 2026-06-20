# MASTER-SPEC — Monitor forward-eval engine-drop WARN (Follow-up 1)

**Mode:** spec (single feature)
**Run dir:** `docs/2026-06-20-monitor-engine-drop-warn/`
**Source spec:** [`docs/superpowers/specs/2026-06-19-monitor-forward-engine-drop-warn-design.md`](../superpowers/specs/2026-06-19-monitor-forward-engine-drop-warn-design.md)
**Date:** 2026-06-20

## What this is

Add one **attribution-only** diagnostic row — `engine_population` — to the
`irc eval monitor_forward` stage report. After an `_ENGINE_VERSION` bump the
append-only `forward_ledger.jsonl` strands prior-engine rows, leaving a thin
matured target-engine population. The stage *already* WARNs at low-n; what's
missing is **attribution** — telling "thin because of the engine reset" apart
from "thin because the signal is generally young." This feature adds exactly
that one bit, as a `state` code on a new `MetricReport`. It **never changes
`overall` or `rc`** (D3): it only flips to `engine_transition` when
`publishable_bias_directional` is *already* `insufficient_data` (and thus
already WARN).

## Scope classification

| # | Item | Class | Notes |
|---|------|-------|-------|
| 001 | `engine_population` diagnostic row: pure `engine_population_status` in `evals/monitor_forward/metrics.py`; runner append in `evals/monitor_forward/runner.py`; name-keyed `details["engine_population"]` block (incl. mandatory `ci_low/ci_high = None`); the 7 tests in §7; CONTEXT.md edits (§9) + ADR 0019 addendum land at ship | **IN** | The whole FU1 code+tests+docs surface |

### Out of scope / deferred (documented, not silently dropped)

These come from the source spec's §8 / §10 and are explicitly **not** owned by
this run:

- **§8.1 — Standalone as-built doc-sync diagram PR** (`evals/docs/monitor-eval-workflow.html`, `docs/diagrams/monitor-workflow.html`). The spec marks this *"shared #168 doc-debt, **not** FU1-owned"* and a prerequisite for **both** FU1 and Spec B. It is a **separate PR**, not part of this implementation run. → `SKIPPED.md`.
- **§8.3 — FU1 diagram overlay** (dashed `engine_population` box on the `monitor_forward` node, promoted to solid at ship). The spec sequences this to *wait for §8.1*. Deferred follow-up. → `SKIPPED.md`.
- **§10 — engine-isolation filter / maturity join / scorer changes, `--all` promotion, gating, configurable WARN threshold.** Hard out-of-scope by the spec.

CONTEXT.md edits (§9) and the ADR 0019 addendum (already drafted in the working
tree) **are IN** — they document the shipped decision and land with the FU1
merge (ADR addendum is committed with the design artifacts; CONTEXT.md edits are
authored/committed at ship per §9).

## Acceptance criteria (from source spec §7)

1. Pure helper truth table: only `(n_excluded_engine > 0, headline_state == "insufficient_data")` → `("WARN", "engine_transition")`; the other three cells → `("PASS", "ok")`.
2. Runner integration: ledger with `engine_mismatch > 0` AND thin `publishable_bias_directional` → `engine_population` report `status="WARN"`, `details["engine_population"]["state"] == "engine_transition"`, `ci_low is None`, `ci_high is None`; `run()` returns `rc 1`.
3. `len(report["metrics"]) == 4` (was 3) and `"engine_population"` present; `build_metric_reports`'s own `len(reports) == 3` test stays green (unchanged).
4. Empty-ledger guard: `engine_population` row `status="PASS"`, `value == 0.0`, state `"ok"`, `n_target_raw == 0`, no crash (do NOT assert whole-stage PASS).
5. Command-edge CI-None preservation through `_predictive_panel_model(...)`: `engine_population` view `ci_low is None`.
6. Pure renderer: `PredictiveMetricView(name="engine_population", …, ci_low=None, …)` → HTML contains `"engine_population"`, `"CI pending"`, and `"n/a"` for all three baseline cells.
7. DELETE the old planned `rank_ic state == "undefined" → WARN` test (it would encode the bug D2 removed).

## Invariants (source spec §6)

- Never gates the brief; never changes `rc` (`monitor_forward` stays `active`, out of `--all`, `rc 0/1/2`).
- Pure metric — no filesystem/network/LLM; reads counts already computed.
- Back-compat — single-engine ledgers (`engine_mismatch == 0`) and pre-bump runs stay PASS / `"ok"`.
- No silent caps — `details.json.excluded_by_engine` still carries raw counts.
- Size budget — one small pure fn + one `MetricReport`.
