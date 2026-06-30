# ADR 0017 — Monitor evidence is isolated from the dual-coverage citation model

**Status:** Accepted (2026-06-15, `irc monitor` design grilling)
**Builds on:** [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md).
**Spec:** `docs/superpowers/specs/2026-06-15-monitor-daily-report-design.md` §4.

## Context

The opportunity/memo pipeline cites evidence as `ThesisEvidence`, whose `scope`
field (`instrument | constituent | asset_class_macro | policy`) is the load-bearing
discriminator of the **dual-coverage gate**: a publishable row needs a data leg AND
an information leg, both with `scope in {instrument, constituent}` and
`owner_instrument_id == row.instrument_id`. Macro/theme news is deliberately built
with `scope="asset_class_macro"` ([opportunity/thesis_evidence.py:143](../../src/irc/opportunity/thesis_evidence.py)) precisely so it can **never** satisfy that gate — it is supplemental context only.

The new `irc monitor` vertical produces a per-fund **directional bias** backed by
macro/theme news (the `macro_tilt` factor) and per-holding news (the `constituent`
factor). An early design proposed *promoting* that macro evidence from
`asset_class_macro` to `instrument`/`constituent` scope so it could be "bound to the
fund as owner." That is both unnecessary (ownership is already `owner_instrument_id`,
and the monitor's own coverage gate counts evidence *families*, never reading
`scope`) and dangerous: if monitor-built evidence ever shared an evidence pool or a
`build_cited_map` pass with the opportunity pipeline, a re-scoped geopolitics headline
would **falsely satisfy the dual-coverage gate** — the exact failure that
`asset_class_macro` exists to prevent.

## Decision

The monitor uses its **own `EvidenceItem`** type — `(source, title, date, url,
owner_fund_id, citation_id)` — with **no `scope` field**, and does **not** reuse
`ThesisEvidence`. Monitor evidence is owner-bound *by construction*: each fund's
evidence pool is assembled only from that fund's own themes and holdings, so there is
no scope to promote and no ownership to assert after the fact. The `citation_id` is
16 hex chars **only** so the shared `\[ref:[0-9a-f]{16}\]` marker regex matches; its
preimage is the monitor's own (e.g. `sha256(owner_fund_id:url_or_fallback:date)`) and
is independent of ADR 0001's `ThesisEvidence` preimage. The monitor's evidence
machinery and the dual-coverage gate **never touch**.

### Considered options

- *Rejected — reuse `ThesisEvidence`, re-scope macro → `instrument`.* Overloads the
  one field the dual-coverage gate keys on with semantics that contradict its
  documented meaning; a latent correctness landmine the moment any pool is shared.
- *Rejected — reuse `ThesisEvidence` with honest scopes + `owner_instrument_id`.*
  Safer (no false gate satisfaction) but still couples the monitor to a type whose
  `scope` it never uses, and pulls the dual-coverage vocabulary into a vertical that
  has no dual-coverage gate. Isolation is cleaner than disciplined reuse here.

## Consequences

- A second, smaller evidence type exists — accepted cost for **complete isolation**:
  no macro headline can ever leak into the dual-coverage gate via the monitor.
- Monitor `citation_id`s are **not comparable** to opportunity/memo `citation_id`s
  (different preimage). This is fine — the pools are separate by design.
- The monitor's coverage gate (independent evidence *families*: price-momentum,
  valuation, crowding, news) is `scope`-agnostic, so dropping `scope` costs it
  nothing.

## Monitor-eval data contracts (2026-06-16, monitor-eval M0)

The monitor-eval **spine** (validation track, milestone M0) adds two durable data
contracts. Both clear the ADR bar (hard to reverse once data accumulates,
surprising without context, chosen over a real alternative) and are recorded here
rather than as a fresh ADR because their surprise and reversibility are rooted in
*this* ADR's evidence-isolation invariant.

### `eval_trace.json` — unified evidence pool, monitor-only

Each `irc monitor` run writes one additive artifact
`outputs/<date>/monitor/eval_trace.json` (the four legacy dumps unchanged), a
schema-versioned, degradation-safe serialization of each fund's resolved params,
NAV, evidence pool, factor scores, signal, impacts, narrative, and gate decision.
**Decision:** the trace's per-fund `evidence_pool` is the **unified** pool
`dedup_by_citation_id(view.evidence_pool ⊕ bundle.constituent_pool)` — the macro
pool (`FundView.evidence_pool`) merged with the constituent pool carried on the
`FundTraceBundle` — so both macro *and* constituent impact/narrative `citation_id`s
resolve under the in-run `citation_integrity` check. *Rejected — extend
`signal.json`* (pinned §7: a new artifact, not an overload). *Rejected — serialize
only the macro pool* (constituent citations would falsely FAIL).

**This unification does not breach the isolation above.** The merged pool is built
**only** from one fund's own `EvidenceItem`s (no `scope` field) and is consumed
**only** by the monitor's own structural checks and offline `monitor_signal` eval.
It never reaches `build_cited_map` or the dual-coverage gate. The isolation
invariant — monitor evidence and the dual-coverage gate never touch — is preserved
verbatim; "unified" means macro ⊕ constituent *within the monitor*, never monitor ⊕
opportunity.

### Forward ledger — real append-mode JSONL, cumulative under `data/`

The forward ledger `data/monitor/forward_ledger.jsonl` starts the per-fund
track-record clock: one row per fund per run, each storing both the raw pre-gate
verdict and the `published_state`, plus the perf basis `nav_acc = coalesce(nav_acc,
nav)`. **Decision:** the writer uses a **real append** (`open(path, "a")`, one JSON
object per line), NOT the project's usual atomic `.tmp.{pid} → os.replace`
whole-file write. A single-line JSONL row is well under `PIPE_BUF`, so the append
is atomic on POSIX, and concurrent/rerun rows are never lost; rerun duplicates for
a `(run_date, fund_id)` are expected and collapsed at *read* time by
`latest_per_key` (last `written_at` wins). *Rejected — atomic temp+replace*: a
whole-file rewrite races and can drop a concurrent run's row, defeating the point
of an append-only track record. A degraded fund (`obs_count == 0`) still gets a row
with `nav_acc = null`; the future ledger scorer drops null-`nav_acc` rows (no
forward basis).

**Why `data/` not `outputs/<date>/`.** The ledger is **cross-run cumulative**
state, unlike every date-partitioned artifact under `outputs/`. It therefore lives
under `data/` alongside the other cumulative caches/ledgers (`fundamentals/`,
`spend/`), deliberately not in the per-run output tree. A future reader who
"normalizes" it into `outputs/<date>/` would silently reset the track record each
run — this placement is intentional, not an oversight.

## M1 LLM-suite data contracts (2026-06-16, monitor-eval M1)

The M1 LLM-quality suites (`monitor_impact` / `monitor_narrative`) add two more
durable contracts. Both clear the ADR bar (hard to reverse, surprising without
context, chosen over a real alternative) and are recorded here — rather than as a
fresh ADR — because both are rooted in *this* ADR's evidence-isolation invariant:
the corpora carry the monitor's own scope-free `EvidenceItem`s, and the paid surface
is the same MiniMax route the monitor itself uses.

### Eval corpora — versioned data fixtures, not test-inline cases

The synthetic/adversarial corpora live as checked-in JSON under
`src/irc/monitor/eval/cases/{impact,narrative}/`, one **case** per file
(`category` + a constructed `evidence_pool` + an `expected`). **Decision:** the
corpora are a **versioned data contract**, loaded *identically* by the pure scorer
unit tests (against canned LLM outputs) and the live runner (against real MiniMax
outputs) — they are NOT inlined into test code. Once the live suite asserts PASS on
them and (M4) thresholds calibrate against them, editing a case silently shifts
pass/fail, so the corpora are as load-bearing as `eval_trace.json` and change under
the same scrutiny. *Rejected — inline cases inside the scorer tests*: would make the
scorer test and the live runner exercise *different* inputs, so a green offline
suite would no longer predict the live suite, and there would be no single artifact
to version. The corpora `evidence_pool`s carry monitor `EvidenceItem`s with **no
`scope` field** (the isolation invariant above): a corpus can never leak into the
dual-coverage gate.

### Live runner is the sole paid LLM surface — scorers are pure

**Decision:** the `live_gated` runner (`evals/monitor_{impact,narrative}/runner.py`)
is the **only** M1 code path that calls the LLM. The scorers
(`metrics_impact.py` / `metrics_narrative.py`) and the corpus loaders are **pure** —
no I/O, no network, no gateway/http import — and that purity is enforced by an
import-graph guard, so the whole scorer suite runs under default `pytest` with no
keys and no network. The runner is therefore the single surface to protect, and it
is **triple-gated**: the `IRC_RUN_LIVE_LLM_EVAL=1` env gate (M0 `eval_cmd` SKIPPED
path) *and* `preflight_gate("eval-live")` before dispatch (M0) *and*
`record_command_run` for actuals after scoring (M1). *Rejected — let the runner
score inline / let a scorer call the LLM*: would couple the free, deterministic
grading logic to the paid network surface, break the no-network unit-test contract,
and create a second un-gated path to LLM spend. The split (pure scorer ⟂ gated
runner) is the reason the offline suite is free and the paid surface is auditable.

---

### Addendum (ADR 0021, 2026-06-30): additive forward-ledger fields

ADR 0021 adds two optional fields to `ledger_row` (→ `ForwardRow`):
`market_composite: float | None` and `market_bias: str | None`.

**Back-compat contract:** both default to `None`; `score_forward` reads them via
`.get()`; old ledger rows without these keys are treated as `None` — the scorer
never crashes on legacy data. `build_metric_reports` emits a
`market_composite_directional` details block **only** when at least one
`ForwardRow` carries a non-None `market_composite` — absent for legacy runs, so
the panel layout is stable.
