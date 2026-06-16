# Item 001 — M0: eval spine

**Run:** `monitor-eval-m0-m1` · **Slug:** `m0-eval-spine` · **Branch:** `monitor-eval`
**Source (authoritative):** [`docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md`](../../superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md) (rev 3) — **§2 (all of "## 2. M0 — eval spine")** + §5 (error handling) + §6 (testing, M0 rows) + §7 (pinned decisions).
**Locked contracts (authoritative):** roadmap [`2026-06-16-monitor-eval-roadmap.md`](../../superpowers/specs/2026-06-16-monitor-eval-roadmap.md) §3.5 (gate semantics), §3.6 (`eval_trace.json` schema), §3.2b/§3.2d (ledger row + idempotency).
**Domain terms:** [`CONTEXT.md`](../../../CONTEXT.md) "Monitor vertical"; [ADR 0017](../../adr/0017-monitor-evidence-isolation.md).

> **This is a faithful EXTRACTION of an already-reviewed (rev 3) design slice, not a fresh design.**
> The source §7 pinned decisions and the roadmap §3.5/§3.6/§3.2 schemas are authoritative and
> reproduced verbatim where load-bearing. This spec adds only item-level precision (exact edge
> cases, the M0/M1 seam) and resolves ambiguities the source left open at the M0 boundary —
> recorded under "Open questions resolved". It does **not** re-open or contradict any resolved
> finding or pinned decision.

---

## Goal

Lay the **eval spine** for the `irc monitor` vertical: a tracer-bullet validation track that starts
the day M0 ships. Every monitor run persists one new per-run artifact
`outputs/<date>/monitor/eval_trace.json` (source §2.1, schema roadmap §3.6) — a lossless,
degradation-safe serialization of each fund's resolved params, NAV, **unified** evidence pool,
factor scores, signal, impacts, narrative, and gate decision — alongside an append-only forward
ledger (`data/monitor/forward_ledger.jsonl`) that starts the track-record clock. M0 adds the pure
eval cores (`structural`, `staleness`, `gate`, plus `latest_stage_report`), the `monitor_signal`
artifact eval (oracle/citation/NAV metrics) with its shared-infra plumbing (`SKIPPED` status +
`EVAL_RC_SKIPPED=3`, a `live_gated` registry lifecycle, the `eval-live` spend scope, and the
`eval_cmd` gate/skip path), and wires the in-run **structural** health into the live run so a fund
whose own run is structurally unsound is rendered `EVAL_GATED` with a Validation panel that keeps the
gap honest. M0 gates **only** on the always-fresh in-run `monitor_signal` structural health
(`GATING_STAGES_M0 = frozenset({"monitor_signal"})`); the LLM suites are registered as `live_gated`
placeholders that **cannot** gate yet (that flip is M1). The four legacy monitor dumps are unchanged.

---

## Acceptance criteria

Each criterion is independently verifiable (test name or grep-able artifact assertion). All new code
is TDD test-first; all pure cores are unit-testable without mocks.

### A. `eval_trace.json` serialization (§2.1, roadmap §3.6)

1. **Artifact emitted per run.** A successful `run_monitor` writes
   `outputs/<date>/monitor/eval_trace.json` via `atomic_write_text` (the integration test asserts the
   file exists after a run). Top-level keys: `{schema_version, engine_version, run_date, funds}`;
   `funds` is keyed by `fund_id`.
2. **Per-fund schema matches roadmap §3.6** for each fund: `resolved` =
   `{analysis_profile, weights, bands, minimum_confidence}` (from the `MonitorFund`); `nav` =
   `{as_of_date, latest_unit_nav, nav_acc, acc_series, obs_count, max_gap_days}`; `evidence_pool` (a
   list of `{source,title,date,url,owner_fund_id,citation_id}`); `factor_scores` (all entries:
   `{name,value,eligible,reason,confidence}`); `signal` (status/bias/composite/signal_confidence/
   available_weight/present_families/contributions/divergence_codes); `impacts` =
   `{macro:[{key,weight,impact,confidence,citation_ids}], constituent:[…]}`; `narrative` =
   `{status, price_action:[…], signal_rationale:[…], risk:[…]}` each claim carrying
   `{claim,attribution_strength,citation_ids}`; `gate` = `{suppressed, failed_stages, reason}`;
   `published_state`; `validation_badge`. `build_eval_trace` is a **pure** function with signature
   `build_eval_trace(items, *, engine_version, run_date) -> dict` where `items` is a tuple of
   `(MonitorFund, FundView, GateDecision, FundTraceBundle)`.
3. **`build_eval_trace` is unit-tested** for a round-trip (build → JSON dump → reload → field
   equality) on a constructed fixture with at least one good fund and one degraded-NAV fund.

### B. Degradation-safe NAV (§2.1, §2.3 — resolves rev-3 P1)

4. **No IndexError on `nav_series=()`.** For a fund whose `view.nav_series == ()` (the degraded path,
   `_make_view` emits `nav_series=()`, `as_of_date="N/A"`), serialization yields `nav_acc=None`
   (JSON `null`), `obs_count=0`, `max_gap_days=None`, `latest_unit_nav=view.latest_nav` (0.0 per
   `_make_view`). Asserted by a unit test that builds a trace from a `nav_series=()` `FundView`
   without raising. (`nav_acc = view.nav_series[-1][1] if view.nav_series else None`.)
5. **Degraded NAV → FAIL → EVAL_GATED, ledger row still written.** A fund with `obs_count == 0` →
   `nav_quality` FAIL → `monitor_signal_health` FAIL → `apply_eval_gate` suppresses →
   `published_state == "EVAL_GATED"`; its ledger row is still produced with `nav_acc == null`. End-to-
   end integration test: a fund with injected `nav_series=()` is `EVAL_GATED` in the trace AND has a
   forward-ledger row carrying `nav_acc: null`, with no exception.

### C. Unified evidence pool — macro AND constituent citations resolve (§2.1/§2.2 — resolves rev-3 P0)

6. **`FundTraceBundle` carries un-aggregated inputs.** Frozen dataclass `FundTraceBundle(fund_id,
   macro_impacts: tuple[ValidatedImpact,...], constituent_impacts: tuple[ValidatedImpact,...],
   constituent_pool: tuple[EvidenceItem,...])`. For non-lookthrough funds (gold/qdii, no constituent
   leg) `constituent_impacts == ()` and `constituent_pool == ()`.
7. **Trace serializes a unified pool.** `eval_trace.json`'s per-fund `evidence_pool` =
   `dedup_by_citation_id(view.evidence_pool + bundle.constituent_pool)` (macro pool ⊕ constituent
   pool, deduped by `citation_id`). Unit-tested: overlapping `citation_id`s appear once; both pools'
   ids are present.
8. **Constituent citation resolves (not a false FAIL).** An active-fund fixture whose constituent
   impact cites a `const_pool`-only `citation_id` → `citation_integrity` PASS against the unified pool
   (test asserts PASS, not FAIL).

### D. The four pure cores (§2.2–§2.4)

9. **Types** (`src/irc/monitor/eval/types.py`, all frozen dataclasses + literals):
   `HealthStatus = Literal["PASS","WARN","FAIL","UNKNOWN"]`, `Badge =
   Literal["validated","caveated","gated"]`, `StageHealth(stage,status,reasons)`,
   `GateDecision(fund_id,suppressed,failed_stages,badge,reason)`, `FundTraceBundle` (per #6).
10. **`structural.py`** (pure) exposes `signal_consistency`, `citation_integrity`, `nav_quality`,
    `monitor_signal_health` over one fund's trace projection. `monitor_signal_health` = worst-wins
    over the three, `stage="monitor_signal"`. Unit-tested per check:
    - `signal_consistency`: PASS when `|composite − Σcontribution| < 1e-9` and `|Σrenorm_weight − 1| <
      1e-9` and (`bias is None` iff `status != "ok"`); FAIL otherwise.
    - `citation_integrity`: PASS when every narrative claim `citation_id` AND every impact (macro +
      constituent) `citation_id` ∈ the unified `evidence_pool` ids; FAIL on any unresolved id.
    - `nav_quality(t, *, minimum_observations, stale_days)`: FAIL when `obs_count == 0` /
      `nav_acc is None` / `as_of == "N/A"`; FAIL when `obs_count < minimum_observations`; FAIL when a
      *parseable* `as_of` is older than `stale_days` (default **7** calendar days); WARN on a single
      gap `> 5d`; else PASS. `as_of` is compared only when it parses as a date (guards `"N/A"`).
11. **`staleness.py::resolve_health`** (pure): `resolve_health(report: StageReport | None, *, now,
    stale_after_days) -> StageHealth`. `None` → `UNKNOWN("absent")`; `overall == "SKIPPED"` →
    `UNKNOWN("skipped")`; `ran_at` older than `stale_after_days` → `UNKNOWN("stale")`; else PASS/WARN/
    FAIL passthrough. `stale_after_days` default **14** (constant `STALE_AFTER_DAYS`). Unit-tested for
    absent / skipped / stale / fresh.
12. **`latest_stage_report`** (new `evals/_shared/latest_report.py`, EDGE read):
    `latest_stage_report(repo_root, stage, *, today_iso=None) -> StageReport | None`. Scans
    `outputs/<YYYY-MM-DD>/evals/<stage>/report.json`, returns the report from the **greatest date-dir
    ≤ today** (Asia/Shanghai date ordering), parsed to `StageReport`; `None` if none. Tested: absent →
    `None`; multiple dates → newest; today present → today; a SKIPPED-today report resolves (via
    `resolve_health`) to `UNKNOWN`. (In M0 unit-tested only; not yet wired into the gate — see #25.)

### E. `gate.py` — the gate (§2.5, roadmap §3.5)

13. **`apply_eval_gate(signal, *, health, gating_stages) -> GateDecision`** (pure) considers only
    `h.stage ∈ gating_stages`. Resolution per roadmap §3.5: a fresh `FAIL` ⇒
    `suppressed=True, badge="gated"`, `failed_stages` lists the failing gating stages; else any
    `WARN`/`UNKNOWN` ⇒ `badge="caveated"`; else `badge="validated"`. Unit-tested for each branch.
14. **`published_state(signal, gate) -> str`** (pure): `"NO_CALL"` if `signal.status != "ok"`;
    `"EVAL_GATED"` if `gate.suppressed`; else `signal.bias`. The `NO_CALL` precedence over
    `EVAL_GATED` is tested (a `status != "ok"` fund renders `NO_CALL`, not `EVAL_GATED`).
15. **`GATING_STAGES_M0 = frozenset({"monitor_signal"})`** is defined in `gate.py` and asserted by a
    test (so M1's `GATING_STAGES_M1` can extend it without redefining the base).

### F. `forward_log.py` — ledger (§2.6, roadmap §3.2b/d)

16. **`ledger_row(...) -> dict`** (pure) produces a row matching roadmap §3.2b:
    `{run_date, fund_id, written_at, raw_status, raw_bias, raw_composite, signal_confidence,
    published_state, gate_reason, nav_acc, nav_unit, nav_basis="coalesce(nav_acc,nav)", as_of_date,
    manifest_versions}`. `nav_acc` is the COALESCE(nav_acc, nav) perf basis (NOT `nav_unit`). Both
    raw (pre-gate) verdict and `published_state` are stored. Unit-tested for field presence + the
    `nav_basis` literal.
17. **`append_ledger(path, rows) -> None`** is a **real append** (`open(path, "a")`), one JSON object
    per line (JSONL) — no read-modify-write. A test writes two batches to the same file and asserts
    both batches' lines survive (append, not overwrite). Write failure is logged and swallowed (never
    raises) — tested by pointing at an unwritable path and asserting no exception.
18. **`latest_per_key(rows) -> list[dict]`** (pure) dedups by `(run_date, fund_id)` keeping the max
    `written_at` (tie → last line). Unit-tested: a rerun day (two rows same key) collapses to the
    last-`written_at` row.

### G. `evals/monitor_signal/` + runner (§2.7)

19. **Metrics** (`evals/monitor_signal/metrics.py`, pure over the trace dict):
    `oracle_signal_match(trace) -> float` (fraction of funds where `compute_signal` re-run from
    `resolved` + `factor_scores` equals the persisted `signal`); `citation_resolution(trace) -> float`
    (fraction of citations resolving into the unified `evidence_pool`); `nav_completeness(trace) ->
    float` (fraction of funds with `obs_count ≥ minimum_observations`). Each unit-tested.
20. **Runner** (`evals/monitor_signal/runner.py`) follows the `evals/scoring/runner.py` pattern:
    `locate(repo_root, ("monitor/eval_trace.json",))` → metrics → `StageReport` → `write_report`;
    missing input → `missing_input_report` FAIL (rc 2). Thresholds: `oracle_signal_match` fail_below
    **1.0**; `citation_resolution` fail_below **1.0**; `nav_completeness` warn_below 0.85 / fail_below
    0.6. **Runner test:** on a good fixture trace → PASS (rc 0); on a trace whose `signal.composite`
    is tampered (oracle mismatch) → FAIL (rc 2).

### H. Shared-infra changes (§2.7)

21. **`evals/_shared/status.py`:** add `"SKIPPED"` to the `Status` literal. `worst_status` is
    **unchanged** (a test asserts `worst_status` still ranks only PASS/WARN/FAIL and is never passed
    `SKIPPED`).
22. **`evals/_shared/missing_input.py`:** add `EVAL_RC_SKIPPED = 3` and
    `skipped_report(stage, reason) -> StageReport` with `overall="SKIPPED"`. Unit-tested.
23. **`evals/_shared/registry.py`:** add `live_gated` to `Lifecycle`; add `is_live_gated(spec)`.
    Register `EvalStageSpec("monitor_signal", "evals.monitor_signal.runner", "active", True)`; register
    `monitor_impact` and `monitor_narrative` as `live_gated, in_all_suite=False` **placeholders** (no
    runner module exists yet in M0 — M1 supplies it). Tests: `active_suite_stages()` **includes**
    `monitor_signal` and **excludes** `monitor_impact`/`monitor_narrative`; `is_live_gated` is True for
    the two placeholders.
24. **`evals/_shared/latest_report.py`** exists per #12.

### I. `eval_cmd` live_gated SKIPPED + spend gate (§2.7 — resolves rev-2 P0b/P2)

25. **`live_gated` SKIPPED path:** when `is_live_gated(spec)` and `IRC_RUN_LIVE_LLM_EVAL` is **unset**,
    `eval_cmd` writes a `skipped_report` (under today's China date), prints "env absent; not executed",
    and returns `EVAL_RC_SKIPPED` (3). **Test:** `irc eval monitor_impact` without the env →
    rc 3 and a `report.json` with `overall == "SKIPPED"`.
26. **`eval-live` spend scope:** `scope.py` adds `COMMAND_TASKS["eval-live"] = ("monitor_impact",
    "monitor_narrative")` with **no** search providers. **Guard test** (mirrors
    `tests/spend/test_scope.py`): `resolve_scope("eval-live").tasks == {monitor_impact,
    monitor_narrative}` and `.search_providers == frozenset()`. The
    `test_every_llm_yaml_task_is_mapped_somewhere` completeness test still passes (both tasks already
    in `ALL_LLM_TASKS` via the `monitor` command).
27. **`eval_cmd` gate-before-runner:** before dispatching a `live_gated` stage **with the env set**,
    `eval_cmd` calls `preflight_gate(repo_root, "eval-live")`; on non-zero rc it returns that rc and
    **does not invoke the runner**. **Guard test** (mirrors `tests/commands/test_gate_wiring.py`):
    monkeypatch the gate to return 5 → `run_eval` returns 5 and the runner module's `run` is never
    called.

### J. Live-run integration + render (§2.8)

28. **`_process_fund` return type → `(view, cost_history, FundTraceBundle)`.** The bundle captures
    `impacts.impacts` (macro `ValidatedImpact`s), `const_impacts.impacts` (constituent), and
    `const_pool` (the constituent `EvidenceItem` pool) — all already in scope — before the lossy
    `ImpactRow` step. For non-lookthrough funds, `constituent_impacts=()` / `constituent_pool=()`.
    Tested by a unit test on `_process_fund`'s return shape.
29. **`run_monitor` wiring order** (before `_write_outputs`): per fund compute
    `health = (monitor_signal_health(trace_fund, …),)` then
    `gate = apply_eval_gate(view.signal, health=health, gating_stages=GATING_STAGES_M0)`; then
    `build_eval_trace(...)` → `atomic_write_text("eval_trace.json")`; then
    `append_ledger(data/monitor/forward_ledger.jsonl, [ledger_row(...) per fund])`; then render with
    `gate`/`published_state`. `eval_trace`/ledger write failures are logged + swallowed (the brief
    still renders — integration test injects a write failure and asserts the HTML still emits).
30. **Render — EVAL-GATED badge + validation chips + Validation panel:**
    - `render_html.py` `_badge` keys off `published_state`: `EVAL_GATED` → a distinct gray
      "EVAL-GATED 🛡" badge (CSS class `eval-gated`), visually separate from `NO_CALL` and `NEUTRAL`.
    - each published bias shows a small **validation chip** from `gate.badge` (`validated` ✓ /
      `caveated` ⚠).
    - new pure `src/irc/monitor/eval/panel.py` renders a **Validation** section: one row per gating
      stage with `overall`, `ran_at`, and per-fund badge counts; in M0 the only row is
      `monitor_signal`. `panel.py` is unit-tested (snapshot).
31. **Integration:** an injected **stale NAV** (NAV older than `stale_days`) → that fund is
    `EVAL_GATED` AND a visible panel/reason names the staleness; asserted end-to-end.

### K. Acceptance guards (§6 last row)

32. **Grep-style acceptance:** a test asserts `eval_trace.json` is emitted by a run AND that a written
    ledger row carries `nav_basis == "coalesce(nav_acc,nav)"` (not unit NAV).

---

## Non-goals

Explicitly **out of scope for item 001** (these are item 002 / M1, or M2–M4 in the parent roadmap —
do not build them here):

- **All of M1 (item 002):** synthetic/adversarial corpora `src/irc/monitor/eval/cases/{impact,
  narrative}/*.json`; pure scorers `metrics_impact.py` / `metrics_narrative.py`; the `live_gated`
  **runners** `evals/monitor_impact/runner.py` + `evals/monitor_narrative/runner.py`; the gating flip
  `GATING_STAGES_M1 = GATING_STAGES_M0 | {"monitor_impact","monitor_narrative"}`. M0 lands only the
  `eval-live` *scope*, the registry *placeholders*, and the `eval_cmd` gate/skip path — the runners
  that call `record_command_run` and the actual LLM calls are M1.
- **The source spec's §9 / roadmap M2–M4:** retro backtest, the forward-ledger **scorer** (M0 only
  *writes* the ledger; the scorer that reads it via `latest_per_key` is M3), ablation, the ADR,
  property-based deterministic suites beyond the M0 oracle, `irc eval --live` aggregate, and any
  weight/band changes or auto-tuning. No human gold sets.
- **No re-design of the locked contracts.** `eval_trace.json` (§3.6), gate semantics (§3.5),
  `EVAL_RC_SKIPPED=3` (§3.1), and ledger idempotency (§3.2d) are reproduced, not revisited.

---

## Constraints

- **FP / immutability (CLAUDE.md, ADRs).** Pure functions, `const`-by-default, never mutate
  arguments. The eval cores (`trace`, `structural`, `staleness`, `gate`, `forward_log.ledger_row` /
  `latest_per_key`, `panel`, `metrics`) are **pure** and unit-testable **without mocks**. Frozen
  dataclasses; new instances via spread/`dataclasses.replace`.
- **Effects at the edges.** Only `append_ledger`, `latest_stage_report` (read), the `eval_cmd`/
  `monitor_cmd` orchestration, and `atomic_write_text` touch I/O. Per roadmap §3.3, `src/irc/monitor/
  eval/*` must **not** import AkShare, providers, the LLM gateway, settings, or the filesystem; edges
  are evaluated through their persisted artifacts.
- **TDD test-first.** Red → green → refactor for every new module; test file mirrors source
  (`foo.py` → `tests/.../test_foo.py`).
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal); extract helpers over nesting > 3.
- **Secrets in `.env` only.** No inline keys; `IRC_RUN_LIVE_LLM_EVAL` is the M0 skip toggle (it gates
  nothing paid in M0 — the runners are M1).
- **The four legacy monitor dumps are unchanged** (`signal.json`, `impacts.json`, `narrative.json`,
  `monitor.json`); `eval_trace.json` is strictly **additive**.
- **Degrade-not-crash** for trace/ledger write failures (log + continue; brief still renders) and for
  malformed/missing trace funds (FAIL → `EVAL_GATED`, the safe default).
- **Citation ID format is locked at 16 hex chars**, regex `\[ref:[0-9a-f]{16}\]` (ADR 0001/0017). The
  monitor's `EvidenceItem.citation_id` preimage is the monitor's own (sha256(owner_fund_id:url_or_
  fallback:date)) and is **not** comparable to opportunity/memo ids — pools stay separate (ADR 0017).
- **The forbidden `基金概况` indicator** must never appear in fetch code (acceptance test greps the
  literal) — M0 adds no fetch code, but any new fetch-adjacent edge must respect it.

---

## Open questions resolved during brainstorming

> Each was genuinely under-specified at the M0 boundary. Resolutions are derived from MASTER-SPEC +
> the source design + the grounded code; none contradict a pinned decision or resolved finding.

**OQ1 — Oracle recompute mechanics for `oracle_signal_match`.** Source §2.7 says "reconstruct a
minimal `MonitorFund` from `resolved` + factor_scores and re-run the pure core" but doesn't pin the
comparison. **Resolved:** rebuild `MonitorFund` using only the four `compute_signal` inputs
(`id`/`weights`/`bands`/`minimum_confidence` from `resolved`; the other `MonitorFund` fields are
placeholders since `compute_signal` ignores them — verified: `signal.py` reads only those four), and a
`FactorScore` tuple from `trace.factor_scores`; re-run `compute_signal`; compare against the persisted
`signal`. Comparison is on the **rounded** persisted fields (`composite`/`signal_confidence` are
already 4dp-rounded in `SignalRecord`), so equality is exact float equality on rounded values, not an
epsilon. Rationale: `compute_signal` is deterministic and rounds before storing, so a faithful
recompute is byte-identical; `fail_below=1.0` (any mismatch is a real bug) only holds under exact
equality.

**OQ2 — `max_gap_days` definition and the WARN gap rule.** Source §2.1 says `max_gap_days =
<computed> if obs_count >= 2 else None`; §2.3 says "a 1-row gap > 5d → WARN". **Resolved:**
`max_gap_days` = the maximum calendar-day delta between consecutive dates in `acc_series` (which is
`view.nav_series`, the accumulated-NAV series per `_make_view`); `None` when `obs_count < 2`. The WARN
trigger fires when `max_gap_days > 5` **and** no FAIL condition applies (FAIL wins under worst-wins).
Rationale: the only series in the trace is the accumulated NAV series (`nav.acc_series` →
`view.nav_series`), so "row" = an `acc_series` point; gap is measured between adjacent observation
dates. This keeps `nav_quality` computable purely from the trace projection.

**OQ3 — M0/M1 seam for `latest_stage_report` + `resolve_health`.** They are M0 code (§2.4) but their
only *consumer* (the gate reading the LLM suites) is M1 (§3.4). **Resolved:** M0 **builds and
unit-tests** both, but does **not** wire them into `apply_eval_gate` — M0's only gating input is the
in-run `monitor_signal_health` (always fresh, never resolved through `latest_stage_report`). The gate
in `run_monitor` is fed `health = (monitor_signal_health(...),)` only. This matches MASTER-SPEC seam
notes and roadmap §3.5 ("M0's only gating input is in-run-fresh") and keeps M1's flip a pure addition.

**OQ4 — Where `EVAL_RC_SKIPPED` / `eval-live` gate live vs. who exercises them.** Per MASTER-SPEC seam
notes. **Resolved:** M0 lands the `EVAL_RC_SKIPPED=3` constant, `skipped_report`, the `eval-live`
scope, the registry `live_gated` placeholders, and the `eval_cmd` skip + `preflight_gate("eval-live")`
gate-before-dispatch. M0's guard tests pin (a) `resolve_scope("eval-live")` and (b) gate-blocks-before-
runner. The live runner's `record_command_run` **actuals** test ships with M1's runner (the code it
pins doesn't exist in M0). Rationale: tests belong with the milestone introducing the code they pin
(MASTER-SPEC seam note, verbatim).

**OQ5 — Placeholder registry rows with no runner module.** §2.7 registers `monitor_impact`/
`monitor_narrative` as `live_gated` placeholders, but their `runner_module` won't import in M0.
**Resolved:** the `EvalStageSpec.runner_module` strings (`"evals.monitor_impact.runner"` /
`"evals.monitor_narrative.runner"`) are registered as forward references but the modules are **not
imported at registry load** (the registry stores module *paths*, resolved lazily via
`importlib.import_module` only in `_resolve_runner`). Because `in_all_suite=False`, `active_suite_
stages()` never resolves them, and the `eval_cmd` SKIPPED path returns **before** `_resolve_runner`
when the env is unset — so a direct `irc eval monitor_impact` in M0 never imports a missing module.
A registry test asserts importability is **not** required for `live_gated` placeholders. Rationale:
matches the existing lazy-resolution pattern in `eval_cmd._resolve_runner`; avoids a hard dependency
on M1 code from M0.

**OQ6 — `engine_version` / `manifest_versions` provenance source.** §3.6 trace and §3.2b ledger both
carry version provenance. **Resolved:** reuse the monitor's existing `Provenance.engine_version`
(`render_types.Provenance`, already assembled in the render path) as the trace `engine_version` and as
the ledger `manifest_versions` (engine + suite version map); M0 has no suite version yet, so
`manifest_versions` carries `{engine: <engine_version>}` and gains the suite entry in M1/M2. Rationale:
no new version source is introduced; this is a serialization of an existing field, consistent with the
"serialization gap, not new computation" framing in roadmap §3.6.

---

### Unresolved (escalate to grill/plan)

None at the M0 boundary. Every ambiguity above was resolvable from MASTER-SPEC + the rev-3 source
design + the grounded code without contradicting a pinned decision. One item to **flag, not change**:
the source pins `nav_quality` `stale_days` default = 7 and `STALE_AFTER_DAYS` = 14 as module
constants (§7). These are reproduced as-is; if a fund ever needs an override they are promoted to
`config/monitor.yaml` (already the pinned escalation path) — not an open question, just the documented
future path.
