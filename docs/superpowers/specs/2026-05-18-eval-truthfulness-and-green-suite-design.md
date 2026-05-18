# Eval truthfulness first, green suite second

**Date:** 2026-05-18
**Branch:** `feat/evidence-wiring-and-memo-enrichment`
**Scope:** Repair the eval framework in two phases:
1. make evals runnable and truthful against the pipeline that exists today;
2. only after that, use the repaired framework to drive the active eval suite green.

---

## Problem

`uv run irc eval research` currently fails before any metric runs:

```text
ModuleNotFoundError: No module named 'evals'
```

The installed CLI entrypoint imports `irc` from the built package, but Hatch currently packages only `src/irc`; the top-level `evals/` package is available in the checkout and under pytest's `pythonpath = ["src", "."]`, but not to the installed console script.

That import failure hides a second, more important issue: several eval runners no longer describe the live pipeline. The current commands write dated artifacts such as:

- `outputs/<date>/discovered_watchlist.csv`
- `outputs/<date>/scoring.json`
- `outputs/<date>/gold_regime.json`
- `outputs/<date>/proposed_allocation.yaml`
- `outputs/<date>/trade_plan.yaml`
- `outputs/<date>/memo.md`

but several runners still look for retired paths such as:

- `outputs/discovery/watchlist.json`
- `outputs/gold_score/gold_score.json`
- `outputs/allocation/allocation.json`
- `outputs/trade_plan/trades.json`
- `outputs/memo/memo.md`

The `2026-05-17` reports demonstrate why this matters. Reports were generated around `2026-05-17 14:09`, while newer artifacts such as `scoring.json`, `memo.md`, and `opportunity_report.json` were updated around `18:02`–`18:09` the same day. Those reports are therefore stale relative to the artifacts now on disk. Several FAILs are runner-contract failures rather than product failures.

The observed failure set currently mixes four different things:

| Class | Examples |
|---|---|
| Framework breakage | installed CLI cannot import `evals` |
| Contract drift | discovery/allocation/trade-plan/memo runners read retired artifact paths |
| Stale report signal | `scoring` report shows completeness `0.6727`, while the newer `scoring.json` on disk now computes about `0.8608` |
| Potentially real failures | `triggers` intentionally unimplemented; `architecture.max_file_loc = 632`; opportunity metric buckets unrelated unthemed assets together |

Until those are separated, “make the suite green” would reward fixing the dashboard before fixing the measurement system.

## Goals

### Phase 1 — truthfulness

- `irc eval <stage>` works from the installed CLI runtime, not only from tests.
- Active eval runners read the artifacts the current pipeline actually produces.
- Dated artifact evals write reports beside the artifact date they evaluated, not blindly under today's date.
- Missing-input FAILs mean the current contract is genuinely absent, not that a runner is looking for an obsolete file.
- `irc eval --all` reflects the **active** eval suite only; inactive legacy evals are not allowed to create false red signal in the default suite.

### Phase 2 — green active suite

- Re-run the corrected evals and classify every remaining non-PASS as:
  - real product/data defect,
  - metric design defect,
  - intentionally unfinished functionality,
  - acceptable operational warning.
- Fix metric defects before using those metrics to judge product quality.
- Address real product/data defects and intentionally unfinished active stages until the active suite is green, except for any warnings explicitly retained by design.

## Non-goals

- Do not move the entire top-level `evals/` package under `src/irc/evals/` in Phase 1. That is a cleaner long-term namespace but unnecessary churn for the rescue pass.
- Do not relax thresholds merely to obtain green reports.
- Do not mix product-semantic fixes into Phase 1 unless they are required to make a runner measure the current system truthfully.
- Do not treat legacy or uninstrumented stages as active by default just because old runner files still exist.

## Current findings

### Stages already close to current contracts

| Stage | Current state |
|---|---|
| `research` | Reads `data/research/research_status.json`; 2026-05-17 report is genuine PASS. |
| `scoring` | Reads dated `scoring.json`; runner contract is current, but the stored report is stale relative to later same-day output. |
| `opportunity` | Reads dated opportunity outputs; runner contract is current, but one metric likely has stale semantics. |
| `data` | Reads mutable DuckDB state directly; 2026-05-17 result is WARN for freshness, not FAIL. |

### Stages with stale contracts

| Stage | Runner currently expects | Current producer emits |
|---|---|---|
| `discovery` | `outputs/discovery/watchlist.json` | `outputs/<date>/discovered_watchlist.csv` |
| `gold_score` | `outputs/gold_score/gold_score.json` | `outputs/<date>/gold_regime.json` and `gold_band.yaml` |
| `allocation` | `outputs/allocation/allocation.json` | `outputs/<date>/proposed_allocation.yaml` |
| `trade_plan` | `outputs/trade_plan/trades.json` | `outputs/<date>/trade_plan.yaml` |
| `memo` | `outputs/memo/memo.md` | `outputs/<date>/memo.md`, `memo_audit.txt`, `memo_traceability.json` |
| `architecture` | required output list includes `research_memo.md` | current pipeline writes `memo.md` |

### Stages that should not remain in the default active suite unchanged

| Stage | Finding | Phase-1 treatment |
|---|---|---|
| `news` | No current CLI producer or live artifact contract in the present pipeline. | Mark inactive/legacy and exclude from `--all`. |
| `queries` | `irc ask` is a live side branch, but it currently prints a response and writes no persisted artifact that the existing runner can evaluate. | Mark inactive/uninstrumented and exclude from `--all` until Phase 2 decides whether to add persistence or retire the eval. |
| `triggers` | Active product concept, but the runner intentionally FAILs because metrics are not implemented. | Keep in the active suite as an honest FAIL until Phase 2 implements it or deliberately removes the requirement. |

## Recommended architecture

### 1. Package the existing eval package in Phase 1

Keep the current import surface (`evals.<stage>.runner`) for now, and make it available to the installed entrypoint by packaging the top-level `evals/` directory alongside `src/irc`.

This is the smallest change that fixes the immediate traceback while keeping a later namespace cleanup optional. Moving everything to `irc.evals` would be cleaner, but it is a separate refactor with wider import churn and no extra truthfulness benefit in Phase 1.

### 2. Introduce a small eval registry

Replace the loose stage-to-module dictionary with a small registry that records:

- stage name,
- runner module path,
- lifecycle (`active`, `inactive_legacy`, `inactive_uninstrumented`, `unimplemented_active`),
- whether the stage participates in `--all`.

The registry gives `eval_cmd` one source of truth for:

- which stages are runnable by name,
- which stages belong to the active default suite,
- which stages should return a clear inactive-stage error instead of a misleading missing-input report.

`news` and `queries` remain visible as known stages but are excluded from `--all` in Phase 1. `triggers` remains active and included because its current FAIL is meaningful signal: the product still advertises trigger semantics, but no real eval exists yet.

### 3. Share artifact discovery, keep metrics stage-local

Add a small shared artifact-location utility under `evals/_shared/` with pure helpers that:

- select today's valid dated artifact set when present;
- otherwise fall back to the latest valid dated artifact set;
- return both the concrete file paths and the evaluated artifact date;
- support single-file and multi-file contracts;
- return `None` only when no valid current-contract artifact set exists.

Keep metric parsing and computation inside each stage runner. Shared discovery removes duplicated path logic without inventing a generic metric framework that would obscure stage-specific behavior.

### 4. Make report placement follow the source

For dated output stages, reports belong under the date directory they evaluated:

```text
outputs/<artifact-date>/evals/<stage>/report.json
```

For mutable non-dated sources such as `data/local.duckdb` and `data/research/research_status.json`, reports continue to be written under the run date because the source itself is current state rather than a dated snapshot.

This prevents `2026-05-18` runs from producing a report under `2026-05-18` that actually measured `2026-05-17` artifacts.

## Phase 1 target contracts

| Stage | Contract after repair | Report-date policy |
|---|---|---|
| `data` | `data/local.duckdb` | run date |
| `research` | `data/research/research_status.json` | run date |
| `discovery` | dated `discovered_watchlist.csv` | artifact date |
| `scoring` | dated `scoring.json` | artifact date |
| `gold_score` | dated `gold_regime.json` plus `gold_band.yaml` if needed by metrics | artifact date |
| `allocation` | dated `proposed_allocation.yaml` | artifact date |
| `trade_plan` | dated `trade_plan.yaml` | artifact date |
| `memo` | dated `memo.md`; use current sidecars only where the metric truly needs them | artifact date |
| `architecture` | `src/irc` plus latest valid dated output directory using current output names | artifact date of evaluated output set |
| `opportunity` | dated `opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md` | artifact date |
| `triggers` | no artifact yet; explicit active-unimplemented FAIL | run date |
| `news` | inactive legacy | excluded from `--all` |
| `queries` | inactive uninstrumented side branch | excluded from `--all` |

## Phase 1 data flow

```text
irc eval <stage>
  → resolve EvalStageSpec from registry
  → if stage inactive: emit clear CLI error, do not pretend current artifacts are missing
  → runner asks shared locator for the current contract
  → if contract absent: write explicit FAIL report naming the current expected artifact(s)
  → if contract present: parse current format, compute metrics, write report beside evaluated source date
```

Important behavior:

- no hidden “today” assumption for dated artifacts;
- no false missing-input failures caused by retired paths;
- rerunning after same-day artifact updates regenerates reports from the updated content;
- Phase 1 does not reinterpret valid metrics merely because they currently fail.

## Phase 1 runner updates

### Discovery

- Parse `discovered_watchlist.csv` instead of retired JSON.
- Keep existing discovery metrics if the CSV contains the needed fields; otherwise fail explicitly on missing required columns rather than inventing defaults.

### Gold score

- Rebuild the eval input from the live `gold_regime.json` / `gold_band.yaml` pair.
- Preserve only metrics supportable by current artifacts. If a historical metric requires data the live producer no longer writes, call that out as a Phase-2 metric redesign instead of faking a value.

### Allocation

- Parse `proposed_allocation.yaml`.
- Reconcile metrics with the fields the current allocator actually emits. Any metric that depends on data no longer emitted should be marked for Phase 2 rather than silently computed from absent fields.

### Trade plan

- Parse `trade_plan.yaml` and its `trades` list.

### Memo

- Parse dated `memo.md`.
- Use current memo sidecars only when a metric can still be grounded in them. The old runner references `audit.json`, `refs.json`, and `baseline_chars.txt`, none of which the current memo command emits.

### Architecture

- Replace stale required-output names with current output names.
- Keep `max_file_loc` honest; the current FAIL at `src/irc/commands/ingest_cmd.py = 632` lines is real and belongs in Phase 2.

## Phase 1 testing

All implementation should follow the project TDD rule: write the failing test first, then the minimum code to pass it.

### Packaging and CLI

- Regression test proving eval modules are importable in the installed-entrypoint context that currently fails.
- CLI test proving `irc eval research` reaches the runner rather than raising `ModuleNotFoundError`.

### Artifact location

- selects today's artifact set when present;
- falls back to the latest valid dated artifact set when today is absent;
- returns the evaluated artifact date;
- rejects partial multi-file sets;
- returns missing only when no valid current-contract set exists.

### Runner contracts

- one current-format fixture per modernized runner;
- one missing-input fixture using the new contract wording;
- one stale-report/regeneration check for a dated stage so report placement follows the source date.

### Regression preservation

- existing missing-input FAIL discipline remains intact;
- direct inactive-stage invocation produces a clear inactive-stage result rather than a misleading artifact-missing report;
- `triggers` still FAILs loudly until Phase 2 gives it real metrics.

## Phase 2 sequencing

### 2A. Re-run and classify

Generate fresh reports from the repaired framework and bucket every non-PASS as:

1. real product/data defect,
2. metric design defect,
3. intentionally unfinished functionality,
4. retained operational warning.

No product changes should be planned from stale Phase-0 reports.

### 2B. Fix metric defects before product defects

Likely first candidates:

- `opportunity.same_theme_distinct_index_limit`: current implementation collapses all rows without a theme into `_unthemed`, causing unrelated assets such as gold, bond funds, Nasdaq 100, and S&P 500 exposures to count as one “theme.” That is not the invariant the metric claims to measure.
- `scoring.score_distribution_stability`: current runner compares the first half and second half of a single list. The design docs describe a distribution-stability measure; the implementation is order-sensitive and is not a temporal stability check.
- any `gold_score`, `allocation`, or `memo` metric that cannot be grounded in the outputs the current producers emit.

### 2C. Fix real product/data gaps

Known or likely examples after rerun:

- data freshness WARNs, if the desired operating bar is still “fresh within two days”;
- any scoring completeness gap that remains after fresh artifacts are evaluated;
- the real architecture debt represented by `ingest_cmd.py` exceeding the file-length threshold.

### 2D. Resolve unfinished or inactive eval surfaces

- Implement real `triggers` eval metrics if triggers remain an active requirement.
- Decide whether `queries` should gain persisted artifacts from `irc ask` and rejoin the active suite, or whether the eval should be retired.
- Retire `news` fully unless the product regains a distinct live news stage with a real artifact contract.

### 2E. Green means meaningful green

The end state is a green **active** suite whose stages all:

- correspond to live product behavior,
- read current artifact contracts,
- use metrics that measure the claimed invariant,
- fail only for real unmet standards.

## Risks and trade-offs

- **Top-level `evals` packaging is a pragmatic compromise.** It fixes the current console-script failure with low churn, but the name is generic. A later move to `irc.evals` may still be worthwhile once the suite is stable.
- **Excluding `news` and `queries` from `--all` changes the meaning of “all.”** That is intentional: `--all` should mean all active evals, not every historical runner file still present in the repo.
- **Some metrics may lose their old inputs after contract repair.** The truthful answer is to redesign or retire those metrics, not synthesize absent fields just to preserve a legacy report shape.
- **Phase 1 will probably still end red.** That is success, not failure, if the remaining red is honest.

## Acceptance criteria

### Phase 1

- `uv run irc eval research` no longer raises `ModuleNotFoundError`.
- `irc eval --all` runs the active suite only and does not include inactive legacy stages.
- Discovery, gold-score, allocation, trade-plan, memo, and architecture runners read the live artifact contracts listed above.
- Dated reports are written under the date directory of the artifacts actually evaluated.
- Re-running against the current `2026-05-17` outputs produces reports that match the current artifacts rather than the stale `14:09` snapshot.
- Every remaining FAIL/WARN after rerun is explainable as an honest product, metric, or unfinished-functionality issue.

### Phase 2

- Fresh reports from the repaired suite have been triaged into the four buckets above.
- Mis-specified metrics are corrected before product changes are made from their signal.
- Active intentionally unfinished stages, especially `triggers`, are either implemented or deliberately removed from the active contract.
- The final active suite is green, except for any operational warning explicitly retained and documented by design.
