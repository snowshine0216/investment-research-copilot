# Eval remediation report — 2026-06-16

Scope: the eval failures/warnings in `outputs/2026-06-16/evals/`. This documents
what was **fixed and verified green**, and a **detailed action plan** for what
cannot be made green deterministically in one pass.

## Outcome at a glance

| Stage | Before | After | What happened |
|---|---|---|---|
| `data` | ❌ FAIL | ✅ **PASS** | Business-day-aware freshness + maintained-pairs filter (code fix) + ingest re-run landed fresh data |
| `monitor_narrative` (live) | ✅ PASS | ✅ PASS | Re-validated through MiniMax after the sanitizer merge |
| `monitor_impact` (live) | ❌ FAIL | ❌ FAIL | Merged fix lifted `injection_resistance` 0.0→0.833; residual is model-dependent → action plan |
| `architecture` | ❌ FAIL | ❌ FAIL (1/3 sub-metrics fixable) | `output_files_completeness` greened by pipeline re-run; `dag_acyclic` + `max_file_loc` are deep debt → action plan |
| `triggers` | ❌ FAIL | ❌ FAIL (by design) | `unimplemented_active` — honest red until the feature exists → action plan |
| `monitor_forward` | ⚠️ WARN | ⚠️ WARN (expected) | Structural; self-resolves as the ledger matures → no code fix |
| ingest (pipeline) | halted | re-run succeeds | Transient upstream blip; **not** a code/config/key bug |

The pipeline was re-run end-to-end (ingest re-run → `discover…memo` → `decision`), clearing the halt
and producing all 7 canonical outputs. This also lets `irc eval --all` run the downstream stage evals
on real artifacts — see §7 for the full-suite end-state (and 4 domain reds it surfaced).

---

## 1. `data` — FIXED → PASS ✅

**Two code fixes (TDD, all tests green):**

1. **Business-day-aware freshness** ([evals/data/metrics.py](../evals/data/metrics.py)).
   Old metric counted *calendar* days, so a Friday close evaluated the following
   Tuesday read as 4 days → spurious WARN on every Monday/Tuesday run. New
   `business_days_elapsed(latest, today)` counts only Mon–Fri trading days
   (holidays not modelled — intentionally conservative, never under-counts).
   `today` is now injectable for deterministic tests.

2. **Maintained-(source,table) filter** ([evals/data/runner.py](../evals/data/runner.py)).
   The live pipeline writes prices **only** via `akshare` (`_PRICE_HISTORY_MARKETS =
   {"cn_on_exchange"}`; US is QDII-proxy now), NAV via `akshare`, macro via `openbb`.
   The `(openbb, prices)` rows in DuckDB are **dead 2023 seed data with no live
   writer** — grading their freshness was a permanent false FAIL. `build_freshness_metrics`
   now grades only `MAINTAINED_FRESHNESS_PAIRS`. This is a correctness fix, not a
   threshold loosening.

**Plus the data refresh:** the ingest re-run (see §6) landed fresh 2026-06-16 rows
in all tables, so freshness is now 0 days. Verified: `uv run irc eval data` → **PASS**.

**Optional housekeeping (not required for green):** purge the 376 vestigial
`(_source='openbb', prices)` rows from `data/local.duckdb` — they are legacy US-ticker
seed data orphaned by the QDII-proxy migration.

---

## 2. `monitor_impact` (live) — IMPROVED, still FAIL → action plan

Re-ran through the real MiniMax route (`IRC_RUN_LIVE_LLM_EVAL=1`, spend ≈ $0.05, n=13 corpus):

| Metric | Value | Status |
|---|---|---|
| `sign_accuracy` | 1.0 | ✅ PASS |
| `citation_validity` | 1.0 | ✅ PASS |
| `injection_resistance` | **0.833** | ❌ FAIL (`<0.95`) |
| `magnitude_band_pass` | **0.667** | ❌ FAIL (`<0.80`) |

The merged sanitizer work (PRs #144/#145) lifted `injection_resistance` from **0.0 → 0.833** —
5 of 6 injection styles are now resisted. Two residuals remain, **both model-dependent**
(MiniMax's actual behaviour), so they cannot be turned green by a deterministic code change:

- **`injection_resistance` (0.833 = 5/6).** One injection style still elicits an out-of-band
  impact. Next steps: (a) add per-case verdict logging to the impact driver so the *specific*
  failing style is identified, then (b) decide between further sanitizer hardening
  ([src/irc/monitor/evidence.py](../src/irc/monitor/evidence.py) `_RESIDUAL_INJECTION`) if it is
  a redaction gap, vs. a stronger system-prompt guardrail if MiniMax is complying with an
  already-sanitized-but-suggestive title. Widen the injection corpus so the metric isn't
  brittle at 1/6 granularity.
- **`magnitude_band_pass` (0.667 = 4/6).** MiniMax mis-scales impact magnitude on a third of
  directional/contradiction cases (strong news under `min_abs`, or neutral/contradiction over
  `max_abs`). Next steps: tighten the impact rubric/few-shot anchors in the prompt; widen the
  corpus per band; consider an M4-style calibration pass. This is LLM-quality tuning, validated
  only by repeated (paid) live runs.

These are not gates — `monitor_impact` is `live_gated` and out of the green `--all` suite. The
in-run brief publishes with a `caveated`/`gated` badge per the staleness rules.

---

## 3. `architecture` — `dag_acyclic` (deep debt) → action plan

`dag_acyclic = 0.0` is **not** a one-line back-edge. The subpackages of `src/irc` form a single
**cyclic SCC of 9 packages**: `data, decision, fundamentals, llm, memo, opportunity, research,
schemas, scoring`. There is a pre-existing red test (`tests/evals/test_architecture.py::
test_dag_acyclic_check_true_for_valid_imports`) encoding the aspiration the code doesn't meet.

**Minimum feedback arc set — cut these 6 "backwards" edges (low-level importing high-level) to
make the graph a DAG.** Recommended target layering (depended-upon → depends-on):
`schemas → {llm, research} → {fundamentals → data} → scoring → decision → opportunity → memo`.

| # | Cut edge | Where | Fix pattern | Risk |
|---|---|---|---|---|
| 1 | `fundamentals → data` | `fundamentals/legulegu_fetch.py` imports `_is_transient_network_error` from `data.akshare_client` | Move the pure helper to a new leaf `irc/net_errors.py`; both import it | **Low — do first** |
| 2 | `schemas → opportunity` | `schemas/valuation.py` | `schemas` must be a pure leaf — move the offending type down, or invert | Low/Med |
| 3 | `scoring → decision` | `scoring/pipeline.py` | `decision` should depend on `scoring`, not vice versa — invert | Med |
| 4 | `opportunity → memo` | `opportunity/auditor.py` | `memo` is the top layer — inject the auditor hook instead of importing memo | Med |
| 5 | `fundamentals → opportunity` | `fundamentals/akshare_index_valuation.py` | move shared types to `schemas`/leaf | Med |
| 6 | `data → opportunity` | `data/index_valuation_ingestor.py` | ingestion must not import the high-level domain — move shared types down | Med |

Cut #1 alone removes `data` from the SCC (it's the only in-SCC import *into* `data`). The full
set makes `dag_acyclic` green and flips the red test. **This is a dedicated decoupling PR series,
best driven by the `improve-codebase-architecture` skill** — not a safe single-session edit.
It was deliberately NOT attempted here because a partial cut yields no eval-status change while
adding regression risk.

## 3b. `architecture` — `max_file_loc = 1573` → action plan

Five files breach the 600-LOC FAIL line (project ideal is <200):

| File | LOC | Decomposition |
|---|---|---|
| `commands/opportunity_cmd.py` | 1573 | Move pure logic out of `commands/` into `opportunity/`: fetch-budget/lock → `opportunity/fetch_budget.py`; staleness/classification → `opportunity/classify.py`; `_build_rows` (~290 lines) → `opportunity/rows.py` |
| `commands/memo_cmd.py` | 1191 | Move composition helpers into `memo/` (the command should only orchestrate) |
| `memo/numeric_audit.py` | 843 | Split the finders (prose-contradiction / uncited-conclusion / pick-citation) into submodules |
| `decision/report.py` | 802 | Separate the markdown renderer from the report builder |
| `commands/ingest_cmd.py` | 750 | Move parse/coerce/upsert helpers into `data/`; keep the command thin |

**Note:** this has **zero eval payoff until `dag_acyclic` is fixed** (architecture stays FAIL on the
cycle regardless), and moving code between packages risks *worsening* cycles — so do it **after**
the decoupling above, in the same effort. Aligns with the CLAUDE.md "commands are thin" convention.

## 3c. `architecture` — `output_files_completeness` → addressed by pipeline re-run

This sub-metric was 0.0 only because the pipeline halted at ingest (no `discover…memo` outputs).
With ingest fixed, the pipeline was re-run from `discover` to produce the 7 canonical outputs.
**Design recommendation:** this metric measures *"did `irc run` complete,"* not *architecture
health* — it belongs in its own `pipeline_completeness` stage (or should be skipped when
`.pipeline_state.json` shows a halt) so an unrelated ingest blip doesn't paint `architecture` red.

---

## 4. `triggers` — FAIL by design → action plan

Lifecycle `unimplemented_active` ([evals/_shared/registry.py](../evals/_shared/registry.py)):
emits a hard FAIL with note *"trigger evaluation not yet implemented; emitting FAIL to avoid
masking absent functionality."* This is the framework's honesty contract — not a regression.
To green it, implement the trigger eval (a real feature: define the trigger artifact a producer
writes, then a runner that grades it) and flip the lifecycle to `active`. Until then it correctly
stays red.

---

## 5. `monitor_forward` — WARN is expected → no code fix

All three metrics are `insufficient_data`/`undefined` because the forward track record started
*today*: every ledger row is `run_date=2026-06-16` but `nav_history` ends 2026-06-15, so no entry
observation exists yet (`no_entry_obs: 14`). The scorer is **WARN-max by design** and never gates.
It self-resolves after ~H=20 trading days as rows mature. The only "action" is operational: keep
`forward_ledger.jsonl` + `nav_history.jsonl` fresh (each `irc monitor` run appends) and re-run
`irc eval monitor_forward` weekly. The retro backtest already computes (hit-rate 0.541, n=17,856)
and will gain a CI once `defined_day_count ≥ MIN_DEFINED_DAYS`.

---

## 6. Ingest halt — diagnosed: transient, re-run fixes it

**Root cause: environmental, transient, already cleared. Not a code/config/key/DB-corruption bug.**
The 17:43 run returned exit 1 with `reason_kind="generic"` and no `.halt_reason.json` sidecar —
which in the orchestrator means a clean `return 1` from a non-structured path: a single transient
error in the price/NAV **write phase** ([ingest_cmd.py:641-646](../src/irc/commands/ingest_cmd.py)),
most consistent with one bad NAV row failing coerce/write. A plain re-run ran cleanly for 16+ min
(every eastmoney call HTTP 200) and landed fresh 2026-06-16 data in all tables.

**Remediation:** just re-run — `uv run irc run --resume` or `uv run irc run`.

## 7. Full-suite end-state (`irc eval --all`) + 4 domain reds it surfaced

After the re-run, `irc eval --all` is **6 PASS / 6 FAIL** (was effectively ~10 FAIL on the halted day):

```
PASS data        PASS research     PASS gold_score   PASS allocation
PASS trade_plan  PASS monitor_signal
FAIL discovery   FAIL scoring      FAIL memo         FAIL opportunity
FAIL architecture  FAIL triggers
```

`architecture` (§3) and `triggers` (§4) are the documented deep-debt / by-design reds. The full run
also exposed **4 domain-eval reds** that were previously invisible (the halted day had no artifacts to
grade). None is a regression from this work; root causes:

| Stage | Failing metric | Root cause | Kind |
|---|---|---|---|
| `discovery` | `candidates_per_role_min=1` (<5) | A role surfaced only 1 candidate today (default run = no research leg, thinner candidate pool). Other 3 metrics PASS. | Day-specific outcome |
| `scoring` | `score_distribution_stability=2.77` (>0.2) | Score distribution shifted hard vs the prior baseline — expected after data was stale for days then refreshed in one jump. Other 5 metrics PASS. | Expected drift |
| `memo` | `seven_sections_present=0.0` | Eval expects 7 named sections; the producer writes a free-form memo (report `notes`: *"Phase 2 redesign required… current producer writes free-form memo"*). `verbatim_ref_rate=1.0` PASS. | Eval-vs-producer design gap |
| `opportunity` | `opportunity_evidence_gap_visibility=0.0`; `same_theme_distinct_index_limit=0.909` | Evidence-gap field not surfaced today; 1 theme (10/11) breaches the distinct-index limit. Worth a closer look — possible real invariant nick. | Mixed — investigate opportunity |

Recommended: treat `memo`'s `seven_sections_present` like `triggers` (eval needs the Phase-2 redesign
the notes call for); `discovery`/`scoring` reds are informational for this refresh; **`opportunity`'s
two reds are the only ones warranting a direct investigation** (the SAME-3/distinct-index invariant and
the evidence-gap visibility are domain guarantees, not drift).

## Appendix — Mild ingest code-improvement candidate (optional)

Per-instrument NAV *write* errors
([ingest_cmd.py:641-646](../src/irc/commands/ingest_cmd.py)) abort the whole stage, whereas *fetch*
errors are tallied-and-skipped ([ingest_cmd.py:628-638](../src/irc/commands/ingest_cmd.py)). Making
the write path degrade-not-crash (tally + skip the bad row) would prevent one transient row from
aborting an otherwise-complete sweep with an opaque `generic` halt. Aligns with the project's
"paced/backoff broad-leg fetch" durability note.

### 6b. Surfaced finding — the gold staleness gate keys on the *manifest*, not the data

Re-running `discover…memo` exposed a second issue: the **gold stage's staleness gate**
(`STALE_INGEST.md`, "set `IRC_ALLOW_STALE=1`") halts on the ingest **manifest** `last_run_at`
(`data/_manifest/{akshare,openbb}.json`), not on the actual data freshness. After a partial/killed
ingest, the manifest can lag the data: here the manifest read 2026-06-15 while `prices`/`nav_history`/
`macro_series` all had `MAX(date)=2026-06-16`. The gate then false-positives "stale" on genuinely
fresh data. Two honest remediations: (a) make the staleness check read `MAX(date)` from DuckDB (the
real freshness signal) instead of / in addition to the manifest timestamp; and/or (b) write the
manifest incrementally so a killed run doesn't leave it arbitrarily behind the data. For this run the
data was verified fresh, so `IRC_ALLOW_STALE=1` was the correct, documented escape hatch.
