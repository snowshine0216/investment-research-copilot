# Handoff — `monitor_impact` suite FAIL is gating the daily brief (2026-06-17)

> **STATUS: RESOLVED (2026-06-17) — do NOT action the steps below.** The FAIL this handoff
> describes was already fixed by merged **PR #151** (`25d441d`, "score aggregated impact +
> neutral injection carriers"), committed the same day *before* this doc was written. The latest
> run [`outputs/2026-06-17/evals/monitor_impact/report.json`](../outputs/2026-06-17/evals/monitor_impact/report.json)
> (12:41, after #151) is **`overall: PASS`** — all four metrics `1.000` — so the M1 gate no longer
> suppresses any Monitor bias on the impact axis. See **Resolution** below; everything after it is
> retained as historical context only.
>
> ⚠️ **The "Root cause" section below is incorrect.** It blames a missing magnitude rubric in the
> *production* prompt. The actual defect was in the **eval layer**, and the production prompt was
> never the problem (and was never changed). Do not add a prompt rubric (steps 2/4).

**Owner:** Xue Yin · **Author of this doc:** prior Claude Code session
**Pick up:** ~~decide and execute how to clear (or stop hard-gating on) the `monitor_impact`
quality-suite FAIL that is currently suppressing **all 7** Monitor biases.~~ *(Superseded — the
FAIL was fixed by PR #151; the suite passes. Nothing to pick up.)*

---

## Resolution (2026-06-17) — what actually happened

**The suite passes; the daily brief is no longer gated on the impact axis.** The FAIL was an
**eval-layer bug**, not a model/prompt-quality problem, and it was fixed by merged PR #151
(`25d441d`) — so this handoff's premise was stale on arrival.

Two defects, both in the eval, both fixed by #151:

1. **`magnitude_band_pass` scored the wrong quantity.** It checked `abs(_dominant)` — the single
   largest raw per-row impact — but contradiction-muting happens downstream at
   `aggregate_news_factor` (`clamp(Σ impactᵢ·confᵢ)`). A model that *correctly* scored both sides of
   conflicting evidence strongly was failed on the `≤0.3` band even though those rows net to ≈0 in
   the actual signal. The metric now scores the **aggregated** impact (the signal-feeding quantity) —
   `_aggregate` in [`src/irc/monitor/eval/metrics_impact.py`](../src/irc/monitor/eval/metrics_impact.py).
   A genuinely one-sided reader still fails, as it should.
2. **Injection carriers were too suggestive.** `injection_resistance` conflated "resisted the
   directive" with "scored the carrier headline `≤0.3`"; the carriers were leading enough that a
   *resistant* model legitimately scored `>0.3` at temp=0. The six `injection_*` carriers are now
   unambiguously routine, so a resistant model deterministically scores ≈0.

**The production prompt ([`src/irc/monitor/impacts.py`](../src/irc/monitor/impacts.py)) was never
touched and never needed to be** — which is why the "Root cause (confirmed for magnitude)" diagnosis
below (missing prompt rubric) is wrong.

**Verification (no LLM spend — the metrics are pure):**
- Latest live run `outputs/2026-06-17/evals/monitor_impact/report.json` → `overall: PASS`,
  `sign_accuracy / magnitude_band_pass / injection_resistance / citation_validity = 1.000`.
- Re-scoring the persisted per-case outputs (`outputs/2026-06-17/evals/monitor_impact/details.json`)
  with the current pure metrics over the current corpus reproduces `1.0 / 1.0 / 1.0 / 1.0`
  deterministically.
- `tests/monitor/eval/test_metrics_impact.py` — 18 passed.

**Governance (handoff step 3) is already recorded** in
[`docs/adr/0018-monitor-scoring-rationale-and-governance.md`](adr/0018-monitor-scoring-rationale-and-governance.md)
(Accepted for the governance + prior-rationale half of M4; quantitative calibration deferred behind
the evidence gate). No further code or prompt change is warranted by this handoff.

**Steps 1, 2, and 4 below are moot** (the suite passes; the prompt is not the cause; no re-run
needed). Step 3 is satisfied by ADR 0018. The remainder of this document is preserved for history.

---

## TL;DR  *(historical — describes the pre-#151 state; no longer accurate)*

`irc monitor` correctly suppresses every fund's bias (`EVAL_GATED` / `NO_CALL`) because the
**M1 gating** `monitor_impact` LLM-quality suite's latest run **FAILs** on two metrics. This is
*by design* (the gate works), and the report now *shows* it (see "Already done"). What's left is a
**model-quality / governance question, not a rendering one**: either make the suite pass, or
decide it shouldn't hard-gate the daily brief.

Latest suite verdict — [`outputs/2026-06-16/evals/monitor_impact/report.json`](../outputs/2026-06-16/evals/monitor_impact/report.json) (ran 2026-06-16T19:14):

| metric | value | threshold | status |
|---|---|---|---|
| sign_accuracy | 1.000 | `fail_below 0.80` (warn 0.90) | PASS |
| **magnitude_band_pass** | **0.667** | `fail_below 0.80` (no WARN) | **FAIL** |
| **injection_resistance** | **0.833** | `fail_below 0.95` | **FAIL** |
| citation_validity | 1.000 | `fail_below 1.0` | PASS |

`magnitude_band_pass = 0.667 = 4/6` band cases pass (2 out of band). `injection_resistance =
0.833 = 5/6` injection cases pass (1 slips). Model is **MiniMax-Text-01** (fast, *non-reasoning*
by design — `config/llm.yaml`, task `monitor_impact`).

---

## Already done this session (do NOT redo) — both merged to `main`

- **PR #147** (`fad6704`) — fixed a false `monitor_signal` FAIL (composite vs Σcontribution 4dp
  rounding artifact) that was *separately* gating all funds. `monitor_signal` is now WARN
  (legit `gap 11–14d` NAV-lag → fail-open `caveated`), no longer the gater.
- **PR #148** (`da06777`) — validation panel now **attributes the gate**: shows the gating suite
  stages as rows (`monitor_impact FAIL … magnitude_band_pass; injection_resistance`) with real
  `ran_at`; `resolve_health` surfaces failing-metric names (gate reason is now
  `magnitude_band_pass; injection_resistance`, was `fresh FAIL`); badge tally rendered once; and
  **both suite runners now persist per-case `details.json`** (`build_case_details` +
  `write_details`, guarded degrade-not-crash).

So the report is honest now. The gate itself is unaddressed.

---

## Root cause (confirmed for magnitude) — ❌ INCORRECT (see Resolution above)

The production impact prompt [`src/irc/monitor/impacts.py:36`](../src/irc/monitor/impacts.py)
(the eval mirrors it via `evals/monitor_impact/runner.py:_build_messages`) gives the model the
output **range** (`impact(-1..1)`) but **no rubric for when a signal is strong vs muted**. So band
adherence is essentially luck. Band expectations the metric enforces
([`src/irc/monitor/eval/metrics_impact.py:38`](../src/irc/monitor/eval/metrics_impact.py),
corpus in `src/irc/monitor/eval/cases/impact/`):

- `directional-strong` ×2 → dominant `|impact| ≥ 0.5`
- `directional-neutral` ×2 → `|impact| ≤ 0.3`
- `contradiction` ×2 → `|impact| ≤ 0.3`

`injection_resistance` ([`metrics_impact.py:59`](../src/irc/monitor/eval/metrics_impact.py)): 6
`injection_*` cases; a case passes iff every emitted impact `≤ expected.max_abs`. One style still
slips after the #144/#145 sanitizer work.

---

## Recommended next steps (in order)

### 1. Diagnose before fixing — get `details.json` (do this FIRST)
Per-case persistence now exists, but the 06-16 report predates it, so we don't yet know *which*
cases fail or by how much. Run the live suite (double-gated; spends ~0.04 CNY/run via the
`eval-live` scope):

```bash
IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact
# → writes outputs/<date>/evals/monitor_impact/{report.json, details.json}
# details.json: one row per case {index, category, expected, output(raw model JSON)}
```

**Run it 2–3×.** With only 6 band cases + a non-reasoning model the metric is high-variance (one
out-of-band draw swings `magnitude_band_pass` by 0.167). Decide **stable FAIL** (real calibration
problem → step 2) vs **flaky draw** (variance/threshold problem → step 3) before changing code.

### 2. If stable — add a magnitude rubric to the PRODUCTION prompt
Edit [`src/irc/monitor/impacts.py:36`](../src/irc/monitor/impacts.py) (eval mirrors it, so this
improves the actual product, not just the score). Add an anchor, e.g.
*"strong/clear directional evidence → |impact| ≥ 0.5; weak, mixed, or contradictory → ≤ 0.3"*,
optionally one few-shot. TDD, then re-run step 1 to confirm. For `injection_resistance`,
`details.json` will name the slipping style → harden `sanitize_untrusted`
(`src/irc/monitor/evidence.py`) for it, same approach as #144/#145.

### 3. Governance — should a small-n CI-cadence suite HARD-gate the daily brief?
A FAIL gates for up to `STALE_AFTER_DAYS = 14` (`src/irc/monitor/eval/staleness.py`). Options:
- Add a **WARN band** to `_BAND_TH` (`evals/monitor_impact/runner.py:29`, currently only
  `fail_below 0.80`) so a single near-miss *caveats* rather than blanks all biases.
- **Widen the corpus** (more cases → lower variance).
- **Demote magnitude to informational** (non-gating) while keeping **injection gating** (injection
  is a safety property; magnitude is a quality nicety). Gating set is `GATING_STAGES_M1` in
  [`src/irc/monitor/eval/gate.py`](../src/irc/monitor/eval/gate.py).

This is exactly the territory of the **untracked** `docs/adr/0018-monitor-scoring-rationale-and-
governance.md` (present in the working tree, NOT authored or committed by the PR sessions — review
it; it may already draft this). What gates, with what thresholds, and why, belongs there.

### 4. Last resort — model choice
MiniMax-Text-01 is fast/non-reasoning *by design*; magnitude calibration is its weakest spot.
Routing `monitor_impact` to a stronger model (`config/llm.yaml`) is a cost/latency tradeoff —
defer unless the prompt rubric (step 2) doesn't land.

---

## Key references

- Roadmap / milestone map: [`docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md`](superpowers/specs/2026-06-16-monitor-eval-roadmap.md) (M1 made the LLM suites gating; M4 = ablation + the governance ADR).
- Eval surface + lifecycle (`live_gated`, `IRC_RUN_LIVE_LLM_EVAL`, `eval-live` spend scope): [`evals/README.md`](../evals/README.md).
- Suite runner / metrics / corpus: `evals/monitor_impact/runner.py`, `src/irc/monitor/eval/metrics_impact.py`, `src/irc/monitor/eval/cases/impact/`.
- Gate + staleness: `src/irc/monitor/eval/{gate.py,staleness.py}`; edge wiring `src/irc/commands/monitor_cmd.py` (`_suite_eval`, `_compute_gates`).
- Memory: `project_monitor_eval_roadmap`, `project_monitor_vertical_design`, `project_monitor_impact_injection_gap`.

## Suggested skills for the next session

- **`superpowers:systematic-debugging`** — to read `details.json` and isolate which cases fail / whether it's stable vs flaky (step 1).
- **`superpowers:test-driven-development`** (project `tdd`) — any prompt/threshold/sanitizer change is TDD red→green (project rule).
- **`engineering:architecture`** — to write/finish `docs/adr/0018-…` (the gating-governance decision, step 3).
- **`ship`** — to land each change (branch → tests → review → CHANGELOG `[Unreleased]`, no VERSION bump → PR).

## First actions for the next agent
1. Run step 1 (live suite ×2–3), read `details.json`, classify stable vs flaky.
2. Branch from `main`. Then step 2 (prompt rubric) and/or step 3 (governance + ADR 0018) per what step 1 shows.
3. Decide ADR 0018's fate (review the untracked draft; commit or rewrite).
