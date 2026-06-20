# Monitor forward-eval engine-drop WARN (`engine_population` diagnostic row) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one attribution-only diagnostic row — `engine_population` — to the `irc eval monitor_forward` stage report that WARNs *only* when an `_ENGINE_VERSION` bump is the proximate cause of a thin headline metric, so an operator can tell "thin because of the engine reset" apart from "thin because the signal is generally young."

**Architecture:** A pure 4-cell truth-table helper `engine_population_status` lives in `evals/monitor_forward/metrics.py`; the runner (`evals/monitor_forward/runner.py`) calls it after `build_metric_reports`, builds a 4th `MetricReport`, **appends** it to `reports`, and writes a name-keyed `details["engine_population"]` block with **mandatory** `ci_low: None` / `ci_high: None`. No schema change, no scorer change, no panel-renderer change — the row rides existing `MetricReport`/`PredictiveMetricView` fields. It is attribution-only: its WARN can only co-occur with a headline WARN that already lifted the stage status, so it never changes `overall`/`rc`.

**Tech Stack:** Python 3.12+, pytest, uv, frozen dataclasses (`MetricReport` / `PredictiveMetricView`), DuckDB-adjacent eval runner (no network/LLM/spend in this stage).

---

## Background the implementer MUST internalize before touching code

Read these constraints once; the tasks below assume them. Getting any of these wrong silently breaks the feature.

1. **The pure helper signature is exact:**
   `engine_population_status(*, n_excluded_engine: int, headline_state: str) -> tuple[str, str]`.
   Only `(n_excluded_engine > 0 AND headline_state == "insufficient_data")` → `("WARN", "engine_transition")`. **All three other cells** → `("PASS", "ok")`. `rank_ic` is DELIBERATELY excluded from the trigger (spec D2) — do not key on it.

2. **The 4th report is APPENDED in `runner.py`, NOT inside `build_metric_reports`.** `build_metric_reports` must keep returning exactly 3 metrics so its direct test (`tests/evals/test_monitor_forward_metrics.py::test_three_metric_rows_named` and `::test_retro_does_not_add_fourth_metric_row`) stays green.

3. **`headline_state` is read by DIRECT indexing:** `details["publishable_bias_directional"]["state"]`. A missing key MUST raise (fail loudly during eval development), never silently default to a false PASS. Do **not** use `.get(...)` here.

4. **`value` = `(len(ledger) - n_excluded_engine) / len(ledger)`** with an **empty-ledger guard** returning `0.0` when `ledger == []` (no division by zero). `n_observations = effective_n(forward_rows)`. These describe two different real populations (raw-ledger share vs matured block span) — that mismatch is intentional and labeled in the details block; do not "fix" it.

5. **`details["engine_population"]` MUST include `ci_low: None` and `ci_high: None` explicitly.** This is the one latent bug to avoid: `_metric_view` (src/irc/commands/monitor_cmd.py:529) does `ci_low=md.get("ci_low", m.value)`. An **explicit** stored `None` flows through to `None` → panel prints `"CI pending"`. **OMITTING** the keys defaults to `m.value` (the share) → a faked `[+v, +v]` interval. So the keys are mandatory and must be `None`. Also include `threshold = {}` on the `MetricReport` (never `fail_below`).

6. **`details["excluded_by_engine"]` raw counts stay unchanged** (runner.py:159-160). The new block is additive.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `evals/monitor_forward/metrics.py` | Pure cores → MetricReports + details | **Add** pure `engine_population_status` helper (no I/O). `build_metric_reports` unchanged. |
| `evals/monitor_forward/runner.py` | EDGE: read ledger → call cores → write report | **Append** the `engine_population` MetricReport + write `details["engine_population"]` block. |
| `tests/evals/test_monitor_forward_metrics.py` | Pure-helper tests | **Add** the 4-cell truth-table test. |
| `tests/evals/test_monitor_forward_runner.py` | Runner integration tests | **Add** engine-transition + empty-ledger tests; **edit** the `len(report["metrics"]) == 3 → 4` assertion at line 214. |
| `tests/commands/test_monitor_cmd_predictive_panel.py` | Command-edge panel-model tests | **Add** CI-None preservation test through `_predictive_panel_model`. |
| `tests/monitor/eval/test_predictive_panel.py` | Pure renderer tests | **Add** `engine_population` row render test. |
| `CONTEXT.md` | Domain glossary (shipped reality) | **Three §9 edits** — land with this PR (see Task 8). |

No schema change: `evals/_shared/report_schema.py`, `src/irc/monitor/eval/types.py`, and `src/irc/monitor/eval/predictive_panel.py` are **untouched**.

---

## Task 1: Pure helper `engine_population_status` (truth table)

**Files:**
- Modify: `evals/monitor_forward/metrics.py` (add helper near top, after the `_IC_TH` constants at line 27)
- Test: `tests/evals/test_monitor_forward_metrics.py`

- [ ] **Step 1: Write the failing truth-table test**

Append to the END of `tests/evals/test_monitor_forward_metrics.py`:

```python


# ── FU1: engine_population diagnostic row — pure status truth table ───────────

def test_engine_population_status_truth_table():
    """4 cells of (n_excluded_engine ∈ {0, >0}) × (headline_state ∈
    {'insufficient_data', 'ok'}). Only (>0, 'insufficient_data') →
    ('WARN', 'engine_transition'); the other three → ('PASS', 'ok').
    rank_ic is DELIBERATELY not an input (spec D2)."""
    from evals.monitor_forward.metrics import engine_population_status

    assert engine_population_status(
        n_excluded_engine=5, headline_state="insufficient_data"
    ) == ("WARN", "engine_transition")
    assert engine_population_status(
        n_excluded_engine=5, headline_state="ok"
    ) == ("PASS", "ok")
    assert engine_population_status(
        n_excluded_engine=0, headline_state="insufficient_data"
    ) == ("PASS", "ok")
    assert engine_population_status(
        n_excluded_engine=0, headline_state="ok"
    ) == ("PASS", "ok")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py::test_engine_population_status_truth_table -q`
Expected: FAIL with `ImportError: cannot import name 'engine_population_status'` (or `AttributeError`).

- [ ] **Step 3: Add the pure helper to `evals/monitor_forward/metrics.py`**

The file currently has these lines at 25-28:

```python
# direction is higher_is_better for all three; thresholds are documentation-only
_HIT_TH: dict[str, float] = {}      # NO fail_below — WARN set manually
_IC_TH: dict[str, float] = {}
```

Insert the helper immediately AFTER the `_IC_TH` line (so it sits at module scope, before `_composite_rows`):

```python
# direction is higher_is_better for all three; thresholds are documentation-only
_HIT_TH: dict[str, float] = {}      # NO fail_below — WARN set manually
_IC_TH: dict[str, float] = {}


def engine_population_status(
    *, n_excluded_engine: int, headline_state: str
) -> tuple[str, str]:
    """PURE. Returns (status, state_code) for the engine_population diagnostic row.

    headline_state is publishable_bias_directional's state from
    build_metric_reports' details dict. rank_ic is DELIBERATELY excluded from the
    trigger (spec D2): its cross-sectional 'undefined' flapping is not an engine
    signal and would resurrect the permanent false-attribution WARN.
    """
    if n_excluded_engine == 0:
        return "PASS", "ok"                   # single-engine ledger; no transition
    if headline_state == "insufficient_data":
        return "WARN", "engine_transition"    # drop is material AND headline is thin
    return "PASS", "ok"                       # drop happened, but headline is sufficient
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py::test_engine_population_status_truth_table -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Verify `build_metric_reports` still returns exactly 3 (no regression)**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py -q`
Expected: PASS — all existing tests green, including `test_three_metric_rows_named` and `test_retro_does_not_add_fourth_metric_row` (the helper does NOT touch `build_metric_reports`).

- [ ] **Step 6: Commit**

```bash
git add evals/monitor_forward/metrics.py tests/evals/test_monitor_forward_metrics.py
git commit -m "feat(monitor): pure engine_population_status helper (truth table)"
```

---

## Task 2: Append the `engine_population` MetricReport in the runner

**Files:**
- Modify: `evals/monitor_forward/runner.py` (import at line 26; append logic after the `excluded_by_engine` write at lines 158-160)
- Test: `tests/evals/test_monitor_forward_runner.py`

### Context: the exact insertion point in `runner.py`

Lines 155-161 currently read:

```python
    reports, details = build_metric_reports(
        forward_rows=forward_rows, retro_points=retro_points,
        seed=20260616, momentum_by_key=momentum_by_key)
    details["forward_excluded"] = _excl
    details["excluded_by_engine"] = {"target_engine": target_engine,
                                     "engine_mismatch": _excl.get("engine_mismatch", 0)}
```

Line 22 already imports `N_MIN_BLOCKS`? No — line 22 imports `FORWARD_H` only. We must add `N_MIN_BLOCKS` and `effective_n` imports, and import the new helper.

- [ ] **Step 1: Write the failing engine-transition runner test**

The existing test helpers `_ledger_line` (no `manifest_versions` ⇒ legacy engine `'0'`) and `_nav_lines` are at the top of `tests/evals/test_monitor_forward_runner.py`. Append this test to the END of the file:

```python


# ── FU1: engine_population diagnostic row ─────────────────────────────────────

def _ledger_line_engine(run_date, fund, as_of, engine, status="ok",
                        comp=0.2, bias="ADD_BIAS"):
    """Like _ledger_line but stamps manifest_versions.engine so the runner's
    _target_engine / engine_mismatch path activates."""
    return json.dumps({
        "run_date": run_date, "fund_id": fund, "written_at": f"{run_date}T09:00:00",
        "raw_status": status, "raw_bias": bias, "raw_composite": comp,
        "nav_acc": 1.0, "as_of_date": as_of, "manifest_versions": {"engine": engine},
    })


def test_engine_population_warns_on_transition(tmp_path: Path):
    """A ledger dominated by legacy-engine rows (dropped under engine_mismatch)
    with a thin matured engine-'2' population → engine_population row WARNs,
    state 'engine_transition', ci_low/ci_high None (producer side of the CI
    contract), and run() returns rc 1 (WARN)."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    # 3 legacy-engine rows (engine '0') + 1 target-engine row (engine '2').
    # target_engine='2' → the 3 legacy rows drop under engine_mismatch, leaving
    # 1 thin matured target-engine row → publishable_bias_directional is
    # insufficient_data → engine_population must WARN.
    lines = [
        _ledger_line_engine(run_date, "a", run_date, "0"),
        _ledger_line_engine(run_date, "b", run_date, "0"),
        _ledger_line_engine(run_date, "c", run_date, "0"),
        _ledger_line_engine(run_date, "a", run_date, "2"),
    ]
    (md / "forward_ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rc = run(tmp_path)
    assert rc == EVAL_RC_WARN
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    names = [m["name"] for m in report["metrics"]]
    assert "engine_population" in names
    ep = next(m for m in report["metrics"] if m["name"] == "engine_population")
    assert ep["status"] == "WARN"

    details = json.loads((out_dir / "details.json").read_text())
    epd = details["engine_population"]
    assert epd["state"] == "engine_transition"
    assert epd["ci_low"] is None and epd["ci_high"] is None
    assert epd["n_excluded"] >= 1
    # raw counts unchanged (additive block)
    assert details["excluded_by_engine"]["engine_mismatch"] >= 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_forward_runner.py::test_engine_population_warns_on_transition -q`
Expected: FAIL — `"engine_population" not in names` (the report still has only 3 metrics) / `KeyError: 'engine_population'`.

- [ ] **Step 3: Add the imports to `evals/monitor_forward/runner.py`**

Line 22 currently reads:

```python
from irc.monitor.eval.constants import FORWARD_H
```

Change it to:

```python
from irc.monitor.eval.constants import FORWARD_H, N_MIN_BLOCKS
```

Line 26 currently reads:

```python
from evals.monitor_forward.metrics import build_metric_reports
```

Change it to:

```python
from evals.monitor_forward.metrics import build_metric_reports, engine_population_status
```

Add the `effective_n` import. Line 13 currently imports from `irc.monitor.eval.stats`? No — `effective_n` is in `irc.monitor.eval.stats` but is not yet imported in the runner. Add a new import line directly after line 24 (`from irc.monitor.resolve import resolve_funds`):

```python
from irc.monitor.resolve import resolve_funds
from irc.monitor.eval.stats import effective_n
from evals.monitor_forward.metrics import build_metric_reports, engine_population_status
```

(So the final import block at lines 24-26 reads: `resolve_funds`, then `effective_n`, then the metrics import on the line you edited in the prior sub-step.)

- [ ] **Step 4: Append the `engine_population` report + details block**

Lines 158-160 currently read:

```python
    details["forward_excluded"] = _excl
    details["excluded_by_engine"] = {"target_engine": target_engine,
                                     "engine_mismatch": _excl.get("engine_mismatch", 0)}
```

Insert the following block IMMEDIATELY AFTER line 160 (after the `excluded_by_engine` assignment, before the comment `# write details.json sibling` at line 162):

```python
    details["forward_excluded"] = _excl
    details["excluded_by_engine"] = {"target_engine": target_engine,
                                     "engine_mismatch": _excl.get("engine_mismatch", 0)}

    # FU1: engine_population diagnostic/attribution row (appended, NOT scored).
    # Surfaces WHY a post-_ENGINE_VERSION-bump forward eval is thin (engine reset)
    # vs general youth. Never gates: its WARN can only co-occur with a headline
    # WARN that already lifted the stage status (spec D3).
    n_excluded_engine = _excl.get("engine_mismatch", 0)
    headline_state = details["publishable_bias_directional"]["state"]  # direct index
    ep_status, ep_state = engine_population_status(
        n_excluded_engine=n_excluded_engine, headline_state=headline_state)
    n_total_raw = len(ledger)
    ep_value = (n_total_raw - n_excluded_engine) / n_total_raw if n_total_raw else 0.0
    reports = [*reports, MetricReport(
        name="engine_population", value=ep_value, status=ep_status,
        n_observations=effective_n([{"run_date": r.run_date} for r in forward_rows]),
        threshold={}, details_ref=None)]
    details["engine_population"] = {
        "state": ep_state,
        "ci_low": None, "ci_high": None,           # MANDATORY — explicit None → "CI pending"
        "headline_low_n": headline_state == "insufficient_data",
        "headline_metric": "publishable_bias_directional",
        "headline_state": headline_state,
        "n_excluded": n_excluded_engine,
        "n_total_raw": n_total_raw,
        "n_target_raw": n_total_raw - n_excluded_engine,
        "value_population": "raw_ledger_target_engine_share",
        "n_observations_population": "matured_target_engine_effective_n_blocks",
        "n_min_blocks": N_MIN_BLOCKS,              # provenance only (not a threshold)
    }
```

> **Note on `MetricReport`:** it is already imported in `runner.py`? Check line 17: `from evals._shared.report_schema import StageReport`. **`MetricReport` is NOT imported.** Add it.

- [ ] **Step 5: Add the `MetricReport` import**

Line 17 currently reads:

```python
from evals._shared.report_schema import StageReport
```

Change it to:

```python
from evals._shared.report_schema import MetricReport, StageReport
```

> **Why `effective_n(forward_rows)` via `[{"run_date": r.run_date} ...]`:** `effective_n` (src/irc/monitor/eval/stats.py:84) takes `Sequence[dict]` keyed on `"run_date"`. `forward_rows` are `ForwardRow` dataclasses, so wrap each as `{"run_date": r.run_date}` (same idiom as `metrics.py:209`). The matured target-engine block span — empty `forward_rows` → `0`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_forward_runner.py::test_engine_population_warns_on_transition -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```bash
git add evals/monitor_forward/runner.py tests/evals/test_monitor_forward_runner.py
git commit -m "feat(monitor): append engine_population diagnostic row in forward runner"
```

---

## Task 3: Update the existing 3→4 metric-count assertion

**Files:**
- Modify: `tests/evals/test_monitor_forward_runner.py:214`

The runner now always appends a 4th metric, so the existing assertion in
`test_runner_still_exactly_three_metric_rows_with_retro` is now wrong (that test
exercises a single-engine ledger where `engine_population` is PASS/`ok`, but the
ROW is still emitted). Per spec §7 #3, the count becomes 4 and we assert
`engine_population` is present.

- [ ] **Step 1: Edit the assertion at line 214**

Line 213-214 currently read:

```python
    report = json.loads((out_dir / "report.json").read_text())
    assert len(report["metrics"]) == 3, f"expected 3 metrics; got {len(report['metrics'])}"
```

Replace line 214 with:

```python
    report = json.loads((out_dir / "report.json").read_text())
    assert len(report["metrics"]) == 4, f"expected 4 metrics; got {len(report['metrics'])}"
    assert "engine_population" in {m["name"] for m in report["metrics"]}
```

> Optionally rename the test function `test_runner_still_exactly_three_metric_rows_with_retro` → `test_runner_emits_four_metric_rows_with_engine_population` for accuracy. If you rename it, grep first: `grep -rn "test_runner_still_exactly_three_metric_rows_with_retro" tests/` — it is not referenced elsewhere, so a rename is safe. Renaming is OPTIONAL; the assertion change is MANDATORY.

- [ ] **Step 2: Run the edited test to verify it passes**

Run: `uv run pytest "tests/evals/test_monitor_forward_runner.py::test_runner_still_exactly_three_metric_rows_with_retro" -q`
(or the new name if you renamed it)
Expected: PASS (1 passed).

- [ ] **Step 3: Confirm `build_metric_reports`'s own `len(reports) == 3` test is UNTOUCHED**

Run: `uv run pytest "tests/evals/test_monitor_forward_metrics.py::test_retro_does_not_add_fourth_metric_row" -q`
Expected: PASS — `build_metric_reports` still returns exactly 3 (the 4th row is appended only in the runner edge, not in `build_metric_reports`).

- [ ] **Step 4: Commit**

```bash
git add tests/evals/test_monitor_forward_runner.py
git commit -m "test(monitor): assert 4 metric rows incl. engine_population in runner"
```

---

## Task 4: Empty-ledger guard test

**Files:**
- Test: `tests/evals/test_monitor_forward_runner.py`

Spec §7 #4: an empty ledger must produce an `engine_population` row with
`status="PASS"`, `value == 0.0`, state `"ok"`, `n_target_raw == 0`, no crash. Do
**NOT** assert whole-stage PASS — empty `forward_rows` still makes the headline
metrics WARN.

> **Important fixture nuance:** the runner returns `EVAL_RC_FAIL` early if
> `forward_ledger.jsonl` is *missing*, and also if all lines are unparseable. An
> empty file (`"\n"`) parses to `raw_lines == []` and `ledger == []` → the
> `if raw_lines and not ledger` FAIL guard does NOT trip (raw_lines is empty), so
> the run proceeds with an empty ledger. That is the path under test.

- [ ] **Step 1: Write the failing empty-ledger test**

Append to the END of `tests/evals/test_monitor_forward_runner.py`:

```python


def test_engine_population_empty_ledger_is_pass_ok(tmp_path: Path):
    """Empty ledger: engine_population ROW is PASS, value 0.0, state 'ok',
    n_target_raw 0, no crash (empty-ledger guard avoids division). Whole-stage is
    NOT asserted PASS — empty forward_rows still WARNs the headline metrics."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    (md / "forward_ledger.jsonl").write_text("\n", encoding="utf-8")  # empty ledger

    rc = run(tmp_path)              # must NOT raise (no ZeroDivisionError)
    assert rc in (EVAL_RC_WARN, 0)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    ep = next(m for m in report["metrics"] if m["name"] == "engine_population")
    assert ep["status"] == "PASS"
    assert ep["value"] == 0.0
    details = json.loads((out_dir / "details.json").read_text())
    epd = details["engine_population"]
    assert epd["state"] == "ok"
    assert epd["n_target_raw"] == 0
    assert epd["ci_low"] is None and epd["ci_high"] is None
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/evals/test_monitor_forward_runner.py::test_engine_population_empty_ledger_is_pass_ok -q`
Expected: PASS — the empty-ledger guard (`if n_total_raw else 0.0` in Task 2 Step 4) already handles this, so this test should pass immediately against the Task 2 implementation. If it FAILS with `ZeroDivisionError`, the guard was implemented wrong — fix the `ep_value` line in `runner.py` to exactly `(n_total_raw - n_excluded_engine) / n_total_raw if n_total_raw else 0.0`.

- [ ] **Step 3: Commit**

```bash
git add tests/evals/test_monitor_forward_runner.py
git commit -m "test(monitor): engine_population empty-ledger guard (PASS/ok/value 0.0)"
```

---

## Task 5: Command-edge CI-None preservation through `_predictive_panel_model`

**Files:**
- Test: `tests/commands/test_monitor_cmd_predictive_panel.py`

Spec §7 #5: a persisted `report.json` + `details.json` carrying `engine_population`
with explicit `null` CIs, taken through the PUBLIC boundary
`_predictive_panel_model(...)` (NOT `_metric_view` directly), must yield an
`engine_population` view with `ci_low is None`. This pins the soft link where the
`md.get("ci_low", m.value)` bug lived (src/irc/commands/monitor_cmd.py:529).

> **Pattern to follow:** the existing `_write_report` helper at the top of this
> file builds a 3-metric report + details. We add a *separate* writer that also
> emits the `engine_population` row + name-keyed details with `null` CIs, so we do
> not perturb the existing tests.

- [ ] **Step 1: Write the failing CI-None preservation test**

Append to the END of `tests/commands/test_monitor_cmd_predictive_panel.py`:

```python


def _write_report_with_engine_population(root: Path, artifact_date: str):
    """Persist a 4-metric report whose engine_population row carries explicit
    null CIs in details.json (the exact on-disk shape the runner writes)."""
    d = root / "outputs" / artifact_date / "evals" / "monitor_forward"
    d.mkdir(parents=True)
    rel = f"outputs/{artifact_date}/evals/monitor_forward/details.json"
    metrics = [
        MetricReport("raw_composite_directional", 0.55, "WARN", 5, {}, rel),
        MetricReport("publishable_bias_directional", 0.6, "WARN", 1, {}, rel),
        MetricReport("rank_ic", 0.1, "WARN", 3, {}, rel),
        MetricReport("engine_population", 0.25, "WARN", 1, {}, rel),
    ]
    rep = StageReport("monitor_forward", f"{artifact_date}T09:00:00+08:00",
                      [], metrics, "WARN")
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")
    details = {
        "publishable_bias_directional": {
            "value": 0.6, "state": "insufficient_data",
            "baseline_deltas": {"random": {"state": "insufficient_data"}},
        },
        "raw_composite_directional": {"value": 0.55, "state": "ok",
                                      "baseline_deltas": {"random": {"delta": 0.0}}},
        "rank_ic": {"value": 0.1, "state": "insufficient_data",
                    "baseline_deltas": {"random": {"state": "insufficient_data"}}},
        "engine_population": {
            "state": "engine_transition", "ci_low": None, "ci_high": None,
            "headline_state": "insufficient_data", "n_excluded": 3,
            "n_total_raw": 4, "n_target_raw": 1,
        },
    }
    (d / "details.json").write_text(json.dumps(details), encoding="utf-8")


def test_engine_population_ci_none_preserved_through_panel_model(tmp_path: Path):
    """The persisted explicit-null CIs must survive _predictive_panel_model →
    _metric_view: the engine_population view has ci_low is None (NOT the value
    faked by md.get('ci_low', m.value))."""
    _write_report_with_engine_population(tmp_path, "2026-06-19")
    model = _predictive_panel_model(tmp_path, today="2026-06-20")
    assert model.present is True
    ep = next(m for m in model.metrics if m.name == "engine_population")
    assert ep.ci_low is None and ep.ci_high is None
    assert ep.state == "engine_transition"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py::test_engine_population_ci_none_preserved_through_panel_model -q`
Expected: PASS — this is a *characterization* test confirming the EXISTING `_metric_view` already preserves explicit `None` (because `md.get("ci_low", m.value)` returns the stored `None`). No source change needed; the test guards the contract against future regression. If it FAILS (e.g. `ep.ci_low == 0.25`), the details block omitted the CI keys somewhere — re-check Task 2 Step 4.

- [ ] **Step 3: Commit**

```bash
git add tests/commands/test_monitor_cmd_predictive_panel.py
git commit -m "test(monitor): pin engine_population CI-None through _predictive_panel_model"
```

---

## Task 6: Pure renderer test for the `engine_population` row

**Files:**
- Test: `tests/monitor/eval/test_predictive_panel.py`

Spec §7 #6: a `PredictiveMetricView(name="engine_population", value=0.5,
status="WARN", state="engine_transition", ci_low=None, ci_high=None,
random_delta=None, momentum_delta=None, buy_hold_delta=None, n_observations=3)`
must render HTML containing `"engine_population"`, `"CI pending"`, and enough
`"n/a"` to cover all three baseline (Δ) cells. The renderer is UNCHANGED — this
test proves the existing pure renderer already handles the new row shape.

- [ ] **Step 1: Write the failing renderer test**

Append to the END of `tests/monitor/eval/test_predictive_panel.py`:

```python


def test_engine_population_row_renders_ci_pending_and_na_deltas():
    """The engine_population row (None CIs, None deltas) renders 'engine_population',
    'CI pending', and 'n/a' for ALL THREE baseline (Δrandom/Δmomentum/Δbuy_hold)
    cells. Renderer is unchanged; this guards the new row's render shape."""
    m = PredictiveMetricView(
        name="engine_population", value=0.5, status="WARN",
        state="engine_transition", ci_low=None, ci_high=None,
        random_delta=None, momentum_delta=None, buy_hold_delta=None,
        n_observations=3,
    )
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-20",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "engine_population" in html
    assert "engine_transition" in html
    assert "CI pending" in html
    assert html.count("n/a") >= 3        # all three Δ cells render n/a
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/monitor/eval/test_predictive_panel.py::test_engine_population_row_renders_ci_pending_and_na_deltas -q`
Expected: PASS — `_ci_cell(None, None)` → `"CI pending"` (predictive_panel.py:15-17), `_delta_cell(None)` → `"n/a"` (predictive_panel.py:8-9) for each of the three Δ columns, and `_metric_row` escapes `name`/`state` into the row (predictive_panel.py:20-31).

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/eval/test_predictive_panel.py
git commit -m "test(monitor): engine_population row renders CI-pending + n/a deltas"
```

---

## Task 7: Confirm the obsolete `rank_ic state == "undefined" → WARN` test is absent (spec §7 #7 — DELETE)

Spec §7 #7 says to DELETE the old planned `rank_ic state == "undefined" → WARN`
test "if it exists." **It does NOT exist in this repo.** A grep confirms the only
`"undefined"` test assertion in the eval tests is
`test_zero_defined_ic_days_sentinel`
(`tests/evals/test_monitor_forward_metrics.py:35-41`), which asserts the rank_ic
sentinel `state == "undefined"` and `status == "WARN"` — that is the EXISTING,
CORRECT rank_ic behavior and **must be kept**. It is NOT an `engine_population`
trigger test. There is nothing to delete.

- [ ] **Step 1: Confirm absence with a grep**

Run:
```bash
grep -rn "engine_population.*undefined\|undefined.*engine_population" tests/
grep -rn "undefined" tests/evals/test_monitor_forward_metrics.py
```
Expected: the first grep returns NOTHING (no such test). The second returns ONLY
line 41 (`assert details["rank_ic"]["state"] == "undefined"`) — the legitimate
rank_ic sentinel test. **Do NOT delete it.**

- [ ] **Step 2: Record the disposition (no code change)**

No file change. This task is satisfied: §7 #7 is **n/a — the obsolete test was
never written** (D2 was decided in the spec grill before any such test existed).
Note it in the implementation summary / PR description.

---

## Task 8: CONTEXT.md §9 amendments (land with this PR)

**Files:**
- Modify: `CONTEXT.md:53` and `CONTEXT.md:55`

Per spec §9 and MASTER-SPEC ("CONTEXT.md edits (§9) … are IN"), three edits land
with the FU1 merge. They document SHIPPED reality, so they ride this same PR.

> **Sequencing:** these three edits are documentation-only (no test). Apply them
> AFTER Tasks 1-7 are green, so CONTEXT.md never describes unshipped behavior
> mid-branch. They are committed here so they ride the same PR rather than being
> deferred to a separate ship step.

- [ ] **Step 1: Amend the "Predictive metrics & baselines" line (line 53)**

The line currently ENDS with:

```
... — retro lives in a labeled `details.retro` sub-block, never as a 4th row.
```

Replace that trailing sentence so the line ends with (find the exact substring
`retro lives in a labeled `` `details.retro` `` sub-block, never as a 4th row.` and
replace it):

```
— retro lives in a labeled `details.retro` sub-block, never as a 4th *predictive* row. After FU1 the stage also emits **one diagnostic/attribution row** — `engine_population` — a different species: it scores population health (raw-ledger share of rows on the current engine + matured `effective_n`), not signal skill, and is **attribution-only / never gating** (it WARNs only when `publishable_bias_directional` is already `insufficient_data`; `rank_ic` is deliberately excluded from its trigger). So the report carries **three predictive-validity metric rows + one diagnostic row**.
```

- [ ] **Step 2: Amend the "Predictive-validity panel" row-state vocabulary (line 55)**

The line currently contains the phrase:

```
with normal / `insufficient_data` / `undefined` / stale / review-trigger states.
```

Replace it with:

```
with normal / `insufficient_data` / `undefined` / `engine_transition` / stale / review-trigger states.
```

- [ ] **Step 3: Verify both edits applied and nothing else changed**

Run: `git diff CONTEXT.md`
Expected: exactly two changed lines (53 and 55); the `engine_transition` token and
the `engine_population` diagnostic-row sentence are present; no other lines touched.

- [ ] **Step 4: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(monitor): CONTEXT.md — engine_population diagnostic row + engine_transition state"
```

> **Glossary entry (§9 bullet 2):** the spec pre-drafts a standalone
> `**engine_population` (diagnostic row)**` glossary paragraph. CONTEXT.md lines
> 53/55 are prose bullets, not a separate glossary section, so the
> diagnostic-row description folded into the line-53 amendment (Step 1) covers the
> glossary content. If a reviewer wants it as a standalone bullet, add it as a new
> bullet immediately after line 53 verbatim from spec §9 bullet 2. This is
> OPTIONAL — the line-53 amendment already carries the substance.

---

## Task 9: Full-suite verification (spec §7 mandate) + lint

Spec §7 mandates running the WHOLE `tests/evals/`, `tests/monitor/`, AND
`tests/commands/` dirs (not just the mirror) before claiming green — the runner
output feeds all three, and a prior signature-change regression once hid in
`tests/commands/` while `tests/monitor/` was green (see MEMORY: "Test scope on
signature changes").

- [ ] **Step 1: Run the whole `tests/evals/` dir**

Run: `uv run pytest tests/evals/ -q`
Expected: all PASS (0 failed). Pay attention to `test_monitor_forward_runner.py`
and `test_monitor_forward_metrics.py`.

- [ ] **Step 2: Run the whole `tests/monitor/` dir**

Run: `uv run pytest tests/monitor/ -q`
Expected: all PASS (0 failed).

- [ ] **Step 3: Run the whole `tests/commands/` dir**

Run: `uv run pytest tests/commands/ -q`
Expected: all PASS (0 failed). This is the dir most likely to surface a hidden
`MetricReport`-shape or panel-model regression.

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests evals`
Expected: `All checks passed!` (line-length 100, target py312). If the new
`runner.py` block trips line-length, wrap the offending line; do not change logic.

- [ ] **Step 5: Final confirming commit (only if Steps 1-4 surfaced fixes)**

If any of Steps 1-4 required a fix, commit it:

```bash
git add -A
git commit -m "fix(monitor): address full-suite/lint findings for engine_population"
```

If Steps 1-4 were already clean, no commit is needed here.

---

## Self-Review (run before declaring done)

- **Spec §4 pure function** → Task 1 (exact signature, exact 4-cell truth table). ✓
- **Spec §4 runner append (not in build_metric_reports)** → Task 2 Step 4 appends in `runner.py`; Task 3 Step 3 confirms `build_metric_reports` still returns 3. ✓
- **Spec §4 direct indexing of `publishable_bias_directional.state`** → Task 2 Step 4 uses `details["publishable_bias_directional"]["state"]` (no `.get`). ✓
- **Spec §4 value formula + empty-ledger guard** → Task 2 Step 4 (`... if n_total_raw else 0.0`); Task 4 proves no `ZeroDivisionError`. ✓
- **Spec §4 mandatory `ci_low/ci_high = None`, `threshold={}`** → Task 2 Step 4 details block + MetricReport `threshold={}`; Tasks 5 & 6 prove the CI-None contract producer→panel. ✓
- **Spec §4 `n_observations = effective_n(forward_rows)`** → Task 2 Step 4 (`effective_n([{"run_date": r.run_date} ...])`). ✓
- **Spec §4 `details["excluded_by_engine"]` unchanged** → Task 2 Step 4 leaves runner.py:159-160 in place; Task 2 Step 1 asserts `engine_mismatch >= 1`. ✓
- **Spec §7 #1-#6 tests** → Tasks 1, 2, 3, 4, 5, 6 respectively. ✓
- **Spec §7 #7 DELETE** → Task 7: confirmed n/a (never written); the only `"undefined"` test is the legitimate rank_ic sentinel and is KEPT. ✓
- **Spec §7 verification discipline (whole evals/monitor/commands dirs + ruff)** → Task 9. ✓
- **Spec §9 CONTEXT.md edits** → Task 8 (two line edits; glossary folded into line 53). ✓
- **Spec §6 invariants (never gates, pure, back-compat, no silent caps, size budget)** → enforced by the append-only edge (no scorer change), the `engine_mismatch == 0 → PASS/ok` branch (back-compat), and the unchanged `excluded_by_engine` raw counts. ✓
- **Placeholder scan** → no TBD/TODO; every code step shows full code. ✓
- **Type consistency** → `engine_population_status(*, n_excluded_engine, headline_state)` identical in Tasks 1 & 2; `MetricReport(name="engine_population", ...)`, details key `"engine_population"`, and state codes `"engine_transition"`/`"ok"` identical across Tasks 2, 5, 6. ✓

---

## Out of scope for this run (do NOT touch — documented in MASTER-SPEC)

- §8.1 / §8.3 diagram work (`evals/docs/monitor-eval-workflow.html`, `docs/diagrams/monitor-workflow.html`, the dashed `engine_population` overlay) — separate doc-sync PR, `SKIPPED.md`.
- Any change to `_filter_engine`, `_target_engine`, the maturity join, or `score_forward` — spec §10.
- Promoting `monitor_forward` into `--all` or making it gate; a configurable numeric WARN threshold — spec §10.
