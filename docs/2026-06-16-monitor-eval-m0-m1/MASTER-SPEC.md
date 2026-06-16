# MASTER-SPEC — Monitor Eval M0 + M1

**Mode:** backlog (N=2)
**Source spec:** [docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md](../superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md) (rev 3)
**Parent roadmap:** [docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md](../superpowers/specs/2026-06-16-monitor-eval-roadmap.md) (Block A, M0–M1)
**Feature branch:** `monitor-eval` (sub-item PRs land here; roll-up PR `monitor-eval → main` opened, not merged, at close-out)
**Project type:** non-web (Python `irc` CLI; post-ship verifier = `/verify`)
**PR shape:** A (per-item PRs)

## Decomposition rationale

The source spec deliberately bundles two milestones with a clean boundary the author
drew themselves (`## 2. M0 — eval spine`, `## 3. M1 — LLM suites`). M1 hard-depends on
M0 (M1's `GATING_STAGES_M1 = GATING_STAGES_M0 | {…}`, reuses `latest_stage_report`,
`resolve_health`, `apply_eval_gate`, the `eval-live` scope, and the registry placeholders
M0 lays down). Splitting yields two independently reviewable/verifiable PRs landing M0
(the spine) before M1 (the suites built on top). User-confirmed at intake.

Because the source spec is already at rev 3 (two review rounds resolving P0/P1/P2 findings),
the per-item **spec (brainstorming)** subagent's job is **faithful extraction + refinement
of the relevant milestone slice of this already-reviewed design — NOT open-ended
re-exploration.** The pinned decisions in §7 of the source spec are authoritative and must
be preserved verbatim by every downstream phase.

## IN-scope items

### 001 — M0: eval spine
**Slug:** `m0-eval-spine`
**Source:** §2 (all of `## 2. M0 — eval spine`) + §5 error-handling + §6 testing (M0 rows) + §7 pinned decisions (M0).

Scope:
- **§2.1** `eval_trace.json` serialization — new pure `src/irc/monitor/eval/trace.py::build_eval_trace`; per-run artifact `outputs/<date>/monitor/eval_trace.json` (the 4 legacy dumps unchanged). Degradation-safe NAV fields (`nav_acc=None`, `obs_count=0` when `nav_series=()`). Unified `evidence_pool = dedup_by_citation_id(view.evidence_pool + bundle.constituent_pool)`.
- **§2.2** `src/irc/monitor/eval/types.py` — `HealthStatus`, `Badge`, `StageHealth`, `GateDecision`, `FundTraceBundle` (frozen dataclasses).
- **§2.3** `src/irc/monitor/eval/structural.py` — `signal_consistency`, `citation_integrity`, `nav_quality`, `monitor_signal_health` (worst-wins). NAV stale_days default 7.
- **§2.4** `src/irc/monitor/eval/staleness.py::resolve_health` (STALE_AFTER_DAYS default 14) **+** new `evals/_shared/latest_report.py::latest_stage_report` (China-date max ≤ today; EDGE read).
- **§2.5** `src/irc/monitor/eval/gate.py` — `apply_eval_gate`, `published_state`; `GATING_STAGES_M0 = frozenset({"monitor_signal"})`.
- **§2.6** `src/irc/monitor/eval/forward_log.py` — `ledger_row` (pure), `append_ledger` (EDGE, real append-mode JSONL `open(path,"a")`), `latest_per_key` (pure, last-`written_at`-wins dedup).
- **§2.7** `evals/monitor_signal/{__init__,runner,metrics}.py` (oracle/citation/nav metrics; thresholds locked) **+ shared-infra changes**: `evals/_shared/status.py` (+`SKIPPED` literal, `worst_status` unchanged), `evals/_shared/missing_input.py` (+`EVAL_RC_SKIPPED=3`, `skipped_report`), `evals/_shared/registry.py` (+`live_gated` Lifecycle, `is_live_gated`; register `monitor_signal` active + `monitor_impact`/`monitor_narrative` as `live_gated, in_all_suite=False` **placeholders**), `src/irc/spend/scope.py` (+`COMMAND_TASKS["eval-live"]`), `src/irc/commands/eval_cmd.py` (live_gated SKIPPED path + `preflight_gate("eval-live")` before dispatching a live stage).
- **§2.8** live-run integration: `_process_fund` return type → `(view, cost_history, FundTraceBundle)`; `run_monitor` collects `(fund, view, bundle)`, builds trace + ledger + gate before `_write_outputs`; render (`render_html.py` + new `src/irc/monitor/eval/panel.py`): `eval-gated` badge, validation chips, Validation panel section.

Acceptance highlights (full list authored in `items/001-spec.md`): trace emitted per run; degraded-NAV fund → `EVAL_GATED` + ledger row with `nav_acc=null` (no IndexError); constituent citations resolve against the unified pool; `irc eval monitor_signal` PASS on good fixture / FAIL on tampered trace; `irc eval monitor_impact` without env → SKIPPED rc 3; spend-wiring guard tests pass.

### 002 — M1: LLM suites
**Slug:** `m1-llm-suites`
**Source:** §3 (all of `## 3. M1 — LLM suites`) + §5 (LLM-suite degradation) + §6 (M1/live rows) + §7 (M1 decisions).
**Depends on:** 001 (registry placeholders, `eval-live` scope, `eval_cmd` gate/skip path, `latest_stage_report`, `resolve_health`, `apply_eval_gate`, `GATING_STAGES_M0`).

Scope:
- **§3.1** synthetic/adversarial corpora `src/irc/monitor/eval/cases/{impact,narrative}/*.json` (directional-strong/neutral, contradiction, injection, citation-discipline; citation-resolve, entailment-ablation, attribution-honesty, no-numbers, injection).
- **§3.2** pure scorers `src/irc/monitor/eval/metrics_impact.py` (`sign_accuracy`, `magnitude_band_pass`, `injection_resistance`, `citation_validity`) and `metrics_narrative.py` (`citation_resolution`, `entailment_ablation_pass`, `attribution_honesty`, `hallucination_rate`); thresholds per §3.2 (tunable, calibration deferred to M4).
- **§3.3** `live_gated` runners `evals/monitor_impact/runner.py` + `evals/monitor_narrative/runner.py`: load `cases/`, run real LLM via gateway (MiniMax route), score with pure metrics, write `StageReport`. Gated by `IRC_RUN_LIVE_LLM_EVAL=1`; budgeted by `preflight_gate("eval-live")` + `record_command_run` (the **only** M1 paid surface).
- **§3.4** flip to gating in the live run: `GATING_STAGES_M1 = GATING_STAGES_M0 | {"monitor_impact","monitor_narrative"}`; each resolves `resolve_health(latest_stage_report(...), stale_after_days=14)` → `apply_eval_gate`. Fresh FAIL ⇒ `EVAL_GATED`; SKIPPED/stale/missing ⇒ `caveated` (fail-open).

Acceptance highlights (full list in `items/002-spec.md`): pure scorers correct on canned outputs; runners SKIPPED rc 3 without env; gated live-LLM test (double-gate `pytest.mark.live_llm` + `IRC_RUN_LIVE_LLM_EVAL=1`) reports PASS on current prompts; live run gates on a fresh-FAIL impact/narrative report, fail-open on stale/missing.

## OUT-scope items

None from this spec. The source spec's §9 "Out of scope" (retro backtest, ledger scorer,
ablation, the ADR, property-based deterministic suites, `irc eval --live`, weight/band
changes) are **M2–M4 milestones** — they are not items in this run at all (not deferred
sub-tasks of M0/M1). They live in the parent roadmap. `SKIPPED.md` is therefore empty.

## Seam notes (for spec/grill/plan subagents)

- The `eval-live` spend **scope** + `eval_cmd` **preflight/skip path** are M0 infra (§2.7), but
  are only *exercised* by M1's live runners (§3.3). M0 lands the scope, the registry
  placeholders, and the `eval_cmd` gate; M1 lands the runners that call `record_command_run`.
  The spend-wiring **guard tests** (§6) belong with whichever milestone introduces the code
  they pin: scope + eval_cmd-gate-before-runner tests → M0; live-runner `record_command_run`
  actuals test → M2-style live, but the runner+record wiring itself is M1.
- §2.7 registers `monitor_impact`/`monitor_narrative` as `live_gated` **placeholders** in M0 so
  `--all` excludes them and the SKIPPED path works before M1 supplies the runner module.
