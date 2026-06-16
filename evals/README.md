# `evals/` — offline, artifact-based evaluation suite

This directory is the **evaluation surface** for the `irc` pipeline. Each eval is an
*offline* runner that reads a stage's **persisted artifact** under `outputs/<date>/…`,
recomputes/scores it against PASS/WARN/FAIL thresholds, and writes a `StageReport` to
`outputs/<date>/evals/<stage>/report.json`. **Evals never re-invoke the producer** — they
grade what the pipeline already wrote.

> Workflow diagram for the monitor eval layer: [`docs/monitor-eval-workflow.html`](docs/monitor-eval-workflow.html).
> Design map: [`docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md`](../docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md).

---

## TL;DR

```bash
# Green suite — every in_all_suite stage, offline, cost-free. Returns the max rc.
uv run irc eval --all

# A single artifact eval (monitor's deterministic core, in the green suite):
uv run irc eval monitor_signal

# A live-LLM suite — double-gated, spends MiniMax budget. SKIPPED (rc 3) without the env:
IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact
IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_narrative
```

Return codes: **`0=PASS`, `1=WARN`, `2=FAIL`, `3=SKIPPED`**. `--all` returns the **max rc**
over every `in_all_suite=True` stage and stays in `{0,1,2}` (live suites are excluded).

---

## How `irc eval` works

`irc eval <stage>` / `irc eval --all` dispatches through
[`src/irc/commands/eval_cmd.py`](../src/irc/commands/eval_cmd.py), which looks the stage up in
the **registry** ([`_shared/registry.py`](_shared/registry.py)) and behaves per the stage's
**lifecycle**:

| Lifecycle | In `--all`? | Direct `irc eval <stage>` behaviour |
|---|---|---|
| `active` | ✅ | Runs the runner; rc `0/1/2`. |
| `unimplemented_active` | ✅ | Honest **FAIL** — the absence of a real measurement shows up red. |
| `live_gated` | ❌ | **Double-gated** (see below). `SKIPPED` (rc 3) without the env gate. |
| `inactive_legacy` / `inactive_uninstrumented` | ❌ | Prints an inactive-stage message, rc 2; no fake report. |

A missing input artifact is treated as **FAIL** (rc 2), not PASS — a stage that never ran must
turn the dashboard red ([`_shared/missing_input.py`](_shared/missing_input.py)).

### The two eval *shapes*

1. **Artifact evals** (`active`, in the green suite, **no LLM**) — `locate` the producer's JSON
   under `outputs/<date>/…`, recompute via the pure core, assert oracle-equality + structural
   health. Cheap, deterministic, run on every `--all`.
2. **Live-LLM suites** (`live_gated`, **out of `--all`**) — ignore the day's artifacts; run a
   synthetic adversarial **corpus** through the real LLM route and score the responses. They are
   the *only* place the eval surface spends LLM budget.

### Live-suite double gate

A `live_gated` stage runs only when **both** gates are open
([`eval_cmd.py:_run_live_gated`](../src/irc/commands/eval_cmd.py)):

1. **Env gate** — `IRC_RUN_LIVE_LLM_EVAL=1` (`true`/`yes`/`on` also accepted). Unset →
   writes a `SKIPPED` report and returns **rc 3** (`"env absent; not executed"`).
2. **Spend gate** — `preflight_gate(root, "eval-live")` (the paid-API budget gate, exit 5 if
   over budget). This is the only eval that charges the `eval-live` spend scope.

`SKIPPED` (rc 3) means *did-not-run*, never *success*. CI's **green** job never invokes these;
CI's **live** job sets the env and expects `0/1/2` — a `3` there means the key is misconfigured.

---

## Monitor eval (M0 + M1 — landed)

The monitor vertical (`irc monitor`, ADR 0017) ships a per-fund **directional bias**
(`ADD_BIAS | NEUTRAL | REDUCE_BIAS`) daily for the 7-fund Monitor set. The eval layer validates
**process trust** ("does each stage do what it claims?") and starts the **forward track record**.

Three registered stages:

| Stage | Lifecycle | Reads | What it checks |
|---|---|---|---|
| `monitor_signal` | `active` (green suite) | `outputs/<date>/monitor/eval_trace.json` | Deterministic core: oracle recompute of `compute_signal`, citation resolution, NAV completeness. |
| `monitor_impact` | `live_gated` | `src/irc/monitor/eval/cases/impact/*.json` | LLM judgment quality on a synthetic corpus (MiniMax route). |
| `monitor_narrative` | `live_gated` | `src/irc/monitor/eval/cases/narrative/*.json` | LLM groundedness / attribution honesty on a synthetic corpus. |

### Where the artifacts come from

`irc monitor` itself (the producer, M0 "spine") emits the inputs the eval reads — this is a
*serialization* of the in-memory `FundView`, not new computation:

- **`outputs/<date>/monitor/eval_trace.json`** — `schema_version "1"`, per-fund projection:
  `resolved` (profile/weights/bands/min-confidence) · `nav` · `evidence_pool` · `factor_scores` ·
  `signal` (with `contributions`) · `impacts` · `narrative` · `gate` · `published_state` ·
  `validation_badge`. Built by [`monitor/eval/trace.py`](../src/irc/monitor/eval/trace.py).
- **`data/monitor/forward_ledger.jsonl`** — append-only JSONL, one row per `(run_date, fund_id)`,
  logging both the **raw** scoring verdict and the **published** state plus the
  `COALESCE(nav_acc, nav)` performance basis. This is the *track-record clock* — every un-logged
  day is forward evidence lost. Writer/reader in
  [`monitor/eval/forward_log.py`](../src/irc/monitor/eval/forward_log.py); the M3 scorer (future)
  joins each row to later NAV.

Both writes are **degrade-not-crash**: if they fail the brief still renders.

### In-run gate + validation badge

On each `irc monitor` run, a per-fund **`GateDecision`** overlay is computed
([`monitor/eval/gate.py`](../src/irc/monitor/eval/gate.py)) — *separate* from the raw
`SignalRecord`, which is never overloaded:

- **In-run structural health** (`monitor_signal_health`, always fresh) — `signal_consistency`
  (`composite == Σcontribution`, `Σrenorm == 1`, `bias is None iff status != ok`),
  `citation_integrity` (every cited id resolves into the evidence pool), `nav_quality`
  (obs count / staleness / gap).
- **Suite health** — the latest `monitor_impact` / `monitor_narrative` `StageReport` resolved via
  [`staleness.resolve_health`](../src/irc/monitor/eval/staleness.py) (`STALE_AFTER = 14d`;
  SKIPPED / absent / stale → `UNKNOWN`).

The gate then derives the **published state** and a **badge**:

| Condition | Published | Badge |
|---|---|---|
| `signal.status != ok` | `NO_CALL` | — |
| a **gating** stage returns a **fresh FAIL** | `EVAL_GATED` (suppressed) | `gated` |
| a gating stage is WARN / UNKNOWN / stale / SKIPPED | the bias (published) | `caveated` |
| every gating stage is fresh-PASS | the bias (published) | `validated` |

**Fail-open by design:** only a *fresh FAIL* suppresses; a missing/stale suite report never blanks
the report — it publishes with a visible `caveated` badge. The report's **validation panel**
([`monitor/eval/panel.py`](../src/irc/monitor/eval/panel.py)) shows each gating stage's `overall`
+ `ran_at` + badge counts so the gap is honest. Publishing a bias never implies it passed
validation — the badge says which.

---

## Expected output

### `irc eval monitor_signal` (and `--all`)

Console: a single line `monitor_signal eval: PASS`. The file
`outputs/<date>/evals/monitor_signal/report.json`:

```json
{
  "stage": "monitor_signal",
  "ran_at": "2026-06-16T13:33:02.371166+08:00",
  "based_on": ["outputs/2026-06-16/monitor/eval_trace.json"],
  "metrics": [
    { "name": "oracle_signal_match", "value": 1.0, "status": "PASS", "n_observations": 1, "threshold": {"fail_below": 1.0} },
    { "name": "citation_resolution", "value": 1.0, "status": "PASS", "n_observations": 1, "threshold": {"fail_below": 1.0} },
    { "name": "nav_completeness",    "value": 1.0, "status": "PASS", "n_observations": 1, "threshold": {"warn_below": 0.85, "fail_below": 0.6} }
  ],
  "overall": "PASS",
  "notes": "",
  "config_versions": {}
}
```

Metric meanings:

| Metric | Definition | Threshold |
|---|---|---|
| `oracle_signal_match` | Re-runs `compute_signal` from `resolved` + `factor_scores` in the trace; fraction of funds whose `status/bias/composite/signal_confidence` match exactly. | FAIL `< 1.0` (must be exact) |
| `citation_resolution` | Fraction of impact/narrative `citation_ids` that resolve into the per-fund `evidence_pool`. | FAIL `< 1.0` |
| `nav_completeness` | Fraction of funds with `obs_count ≥ 2`. | WARN `< 0.85`, FAIL `< 0.6` |

`overall` is the **worst** metric status; `n_observations` is the fund count.

### `irc eval --all`

Runs every `in_all_suite` stage, then prints a summary and returns the max rc:

```
eval summary:
  PASS data
  PASS scoring
  ...
  PASS monitor_signal
overall: PASS
```

### `irc eval monitor_impact` / `monitor_narrative`

**Without** `IRC_RUN_LIVE_LLM_EVAL` — `SKIPPED`, rc 3, a SKIPPED report is written:

```
monitor_impact eval: SKIPPED (env absent; not executed)
```

**With** the env gate (and budget available) — drives the synthetic corpus through MiniMax,
scores with the pure scorers, and writes
`outputs/<date>/evals/monitor_{impact,narrative}/report.json`. Spend is recorded to the ledger.
Metrics scored:

- **impact** ([`metrics_impact.py`](../src/irc/monitor/eval/metrics_impact.py)) —
  `sign_accuracy` (WARN `<0.90` / FAIL `<0.80`), `magnitude_band_pass` (FAIL `<0.80`),
  `injection_resistance` (FAIL `<0.95`), `citation_validity` (FAIL `<1.0`).
- **narrative** ([`metrics_narrative.py`](../src/irc/monitor/eval/metrics_narrative.py)) —
  `citation_resolution` (FAIL `<1.0`), `entailment_ablation_pass` (FAIL `<0.80`),
  `attribution_honesty` (FAIL `<1.0`), `hallucination_rate` (lower-is-better, FAIL `>0.0`),
  `injection_resistance` (FAIL `<0.95`).

Each corpus case is a small JSON fixture with `category`, `messages_seed`, an `evidence_pool`
(carrying real 16-hex `citation_id`s), and an `expected` block. A per-case transport/parse error
degrades that case to a category failure — the suite never crashes
([`monitor_suite/driver.py`](monitor_suite/driver.py), `drive_case`).

---

## Layout

```
evals/
├── README.md                     # this file
├── docs/
│   └── monitor-eval-workflow.html  # workflow diagram (self-contained HTML+SVG)
├── _shared/                      # shared eval framework
│   ├── registry.py               # EvalStageSpec + lifecycle (incl. live_gated)
│   ├── missing_input.py          # EVAL_RC_PASS/WARN/FAIL/SKIPPED; missing→FAIL
│   ├── status.py                 # classify_status / worst_status
│   ├── report_schema.py          # MetricReport / StageReport
│   ├── report_paths.py           # outputs/<date>/evals/<stage>/report.json writer
│   ├── locator.py                # find a producer artifact by date
│   └── latest_report.py          # newest StageReport for a stage (feeds the in-run gate)
├── monitor_signal/{runner,metrics}.py    # artifact eval (green suite)
├── monitor_impact/runner.py              # live_gated suite
├── monitor_narrative/runner.py           # live_gated suite
├── monitor_suite/driver.py               # shared drive_case + build_stage_report
└── <other stages>/runner.py …            # data, scoring, memo, opportunity, …
```

The **pure** monitor-eval cores live under
[`src/irc/monitor/eval/`](../src/irc/monitor/eval/) (trace, gate, staleness, structural, panel,
forward_log, metrics_*, case_loader, cases/) — they import only the monitor cores + their own
types, never AkShare / providers / LLM gateway / settings / filesystem (ADR 0017 §3.3). The
runners here are the thin I/O boundary.

---

## Roadmap status

- **M0 — eval spine** ✅ `eval_trace.json` + `monitor_signal` artifact eval + `GateDecision`/
  `EVAL_GATED`/validation panel + forward-ledger **writer**.
- **M1 — LLM suites** ✅ synthetic corpora + pure scorers; `monitor_impact` / `monitor_narrative`
  `live_gated` runners.
- **M2 — deterministic rigor** ⬜ property/oracle tests for `build_factor_scores` / `compute_signal`.
- **M3 — backtest + forward scorer** ⬜ NAV replay → IC/hit-rate; ledger **scorer** joins realized
  forward return (consumes the M0 ledger).
- **M4 — algorithm justification** ⬜ factor ablation + weight/band sensitivity + economic-rationale ADR.

See the [roadmap](../docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md) for the full
validation taxonomy, gate semantics, and per-stage eval map.
