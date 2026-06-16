# Monitor Validation & Evaluation — Roadmap

**Status:** Draft for review — rev 4 (2026-06-16, third review-block resolved)
**Owner:** Xue Yin
**Relates to:** [CONTEXT.md](../../../CONTEXT.md) "Monitor set" · [ADR 0017](../../adr/0017-monitor-evidence-isolation.md) · [2026-06-15 monitor daily report design](2026-06-15-monitor-daily-report-design.md) · existing eval surface [evals/_shared/registry.py](../../../evals/_shared/registry.py) · [eval_cmd.py](../../../src/irc/commands/eval_cmd.py)
**Umbrella for:** per-milestone design specs + plans (this doc is the map, not the build instructions).

> **Rev-4 changelog (resolves 2026-06-16 third review block).** New §3.6 pins the **persisted
> `eval_trace.json` artifact** so M0's edge/oracle metrics have the inputs they require (P1a); §3.1
> gives `SKIPPED` a concrete **`EVAL_RC_SKIPPED=3` return-code contract** (P1b); §3.5 replaces the
> contradictory "assert only once stages pass" wording with an explicit **publish invariant +
> `validated`/`caveated`/`gated` badge** (P1c). Rev-2 and rev-3 resolutions remain.
>
> **Rev-3 changelog (resolves 2026-06-16 second review block).** §3.1 + §3.5 define how the
> **live-LLM suites coexist with `irc eval --all`** without breaking the green suite, masking, or
> making live calls by default (P0); the **milestone-scoped gating set** so M0 cannot suppress
> every bias before M1 exists (P1a); a concrete **staleness / no-report fail-open policy** M0 can
> implement (P1b); and **ledger idempotency** under reruns (P2). Rev-2 (P0a/P0b/P1/edge-import/P2)
> remains as resolved.

---

## 1. The problem — the conviction gap

`irc monitor` emits a per-fund **directional bias** (`ADD_BIAS | NEUTRAL | REDUCE_BIAS`) plus
attribution claims, every day, for the 7-fund Monitor set. Today **nothing validates that any
stage is correct or useful**:

- The LLM stages (`monitor_impact`, `monitor_narrative`) are exercised only by *structural*
  tests (schema valid, citations resolve). Whether the **judgment** is right — does this
  evidence actually imply a bearish impact? is this claim grounded in its cited source? — is
  unmeasured.
- The scoring algorithm (`build_factor_scores` → `compute_signal`) has unit tests for mechanics
  but **no justification**: weights, bands, and gate thresholds (`Σw ≥ 0.60`, `≥2 families`,
  buy/sell bands) are hand-chosen and unargued.
- The output **bias has never been checked against any outcome**. We don't know if `ADD_BIAS`
  precedes higher forward NAV than `REDUCE_BIAS`, or if the signal is noise.

## 2. Validation taxonomy — three layers, three machineries

| Layer | Question | Method | Ground truth | Feasible now? |
|---|---|---|---|---|
| **A · Process trust** | Does each *stage* do what it claims? | Synthetic/adversarial suites (LLM) + property/oracle (pure) + structural health (edge artifacts) | Constructed, known-answer | **Yes**, offline |
| **B · Predictive validity** | Does the *bias* predict anything? | Retro backtest of evidence-free factors + forward-logger for the full signal | Realized forward NAV total return | Partial: deterministic core retro **now**; full signal **accrues** |
| **C · Algorithm justification** | Is the *scoring design* defensible? | Factor ablation + weight/band sensitivity + economic-rationale ADR | B's outcome data | After B has data |

**Key constraint (shapes everything):** the monitor shipped 2026-06-15, so there is ~no bias
track record yet; and the evidence pool is fetched fresh (7-day web freshness), so it **cannot
be reconstructed point-in-time**. The *full* signal can only be validated **forward**; only the
evidence-free factors (trend; later valuation/heat) can be retro-backtested.

## 3. Approach

### 3.1 Adopt the existing `evals/` surface (resolves rev-1 P2)

The repo already has an eval framework the monitor must reuse, not duplicate:

- **Per-stage** `evals/<stage>/runner.py` + `metrics.py`, registered in
  [`evals/_shared/registry.py`](../../../evals/_shared/registry.py) as an `EvalStageSpec(stage,
  runner_module, lifecycle, in_all_suite)`.
- **Offline & artifact-based** — a runner `locate`s the producer's persisted JSON under
  `outputs/<date>/…`, computes `MetricReport`s against PASS/WARN/FAIL thresholds, and writes a
  `StageReport` to `outputs/<date>/evals/<stage>/report.json`. It never re-invokes the producer.
- **CLI** `irc eval <stage>` / `irc eval --all`; rc `0=PASS / 1=WARN / 2=FAIL`, `--all` returns the
  **max rc** over every `in_all_suite=True` stage ([eval_cmd.py](../../../src/irc/commands/eval_cmd.py)).

Two eval *shapes* coexist under this one surface:

1. **Artifact evals** (existing pattern, no LLM, `in_all_suite=True`) — read
   `outputs/<date>/monitor/*.json`, recompute via the pure core, assert oracle-equality + structural
   health. `monitor_signal` is this shape and joins the default green suite.
2. **Suite/fixture evals** (new, **live-LLM, `in_all_suite=False`**) — ignore the day's artifacts;
   run a synthetic adversarial corpus through the LLM and score it. `monitor_impact` /
   `monitor_narrative` are this shape.

#### Live-LLM suites vs `irc eval --all` (resolves rev-2 P0)

The existing `--all` runs every active stage unconditionally and returns max-rc — so a live-LLM
stage in `--all` would either make paid calls by default (cost-boundary violation), FAIL the green
suite when LLM env is absent, or PASS/WARN and **mask** the missing validation. None acceptable.
Resolution — a new registry lifecycle **`live_gated`**:

- **Excluded from `--all`** (`in_all_suite=False`) → the default green suite stays cost-free and
  unbroken.
- **Double-gated** like other live tests: runs only on explicit `irc eval monitor_impact` **and**
  with `IRC_RUN_LIVE_LLM_EVAL=1` set (CI's live job). This is the only place the suite spends LLM
  budget — never the daily `irc monitor` run, never default `--all`.
- **`SKIPPED` outcome** when invoked without the env gate: a new `StageReport.overall == "SKIPPED"`
  (distinct from PASS/WARN/FAIL) — neither masks (it is not PASS) nor lies (it is not FAIL). It
  means "not executed; env absent." A convenience `irc eval --live` aggregate (runs the
  `live_gated` set) is optional, deferred to the M1 spec.

**`SKIPPED` return-code contract (resolves rev-3 P1b).** Shared constants today are
`EVAL_RC_PASS=0 / WARN=1 / FAIL=2` ([missing_input.py:20](../../../evals/_shared/missing_input.py)).
Add **`EVAL_RC_SKIPPED=3`**. Semantics:

- `live_gated` stages are **never in `--all`**, so rc 3 never enters its max-rc → the green suite is
  untouched (`--all` stays in {0,1,2}).
- Direct `irc eval monitor_impact` **without** `IRC_RUN_LIVE_LLM_EVAL` → writes
  `overall="SKIPPED"`, returns **3**, prints a clear "env absent; not executed" message.
- **Caller interpretation:** CI's *green* job never invokes these; CI's *live* job sets the env and
  expects 0/1/2 — a 3 there means **env misconfigured → fail the live job** (catches a silently
  unset key). Scripts treat 3 as "did-not-run," never as success.
- The in-monitor gate reads `StageReport.overall` (not the rc): `SKIPPED → UNKNOWN → fail-open` (§3.5).

So the monitor LLM suites are registered **`live_gated`, not `unimplemented_active`** — the
honest-FAIL `unimplemented_active` mechanism is for *in-`--all`* artifact evals; live suites use
`live_gated` + `SKIPPED` instead.

### 3.2 Data-model decisions (resolves rev-1 P0a, P0b, P1a + rev-2 P2)

**(a) Gating overlay, not a status overload.** The raw `SignalRecord` —
`status ∈ {ok, insufficient_evidence, low_confidence}`, `bias=None iff status≠ok`
([types.py:5](../../../src/irc/monitor/types.py)) — stays **the scoring function's verdict,
unchanged**. The eval gate is a **separate overlay** computed at the edge:

```
GateDecision(fund_id, suppressed: bool, failed_stages: tuple[str,...], reason: str)
published_state(signal, gate) =                       # pure, derived
    NO_CALL      if signal.status != "ok"             # existing derived label, unchanged
    EVAL_GATED   if gate.suppressed                   # NEW, visually distinct render state
    else         signal.bias
```

`EVAL_GATED` is a **distinct render label** so a reader can tell *"no signal"* (`NO_CALL`) from
*"signal suppressed pending validation"* (`EVAL_GATED`) from `NEUTRAL`. Recorded, not render-only.

**(b) Forward ledger logs the COALESCE NAV basis.** `latest_nav` is **unit NAV, display only**; all
performance math uses `COALESCE(nav_acc, nav)`
([daily design §4](2026-06-15-monitor-daily-report-design.md), [fetch.py:38](../../../src/irc/monitor/fetch.py)).
Ledger row:

```
{ run_date, fund_id, written_at,                       # written_at: idempotency tie-break (see d)
  raw_status, raw_bias, raw_composite, signal_confidence,   # the scoring fn's verdict
  published_state, gate_reason,                              # what the user saw
  nav_acc,            # COALESCE(nav_acc, nav) at as_of_date — the perf basis
  nav_unit, nav_basis="coalesce(nav_acc,nav)", as_of_date,   # provenance (NAV may lag run_date)
  manifest_versions }                                        # engine+suite versions used to gate
```

Forward return is **not** pre-stored; the M3 scorer joins each row to the fund's later `nav_acc` at
`run_date + H` per horizon `H`.

**(c) Ledger records BOTH raw and published.** Predictive validity must score the **raw scoring
function** (`raw_bias`/`raw_composite`), so the ledger stores the pre-gate verdict; it also stores
`published_state`. This requires **enriching the monitor's persisted output** in M0: today
`signal.json` holds only `{status, bias}` ([monitor_cmd.py](../../../src/irc/commands/monitor_cmd.py));
M0 adds the factor-trace needed for both the ledger and the `monitor_signal` oracle recompute.

**(d) Ledger idempotency under reruns (resolves rev-2 P2).** `run_monitor` always writes when
invoked and has no "already logged today" guard, so retries / manual reruns can duplicate a
`(run_date, fund_id)`. Decision: **append-only writer; logical key `(run_date, fund_id)`;
last-write-wins on read.**

- Writer stays a trivial atomic append (no read-modify-write on the hot path → crash-safe), tagging
  each row with `written_at`.
- A pure reader `latest_per_key(rows)` collapses to one row per `(run_date, fund_id)` by max
  `written_at` (tie → last line). The M3 scorer **dedups before** computing IC, so a rerun day is
  never double-counted. Semantics: last write of the day = "what was finally published that day."

### 3.3 What eval may import (resolves rev-1 P1)

| Code | May import | May NOT import |
|---|---|---|
| `src/irc/monitor/eval/*` (pure: structural, gate, panel, backtest, metrics) | pure monitor cores + eval's own types | AkShare, providers, LLM gateway, settings, filesystem |
| `evals/monitor_*/runner.py` (offline IO boundary) | the pure metrics above + locator/report_paths; LLM gateway **only** in the `live_gated` suite runner | — |

Edge stages (`nav_series_for`, `build_evidence_pool`) are evaluated through their **persisted
artifacts**, so eval never imports or re-invokes an edge.

### 3.4 Surface + gate; weights stay human-owned

The report shows a validation panel; a bias auto-`EVAL_GATED`s when an upstream **gating** stage
returns a fresh FAIL (§3.5). Eval *justifies and documents* weights/bands (ablation, sensitivity,
ADR) — it does **not** auto-tune them. No closed-loop calibration on tiny history.

### 3.5 Gate semantics — milestone-scoped + staleness fail-open (resolves rev-2 P1a, P1b)

**Milestone-scoped gating set.** A stage influences suppression only when its milestone marks it
`gating`; before that it is `not_yet` (the panel shows "validation pending", it never suppresses).

| Stage | M0 | M1 | M2+ |
|---|---|---|---|
| `monitor_signal` (in-run structural / oracle) | **gating** (always fresh) | gating | gating |
| `monitor_impact`, `monitor_narrative` (live suite) | `not_yet` | **gating** | gating |

So in M0 the only gating input is the **in-run structural health** of the current run (always
fresh) — the `unimplemented_active`/SKIPPED LLM placeholders **cannot** suppress any bias. This is
why M0 registers the LLM suites `live_gated`, not `unimplemented_active`.

**Per-gating-stage truth table** (the resolved-health → action the gate applies):

| Resolved health | Typical source | Gate action | Panel |
|---|---|---|---|
| PASS (fresh) | in-run structural; fresh suite `StageReport` | allow | ✓ validated |
| WARN (fresh) | " | allow | ⚠ flagged |
| **FAIL (fresh)** | " | **EVAL_GATED** (suppress) | ✗ gated + reason |
| `SKIPPED` / missing / older than `STALE_AFTER` | live suite not run / CI lagged | **allow (fail-open)** | ⚠ "unvalidated — suite not run / stale" |

**Publish invariant + validation badge (resolves rev-3 P1c).** The earlier "the report may assert a
bias only once upstream gating stages pass" wording contradicted fail-open. Replaced by an explicit
invariant in which **publishing a bias never implies it passed validation** — the badge says so:

- A fund's bias is **suppressed → `EVAL_GATED`** *iff* some **gating** stage returns a **fresh FAIL**.
- Otherwise the bias is **published**, carrying a **validation badge**:
  - **`validated`** — every gating stage is fresh-PASS.
  - **`caveated`** — at least one gating stage is WARN / `SKIPPED` / missing / stale (publish
    fail-open, but visibly *unvalidated*).
  - (**`gated`** is the suppressed case above; rendered as `EVAL_GATED`.)
- A stage that is not yet `gating` (§ table above) does **not** affect the badge; the panel shows it
  as "pending." So in M0, the badge derives solely from `monitor_signal`'s in-run structural health.

**Why fail-open on unknown:** suppressing whenever a `StageReport` is absent or stale would blank
the report every time CI lagged — worse than a visible caveat; weights/bands are human-owned; the
panel keeps the gap honest. Only a **fresh FAIL** suppresses.

`STALE_AFTER` default **14 days** (configurable). Rationale: the monitor runs daily but the live
suite runs on merge / scheduled CI, not daily; 14 days bounds drift while tolerating CI cadence.
The panel always shows each gating stage's `overall` + `ran_at` so staleness is visible.

### 3.6 Persisted eval-trace artifact (resolves rev-3 P1a)

The artifact evals (§4) and the ledger read `outputs/<date>/monitor/*.json`, but today's dumps drop
what they need: `signal.json` is `{status,bias}` only, `impacts.json` is contributions only,
`narrative.json` drops `citation_ids`, `monitor.json` has latest-NAV only — no `nav_series`, no
evidence pool, no factor inputs ([monitor_cmd.py](../../../src/irc/commands/monitor_cmd.py)).
**Everything required already lives on `FundView` in memory** (`nav_series`, `evidence_pool`,
`factor_scores`, `signal`, `narrative`) ([render_types.py:14](../../../src/irc/monitor/render_types.py)) —
this is a *serialization* gap, not new computation.

**Decision: M0 persists one new `outputs/<date>/monitor/eval_trace.json`** (the existing human/
back-compat dumps stay unchanged — this resolves the rev-2 §9 "extend vs new file" open item in
favour of a new file). Per-fund schema:

```
eval_trace.json = { schema_version, engine_version, run_date,
  funds: { <fund_id>: {
    resolved: { analysis_profile, weights, bands, minimum_confidence },   # MonitorFund params → oracle
    nav:      { as_of_date, latest_unit_nav, nav_acc, acc_series:[[date,nav_acc],…], obs_count, max_gap_days },
    evidence_pool: [ {source,title,date,url,owner_fund_id,citation_id}, … ],
    factor_scores: [ {name,value,eligible,reason,confidence}, … ],         # all 5
    signal:   { status,bias,composite,signal_confidence,available_weight,present_families,
                contributions:[{name,renorm_weight,value,contribution,confidence}],divergence_codes },
    impacts:  { macro:[{key,weight,impact,confidence,citation_ids}], constituent:[…] },
    narrative:{ status, price_action:[{claim,attribution_strength,citation_ids}], signal_rationale:[…], risk:[…] },
    gate:     { suppressed, failed_stages, reason }, published_state, validation_badge } } }
```

This single artifact feeds: the `monitor_signal` **oracle** (re-run `compute_signal` from
`resolved` + `factor_scores`, assert equality), the `nav_series_for` edge metric (`obs_count`,
`max_gap_days`, staleness), the `build_evidence_pool` edge metric (owner-binding, dedup, freshness),
the M1 LLM-artifact checks (impact/narrative citations resolve into `evidence_pool`), and the
forward-ledger writer (`signal` + `nav_acc` + `published_state`). M0 edge metrics are therefore
implementable; none need to be dropped.

## 4. Per-stage eval map

| Stage | Kind | **Evaluated via** | Core metrics | Milestone |
|---|---|---|---|---|
| `nav_series_for` | edge | persisted NAV artifact | staleness, gap count, `obs ≥ minimum_observations` | M0 |
| `build_evidence_pool` | edge | persisted evidence artifact | owner-binding, citation determinism, dedup, items/theme, freshness | M0 / M1 |
| `monitor_impact` | LLM | **fixture + LLM suite** (`live_gated`) | sign-accuracy, magnitude-MAE, injection-resistance, citation-validity | **M1** |
| `monitor_narrative` | LLM | **fixture + LLM suite** (`live_gated`) | groundedness, attribution-honesty, banned-verb correctness, hallucination rate | **M1** |
| `build_factor_scores` | pure | oracle + property | exact-value vs oracle, eligibility/N-A reasons, monotonicity, clamp | M2 |
| `compute_signal` | pure | oracle + property (artifact recompute) | composite `= Σ w′·s` exactly, gate logic, renorm = 1, bands, divergence | M0 (recompute) / M2 (property) |
| composite → bias | algorithm | ablation + calibration | leave-one-out IC, weight/band sensitivity, C-vs-forward calibration | M4 |
| forward signal | outcome | backtest + forward ledger | IC, hit-rate vs buy-hold/momentum/random, ledger N | M3 |

## 5. Milestones

Each milestone tightens the **suppression rule** (§3.5 publish invariant): a bias is gated
(`EVAL_GATED`) only on a **fresh FAIL** from a `gating` stage; otherwise it publishes with a
`validated` / `caveated` badge. The milestones below note what each adds to the gating set.

- **M0 — eval spine (tracer bullet).** (1) Persist `eval_trace.json` (§3.6). (2) Land
  `evals/monitor_signal/` artifact-eval (oracle-recompute composite from the trace; assert gate
  logic + renorm) — joins the `--all` green suite. (3) Register `monitor_impact`/`monitor_narrative`
  as **`live_gated`** (out of `--all`, gating=`not_yet`). (4) `GateDecision` overlay + `EVAL_GATED`
  render state + validation panel (renders each gating stage's `overall`/`ran_at`, with the §3.5
  staleness display states). (5) Forward-ledger **writer** (correct NAV basis, raw+published,
  idempotent per §3.2d) — *starts the track-record clock immediately*.
  *Publish-gate:* in-run structural failure (unresolved citation / invalid schema / NAV too stale)
  → `EVAL_GATED`. LLM suites cannot gate yet (`not_yet`).

- **M1 — LLM suites.** Synthetic/adversarial corpora + pure scorers for `monitor_impact` /
  `monitor_narrative`; the two `live_gated` runners become real (SKIPPED without env, scored with
  `IRC_RUN_LIVE_LLM_EVAL=1`); flip both to **gating**.
  *Publish-gate:* a fresh suite `StageReport.overall == FAIL` → that stage's funds `EVAL_GATED`;
  SKIPPED/stale → fail-open + panel flag (§3.5).

- **M2 — deterministic rigor.** Property-based + oracle tests for `build_factor_scores` /
  `compute_signal` beyond the M0 recompute; surface deterministic-stage health in the panel.
  *Publish-gate:* hardens confidence; no new runtime gate.

- **M3 — retro backtest + forward scorer.** Replay trend (later valuation/heat) over NAV history →
  IC / hit-rate vs baselines (using `nav_acc`); forward-ledger **scorer** (dedups per §3.2d) joins
  later NAV to realized total return; backtest numbers appear in the panel.
  *Publish-gate:* informational; sustained negative IC is a human review trigger, not an auto-gate.

- **M4 — algorithm justification.** Factor ablation, weight/band sensitivity, and an **ADR**
  documenting each factor's economic rationale and the composite design.

## 6. Grouping & sequencing (suggestions)

### Dependency graph

```
M0 (spine: trace + monitor_signal eval + gate/panel + ledger WRITER) ──┬──> M1 (LLM suites) ──┐
                                                                        ├──> M2 (det. rigor) ──┼──> M4
                                                                        └──> M3 (backtest +    ┘
                                                                              ledger SCORER)
```

### Suggested work-blocks

- **Block A · Process Trust = M0 + M1 + M2.** The "is each stage right?" release. M0 already lands
  *real* value via the `monitor_signal` artifact-eval (oracle recompute) on the existing surface —
  not just plumbing. *Start here;* this roadmap's first spec covers **M0–M1**, M2 follows in-block.
- **Block B · Predictive Validity = M3.** Largely independent (NAV replay + ledger scorer); needs
  only M0's ledger writer + panel slot. Can run **in parallel** with Block A.
- **Block C · Algorithm Justification = M4.** Depends on Block B's outcome data. The capstone ADR.

### Two sequencing insights worth acting on

1. **Start the track-record clock in M0, not M3.** The ledger *writer* lands in M0 (idempotent
   append, correct NAV basis); the *scorer/backtest* is Block B. Every un-logged day is forward
   evidence permanently lost — the highest-leverage early move.
2. **M2-before-M1 is a valid swap** (M2 is cheaper and gates deterministic stages sooner). We keep
   **M0 → M1 → M2** because M1 most directly answers "is `monitor_impact`/`narrative` right?" — but
   swap if budget tightens.

## 7. Architecture artifacts (target shape)

```
src/irc/monitor/eval/         # PURE — imports only monitor cores + own types
  types.py        # StageHealth, GateDecision, LedgerRow, BacktestResult …
  structural.py   # pure per-run structural health (cheap, in-run)
  gate.py         # pure apply_eval_gate(signal, in_run_health, suite_reports) → GateDecision; published_state(...)
  staleness.py    # pure resolve_health(report|None, now) → PASS|WARN|FAIL|UNKNOWN  (§3.5)
  panel.py        # pure validation-panel HTML
  backtest.py     # pure NAV replay + factor → IC / hit-rate
  metrics_impact.py / metrics_narrative.py   # pure expected-vs-actual scorers
  cases/          # synthetic adversarial corpora (data fixtures)

src/irc/monitor/forward_log.py   # EDGE — append-only idempotent ledger writer + pure latest_per_key reader

evals/monitor_signal/{runner,metrics}.py      # artifact-eval, in_all_suite=True
evals/monitor_impact/{runner,metrics}.py      # live_gated suite runner (SKIPPED w/o env)
evals/monitor_narrative/{runner,metrics}.py   # live_gated suite runner
# evals/_shared: registry.py +live_gated lifecycle; status.py +SKIPPED; missing_input.py +EVAL_RC_SKIPPED=3
# monitor run also emits outputs/<date>/monitor/eval_trace.json (§3.6) — the eval/ledger source artifact
```

- **eval-trace** = `outputs/<date>/monitor/eval_trace.json` (§3.6) — the single artifact the
  artifact-evals + ledger writer read; the human-facing dumps are unchanged.
- **"Manifest"** = the latest `outputs/<date>/evals/monitor_*/report.json` (`StageReport`). The
  in-run gate reads the latest suite report per **gating** stage and applies §3.5; no separate
  manifest format.
- **Forward ledger** — append-only JSONL (`data/monitor/forward_ledger.jsonl`); schema §3.2(b),
  idempotency §3.2(d).

## 8. Constraints, risks, non-goals

**Constraints / risks**
- *No historical evidence* → full-signal backtest is forward-only (§2).
- *Tiny N* (7 funds) + short history → predictive metrics are low-power; report with confidence
  intervals and an explicit "insufficient data" state; beware multiple-testing.
- *Overfitting* → no auto-calibration of weights/bands (§3.4).
- *Judge circularity* sidestepped by **synthetic/adversarial** ground truth (decided 2026-06-16).
- *LLM cost* → live suites are `live_gated`: never in the daily run or default `--all`; only
  `irc eval monitor_* ` under `IRC_RUN_LIVE_LLM_EVAL=1` (§3.1).
- *Staleness* → fail-open + visible, `STALE_AFTER=14d` default (§3.5); never blanks the report.

**Non-goals**
- Closed-loop automatic weight/band re-calibration.
- Human-labeled gold sets / labeling pipeline.
- Any trading or execution logic (stays out of IRC).

## 9. Open questions (deferred to per-milestone specs)

- `monitor_impact` magnitude tolerance bands and the sign-accuracy bar for M1's FAIL threshold.
- Backtest horizon(s) `H` and baseline set for M3.
- `STALE_AFTER` final value + whether per-stage (M1 may tune the 14-day default).
- Whether to add the `irc eval --live` aggregate convenience or rely on explicit per-stage runs (M1).

## Appendix — review findings resolution

**Rev-1 block (2026-06-16, first round)**

| Finding | Sev | Resolution |
|---|---|---|
| Gated `NO_CALL` required before data model defined | P0 | §3.2(a): `GateDecision` overlay + distinct `EVAL_GATED`; raw `SignalRecord` unchanged |
| Ledger logs wrong NAV basis (`latest_nav` is unit NAV) | P0 | §3.2(b): `nav_acc`=`COALESCE(nav_acc,nav)` + `nav_basis` + `as_of_date` |
| Raw vs published signal in ledger undefined | P1 | §3.2(c): ledger stores both; M0 enriches output |
| "Eval imports only pure cores" vs edge stages | P1 | §3.3: edges evaluated via persisted artifacts; import table |
| Command shape conflicts with `irc eval` surface | P2 | §3.1: adopt repo-root `evals/` registry + `StageReport` |

**Rev-2 block (2026-06-16, second round)**

| Finding | Sev | Resolution |
|---|---|---|
| Live LLM suites don't fit `irc eval --all` (cost / env-absent) | P0 | §3.1: new `live_gated` lifecycle (out of `--all`), `IRC_RUN_LIVE_LLM_EVAL` double-gate, `SKIPPED` outcome |
| M0 can suppress every bias before M1 (`unimplemented_active`=FAIL) | P1 | §3.5: milestone-scoped gating set; LLM suites are `live_gated`/`not_yet` in M0, so they cannot gate |
| `StageReport` staleness deferred but M0 depends on it | P1 | §3.5: fail-open truth table for SKIPPED/missing/stale + `STALE_AFTER=14d`; M0's only gating input is in-run-fresh |
| Append-only ledger lacks idempotency under reruns | P2 | §3.2(d): logical key `(run_date,fund_id)`, `written_at`, last-write-wins dedup in the pure reader/scorer |

**Rev-3 block (2026-06-16, third round)**

| Finding | Sev | Resolution |
|---|---|---|
| M0 lacks the persisted artifacts its eval map requires | P1 | §3.6: M0 persists `eval_trace.json` (nav_series, evidence pool, factor inputs, impact/narrative citations) — serialization of existing in-memory `FundView` |
| `SKIPPED` has no CLI return-code contract | P1 | §3.1: `EVAL_RC_SKIPPED=3`; out of `--all`; rc-3 = "did-not-run" (live job treats as misconfig); gate reads `overall` not rc |
| Publish-gate language contradicts fail-open | P1 | §3.5: explicit publish invariant — fresh FAIL suppresses; else publish with `validated`/`caveated` badge so "assert a bias" ≠ "validated" |
