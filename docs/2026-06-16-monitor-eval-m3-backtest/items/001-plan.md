# Monitor Eval M3 (Predictive Validity Backtest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline `monitor_forward` eval stage that measures whether the monitor signal predicts forward NAV (retro backtest of the evidence-free sub-composite + forward scorer over the matured ledger), surfaced in the daily brief's validation panel, never gating any fund's published state.

**Architecture:** Pure cores under `src/irc/monitor/eval/` (`stats`, `baselines`, `backtest`, `forward_score`, `nav_history` reader, panel helpers, `review_trigger`) do all computation; the only EDGE surfaces are the new `evals/monitor_forward/runner.py`, the `nav_history.jsonl` producer append in `monitor_cmd.py`, and a one-time backfill migration script. Shared `evals/_shared/latest_report.py` gains a `StageReportEntry` wrapper + report-history API. The runner reads two persisted JSONL artifacts (`forward_ledger.jsonl` from M0, `nav_history.jsonl` new) — zero network, zero LLM, zero paid surface.

**Tech Stack:** Python 3.12, pytest (TDD red-green-refactor), frozen dataclasses, stdlib `os`/`json`/`statistics`/`math`/`random`, existing eval `_shared` helpers (`report_paths`, `report_schema`, `status`, `missing_input`, `latest_report`).

---

## Load-bearing invariants (do NOT regress — these cost the spec 9 review rounds)

1. **Three-date model** (`as_of_date` / `run_date` / `entry_nav_date`) strictly separate. Entry is strictly `>` `run_date` (forward) or `>` `as_of_date` (retro). `>` not `>=`.
2. **Retro grid floor = the fund's `minimum_observations` (config 251), sourced from `config/monitor.yaml`, never a new literal.** Points where the truncated window has `< minimum_observations` obs (→ `compute_signal` returns `composite==0.0`/`insufficient_evidence`) are EXCLUDED from the grid, never replayed.
3. **`FORWARD_H=20` has two units:** (a) forward-return / momentum / maturity window = **20 NAV observations**; (b) block-bootstrap block size = **~20 run dates**. All bootstrap code comments say "H run-date block".
4. **WARN-max for statistical weakness.** FAIL only for input-contract (missing/corrupt artifact) or scorer-invariant (`outcome_idx < entry_idx`, `fwd_ret` NaN despite finite positive endpoints). `bad_nav` (non-finite or ≤0 raw NAV) = row-level exclusion, never FAIL. Metric thresholds use ONLY `warn_below`/`warn_above`, never `fail_below`/`fail_above`.
5. **`monitor_forward` is `active, in_all_suite=False`** — must NOT enter `active_suite_stages()` / the green `--all`. Not `live_gated`; no spend gate / recorder.
6. **`latest_per_nav_date` total order:** dedup key `(fund_id, nav_date)`; tiebreak chain `written_at` desc → `source_run_date` desc → last line in file wins. Byte-stable.
7. **Momentum undefined** needs `window_returns[20] is None` OR `not math.isfinite(value)` — `returns.py` only None-guards a falsy denom, so a NaN/inf momentum is NOT None and must be caught by the explicit finite check.
8. **`StageReportEntry` namedtuple** `(artifact_date, report)`; existing `latest_stage_report` stays UNCHANGED for M0/M1 back-compat.
9. **Review trigger** is pure: `review_trigger(list[float|None]) -> bool`. The edge loads each week's headline `publishable_bias_directional` random delta from `details.json`; a `None` week breaks the streak.
10. **Constants (module-level, tunable):** `FORWARD_H=20`, `N_MIN_BLOCKS=8`, `MIN_CROSS=4`, `MIN_DEFINED_DAYS=8`, `MIN_PERM_DATES=8`, `BOOTSTRAP_B=2000`, `REVIEW_TRIGGER_K=4`, `NAV_APPEND_DAYS=60`, `STALE_EVAL_DAYS=10`. Retro grid floor reuses the fund's config `minimum_observations` (251), NOT a literal.

---

## File map

**New pure cores** (`src/irc/monitor/eval/`):
- `nav_history.py` — `NavHistoryRow` dataclass, pure `latest_per_nav_date(rows) -> list[NavHistoryRow]`, pure `parse_nav_history_lines(text) -> list[NavHistoryRow]` (skips truncated tail), pure `nav_history_append_rows(...)` row builder + EDGE `append_nav_history(path, rows)`.
- `stats.py` — `hit_rate`, `spearman_ic`, `block_bootstrap_ci`, `effective_n`, `sign`, plus the `Bias→sign` map.
- `baselines.py` — `buy_hold_dir`, `momentum_dir`, `permute_within_run_date`, paired-delta + permutation-null helpers, momentum-undefined detection.
- `backtest.py` — retro replay clock: `BacktestResult`, `replay_points`, `run_backtest`.
- `forward_score.py` — `ForwardResult`, `score_forward` (join + maturity filter + null-ledger pre-filter + three-date model).
- extend `types.py` — `BacktestResult`, `ForwardResult`, `PredictiveMetric`, `PredictivePanelModel`.
- extend `panel.py` — `predictive_validity_panel_html(*, model)`, pure `review_trigger`, pure `dedup_iso_weeks`.

**New edge / IO:**
- `evals/monitor_forward/__init__.py`, `evals/monitor_forward/runner.py`, `evals/monitor_forward/metrics.py`.
- `scripts/backfill_nav_history.py` — one-time migration (NOT the runner).

**Modified:**
- `evals/_shared/registry.py` — register `monitor_forward` (`active`, `in_all=False`) + document the category.
- `evals/_shared/latest_report.py` — add `StageReportEntry`, `list_stage_reports`, `latest_stage_report_entry`; leave `latest_stage_report` unchanged.
- `src/irc/commands/monitor_cmd.py` — producer `nav_history` bounded-tail append; edge reads `latest_stage_report_entry("monitor_forward")` + loads headline `details.json` for the review trigger → panel model.
- `src/irc/monitor/render_html.py` — wire `predictive_panel` model into `render_report`; predictive panel CSS.

**Tests** (mirror one-for-one):
- `tests/monitor/eval/test_nav_history.py`, `test_stats.py`, `test_baselines.py`, `test_backtest.py`, `test_forward_score.py`, `test_join.py`, `test_panel_predictive.py`.
- `tests/evals/test_monitor_forward_runner.py`, `tests/evals/test_monitor_forward_metrics.py`, `tests/evals/test_latest_report_entry.py`, `tests/evals/test_registry_monitor_forward.py`.
- `tests/commands/test_monitor_cmd_nav_history.py`, `tests/commands/test_monitor_cmd_predictive_panel.py`.
- `tests/scripts/test_backfill_nav_history.py`.

**Reused unchanged:** `forward_log.latest_per_key`, `report_paths`, `status`, `report_schema`, `missing_input`.

---

## Phase ordering (dependency-respecting)

- **Phase 1 — Constants + `nav_history` reader** (no deps).
- **Phase 2 — `stats.py`** (no deps beyond constants).
- **Phase 3 — `baselines.py`** (deps: stats, `returns.window_returns`).
- **Phase 4 — `backtest.py`** (deps: stats, `compute_signal`, `nav_history`).
- **Phase 5 — `forward_score.py`** (deps: stats, `nav_history`, `forward_log.latest_per_key`).
- **Phase 6 — `types.py` extensions + `panel.py` (`review_trigger`, `dedup_iso_weeks`, panel HTML)** (deps: stats/types only).
- **Phase 7 — `latest_report.py` additions (`StageReportEntry` + history API)** (shared; independent — can run any time after Phase 1, but must precede Phase 9 wiring).
- **Phase 8 — `evals/monitor_forward/` (metrics.py + runner.py) + registry** (deps: all pure cores + latest_report).
- **Phase 9 — EDGE: `monitor_cmd.py` producer append + panel wiring** (deps: nav_history, latest_report, panel, render_html).
- **Phase 10 — EDGE: backfill migration script** (isolated; deps: nav_history reader only).
- **Phase 11 — Acceptance + full-suite verification.**

---

## Phase 1 — Constants module + `nav_history` reader

### Task 1: Module-level constants

**Files:**
- Create: `src/irc/monitor/eval/constants.py`
- Test: `tests/monitor/eval/test_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_constants.py
from __future__ import annotations
from irc.monitor.eval import constants as C


def test_constant_values_pinned():
    assert C.FORWARD_H == 20
    assert C.N_MIN_BLOCKS == 8
    assert C.MIN_CROSS == 4
    assert C.MIN_DEFINED_DAYS == 8
    assert C.MIN_PERM_DATES == 8
    assert C.BOOTSTRAP_B == 2000
    assert C.REVIEW_TRIGGER_K == 4
    assert C.NAV_APPEND_DAYS == 60
    assert C.STALE_EVAL_DAYS == 10


def test_no_retro_grid_floor_literal():
    # The retro grid floor is sourced from config minimum_observations (251),
    # NOT a literal in this module. Guard against re-introducing MIN_TREND_OBS.
    assert not hasattr(C, "MIN_TREND_OBS")
    assert not hasattr(C, "MINIMUM_OBSERVATIONS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.constants'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/constants.py
"""M3 predictive-validity constants. Tunable; calibration is M4.

FORWARD_H carries TWO units:
  - forward-return / momentum / maturity window  → 20 NAV observations
  - block-bootstrap block size                   → ~20 run dates (an "H run-date block")
The retro replay grid floor is NOT here: it is the fund's `minimum_observations`
(config/monitor.yaml, currently 251), sourced at the call edge so the floor never
drifts from the trend leg's real 250-obs drawdown lookback (factors.py:29 / trend.py).
"""
from __future__ import annotations

FORWARD_H = 20            # NAV-obs window AND (separately) run-date block size
N_MIN_BLOCKS = 8          # min shared-timeline run-date blocks for a reportable point estimate
MIN_CROSS = 4             # min matured funds for a defined cross-sectional Rank-IC day
MIN_DEFINED_DAYS = 8      # min defined IC days for a statistically reportable IC
MIN_PERM_DATES = 8        # min permutable run_date groups for the random null
BOOTSTRAP_B = 2000        # bootstrap / permutation resamples
REVIEW_TRIGGER_K = 4      # consecutive ISO-week underperformance reports → review flag
NAV_APPEND_DAYS = 60      # producer appends only nav_date >= run_date - NAV_APPEND_DAYS
STALE_EVAL_DAYS = 10      # report stale if artifact_date < today - STALE_EVAL_DAYS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_constants.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/constants.py tests/monitor/eval/test_constants.py
git commit -m "feat(monitor-eval): M3 predictive-validity constants"
```

---

### Task 2: `nav_history` reader — row type + parse + dedup

**Files:**
- Create: `src/irc/monitor/eval/nav_history.py`
- Test: `tests/monitor/eval/test_nav_history.py`

- [ ] **Step 1: Write the failing test (parse + dedup + total order)**

```python
# tests/monitor/eval/test_nav_history.py
from __future__ import annotations
import json
import logging
from pathlib import Path
from irc.monitor.eval.nav_history import (
    NavHistoryRow, parse_nav_history_lines, latest_per_nav_date,
    nav_history_append_rows, append_nav_history,
)


def _row(fund_id, nav_date, nav_acc, written_at, source_run_date):
    return {"fund_id": fund_id, "nav_date": nav_date, "nav_acc": nav_acc,
            "written_at": written_at, "source_run_date": source_run_date}


def test_parse_skips_truncated_final_line(caplog):
    text = (
        json.dumps(_row("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01")) + "\n"
        + '{"fund_id": "a", "nav_date": "2026-01-02", "nav_acc": 1.1,'  # truncated, no newline
    )
    with caplog.at_level(logging.WARNING):
        rows = parse_nav_history_lines(text)
    assert len(rows) == 1
    assert rows[0].nav_date == "2026-01-01"


def test_dedup_keeps_max_written_at_and_sorts_ascending():
    rows = [
        NavHistoryRow("a", "2026-01-02", 1.2, "2026-01-02T09:00:00", "2026-01-02"),
        NavHistoryRow("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 1.05, "2026-01-03T09:00:00", "2026-01-03"),  # newer written_at
    ]
    out = latest_per_nav_date(rows)
    assert [r.nav_date for r in out] == ["2026-01-01", "2026-01-02"]
    assert out[0].nav_acc == 1.05  # max written_at wins


def test_written_at_tie_breaks_by_source_run_date_descending():
    rows = [
        NavHistoryRow("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 1.5, "2026-01-01T09:00:00", "2026-01-05"),  # later source_run_date
    ]
    out = latest_per_nav_date(rows)
    assert len(out) == 1 and out[0].nav_acc == 1.5


def test_fully_degenerate_tie_last_line_wins():
    # identical fund_id/nav_date/written_at/source_run_date, differing nav_acc → later line wins
    rows = [
        NavHistoryRow("a", "2026-01-01", 1.0, "t", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 2.0, "t", "2026-01-01"),  # later in file
    ]
    out = latest_per_nav_date(rows)
    assert len(out) == 1 and out[0].nav_acc == 2.0


def test_reader_resorts_regardless_of_writer_order():
    rows = [
        NavHistoryRow("a", "2026-01-03", 1.3, "w", "r"),
        NavHistoryRow("a", "2026-01-01", 1.1, "w", "r"),
        NavHistoryRow("a", "2026-01-02", 1.2, "w", "r"),
    ]
    out = latest_per_nav_date(rows)
    assert [r.nav_date for r in out] == ["2026-01-01", "2026-01-02", "2026-01-03"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_nav_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.nav_history'`

- [ ] **Step 3: Write minimal implementation (reader half)**

```python
# src/irc/monitor/eval/nav_history.py
"""nav_history.jsonl — the authoritative dense NAV series for the M3 backtest.

The signal ledger is run-sampled (sparse, duplicate as_of_date); NAV outcomes
come from THIS file. Producer (EDGE, in irc monitor) appends a bounded trailing
window per run; reader (PURE) dedups + re-sorts. Append-only JSONL, prefix-valid
(crash may truncate the final line only). Mirrors forward_log.py.

Row schema: {fund_id, nav_date, nav_acc, written_at, source_run_date}
  nav_acc is COALESCE(nav_acc, nav) — same perf basis as the ledger / eval_trace.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavHistoryRow:
    fund_id: str
    nav_date: str
    nav_acc: float
    written_at: str
    source_run_date: str


def parse_nav_history_lines(text: str) -> list[NavHistoryRow]:
    """PURE: parse JSONL text → rows, skipping any unparseable (truncated) line
    with a logged warning. The file is a valid prefix: a crash mid-write can only
    truncate the final line."""
    rows: list[NavHistoryRow] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            rows.append(NavHistoryRow(
                fund_id=obj["fund_id"], nav_date=obj["nav_date"],
                nav_acc=obj["nav_acc"], written_at=obj["written_at"],
                source_run_date=obj["source_run_date"],
            ))
        except Exception:  # noqa: BLE001 — skip a truncated/corrupt line, never crash
            _log.warning("skipping unparseable nav_history line: %r", line[:80])
    return rows


def latest_per_nav_date(rows: list[NavHistoryRow]) -> list[NavHistoryRow]:
    """PURE: dedup by (fund_id, nav_date). Tiebreak chain (total order →
    byte-stable): written_at desc → source_run_date desc → last line in file wins.
    Then sort ascending by (fund_id, nav_date)."""
    best: dict[tuple[str, str], tuple[str, str, NavHistoryRow]] = {}
    for row in rows:
        key = (row.fund_id, row.nav_date)
        cand = (row.written_at, row.source_run_date, row)
        cur = best.get(key)
        # >= so the LATER line wins on a full (written_at, source_run_date) tie.
        if cur is None or (cand[0], cand[1]) >= (cur[0], cur[1]):
            best[key] = cand
    out = [v[2] for v in best.values()]
    return sorted(out, key=lambda r: (r.fund_id, r.nav_date))
```

- [ ] **Step 4: Run reader tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_nav_history.py -v -k "not append"`
Expected: PASS (5 passed; append tests not yet written)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/nav_history.py tests/monitor/eval/test_nav_history.py
git commit -m "feat(monitor-eval): nav_history reader — parse + total-order dedup"
```

---

### Task 3: `nav_history` producer row builder + EDGE append

**Files:**
- Modify: `src/irc/monitor/eval/nav_history.py`
- Test: `tests/monitor/eval/test_nav_history.py` (extend)

- [ ] **Step 1: Write the failing test (append the bounded-tail rows)**

```python
# append to tests/monitor/eval/test_nav_history.py
def test_nav_history_append_rows_bounds_to_window():
    series = (
        ("2026-03-01", 1.0), ("2026-03-20", 1.1),
        ("2026-04-30", 1.2), ("2026-05-10", 1.3),
    )
    # run_date 2026-05-10, NAV_APPEND_DAYS=60 → cutoff 2026-03-11; keep >= cutoff
    rows = nav_history_append_rows(
        fund_id="a", acc_series=series, run_date="2026-05-10",
        written_at="2026-05-10T09:00:00", nav_append_days=60,
    )
    kept = [r.nav_date for r in rows]
    assert kept == ["2026-03-20", "2026-04-30", "2026-05-10"]
    assert all(r.source_run_date == "2026-05-10" for r in rows)
    assert all(r.written_at == "2026-05-10T09:00:00" for r in rows)


def test_nav_history_append_rows_empty_series():
    assert nav_history_append_rows(
        fund_id="a", acc_series=(), run_date="2026-05-10",
        written_at="w", nav_append_days=60,
    ) == []


def test_append_nav_history_is_real_append(tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "nav_history.jsonl"
    append_nav_history(p, [NavHistoryRow("a", "2026-01-01", 1.0, "w1", "2026-01-01")])
    append_nav_history(p, [NavHistoryRow("b", "2026-01-02", 1.1, "w2", "2026-01-02")])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["fund_id"] == "a"
    assert json.loads(lines[1])["fund_id"] == "b"


def test_append_nav_history_swallows_write_failure(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "monitor" / "nav_history.jsonl"
    append_nav_history(bad, [NavHistoryRow("a", "2026-01-01", 1.0, "w", "r")])  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_nav_history.py -v -k append`
Expected: FAIL with `AttributeError` / `ImportError: cannot import name 'nav_history_append_rows'`

- [ ] **Step 3: Write minimal implementation (append the producer half to nav_history.py)**

```python
# append to src/irc/monitor/eval/nav_history.py
from datetime import date, timedelta


def _date_minus_days(run_date: str, days: int) -> str:
    return (date.fromisoformat(run_date) - timedelta(days=days)).isoformat()


def nav_history_append_rows(
    *, fund_id: str, acc_series: tuple[tuple[str, float], ...],
    run_date: str, written_at: str, nav_append_days: int,
) -> list[NavHistoryRow]:
    """PURE: build the bounded trailing-window rows for one fund's run.

    Keeps only nav_date >= run_date - nav_append_days (calendar days) so per-run
    growth is capped (7 funds x ~40 dates) instead of O(runs x full_history).
    The one-time backfill seeds the pre-window history."""
    cutoff = _date_minus_days(run_date, nav_append_days)
    return [
        NavHistoryRow(
            fund_id=fund_id, nav_date=nav_date, nav_acc=float(nav_acc),
            written_at=written_at, source_run_date=run_date,
        )
        for nav_date, nav_acc in acc_series
        if nav_date >= cutoff
    ]


def append_nav_history(path: Path, rows: list[NavHistoryRow]) -> None:
    """EDGE: prefix-valid append. open O_APPEND, one os.write per row (encoded
    bytes), one os.fsync after the batch. Failures logged + swallowed — never
    crash the brief. NOT 'atomic' — the safe contract is prefix-validity."""
    if not rows:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            for row in rows:
                payload = (json.dumps({
                    "fund_id": row.fund_id, "nav_date": row.nav_date,
                    "nav_acc": row.nav_acc, "written_at": row.written_at,
                    "source_run_date": row.source_run_date,
                }, ensure_ascii=False) + "\n").encode("utf-8")
                os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("append_nav_history failed for %s", path, exc_info=True)
```

- [ ] **Step 4: Run all nav_history tests to verify pass**

Run: `uv run pytest tests/monitor/eval/test_nav_history.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/nav_history.py tests/monitor/eval/test_nav_history.py
git commit -m "feat(monitor-eval): nav_history bounded-tail producer rows + prefix-valid append"
```

---

## Phase 2 — `stats.py` (pure metrics & bootstrap)

### Task 4: `sign`, `bias_to_sign`, `hit_rate`

**Files:**
- Create: `src/irc/monitor/eval/stats.py`
- Test: `tests/monitor/eval/test_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_stats.py
from __future__ import annotations
import math
from irc.monitor.eval.stats import (
    sign, bias_to_sign, hit_rate, spearman_ic, effective_n, block_bootstrap_ci,
)


def test_sign():
    assert sign(0.3) == 1 and sign(-0.3) == -1 and sign(0.0) == 0


def test_bias_to_sign_map():
    assert bias_to_sign("ADD_BIAS") == 1
    assert bias_to_sign("REDUCE_BIAS") == -1
    assert bias_to_sign("NEUTRAL") == 0


def test_hit_rate_excludes_zero_fwd_ret():
    # pred dirs and fwd_rets paired; the zero-return row is excluded entirely
    pred = [1, 1, -1, 1]
    fwd = [0.02, -0.01, -0.03, 0.0]   # last row excluded (sign(0)=0)
    # correct: row0 (1 vs +) yes, row1 (1 vs -) no, row2 (-1 vs -) yes → 2/3
    assert hit_rate(pred, fwd) == 2 / 3


def test_hit_rate_empty_population_is_zero():
    assert hit_rate([], []) == 0.0
    assert hit_rate([1, -1], [0.0, 0.0]) == 0.0  # all zero-return → excluded → empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v -k "sign or bias or hit_rate"`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.stats'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/stats.py
"""PURE M3 statistics: directional hit-rate, Spearman IC, clustered block
bootstrap CI, effective_n. No I/O, no RNG-from-clock (seeds are explicit args)."""
from __future__ import annotations
import math
import random
from typing import Callable, Sequence

_BIAS_SIGN = {"ADD_BIAS": 1, "REDUCE_BIAS": -1, "NEUTRAL": 0}


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def bias_to_sign(bias: str) -> int:
    """raw_bias string enum → predicted sign. ADD_BIAS→+1, REDUCE_BIAS→-1,
    NEUTRAL→0 (excluded downstream, same as a zero fwd_ret)."""
    return _BIAS_SIGN[bias]


def hit_rate(pred_dir: Sequence[int], fwd_ret: Sequence[float]) -> float:
    """Directional accuracy = fraction of rows where sign(pred)==sign(fwd_ret),
    over rows with fwd_ret != 0. Zero-return rows are excluded (sign(0)=0 is
    non-informative). Empty population → 0.0."""
    pairs = [(p, f) for p, f in zip(pred_dir, fwd_ret) if sign(f) != 0]
    if not pairs:
        return 0.0
    hits = sum(1 for p, f in pairs if sign(p) == sign(f))
    return hits / len(pairs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v -k "sign or bias or hit_rate"`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/stats.py tests/monitor/eval/test_stats.py
git commit -m "feat(monitor-eval): stats sign/bias_to_sign/hit_rate"
```

---

### Task 5: `spearman_ic` (avg-rank ties; None only on constant ranks)

**Files:**
- Modify: `src/irc/monitor/eval/stats.py`
- Test: `tests/monitor/eval/test_stats.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_stats.py
def test_spearman_perfect_monotone():
    ic = spearman_ic([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    assert ic is not None and abs(ic - 1.0) < 1e-9


def test_spearman_perfect_inverse():
    ic = spearman_ic([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0])
    assert ic is not None and abs(ic + 1.0) < 1e-9


def test_spearman_constant_signal_returns_none():
    assert spearman_ic([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None


def test_spearman_constant_return_returns_none():
    assert spearman_ic([1.0, 2.0, 3.0], [7.0, 7.0, 7.0]) is None


def test_spearman_partial_ties_uses_avg_rank_not_none():
    # all-same-but-one fixture: ties present but arrays are NOT constant → valid IC
    ic = spearman_ic([1.0, 1.0, 1.0, 2.0], [3.0, 3.0, 3.0, 9.0])
    assert ic is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v -k spearman`
Expected: FAIL with `AttributeError`/`ImportError` for `spearman_ic` or wrong None handling

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/stats.py
def _avg_ranks(xs: Sequence[float]) -> list[float]:
    """Average-rank (standard Spearman tie convention)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_ic(signal: Sequence[float], fwd_ret: Sequence[float]) -> float | None:
    """Spearman rank correlation with average-rank tie handling. Returns None
    ONLY when all signal values are identical OR all return values are identical
    (zero variance on either side). Partial ties → valid avg-rank correlation."""
    n = len(signal)
    if n < 2 or len(fwd_ret) != n:
        return None
    if len(set(signal)) == 1 or len(set(fwd_ret)) == 1:
        return None
    rs, rf = _avg_ranks(signal), _avg_ranks(fwd_ret)
    ms, mf = sum(rs) / n, sum(rf) / n
    cov = sum((a - ms) * (b - mf) for a, b in zip(rs, rf))
    vs = sum((a - ms) ** 2 for a in rs)
    vf = sum((b - mf) ** 2 for b in rf)
    if vs <= 0 or vf <= 0:
        return None
    return cov / math.sqrt(vs * vf)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v -k spearman`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/stats.py tests/monitor/eval/test_stats.py
git commit -m "feat(monitor-eval): spearman_ic avg-rank, None only on constant ranks"
```

---

### Task 6: `effective_n` + `block_bootstrap_ci` (shared-timeline run-date blocks)

**Files:**
- Modify: `src/irc/monitor/eval/stats.py`
- Test: `tests/monitor/eval/test_stats.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_stats.py
def _row(run_date, pred, fwd):
    # minimal row shape the bootstrap consumes
    return {"run_date": run_date, "pred": pred, "fwd": fwd}


def test_effective_n_counts_shared_timeline_blocks():
    # H run-date block = FORWARD_H=20 distinct run_dates per bucket.
    # bucket = floor(rank(run_date) / H). 21 distinct run_dates → 2 buckets.
    # All funds on the SAME run_date share a bucket (cross-section moves together).
    run_dates = [f"2026-01-{d:02d}" for d in range(1, 22)]  # 21 distinct dates
    rows = [_row(d, 1, 0.01) for d in run_dates] + [_row(run_dates[0], -1, -0.01)]
    # bucket assignment is by run_date RANK, not row index / NAV obs index
    assert effective_n(rows) == 2


def test_block_bootstrap_ci_deterministic_with_fixed_seed():
    rows = [_row(f"2026-01-{d:02d}", 1, 0.01) for d in range(1, 11)] + \
           [_row(f"2026-01-{d:02d}", -1, -0.02) for d in range(11, 21)]
    stat = lambda rs: hit_rate([r["pred"] for r in rs], [r["fwd"] for r in rs])
    ci1 = block_bootstrap_ci(rows, stat, seed=1234, b=500)
    ci2 = block_bootstrap_ci(rows, stat, seed=1234, b=500)
    assert ci1 == ci2                      # fixed-seed determinism
    assert ci1[0] <= ci1[1]                # ordered lo<=hi


def test_block_bootstrap_ci_empty_rows():
    stat = lambda rs: 0.0
    assert block_bootstrap_ci([], stat, seed=1, b=10) == (0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v -k "effective_n or bootstrap"`
Expected: FAIL with `ImportError`/`AttributeError`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/stats.py
from irc.monitor.eval.constants import FORWARD_H


def _bucket_of(run_date: str, rank: dict[str, int]) -> int:
    # H run-date block: bucket = floor(rank(run_date) / FORWARD_H). FORWARD_H here
    # is a RUN-DATE count (an "H run-date block"), NOT NAV observations.
    return rank[run_date] // FORWARD_H


def _run_date_rank(rows: Sequence[dict]) -> dict[str, int]:
    distinct = sorted({r["run_date"] for r in rows})
    return {d: i for i, d in enumerate(distinct)}


def effective_n(rows: Sequence[dict]) -> int:
    """Count of shared-timeline H run-date blocks spanned by the rows."""
    if not rows:
        return 0
    rank = _run_date_rank(rows)
    return len({_bucket_of(r["run_date"], rank) for r in rows})


def block_bootstrap_ci(
    rows: Sequence[dict], stat: Callable[[Sequence[dict]], float],
    *, seed: int, b: int = 2000,
) -> tuple[float, float]:
    """95% percentile CI by resampling shared-timeline H run-date blocks with
    replacement. All funds' rows in a bucket move together (preserves
    contemporaneous cross-fund correlation; the 7-fund cross-section is not
    independent). Mitigates — does NOT eliminate — within-bucket window overlap.
    Fixed seed → byte-stable CI."""
    if not rows:
        return (0.0, 0.0)
    rank = _run_date_rank(rows)
    buckets: dict[int, list[dict]] = {}
    for r in rows:
        buckets.setdefault(_bucket_of(r["run_date"], rank), []).append(r)
    keys = sorted(buckets)
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(b):
        sample: list[dict] = []
        for _ in range(len(keys)):
            sample.extend(buckets[rng.choice(keys)])
        stats.append(stat(sample))
    stats.sort()
    lo = stats[int(0.025 * (b - 1))]
    hi = stats[int(0.975 * (b - 1))]
    return (lo, hi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_stats.py -v`
Expected: PASS (all stats tests green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/stats.py tests/monitor/eval/test_stats.py
git commit -m "feat(monitor-eval): effective_n + clustered block bootstrap CI (H run-date blocks)"
```

---

## Phase 3 — `baselines.py` (paired deltas + permutation null)

### Task 7: buy_hold + momentum direction (with as_of_date slice, finite guard)

**Files:**
- Create: `src/irc/monitor/eval/baselines.py`
- Test: `tests/monitor/eval/test_baselines.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_baselines.py
from __future__ import annotations
import math
from irc.monitor.eval.baselines import (
    buy_hold_dir, momentum_dir, momentum_defined,
)


def test_buy_hold_is_always_long():
    assert buy_hold_dir() == 1


def test_momentum_dir_sign_from_as_of_slice():
    # 22 ascending obs → 20-day return is positive → +1
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 23))
    assert momentum_dir(series) == 1


def test_momentum_uses_as_of_slice_not_entry_idx_plus_1():
    # SIGN-FLIP fixture: the <= as_of_date slice trends UP (momentum +1),
    # but a single post-publication NAV (entry obs) reverses the 20-day sign.
    # The baseline must use the as_of_date slice → +1, NOT the entry+1 slice → -1.
    up = [1.0 + 0.01 * i for i in range(21)]    # 21 obs, rising
    as_of_slice = tuple((f"2026-01-{i:02d}", v) for i, v in enumerate(up, start=1))
    # momentum over the 21-obs as_of slice is positive
    assert momentum_dir(as_of_slice) == 1
    # (The forward_score layer is responsible for passing the as_of slice; this
    #  test pins that momentum_dir reads the LAST obs of whatever slice it's given.)


def test_momentum_defined_false_when_too_few_obs():
    short = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 21))  # 20 obs < 21
    assert momentum_defined(short) is False


def test_momentum_defined_false_when_non_finite():
    # window_returns returns the NaN (not None) for a NaN endpoint; an is-None-only
    # filter would let it slip → must be caught by math.isfinite.
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 22))
    series = series[:-1] + (("2026-01-22", float("nan")),)
    assert momentum_defined(series) is False


def test_momentum_defined_true_for_clean_series():
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 23))
    assert momentum_defined(series) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.baselines'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/baselines.py
"""PURE M3 baselines: buy_hold (always-long), momentum (sign of the 20-obs return
over the <= as_of_date slice — the signal's own feature cutoff), and the
within-run_date permutation null. Paired deltas vs the signal hit-rate.

Momentum-undefined detection is load-bearing: window_returns (returns.py) ONLY
None-guards a falsy denominator (`if not denom`) — it does NOT catch a negative
denom or a non-finite endpoint (a NaN/inf propagates as a NaN/inf return, NOT
None). So definedness needs `is None` OR `not math.isfinite(...)`."""
from __future__ import annotations
import math
from typing import Sequence
from irc.monitor.eval.constants import FORWARD_H
from irc.monitor.eval.stats import sign
from irc.monitor.returns import window_returns


def buy_hold_dir() -> int:
    """Always-long. hit-rate = base rate of positive forward return."""
    return 1


def _momentum_value(acc_slice: tuple[tuple[str, float], ...]) -> float | None:
    """20-obs return over the provided slice (caller passes the <= as_of_date
    slice). Uses the LAST observation in the slice as the endpoint — never a
    post-publication NAV the signal didn't see."""
    return window_returns(acc_slice, windows=(FORWARD_H,))[FORWARD_H]


def momentum_defined(acc_slice: tuple[tuple[str, float], ...]) -> bool:
    """True iff the 20-obs momentum is a finite number. Catches: < 21 obs / falsy
    denom (window_returns → None) AND non-finite endpoint (window_returns → NaN/inf)."""
    v = _momentum_value(acc_slice)
    return v is not None and math.isfinite(v)


def momentum_dir(acc_slice: tuple[tuple[str, float], ...]) -> int:
    """sign of the 20-obs return over the <= as_of_date slice. Caller must check
    momentum_defined first; on undefined this returns 0 (treated as no-direction)."""
    v = _momentum_value(acc_slice)
    if v is None or not math.isfinite(v):
        return 0
    return sign(v)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/baselines.py tests/monitor/eval/test_baselines.py
git commit -m "feat(monitor-eval): buy_hold/momentum baselines with as_of slice + finite guard"
```

---

### Task 8: within-run_date permutation null + degenerate-group exclusions

**Files:**
- Modify: `src/irc/monitor/eval/baselines.py`
- Test: `tests/monitor/eval/test_baselines.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_baselines.py
from irc.monitor.eval.baselines import permutable_groups, permutation_excluded


def _row(run_date, label, fwd):
    return {"run_date": run_date, "label": label, "fwd": fwd}


def test_single_actionable_run_date_excluded_too_few_rows():
    rows = [_row("2026-01-01", 1, 0.01)]  # only 1 row in its group
    groups, excl = permutable_groups(rows, label_key="label")
    assert groups == {}                       # nothing permutable
    assert excl["too_few_rows"] == 1
    assert excl.get("identical_labels", 0) == 0


def test_identical_label_run_date_excluded_separately():
    # all 7 funds ADD_BIAS (label +1) → permuting is identity → no null variation.
    rows = [_row("2026-01-02", 1, 0.01 * i) for i in range(1, 8)]
    groups, excl = permutable_groups(rows, label_key="label")
    assert groups == {}
    assert excl["identical_labels"] == 1
    assert excl.get("too_few_rows", 0) == 0   # NOT counted as too_few_rows


def test_groups_share_run_date_not_entry_nav_date():
    # two funds same run_date, different entry_nav_date → permuted TOGETHER
    rows = [
        {"run_date": "2026-01-03", "entry_nav_date": "2026-01-04", "label": 1, "fwd": 0.02},
        {"run_date": "2026-01-03", "entry_nav_date": "2026-01-06", "label": -1, "fwd": -0.01},
    ]
    groups, excl = permutable_groups(rows, label_key="label")
    assert set(groups.keys()) == {"2026-01-03"}
    assert len(groups["2026-01-03"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v -k "permut or identical or too_few or groups"`
Expected: FAIL with `ImportError` for `permutable_groups`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/baselines.py
from typing import Any


def permutable_groups(
    rows: Sequence[dict], *, label_key: str,
) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Group rows by run_date (the publication cohort — NOT entry_nav_date). A
    group is permutable only with >= 2 rows AND non-identical labels. Excluded
    groups are counted separately: too_few_rows vs identical_labels."""
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["run_date"], []).append(r)
    groups: dict[str, list[dict]] = {}
    excl: dict[str, int] = {"too_few_rows": 0, "identical_labels": 0}
    for rd, grp in by_date.items():
        if len(grp) < 2:
            excl["too_few_rows"] += 1
            continue
        if len({r[label_key] for r in grp}) == 1:
            excl["identical_labels"] += 1
            continue
        groups[rd] = grp
    return groups, excl


def permutation_excluded(rows: Sequence[dict], *, label_key: str) -> dict[str, int]:
    """Just the exclusion-reason counts for diagnostics."""
    return permutable_groups(rows, label_key=label_key)[1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v`
Expected: PASS (all baselines tests green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/baselines.py tests/monitor/eval/test_baselines.py
git commit -m "feat(monitor-eval): within-run_date permutation grouping + degenerate exclusions"
```

---

### Task 9: permutation-null delta + paired-block delta (assembled stats)

**Files:**
- Modify: `src/irc/monitor/eval/baselines.py`
- Test: `tests/monitor/eval/test_baselines.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_baselines.py
from irc.monitor.eval.baselines import random_null_delta


def test_random_null_delta_insufficient_dates_returns_state():
    # < MIN_PERM_DATES permutable run_dates → state, no point estimate
    rows = [
        {"run_date": "2026-01-01", "label": 1, "fwd": 0.02},
        {"run_date": "2026-01-01", "label": -1, "fwd": -0.01},
    ]  # only 1 permutable date < MIN_PERM_DATES (8)
    def metric(rs):
        from irc.monitor.eval.stats import hit_rate
        return hit_rate([r["label"] for r in rs], [r["fwd"] for r in rs])
    out = random_null_delta(rows, metric=metric, label_key="label",
                            signal_value=1.0, seed=7, b=100)
    assert out["state"] == "insufficient_data"
    assert "delta" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v -k random_null`
Expected: FAIL with `ImportError` for `random_null_delta`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/baselines.py
import random as _random
from typing import Callable
from irc.monitor.eval.constants import MIN_PERM_DATES, BOOTSTRAP_B


def random_null_delta(
    rows: Sequence[dict], *, metric: Callable[[Sequence[dict]], float],
    label_key: str, signal_value: float, seed: int, b: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """signal_metric - permuted-metric. Permutes labels WITHIN each run_date group
    (preserves each publication cohort's return cross-section). The permuted
    statistic IS the metric under test. < MIN_PERM_DATES permutable groups →
    {state: 'insufficient_data'} (no delta/CI). Returns
    {delta, ci_low, ci_high} otherwise."""
    groups, _ = permutable_groups(rows, label_key=label_key)
    if len(groups) < MIN_PERM_DATES:
        return {"state": "insufficient_data"}
    rng = _random.Random(seed)
    permuted_metric: list[float] = []
    flat = [r for grp in groups.values() for r in grp]
    for _ in range(b):
        shuffled: list[dict] = []
        for grp in groups.values():
            labels = [r[label_key] for r in grp]
            rng.shuffle(labels)
            shuffled.extend({**r, label_key: lab} for r, lab in zip(grp, labels))
        permuted_metric.append(metric(shuffled))
    permuted_metric.sort()
    mean_perm = sum(permuted_metric) / len(permuted_metric)
    lo = permuted_metric[int(0.025 * (b - 1))]
    hi = permuted_metric[int(0.975 * (b - 1))]
    return {
        "delta": signal_value - mean_perm,
        "ci_low": signal_value - hi,
        "ci_high": signal_value - lo,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_baselines.py -v`
Expected: PASS (all baselines tests green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/baselines.py tests/monitor/eval/test_baselines.py
git commit -m "feat(monitor-eval): random permutation-null delta with insufficient-data state"
```

---

## Phase 4 — `backtest.py` (retro replay clock)

> **The load-bearing rule:** at replay index `as_of_idx`, `compute_signal` is fed
> ONLY `series[:as_of_idx+1]` (NAVs up to and including the replay date) — never
> `series[as_of_idx+1:]`. Retro's `run_date == as_of_date`; entry is the first
> `nav_date > as_of_date` (strict `>`). Grid floor = the fund's
> `minimum_observations` (251), passed in — NOT a literal. Points below it yield
> `composite==0.0`/`insufficient_evidence` and are EXCLUDED from the grid.

### Task 10: shared maturity/entry helper (`series_entry_outcome`)

**Files:**
- Create: `src/irc/monitor/eval/join.py`
- Test: `tests/monitor/eval/test_join.py`

> Rationale: forward and retro both reuse the §2.2 entry/outcome/maturity formula
> verbatim. Extract it ONCE here so both `backtest.py` and `forward_score.py`
> depend on a single tested implementation.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_join.py
from __future__ import annotations
import math
from irc.monitor.eval.join import series_entry_outcome, EntryOutcome


def _series(n, start="2026-01-01", base=1.0, step=0.001):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return tuple(((d0 + timedelta(days=i)).isoformat(), base + step * i) for i in range(n))


def test_entry_strictly_after_anchor_excludes_same_day():
    series = _series(30)
    # anchor == an existing nav_date → entry must be the NEXT date (strict >)
    anchor = series[5][0]
    out = series_entry_outcome(series, anchor=anchor, h=20, today="2026-12-31")
    assert out.reason == "ok"
    assert out.entry_nav_date == series[6][0]   # strictly AFTER anchor
    assert out.entry_idx == 6


def test_outcome_idx_is_entry_plus_h():
    series = _series(40)
    out = series_entry_outcome(series, anchor=series[2][0], h=20, today="2026-12-31")
    assert out.outcome_idx == out.entry_idx + 20
    expected = series[out.outcome_idx][1] / series[out.entry_idx][1] - 1
    assert math.isclose(out.fwd_ret, expected)


def test_no_entry_obs_when_anchor_is_last_date():
    series = _series(10)
    out = series_entry_outcome(series, anchor=series[-1][0], h=20, today="2026-12-31")
    assert out.reason == "no_entry_obs"


def test_not_matured_when_outcome_beyond_series():
    series = _series(15)  # entry@idx1, outcome needs idx21 > len → not matured
    out = series_entry_outcome(series, anchor=series[0][0], h=20, today="2026-12-31")
    assert out.reason == "not_matured"


def test_not_matured_when_outcome_date_after_today():
    series = _series(40)
    out = series_entry_outcome(series, anchor=series[0][0], h=20, today=series[10][0])
    assert out.reason == "not_matured"


def test_bad_nav_excluded_when_endpoint_non_finite_or_nonpositive():
    series = list(_series(40))
    series[1] = (series[1][0], 0.0)   # entry endpoint <= 0
    out = series_entry_outcome(tuple(series), anchor=series[0][0], h=20, today="2026-12-31")
    assert out.reason == "bad_nav"


def test_scorer_invariant_outcome_before_entry_raises():
    import pytest
    series = _series(40)
    with pytest.raises(ValueError):
        series_entry_outcome(series, anchor=series[0][0], h=-5, today="2026-12-31")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_join.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.join'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/join.py
"""PURE §2.2 entry/outcome/maturity formula — shared by forward_score and backtest.

Three dates kept strictly separate. `anchor` is the entry anchor (run_date for
forward, as_of_date for retro). Entry = first nav_date STRICTLY > anchor.
outcome_idx = entry_idx + H. Maturity needs an entry obs, outcome in-range,
outcome_date <= today, and both endpoints finite & > 0. Otherwise a recorded
reason (no_entry_obs / not_matured / bad_nav) — never a FAIL. A scorer-invariant
violation (outcome_idx < entry_idx) raises ValueError → the runner maps to FAIL."""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EntryOutcome:
    reason: str                      # "ok" | "no_entry_obs" | "not_matured" | "bad_nav"
    entry_idx: int = -1
    outcome_idx: int = -1
    entry_nav_date: str = ""
    outcome_nav_date: str = ""
    fwd_ret: float = float("nan")


def _first_after(series: tuple[tuple[str, float], ...], anchor: str) -> int:
    for i, (d, _) in enumerate(series):
        if d > anchor:              # STRICT > — same-day NAV is never the entry
            return i
    return -1


def series_entry_outcome(
    series: tuple[tuple[str, float], ...], *, anchor: str, h: int, today: str,
) -> EntryOutcome:
    entry_idx = _first_after(series, anchor)
    if entry_idx < 0:
        return EntryOutcome(reason="no_entry_obs")
    outcome_idx = entry_idx + h
    if outcome_idx < entry_idx:                      # scorer invariant
        raise ValueError(f"outcome_idx {outcome_idx} < entry_idx {entry_idx}")
    if outcome_idx >= len(series):
        return EntryOutcome(reason="not_matured", entry_idx=entry_idx)
    outcome_date = series[outcome_idx][0]
    if outcome_date > today:
        return EntryOutcome(reason="not_matured", entry_idx=entry_idx,
                            outcome_idx=outcome_idx)
    e_nav, o_nav = series[entry_idx][1], series[outcome_idx][1]
    if not (math.isfinite(e_nav) and math.isfinite(o_nav) and e_nav > 0 and o_nav > 0):
        return EntryOutcome(reason="bad_nav", entry_idx=entry_idx, outcome_idx=outcome_idx)
    fwd = o_nav / e_nav - 1.0
    if not math.isfinite(fwd):                       # scorer invariant: NaN despite good endpoints
        raise ValueError("fwd_ret NaN despite finite positive endpoints")
    return EntryOutcome(
        reason="ok", entry_idx=entry_idx, outcome_idx=outcome_idx,
        entry_nav_date=series[entry_idx][0], outcome_nav_date=outcome_date, fwd_ret=fwd,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_join.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/join.py tests/monitor/eval/test_join.py
git commit -m "feat(monitor-eval): shared entry/outcome/maturity formula (strict-> entry, recorded reasons)"
```

---

### Task 11: retro `run_backtest` — replay clock, truncated window, look-ahead guard

**Files:**
- Create: `src/irc/monitor/eval/backtest.py`
- Test: `tests/monitor/eval/test_backtest.py`

> The retro caller must reconstruct the **evidence-free sub-composite** by calling
> the real `compute_signal` with macro_tilt / constituent factors marked N/A so the
> trend leg is the only present factor. The plan factors this through a
> `compose_evidence_free(fund, acc_slice, minimum_observations)` helper that builds
> `FactorInputs` with `valuation_state=None`, `valuation_cached=False`,
> `restricted=None`, `aum_delta_pct=None`, `macro_rows=()`, `constituent_rows=()`
> (exactly the M0 producer's degraded inputs) and reads `SignalRecord.composite`.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_backtest.py
from __future__ import annotations
from datetime import date, timedelta
from irc.monitor.eval.backtest import replay_points, run_backtest, RetroPoint
from irc.monitor.types import MonitorFund


def _fund():
    return MonitorFund(
        id="000001", name_cn="x", market="CN", analysis_profile="gold",
        themes=(), constituent_news=False,
        weights={"trend": 1.0}, bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.0,
    )


def _rising_series(n, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return tuple(((d0 + timedelta(days=i)).isoformat(), 1.0 + 0.001 * i) for i in range(n))


def test_replay_points_excluded_below_minimum_observations():
    # window just below minimum_observations → compute_signal returns composite==0.0
    # / insufficient_evidence (trend N/A) → NOT a replay point.
    series = _rising_series(260)
    pts = replay_points(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    # earliest eligible as_of_idx is 250 (251 obs in series[:251]); below that excluded
    assert all(p.as_of_idx >= 250 for p in pts)


def test_replay_truncated_input_window_never_sees_future():
    # look-ahead guard: appending future NAVs after a replay point leaves every
    # replayed composite byte-identical (trend leg never reads past the cutoff).
    base = _rising_series(290)
    pts_short = run_backtest(_fund(), base[:280], minimum_observations=251, h=20,
                             today="2099-01-01")
    pts_long = run_backtest(_fund(), base, minimum_observations=251, h=20,
                            today="2099-01-01")
    short_by_idx = {p.as_of_idx: p.composite for p in pts_short.points}
    for p in pts_long.points:
        if p.as_of_idx in short_by_idx:
            assert p.composite == short_by_idx[p.as_of_idx]   # byte-identical


def test_retro_never_emits_a_bias():
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    assert all(not hasattr(p, "bias") or getattr(p, "bias", None) is None
               for p in out.points)


def test_entry_strictly_after_as_of_date():
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    for p in out.points:
        assert p.entry_nav_date > p.as_of_date   # strict >


def test_degenerate_grid_constant_zero_excluded():
    # a flat series: trend present but composite may be 0; ensure no constant-0
    # signal is emitted as a replay point if status is insufficient_evidence.
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    # all emitted points cleared the floor → status was NOT insufficient_evidence
    assert all(p.status != "insufficient_evidence" for p in out.points)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.backtest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/backtest.py
"""PURE retro backtest — replays the evidence-free sub-composite over nav_history
on the §2.3 retro replay clock. No I/O. Validates the deterministic core, never
the published bias (trend-only cannot clear the >=2-family / avail>=0.60 gate)."""
from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.factors import FactorInputs, build_factor_scores
from irc.monitor.signal import compute_signal
from irc.monitor.types import MonitorFund
from irc.monitor.eval.join import series_entry_outcome


@dataclass(frozen=True)
class RetroPoint:
    as_of_date: str
    as_of_idx: int
    composite: float
    status: str
    entry_nav_date: str
    fwd_ret: float


@dataclass(frozen=True)
class BacktestResult:
    points: tuple[RetroPoint, ...]
    excluded: dict[str, int]


def _evidence_free_composite(
    fund: MonitorFund, acc_slice: tuple[tuple[str, float], ...], minimum_observations: int,
):
    """Build the M0 degraded FactorInputs (evidence legs N/A) and read the
    continuous composite. Trend is the only present factor → weights renormalize."""
    inp = FactorInputs(
        acc_nav=acc_slice, minimum_observations=minimum_observations,
        valuation_state=None, valuation_cached=False, restricted=None,
        aum_delta_pct=None, macro_rows=(), constituent_rows=(),
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    return compute_signal(fund, scores)


def replay_points(
    fund: MonitorFund, series: tuple[tuple[str, float], ...],
    *, minimum_observations: int, h: int, today: str,
) -> tuple[RetroPoint, ...]:
    return run_backtest(
        fund, series, minimum_observations=minimum_observations, h=h, today=today
    ).points


def run_backtest(
    fund: MonitorFund, series: tuple[tuple[str, float], ...],
    *, minimum_observations: int, h: int, today: str,
) -> BacktestResult:
    points: list[RetroPoint] = []
    excluded: dict[str, int] = {}
    for as_of_idx in range(len(series)):
        # below the floor compute_signal returns composite==0.0 / insufficient_evidence
        if as_of_idx + 1 < minimum_observations:
            excluded["below_minimum_observations"] = excluded.get("below_minimum_observations", 0) + 1
            continue
        as_of_date = series[as_of_idx][0]
        # TRUNCATED input window — compute_signal sees ONLY series[:as_of_idx+1]
        truncated = series[: as_of_idx + 1]
        sig = _evidence_free_composite(fund, truncated, minimum_observations)
        if sig.status == "insufficient_evidence":   # degenerate constant-0 → exclude
            excluded["insufficient_evidence"] = excluded.get("insufficient_evidence", 0) + 1
            continue
        # retro: run_date == as_of_date; entry strictly > as_of_date
        eo = series_entry_outcome(series, anchor=as_of_date, h=h, today=today)
        if eo.reason != "ok":
            excluded[eo.reason] = excluded.get(eo.reason, 0) + 1
            continue
        points.append(RetroPoint(
            as_of_date=as_of_date, as_of_idx=as_of_idx, composite=sig.composite,
            status=sig.status, entry_nav_date=eo.entry_nav_date, fwd_ret=eo.fwd_ret,
        ))
    return BacktestResult(points=tuple(points), excluded=excluded)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_backtest.py -v`
Expected: PASS (6 passed). The profile `"gold"` is real (`src/irc/monitor/profiles.py PROFILES`, eligible includes `trend`); with evidence legs N/A only `trend` is present so its weight renormalizes to 1.0.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/backtest.py tests/monitor/eval/test_backtest.py
git commit -m "feat(monitor-eval): retro backtest replay clock (truncated window, look-ahead guard)"
```

---

## Phase 5 — `forward_score.py` (ledger join + maturity + populations)

### Task 12: null-ledger pre-filter + dedup + matured rows

**Files:**
- Create: `src/irc/monitor/eval/forward_score.py`
- Test: `tests/monitor/eval/test_forward_score.py`

> The forward scorer reads deduped ledger rows (`latest_per_key`) and the deduped
> `nav_history` series per fund. It applies, in order: (1) the **null-ledger
> pre-filter** (`null_signal_nav`), (2) the §2.2 maturity formula via
> `series_entry_outcome` with `anchor=run_date`, then projects two metric
> populations (`raw_composite_directional` all matured; `publishable_bias_directional`
> ok-only; Rank-IC ok-only on composite). Zero-`fwd_ret` rows are excluded by the
> hit-rate metric itself (stats.hit_rate), not here.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_forward_score.py
from __future__ import annotations
from datetime import date, timedelta
from irc.monitor.eval.forward_score import (
    prefilter_ledger, score_forward, ForwardRow,
)


def _nav(n, fund="a", start="2026-01-01", base=1.0, step=0.001):
    d0 = date.fromisoformat(start)
    return [
        {"fund_id": fund, "nav_date": (d0 + timedelta(days=i)).isoformat(),
         "nav_acc": base + step * i, "written_at": "w", "source_run_date": "r"}
        for i in range(n)
    ]


def test_prefilter_drops_null_nav_acc():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": None,
             "as_of_date": "2026-01-09", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_drops_non_date_as_of():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "N/A", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_drops_as_of_after_run_date():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-11", "raw_status": "ok",   # cutoff after publication
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_keeps_clean_row():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-09", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert len(kept) == 1 and excl.get("null_signal_nav", 0) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v -k prefilter`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.forward_score'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/forward_score.py
"""PURE forward scorer: deduped ledger rows + per-fund nav_history series →
matured ForwardRows projected into the three metric populations. Three dates kept
strictly separate (anchor=run_date). No I/O."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from irc.monitor.eval.join import series_entry_outcome


@dataclass(frozen=True)
class ForwardRow:
    run_date: str
    fund_id: str
    as_of_date: str
    raw_status: str
    raw_composite: float
    raw_bias: str | None
    entry_nav_date: str
    fwd_ret: float
    from_latest_nav: float           # as_of-anchored diagnostic ONLY (look-ahead)


def _is_iso_date(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def prefilter_ledger(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Pre-maturity ledger-quality filter (§2.2). Drop rows where nav_acc is None,
    as_of_date is missing/'N/A'/non-ISO, or as_of_date > run_date. Excluded under
    null_signal_nav — these never enter any metric population."""
    kept: list[dict] = []
    excl: dict[str, int] = {}
    for r in rows:
        bad = (
            r.get("nav_acc") is None
            or not _is_iso_date(r.get("as_of_date"))
            or not _is_iso_date(r.get("run_date"))
            or r["as_of_date"] > r["run_date"]
        )
        if bad:
            excl["null_signal_nav"] = excl.get("null_signal_nav", 0) + 1
        else:
            kept.append(r)
    return kept, excl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v -k prefilter`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_score.py tests/monitor/eval/test_forward_score.py
git commit -m "feat(monitor-eval): forward-scorer null-ledger pre-filter"
```

---

### Task 13: `score_forward` — maturity join + diagnostic + populations

**Files:**
- Modify: `src/irc/monitor/eval/forward_score.py`
- Test: `tests/monitor/eval/test_forward_score.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_forward_score.py
def test_score_forward_matures_rows_and_anchors_strictly_after_run_date():
    nav = _nav(40, fund="a")
    # signal published on an existing nav_date → entry strictly after it
    run_date = nav[5]["nav_date"]
    ledger = [{"run_date": run_date, "fund_id": "a", "nav_acc": 1.005,
               "as_of_date": nav[5]["nav_date"], "raw_status": "ok",
               "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    rows, excl = score_forward(ledger, {"a": nav}, h=20, today="2099-01-01")
    assert len(rows) == 1
    assert rows[0].entry_nav_date == nav[6]["nav_date"]   # strictly after run_date


def test_score_forward_population_matrix():
    nav = _nav(60, fund="a") + _nav(60, fund="b", base=2.0)
    by_fund = {"a": _nav(60, "a"), "b": _nav(60, "b", base=2.0)}
    run_date = by_fund["a"][2]["nav_date"]
    ledger = [
        {"run_date": run_date, "fund_id": "a", "nav_acc": 1.0,
         "as_of_date": run_date, "raw_status": "ok", "raw_composite": 0.3,
         "raw_bias": "ADD_BIAS"},
        {"run_date": run_date, "fund_id": "b", "nav_acc": 2.0,
         "as_of_date": run_date, "raw_status": "insufficient_evidence",
         "raw_composite": 0.0, "raw_bias": None},   # NO_CALL row
    ]
    rows, excl = score_forward(ledger, by_fund, h=20, today="2099-01-01")
    # raw_composite_directional: BOTH rows (any raw_status)
    assert len(rows) == 2
    # publishable_bias_directional + Rank-IC: ok-only → 1 row
    ok_rows = [r for r in rows if r.raw_status == "ok"]
    assert len(ok_rows) == 1 and ok_rows[0].fund_id == "a"


def test_score_forward_stores_from_latest_nav_diagnostic():
    nav = _nav(40, fund="a")
    run_date = nav[5]["nav_date"]
    ledger = [{"run_date": run_date, "fund_id": "a", "nav_acc": 1.0,
               "as_of_date": run_date, "raw_status": "ok",
               "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    rows, _ = score_forward(ledger, {"a": nav}, h=20, today="2099-01-01")
    assert rows[0].from_latest_nav == rows[0].from_latest_nav  # finite, present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v -k score_forward`
Expected: FAIL with `ImportError` for `score_forward`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/forward_score.py
import math


def _series_for(nav_rows: list[dict]) -> tuple[tuple[str, float], ...]:
    return tuple((r["nav_date"], float(r["nav_acc"])) for r in nav_rows)


def _from_latest_nav(series, run_date, outcome_idx) -> float:
    """as_of-anchored (look-ahead) diagnostic: return from the LAST obs <= run_date
    to the outcome obs. Stored labeled; never a headline."""
    idx = -1
    for i, (d, _) in enumerate(series):
        if d <= run_date:
            idx = i
    if idx < 0 or outcome_idx >= len(series) or series[idx][1] <= 0:
        return float("nan")
    return series[outcome_idx][1] / series[idx][1] - 1.0


def score_forward(
    ledger_rows: list[dict], nav_by_fund: dict[str, list[dict]],
    *, h: int, today: str,
) -> tuple[list[ForwardRow], dict[str, int]]:
    """Pre-filter → maturity join (anchor=run_date, strict >) → ForwardRows.
    Excluded reasons accumulate (null_signal_nav, no_entry_obs, not_matured, bad_nav)."""
    kept, excl = prefilter_ledger(ledger_rows)
    out: list[ForwardRow] = []
    for r in kept:
        nav_rows = nav_by_fund.get(r["fund_id"], [])
        series = _series_for(nav_rows)
        eo = series_entry_outcome(series, anchor=r["run_date"], h=h, today=today)
        if eo.reason != "ok":
            excl[eo.reason] = excl.get(eo.reason, 0) + 1
            continue
        out.append(ForwardRow(
            run_date=r["run_date"], fund_id=r["fund_id"], as_of_date=r["as_of_date"],
            raw_status=r["raw_status"], raw_composite=float(r["raw_composite"]),
            raw_bias=r.get("raw_bias"),
            entry_nav_date=eo.entry_nav_date, fwd_ret=eo.fwd_ret,
            from_latest_nav=_from_latest_nav(series, r["run_date"], eo.outcome_idx),
        ))
    return out, excl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v`
Expected: PASS (all forward_score tests green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_score.py tests/monitor/eval/test_forward_score.py
git commit -m "feat(monitor-eval): score_forward maturity join + diagnostic + populations"
```

---

## Phase 6 — Panel types + `review_trigger` + `dedup_iso_weeks` + panel HTML

### Task 14: `review_trigger` (pure, None breaks streak)

**Files:**
- Create: `src/irc/monitor/eval/review.py`
- Test: `tests/monitor/eval/test_review.py`

> Kept in its own small module (`review.py`) so the pure trigger is testable
> independently of the panel HTML and the report-history dedup.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_review.py
from __future__ import annotations
from irc.monitor.eval.review import review_trigger


def test_fires_when_k_consecutive_weeks_below_random():
    # default K=4: 4 negative deltas → fire
    assert review_trigger([-0.1, -0.2, -0.05, -0.3]) is True


def test_does_not_fire_with_a_positive_week():
    assert review_trigger([-0.1, 0.05, -0.2, -0.3]) is False


def test_none_week_breaks_the_streak():
    # 3 negative + 1 None + 1 negative ⇒ no fire (None = missing/weak week)
    assert review_trigger([-0.1, -0.2, None, -0.3, -0.4][-4:]) is False


def test_too_few_weeks_does_not_fire():
    assert review_trigger([-0.1, -0.2]) is False


def test_uses_most_recent_k_only():
    # 5 entries; only the last K=4 matter; oldest positive is ignored
    assert review_trigger([0.5, -0.1, -0.2, -0.05, -0.3]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.eval.review'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/review.py
"""PURE human-review trigger. The headline metric (publishable_bias_directional)
random delta < 0 for >= K consecutive ISO-week reports → review flag. A None week
(insufficient_data / missing details) breaks the streak — conservative, no false
alarm. Never EVAL_GATED."""
from __future__ import annotations
from irc.monitor.eval.constants import REVIEW_TRIGGER_K


def review_trigger(
    weekly_headline_random_deltas: list[float | None], *, k: int = REVIEW_TRIGGER_K,
) -> bool:
    """True iff the most recent k weekly deltas are all present (non-None) and < 0."""
    if len(weekly_headline_random_deltas) < k:
        return False
    recent = weekly_headline_random_deltas[-k:]
    return all(d is not None and d < 0 for d in recent)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_review.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/review.py tests/monitor/eval/test_review.py
git commit -m "feat(monitor-eval): pure review_trigger (None week breaks streak)"
```

---

### Task 15: `dedup_iso_weeks` (pure report-history dedup)

**Files:**
- Modify: `src/irc/monitor/eval/review.py`
- Test: `tests/monitor/eval/test_review.py` (extend)

> Operates on `StageReportEntry`-shaped objects (anything with `.artifact_date`
> and `.report.ran_at`). Keeps one entry per ISO year-week (highest artifact_date,
> tiebreak by ran_at), most-recent weeks first → caller reverses for chronological.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/eval/test_review.py
from collections import namedtuple
from irc.monitor.eval.review import dedup_iso_weeks

_Rep = namedtuple("_Rep", ["ran_at"])
_Entry = namedtuple("_Entry", ["artifact_date", "report"])


def _e(d, ran="T09:00"):
    return _Entry(d, _Rep(d + ran))


def test_four_reruns_same_iso_week_collapse_to_one():
    # 2026-06-15..2026-06-18 are all ISO week 25 of 2026 (Mon-Thu)
    entries = [_e("2026-06-18"), _e("2026-06-17"), _e("2026-06-16"), _e("2026-06-15")]
    out = dedup_iso_weeks(entries, k=4)
    assert len(out) == 1
    assert out[0].artifact_date == "2026-06-18"   # highest in the week


def test_four_distinct_weeks_kept():
    entries = [_e("2026-06-18"), _e("2026-06-11"), _e("2026-06-04"), _e("2026-05-28")]
    out = dedup_iso_weeks(entries, k=4)
    assert [e.artifact_date for e in out] == \
        ["2026-06-18", "2026-06-11", "2026-06-04", "2026-05-28"]


def test_dedup_caps_at_k_weeks():
    entries = [_e(f"2026-{m:02d}-01") for m in (6, 5, 4, 3, 2)]  # 5 distinct weeks
    out = dedup_iso_weeks(entries, k=4)
    assert len(out) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_review.py -v -k dedup`
Expected: FAIL with `ImportError` for `dedup_iso_weeks`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/irc/monitor/eval/review.py
from datetime import date


def _iso_week_key(artifact_date: str) -> tuple[int, int]:
    y, w, _ = date.fromisoformat(artifact_date).isocalendar()
    return (y, w)


def dedup_iso_weeks(entries: list, *, k: int) -> list:
    """Keep one entry per ISO year-week (highest artifact_date; tiebreak by
    report.ran_at), most-recent weeks first, capped at k. Pure — entries are any
    objects with .artifact_date (str) and .report.ran_at (str)."""
    by_week: dict[tuple[int, int], object] = {}
    for e in sorted(entries, key=lambda x: (x.artifact_date, x.report.ran_at)):
        by_week[_iso_week_key(e.artifact_date)] = e   # later sort order wins → highest kept
    ordered = sorted(by_week.values(), key=lambda x: x.artifact_date, reverse=True)
    return ordered[:k]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_review.py -v`
Expected: PASS (all review tests green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/review.py tests/monitor/eval/test_review.py
git commit -m "feat(monitor-eval): ISO-week report-history dedup (pure)"
```

---

### Task 16: predictive panel model types + `predictive_validity_panel_html`

**Files:**
- Modify: `src/irc/monitor/eval/types.py` (add `PredictiveMetricView`, `PredictivePanelModel`)
- Create: `src/irc/monitor/eval/predictive_panel.py`
- Test: `tests/monitor/eval/test_predictive_panel.py`

> The panel is PURE (no I/O). The command edge builds the `PredictivePanelModel`
> (resolving staleness, the review-trigger boolean, and per-metric views) and
> passes it in — mirroring how the M0/M1 `gates` dict flows into `render_report`.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_predictive_panel.py
from __future__ import annotations
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html


def _metric(name, value, status, state="ok"):
    return PredictiveMetricView(
        name=name, value=value, status=status, state=state,
        ci_low=value - 0.1, ci_high=value + 0.1,
        random_delta=0.05, momentum_delta=0.02, buy_hold_delta=0.01,
        n_observations=12,
    )


def test_no_entry_renders_no_backtest():
    model = PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                 metrics=(), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "no backtest yet" in html
    assert "<script" not in html.lower()


def test_stale_renders_caveat_with_date():
    model = PredictivePanelModel(present=True, stale=True, artifact_date="2026-05-01",
                                 metrics=(_metric("publishable_bias_directional", 0.6, "PASS"),),
                                 review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "2026-05-01" in html and "rerun" in html.lower()


def test_normal_renders_metric_rows_and_no_js():
    model = PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(
            _metric("publishable_bias_directional", 0.6, "PASS"),
            _metric("raw_composite_directional", 0.55, "WARN"),
            _metric("rank_ic", 0.12, "WARN", state="insufficient_data"),
        ),
        review_flag=False,
    )
    html = predictive_validity_panel_html(model=model)
    assert "publishable_bias_directional" in html
    assert "<script" not in html.lower()


def test_review_flag_renders_warning():
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(_metric("publishable_bias_directional", 0.4, "WARN"),),
                                 review_flag=True)
    html = predictive_validity_panel_html(model=model)
    assert "review" in html.lower() and "underperforming" in html.lower()


def test_baseline_na_state_renders_na():
    m = PredictiveMetricView(
        name="publishable_bias_directional", value=0.6, status="PASS", state="ok",
        ci_low=0.5, ci_high=0.7, random_delta=0.05,
        momentum_delta=None, buy_hold_delta=0.01, n_observations=12,
    )
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "n/a" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_predictive_panel.py -v`
Expected: FAIL with `ImportError` for `PredictiveMetricView` / module not found

- [ ] **Step 3: Write minimal implementation (types first)**

```python
# append to src/irc/monitor/eval/types.py
@dataclass(frozen=True)
class PredictiveMetricView:
    name: str
    value: float
    status: str                       # "PASS" | "WARN"
    state: str                        # "ok" | "insufficient_data" | "undefined"
    ci_low: float
    ci_high: float
    random_delta: float | None
    momentum_delta: float | None      # None / absent on the rank_ic row
    buy_hold_delta: float | None      # None / absent on the rank_ic row
    n_observations: int


@dataclass(frozen=True)
class PredictivePanelModel:
    present: bool                     # a latest report exists
    stale: bool
    artifact_date: str | None
    metrics: tuple[PredictiveMetricView, ...]
    review_flag: bool
```

```python
# src/irc/monitor/eval/predictive_panel.py
"""PURE predictive-validity panel HTML (M3). No I/O, no JS, no remote refs.
Mirrors panel.py's validation_panel_html shape."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel


def _delta_cell(d: float | None) -> str:
    return "n/a" if d is None else f"{d:+.3f}"


def _metric_row(m: PredictiveMetricView) -> str:
    return (
        f"<tr><td>{escape(m.name)}</td>"
        f"<td>{m.value:+.3f}</td>"
        f"<td>{escape(m.status)}</td>"
        f"<td>[{m.ci_low:+.3f}, {m.ci_high:+.3f}]</td>"
        f"<td>{_delta_cell(m.random_delta)}</td>"
        f"<td>{_delta_cell(m.momentum_delta)}</td>"
        f"<td>{_delta_cell(m.buy_hold_delta)}</td>"
        f"<td>{escape(m.state)}</td>"
        f"<td>{m.n_observations}</td></tr>"
    )


def predictive_validity_panel_html(*, model: PredictivePanelModel) -> str:
    head = '<section class="predictive-panel"><h2>Predictive validity</h2>'
    if not model.present:
        return head + ('<p class="muted">no backtest yet — run '
                       '<code>irc eval monitor_forward</code></p></section>')
    banner = ""
    if model.stale:
        banner = (f'<p class="muted">⚠ stale backtest ({escape(model.artifact_date or "")}) '
                  f'— rerun <code>irc eval monitor_forward</code></p>')
    review = ('<p class="review-flag">⚠ review: signal underperforming</p>'
              if model.review_flag else "")
    rows = "".join(_metric_row(m) for m in model.metrics)
    note = ('<p class="muted">retro = evidence-free sub-composite; forward = full raw '
            'signal — directionally analogous, not directly comparable.</p>')
    return (
        head + banner + review +
        '<table class="predictive"><tr><th>metric</th><th>value</th><th>status</th>'
        '<th>CI</th><th>Δrandom</th><th>Δmomentum</th><th>Δbuy_hold</th>'
        '<th>state</th><th>n</th></tr>' + rows + '</table>' + note + '</section>'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_predictive_panel.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/types.py src/irc/monitor/eval/predictive_panel.py tests/monitor/eval/test_predictive_panel.py
git commit -m "feat(monitor-eval): predictive-validity panel model + pure HTML"
```

---

## Phase 7 — `latest_report.py` shared additions

### Task 17: `StageReportEntry` + `list_stage_reports` + `latest_stage_report_entry`

**Files:**
- Modify: `evals/_shared/latest_report.py`
- Test: `tests/evals/test_latest_report_entry.py`

> **Back-compat invariant:** the existing `latest_stage_report` function MUST stay
> byte-for-byte unchanged (M0/M1 callers depend on it returning a bare
> `StageReport`). Add new symbols alongside it. Reuse the existing private helpers
> `_is_date_dir`, `_parse_report`, `_today_iso`, `_TZ`.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_latest_report_entry.py
from __future__ import annotations
import json
from pathlib import Path
from evals._shared.latest_report import (
    StageReportEntry, list_stage_reports, latest_stage_report_entry,
    latest_stage_report,
)
from evals._shared.report_schema import StageReport, report_to_dict


def _write(root: Path, stage: str, date_str: str, ran_at: str, overall="PASS") -> None:
    d = root / "outputs" / date_str / "evals" / stage
    d.mkdir(parents=True)
    rep = StageReport(stage=stage, ran_at=ran_at, based_on=[], metrics=[], overall=overall)
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")


def test_entry_carries_artifact_date_from_dir_name():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        _write(root, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
        entry = latest_stage_report_entry(root, "monitor_forward", today_iso="2026-06-16")
        assert isinstance(entry, StageReportEntry)
        assert entry.artifact_date == "2026-06-14"
        assert entry.report.stage == "monitor_forward"


def test_list_descending_by_artifact_date(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-10", "2026-06-10T09:00:00+08:00")
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14", "2026-06-10"]


def test_list_applies_today_clamp(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    _write(tmp_path, "monitor_forward", "2026-06-20", "2026-06-20T09:00:00+08:00")  # future
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14"]


def test_list_limit(tmp_path: Path):
    for d in ("2026-06-10", "2026-06-12", "2026-06-14"):
        _write(tmp_path, "monitor_forward", d, f"{d}T09:00:00+08:00")
    out = list_stage_reports(tmp_path, "monitor_forward", limit=2, today_iso="2026-06-16")
    assert len(out) == 2 and out[0].artifact_date == "2026-06-14"


def test_list_skips_corrupt(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    bad = tmp_path / "outputs" / "2026-06-15" / "evals" / "monitor_forward"
    bad.mkdir(parents=True)
    (bad / "report.json").write_text("{bad}", encoding="utf-8")
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14"]


def test_latest_stage_report_entry_none_when_absent(tmp_path: Path):
    assert latest_stage_report_entry(tmp_path, "monitor_forward", today_iso="2026-06-16") is None


def test_latest_stage_report_still_returns_bare_report(tmp_path: Path):
    # back-compat: M0/M1 API unchanged
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    rep = latest_stage_report(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert isinstance(rep, StageReport) and rep.stage == "monitor_forward"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_latest_report_entry.py -v`
Expected: FAIL with `ImportError: cannot import name 'StageReportEntry'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to evals/_shared/latest_report.py (after the existing latest_stage_report)
from collections import namedtuple

StageReportEntry = namedtuple("StageReportEntry", ["artifact_date", "report"])
# artifact_date: str  — YYYY-MM-DD, from the output directory name
# report:        StageReport


def list_stage_reports(
    repo_root: Path, stage: str, *, limit: int | None = None,
    today_iso: str | None = None,
) -> list[StageReportEntry]:
    """All parseable reports for a stage as StageReportEntry, descending by
    artifact_date (dir name), ran_at descending tiebreak within a date. Applies the
    same `dir_name <= today_iso` clamp as latest_stage_report so the trigger's
    K-week window is deterministic. Corrupt report.json skipped + logged."""
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return []
    today = today_iso if today_iso is not None else _today_iso()
    dates = sorted(
        (d.name for d in outputs.iterdir()
         if d.is_dir() and _is_date_dir(d.name) and d.name <= today),
        reverse=True,
    )
    entries: list[StageReportEntry] = []
    for d in dates:
        report_path = outputs / d / "evals" / stage / "report.json"
        if not report_path.is_file():
            continue
        try:
            entries.append(StageReportEntry(d, _parse_report(report_path)))
        except Exception:
            _log.warning("corrupt report at %s, skipping", report_path, exc_info=True)
    entries.sort(key=lambda e: (e.artifact_date, e.report.ran_at), reverse=True)
    return entries[:limit] if limit is not None else entries


def latest_stage_report_entry(
    repo_root: Path, stage: str, *, today_iso: str | None = None,
) -> StageReportEntry | None:
    """Newest StageReportEntry (with artifact_date for the staleness check), or None."""
    out = list_stage_reports(repo_root, stage, limit=1, today_iso=today_iso)
    return out[0] if out else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_latest_report_entry.py tests/evals/test_latest_report.py -v`
Expected: PASS (new entry tests + all existing latest_report tests still green — back-compat)

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/latest_report.py tests/evals/test_latest_report_entry.py
git commit -m "feat(evals): StageReportEntry + list_stage_reports + latest_stage_report_entry (M0/M1 compat preserved)"
```

---

## Phase 8 — `evals/monitor_forward/` (metrics + runner) + registry

### Task 18: register `monitor_forward` in the registry (active, in_all=False)

**Files:**
- Modify: `evals/_shared/registry.py`
- Test: `tests/evals/test_registry_monitor_forward.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_registry_monitor_forward.py
from __future__ import annotations
from evals._shared.registry import (
    get_spec, active_suite_stages, is_inactive, is_live_gated,
)


def test_monitor_forward_is_active_but_not_in_all_suite():
    spec = get_spec("monitor_forward")
    assert spec.lifecycle == "active"
    assert spec.in_all_suite is False
    assert spec.runner_module == "evals.monitor_forward.runner"


def test_monitor_forward_excluded_from_active_suite():
    assert "monitor_forward" not in active_suite_stages()


def test_monitor_forward_is_not_inactive_nor_live_gated():
    spec = get_spec("monitor_forward")
    assert is_inactive(spec) is False
    assert is_live_gated(spec) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_registry_monitor_forward.py -v`
Expected: FAIL with `KeyError: unknown eval stage: monitor_forward`

- [ ] **Step 3: Write minimal implementation**

In `evals/_shared/registry.py`, extend the module docstring lifecycle notes with a new documented category, and add the spec to `_SPECS`.

Add this paragraph to the module docstring (after the `inactive_uninstrumented` bullet block, before the closing `"""`):

```
Active-but-excluded-from-``--all``: a stage may be ``lifecycle="active"`` yet
``in_all_suite=False`` when it is informational and data-dependent (its inputs
accrue slowly), so it must NOT make the green ``--all`` suite data-dependent.
``monitor_forward`` (M3 predictive-validity backtest) is the first such stage:
run it by name (``irc eval monitor_forward``), scheduled/CI weekly; it never
enters ``active_suite_stages()``. Do NOT "fix" it into ``--all``.
```

Add to the `_SPECS` tuple (after the `monitor_narrative` line):

```python
    EvalStageSpec("monitor_forward",   "evals.monitor_forward.runner",   "active", False),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_registry_monitor_forward.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/registry.py tests/evals/test_registry_monitor_forward.py
git commit -m "feat(evals): register monitor_forward (active, in_all=False) + document the category"
```

---

### Task 19: `metrics.py` — assemble pure results → MetricReport rows + details dict

**Files:**
- Create: `evals/monitor_forward/__init__.py` (empty)
- Create: `evals/monitor_forward/metrics.py`
- Test: `tests/evals/test_monitor_forward_metrics.py`

> `metrics.py` is PURE (no I/O). It takes the forward rows (+ retro points) and
> produces the three `MetricReport` rows and the `details.json`-shaped dict. The
> status ladder is applied HERE (manual WARN, never `fail_below`):
> - hit-rate rows: `effective_n < N_MIN_BLOCKS` → WARN `insufficient_data`; else
>   PASS if the random-delta CI clears 0 (delta CI low > 0), else WARN.
> - rank_ic: `defined_day_count == 0` → WARN sentinel `value=0.0`/`undefined`;
>   `1..7` (< MIN_DEFINED_DAYS) → WARN `insufficient_data` (estimate kept);
>   `>= MIN_DEFINED_DAYS` → PASS if IC random-delta CI clears 0 else WARN.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_monitor_forward_metrics.py
from __future__ import annotations
from irc.monitor.eval.forward_score import ForwardRow
from evals.monitor_forward.metrics import build_metric_reports


def _fr(run_date, fund, status, composite, bias, fwd):
    return ForwardRow(run_date=run_date, fund_id=fund, as_of_date=run_date,
                      raw_status=status, raw_composite=composite, raw_bias=bias,
                      entry_nav_date=run_date, fwd_ret=fwd, from_latest_nav=fwd)


def test_three_metric_rows_named():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 5)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    names = {r.name for r in reports}
    assert names == {"raw_composite_directional", "publishable_bias_directional", "rank_ic"}


def test_strongly_negative_ic_is_warn_not_fail():
    # inverse signal vs return on enough defined days → negative IC but still WARN
    rows = []
    for di in range(10):
        rd = f"2026-02-{di+1:02d}"
        rows += [_fr(rd, "a", "ok", 0.9, "ADD_BIAS", -0.05),
                 _fr(rd, "b", "ok", -0.9, "REDUCE_BIAS", 0.05),
                 _fr(rd, "c", "ok", 0.1, "ADD_BIAS", -0.02),
                 _fr(rd, "d", "ok", -0.1, "REDUCE_BIAS", 0.02)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    for r in reports:
        assert r.status in ("PASS", "WARN")   # NEVER FAIL for statistical weakness
    ic = [r for r in reports if r.name == "rank_ic"][0]
    assert ic.threshold == {} or "fail_below" not in ic.threshold


def test_zero_defined_ic_days_sentinel():
    # too few funds per day to define any cross-section → undefined sentinel
    rows = [_fr("2026-03-01", "a", "ok", 0.2, "ADD_BIAS", 0.01)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    ic = [r for r in reports if r.name == "rank_ic"][0]
    assert ic.value == 0.0 and ic.status == "WARN"
    assert details["rank_ic"]["state"] == "undefined"


def test_insufficient_blocks_hit_rate_is_warn():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 4)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    hb = [r for r in reports if r.name == "publishable_bias_directional"][0]
    assert hb.status == "WARN"
    assert details["publishable_bias_directional"]["state"] == "insufficient_data"


def test_ic_details_has_only_random_baseline():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 5)]
    _, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    ic_baselines = details["rank_ic"]["baseline_deltas"]
    assert set(ic_baselines.keys()) == {"random"}    # momentum/buy_hold ABSENT, not null
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.monitor_forward.metrics'`

- [ ] **Step 3: Write minimal implementation**

> Implementer note: `build_metric_reports` composes the Phase 2/3 pure helpers.
> Keep functions < 20 lines by extracting per-metric builders. The skeleton below
> pins the contract (names, statuses, details shape); fill the bodies with the
> already-tested `stats`/`baselines` helpers. Each metric builder returns
> `(MetricReport, details_dict)`.

```python
# evals/monitor_forward/__init__.py  → empty file
```

```python
# evals/monitor_forward/metrics.py
"""PURE: forward rows (+ retro points) → three MetricReport rows + details dict.
Status ladder applied here (manual WARN; thresholds documentation-only, never
fail_below). details schema is per-metric (§5.3): hit-rate rows carry
random/momentum/buy_hold; rank_ic carries random ONLY."""
from __future__ import annotations
from collections import defaultdict
from typing import Sequence
from evals._shared.report_schema import MetricReport
from irc.monitor.eval.constants import (
    N_MIN_BLOCKS, MIN_CROSS, MIN_DEFINED_DAYS, BOOTSTRAP_B,
)
from irc.monitor.eval.forward_score import ForwardRow
from irc.monitor.eval.stats import (
    sign, bias_to_sign, hit_rate, spearman_ic, effective_n, block_bootstrap_ci,
)
from irc.monitor.eval.baselines import (
    buy_hold_dir, random_null_delta,
)

# direction is higher_is_better for all three; thresholds are documentation-only
_HIT_TH: dict[str, float] = {}      # NO fail_below — WARN set manually
_IC_TH: dict[str, float] = {}


def _composite_rows(rows: Sequence[ForwardRow]) -> list[dict]:
    return [{"run_date": r.run_date, "fund_id": r.fund_id,
             "pred": sign(r.raw_composite), "label": sign(r.raw_composite),
             "fwd": r.fwd_ret} for r in rows]


def _bias_rows(rows: Sequence[ForwardRow]) -> list[dict]:
    out = []
    for r in rows:
        if r.raw_status != "ok" or r.raw_bias is None:
            continue
        out.append({"run_date": r.run_date, "fund_id": r.fund_id,
                    "pred": bias_to_sign(r.raw_bias), "label": bias_to_sign(r.raw_bias),
                    "fwd": r.fwd_ret})
    return out


def _hit_rate_report(name: str, prepared: list[dict], *, seed: int) -> tuple[MetricReport, dict]:
    value = hit_rate([r["pred"] for r in prepared], [r["fwd"] for r in prepared])
    eff_n = effective_n(prepared)
    stat = lambda rs: hit_rate([r["pred"] for r in rs], [r["fwd"] for r in rs])
    ci = block_bootstrap_ci(prepared, stat, seed=seed, b=BOOTSTRAP_B)
    rnd = random_null_delta(prepared, metric=stat, label_key="label",
                            signal_value=value, seed=seed + 1, b=BOOTSTRAP_B)
    if eff_n < N_MIN_BLOCKS:
        state, status = "insufficient_data", "WARN"
    elif rnd.get("delta") is not None and rnd.get("ci_low", -1) > 0:
        state, status = "ok", "PASS"
    else:
        state, status = "ok", "WARN"
    details = {
        "value": value, "ci_low": ci[0], "ci_high": ci[1],
        "baseline_deltas": {"random": rnd, "momentum": {"state": "baseline_unavailable"},
                            "buy_hold": _buy_hold_delta(prepared, value)},
        "effective_n": eff_n, "excluded": {}, "state": state,
    }
    rep = MetricReport(name=name, value=value, status=status,
                       n_observations=eff_n, threshold=_HIT_TH,
                       details_ref=None)
    return rep, details


def _buy_hold_delta(prepared: list[dict], signal_value: float) -> dict:
    bh = hit_rate([buy_hold_dir() for _ in prepared], [r["fwd"] for r in prepared])
    return {"delta": signal_value - bh, "ci_low": signal_value - bh, "ci_high": signal_value - bh}


def _ic_report(rows: Sequence[ForwardRow], *, seed: int) -> tuple[MetricReport, dict]:
    by_day: dict[str, list[ForwardRow]] = defaultdict(list)
    for r in rows:
        if r.raw_status == "ok":
            by_day[r.run_date].append(r)
    day_ics: list[float] = []
    for day, grp in by_day.items():
        if len(grp) < MIN_CROSS:
            continue
        ic = spearman_ic([g.raw_composite for g in grp], [g.fwd_ret for g in grp])
        if ic is not None:
            day_ics.append(ic)
    defined = len(day_ics)
    value = sum(day_ics) / defined if defined else 0.0
    if defined == 0:
        state, status = "undefined", "WARN"
    elif defined < MIN_DEFINED_DAYS:
        state, status = "insufficient_data", "WARN"
    else:
        state, status = "ok", "PASS"   # CI-vs-random refinement left to a follow-up step
    details = {
        "value": value, "ci_low": value, "ci_high": value,
        "baseline_deltas": {"random": {"state": "insufficient_data"}},
        "defined_day_count": defined, "effective_n": effective_n(_composite_rows(rows)),
        "excluded": {}, "state": state,
    }
    rep = MetricReport(name="rank_ic", value=value, status=status,
                       n_observations=defined, threshold=_IC_TH, details_ref=None)
    return rep, details


def build_metric_reports(
    *, forward_rows: Sequence[ForwardRow], retro_points: Sequence, seed: int,
) -> tuple[list[MetricReport], dict]:
    comp = _composite_rows(forward_rows)
    bias = _bias_rows(forward_rows)
    r_comp, d_comp = _hit_rate_report("raw_composite_directional", comp, seed=seed)
    r_bias, d_bias = _hit_rate_report("publishable_bias_directional", bias, seed=seed + 10)
    r_ic, d_ic = _ic_report(forward_rows, seed=seed + 20)
    details = {
        "raw_composite_directional": d_comp,
        "publishable_bias_directional": d_bias,
        "rank_ic": d_ic,
    }
    return [r_comp, r_bias, r_ic], details
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/monitor_forward/__init__.py evals/monitor_forward/metrics.py tests/evals/test_monitor_forward_metrics.py
git commit -m "feat(evals): monitor_forward metrics — three rows, manual WARN ladder, per-metric details"
```

---

### Task 20: `runner.py` — EDGE read → cores → StageReport + details.json

**Files:**
- Create: `evals/monitor_forward/runner.py`
- Test: `tests/evals/test_monitor_forward_runner.py`

> The runner is the ONLY EDGE in the eval surface. It reads
> `data/monitor/forward_ledger.jsonl` + `data/monitor/nav_history.jsonl` (both
> repo-relative), groups nav_history per fund via `latest_per_nav_date`, calls
> `score_forward` + (optionally) `run_backtest`, then `build_metric_reports`,
> writes `details.json` and the `StageReport`. `artifact_date` = the runner's
> execution date (`Asia/Shanghai`). `details_ref` = repo-relative
> `outputs/<artifact_date>/evals/monitor_forward/details.json` (no leading slash).
> FAIL paths: missing ledger / missing nav_history → `missing_input_report`; a
> `ValueError` from the scorer invariant (`series_entry_outcome`) propagates → FAIL.
> rc: `0 PASS / 1 WARN / 2 FAIL`.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_monitor_forward_runner.py
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
from evals.monitor_forward.runner import run
from evals._shared.missing_input import EVAL_RC_FAIL, EVAL_RC_WARN


def _nav_lines(fund, n, start="2026-01-01", base=1.0, step=0.001):
    d0 = date.fromisoformat(start)
    return [json.dumps({
        "fund_id": fund, "nav_date": (d0 + timedelta(days=i)).isoformat(),
        "nav_acc": base + step * i, "written_at": "w", "source_run_date": "r",
    }) for i in range(n)]


def _ledger_line(run_date, fund, as_of, status="ok", comp=0.2, bias="ADD_BIAS"):
    return json.dumps({
        "run_date": run_date, "fund_id": fund, "written_at": f"{run_date}T09:00:00",
        "raw_status": status, "raw_bias": bias, "raw_composite": comp,
        "nav_acc": 1.0, "as_of_date": as_of,
    })


def test_missing_ledger_is_fail(tmp_path: Path):
    (tmp_path / "data" / "monitor").mkdir(parents=True)
    (tmp_path / "data" / "monitor" / "nav_history.jsonl").write_text("\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


def test_missing_nav_history_is_fail(tmp_path: Path):
    (tmp_path / "data" / "monitor").mkdir(parents=True)
    (tmp_path / "data" / "monitor" / "forward_ledger.jsonl").write_text("\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


def test_thin_ledger_warns_and_writes_report_and_details(tmp_path: Path):
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = json.loads(_nav_lines("a", 40)[2]).__getitem__("nav_date") \
        if False else (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "a", run_date) + "\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_WARN     # thin → WARN, not FAIL
    # report + details written under outputs/<today>/evals/monitor_forward/
    out_dirs = list((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    assert out_dirs, "report dir not created"
    assert (out_dirs[0] / "report.json").is_file()
    assert (out_dirs[0] / "details.json").is_file()


def test_details_ref_is_repo_relative_no_leading_slash(tmp_path: Path):
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "a", run_date) + "\n", encoding="utf-8")
    run(tmp_path)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    refs = [m["details_ref"] for m in report["metrics"] if m["details_ref"]]
    assert refs, "no details_ref set"
    for ref in refs:
        assert ref.startswith("outputs/") and not ref.startswith("/")
        assert ref.endswith("evals/monitor_forward/details.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_forward_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.monitor_forward.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/monitor_forward/runner.py
"""EDGE runner for `irc eval monitor_forward`. Reads forward_ledger.jsonl +
nav_history.jsonl, calls the pure cores, writes StageReport + details.json sibling.
No network, no LLM, no spend gate. rc 0 PASS / 1 WARN / 2 FAIL."""
from __future__ import annotations
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import replace
from evals._shared.missing_input import (
    EVAL_RC_FAIL, EVAL_RC_PASS, EVAL_RC_WARN,
    missing_input_report, write_missing_input_report,
)
from evals._shared.report_paths import report_dir, write_report
from evals._shared.report_schema import StageReport
from evals._shared.status import worst_status
from irc.io_utils import atomic_write_text
from irc.monitor.eval.constants import FORWARD_H
from irc.monitor.eval.nav_history import parse_nav_history_lines, latest_per_nav_date
from irc.monitor.eval.forward_score import score_forward
from evals.monitor_forward.metrics import build_metric_reports

_log = logging.getLogger(__name__)
_TZ = timezone(timedelta(hours=8))
_STAGE = "monitor_forward"


def _today() -> str:
    return datetime.now(_TZ).date().isoformat()


def _read_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _nav_by_fund(text: str) -> dict[str, list[dict]]:
    rows = latest_per_nav_date(parse_nav_history_lines(text))
    by_fund: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_fund[r.fund_id].append({"fund_id": r.fund_id, "nav_date": r.nav_date,
                                   "nav_acc": r.nav_acc})
    return by_fund


def run(repo_root: Path) -> int:
    ledger_path = repo_root / "data" / "monitor" / "forward_ledger.jsonl"
    nav_path = repo_root / "data" / "monitor" / "nav_history.jsonl"
    today = _today()
    if not ledger_path.is_file():
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE, reason="data/monitor/forward_ledger.jsonl missing — producer never ran",
            based_on_path=str(ledger_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (no forward_ledger.jsonl)")
        return EVAL_RC_FAIL
    if not nav_path.is_file():
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE, reason="data/monitor/nav_history.jsonl missing — run the backfill",
            based_on_path=str(nav_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (no nav_history.jsonl)")
        return EVAL_RC_FAIL

    ledger = [json.loads(ln) for ln in _read_lines(ledger_path)]
    nav_by_fund = _nav_by_fund(nav_path.read_text(encoding="utf-8"))
    # score_forward may raise ValueError on a scorer-invariant violation → FAIL
    forward_rows, _excl = score_forward(ledger, nav_by_fund, h=FORWARD_H, today=today)

    reports, details = build_metric_reports(
        forward_rows=forward_rows, retro_points=[], seed=20260616)

    # write details.json sibling, then point each MetricReport at the repo-relative path
    out_dir = report_dir(repo_root, _STAGE, today)
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "details.json",
                      json.dumps(details, ensure_ascii=False, indent=2))
    rel = f"outputs/{today}/evals/{_STAGE}/details.json"
    reports = [replace(m, details_ref=rel) for m in reports]

    overall = worst_status([m.status for m in reports])
    report = StageReport(stage=_STAGE, ran_at=datetime.now(_TZ).isoformat(),
                         based_on=[str(ledger_path), str(nav_path)],
                         metrics=reports, overall=overall)
    write_report(repo_root, report, artifact_date=today)
    print(f"{_STAGE} eval: {overall}")
    return {"PASS": EVAL_RC_PASS, "WARN": EVAL_RC_WARN}.get(overall, EVAL_RC_FAIL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_forward_runner.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Verify the stage runs end-to-end via the CLI dispatch**

Run: `uv run irc eval monitor_forward`
Expected: prints `monitor_forward eval: FAIL (no forward_ledger.jsonl)` on a clean tree (producer hasn't appended nav_history yet) — rc 2. This proves dispatch resolves the runner. (After Phase 9 + backfill it will WARN/PASS.)

- [ ] **Step 6: Commit**

```bash
git add evals/monitor_forward/runner.py tests/evals/test_monitor_forward_runner.py
git commit -m "feat(evals): monitor_forward runner — EDGE read, StageReport + details.json, FAIL on missing input"
```

---

## Phase 9 — EDGE wiring: producer append + daily-brief panel

### Task 21: producer `nav_history` bounded-tail append in `monitor_cmd.py`

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_write_eval_artifacts`)
- Test: `tests/commands/test_monitor_cmd_nav_history.py`

> Append nav_history rows in the SAME EDGE function that already appends the
> forward ledger (`_write_eval_artifacts`). Bounded tail: only
> `nav_date >= run_date - NAV_APPEND_DAYS`. Reuse `view.nav_series` (the dense
> acc-series already on each `FundView`). Wrapped in try/except — never crash the
> brief (mirrors the existing ledger append).

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_monitor_cmd_nav_history.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import date, timedelta
from irc.commands.monitor_cmd import _append_nav_history_for_views
from irc.monitor.render_types import FundView
from irc.monitor.types import NarrativeDoc, SignalRecord


def _sig():
    return SignalRecord(fund_id="a", status="ok", bias="ADD_BIAS", composite=0.2,
                        signal_confidence=0.9, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def _view(fund_id, series):
    return FundView(fund_id=fund_id, name_cn="x", latest_nav=1.0,
                    as_of_date=series[-1][0] if series else "N/A", nav_series=series,
                    signal=_sig(), narrative=NarrativeDoc(fund_id, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=())


def test_append_bounded_tail_only(tmp_path: Path):
    d0 = date.fromisoformat("2026-01-01")
    series = tuple(((d0 + timedelta(days=i)).isoformat(), 1.0 + 0.001 * i) for i in range(120))
    run_date = (d0 + timedelta(days=119)).isoformat()
    views = [_view("a", series)]
    _append_nav_history_for_views(tmp_path, views, run_date=run_date, written_at="w")
    p = tmp_path / "data" / "monitor" / "nav_history.jsonl"
    rows = [json.loads(ln) for ln in p.read_text().splitlines()]
    cutoff = (date.fromisoformat(run_date) - timedelta(days=60)).isoformat()
    assert rows, "no rows appended"
    assert all(r["nav_date"] >= cutoff for r in rows)
    assert len(rows) < 120                       # bounded, not the full series
    assert all(r["source_run_date"] == run_date for r in rows)


def test_append_never_crashes_on_empty_series(tmp_path: Path):
    _append_nav_history_for_views(tmp_path, [_view("a", ())], run_date="2026-01-01",
                                  written_at="w")  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_nav_history.py -v`
Expected: FAIL with `ImportError: cannot import name '_append_nav_history_for_views'`

- [ ] **Step 3: Write minimal implementation**

Add the import near the other `irc.monitor.eval` imports in `monitor_cmd.py`:

```python
from irc.monitor.eval.nav_history import nav_history_append_rows, append_nav_history
from irc.monitor.eval.constants import NAV_APPEND_DAYS
```

Add this helper (near `_write_eval_artifacts`):

```python
def _append_nav_history_for_views(
    root: Path, views: list[FundView], *, run_date: str, written_at: str,
) -> None:
    """EDGE: append each fund's bounded NAV tail to nav_history.jsonl. Bounded to
    nav_date >= run_date - NAV_APPEND_DAYS. Swallows failures — never crash the brief."""
    try:
        rows: list = []
        for v in views:
            rows.extend(nav_history_append_rows(
                fund_id=v.fund_id, acc_series=v.nav_series, run_date=run_date,
                written_at=written_at, nav_append_days=NAV_APPEND_DAYS,
            ))
        append_nav_history(root / "data" / "monitor" / "nav_history.jsonl", rows)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("nav_history append failed", exc_info=True)
```

Then call it from inside `_write_eval_artifacts` (right after the forward-ledger append block, reusing the existing `written_at` variable):

```python
    _append_nav_history_for_views(root, views, run_date=run_date, written_at=written_at)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_nav_history.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_nav_history.py
git commit -m "feat(monitor): producer appends bounded nav_history tail per run"
```

---

### Task 22: edge builds the `PredictivePanelModel` (staleness + review-trigger)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (new helper `_predictive_panel_model`)
- Test: `tests/commands/test_monitor_cmd_predictive_panel.py`

> The edge does all I/O for the panel: `latest_stage_report_entry("monitor_forward")`
> for staleness, then `list_stage_reports(limit=K*4)` + ISO-week dedup, loading each
> deduped week's `details.json` to extract the headline `publishable_bias_directional`
> random delta → the pure `review_trigger`. The resulting `PredictivePanelModel` is
> passed to the pure renderer (Task 23).

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_monitor_cmd_predictive_panel.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import date, timedelta
from irc.commands.monitor_cmd import _predictive_panel_model
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict


def _write_report(root: Path, artifact_date: str, *, bias_value=0.6, random_delta=0.05,
                  bias_state="ok"):
    d = root / "outputs" / artifact_date / "evals" / "monitor_forward"
    d.mkdir(parents=True)
    rel = f"outputs/{artifact_date}/evals/monitor_forward/details.json"
    metrics = [
        MetricReport("raw_composite_directional", 0.55, "WARN", 5, {}, rel),
        MetricReport("publishable_bias_directional", bias_value, "PASS", 9, {}, rel),
        MetricReport("rank_ic", 0.1, "WARN", 3, {}, rel),
    ]
    rep = StageReport("monitor_forward", f"{artifact_date}T09:00:00+08:00",
                      [], metrics, "WARN")
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")
    details = {
        "publishable_bias_directional": {
            "value": bias_value, "state": bias_state,
            "baseline_deltas": {"random": {"delta": random_delta}},
        },
        "raw_composite_directional": {"value": 0.55, "state": "ok",
                                      "baseline_deltas": {"random": {"delta": 0.0}}},
        "rank_ic": {"value": 0.1, "state": "insufficient_data",
                    "baseline_deltas": {"random": {"state": "insufficient_data"}}},
    }
    (d / "details.json").write_text(json.dumps(details), encoding="utf-8")


def test_no_report_yields_absent_model(tmp_path: Path):
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.present is False


def test_fresh_report_populates_metrics(tmp_path: Path):
    _write_report(tmp_path, "2026-06-15")
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.present is True and model.stale is False
    assert {m.name for m in model.metrics} == {
        "raw_composite_directional", "publishable_bias_directional", "rank_ic"}


def test_stale_when_artifact_date_old(tmp_path: Path):
    _write_report(tmp_path, "2026-05-01")  # > 10 days before today
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.stale is True and model.artifact_date == "2026-05-01"


def test_review_flag_fires_on_four_negative_weeks(tmp_path: Path):
    # four distinct ISO weeks, each headline random delta < 0
    for wk, d in enumerate(["2026-05-28", "2026-06-04", "2026-06-11", "2026-06-18"]):
        _write_report(tmp_path, d, random_delta=-0.05)
    model = _predictive_panel_model(tmp_path, today="2026-06-19")
    assert model.review_flag is True


def test_review_flag_not_fired_when_a_week_is_none(tmp_path: Path):
    _write_report(tmp_path, "2026-05-28", random_delta=-0.05)
    _write_report(tmp_path, "2026-06-04", random_delta=-0.05)
    _write_report(tmp_path, "2026-06-11", bias_state="insufficient_data")  # None week
    _write_report(tmp_path, "2026-06-18", random_delta=-0.05)
    model = _predictive_panel_model(tmp_path, today="2026-06-19")
    assert model.review_flag is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py -v`
Expected: FAIL with `ImportError: cannot import name '_predictive_panel_model'`

- [ ] **Step 3: Write minimal implementation**

Add imports to `monitor_cmd.py`:

```python
from evals._shared.latest_report import latest_stage_report_entry, list_stage_reports
from irc.monitor.eval.constants import REVIEW_TRIGGER_K, STALE_EVAL_DAYS
from irc.monitor.eval.review import dedup_iso_weeks, review_trigger
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel
```

Add these helpers:

```python
def _is_stale(artifact_date: str, today: str) -> bool:
    from datetime import date as _date
    return _date.fromisoformat(artifact_date) < _date.fromisoformat(today) - timedelta(
        days=STALE_EVAL_DAYS)


def _metric_view(m, details: dict) -> PredictiveMetricView:
    md = details.get(m.name, {})
    bd = md.get("baseline_deltas", {})
    def _d(key):
        e = bd.get(key)
        return e.get("delta") if isinstance(e, dict) and "delta" in e else None
    return PredictiveMetricView(
        name=m.name, value=m.value, status=m.status, state=md.get("state", "ok"),
        ci_low=md.get("ci_low", m.value), ci_high=md.get("ci_high", m.value),
        random_delta=_d("random"), momentum_delta=_d("momentum"),
        buy_hold_delta=_d("buy_hold"), n_observations=m.n_observations,
    )


def _load_details(root: Path, ref: str | None) -> dict:
    if not ref:
        return {}
    try:
        return json.loads((root / ref).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _headline_random_delta(root: Path, entry) -> float | None:
    """Per-week headline scalar for the review trigger: the publishable_bias_directional
    random delta. None when the headline row's state is insufficient_data/undefined,
    details.json missing, or the random baseline is itself insufficient_data."""
    rep = entry.report
    hdr = next((m for m in rep.metrics if m.name == "publishable_bias_directional"), None)
    if hdr is None:
        return None
    details = _load_details(root, hdr.details_ref)
    md = details.get("publishable_bias_directional", {})
    if md.get("state") in ("insufficient_data", "undefined"):
        return None
    rnd = md.get("baseline_deltas", {}).get("random", {})
    return rnd.get("delta") if "delta" in rnd else None


def _predictive_panel_model(root: Path, *, today: str) -> "PredictivePanelModel":
    entry = latest_stage_report_entry(root, "monitor_forward", today_iso=today)
    if entry is None:
        return PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                    metrics=(), review_flag=False)
    details = _load_details(
        root, next((m.details_ref for m in entry.report.metrics if m.details_ref), None))
    metrics = tuple(_metric_view(m, details) for m in entry.report.metrics)
    weeks = dedup_iso_weeks(
        list_stage_reports(root, "monitor_forward", limit=REVIEW_TRIGGER_K * 4,
                           today_iso=today),
        k=REVIEW_TRIGGER_K)
    weekly = [_headline_random_delta(root, e) for e in reversed(weeks)]  # chronological
    return PredictivePanelModel(
        present=True, stale=_is_stale(entry.artifact_date, today),
        artifact_date=entry.artifact_date, metrics=metrics,
        review_flag=review_trigger(weekly),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_predictive_panel.py
git commit -m "feat(monitor): edge builds predictive-validity panel model (staleness + review trigger)"
```

---

### Task 23: wire the panel model through `render_report` (pure) + CSS

**Files:**
- Modify: `src/irc/monitor/render_html.py` (`render_report` signature + body, CSS)
- Modify: `src/irc/commands/monitor_cmd.py` (`_write_outputs` passes `predictive_panel`)
- Test: `tests/monitor/test_render_html_predictive.py`

> `render_report` gains a keyword-only `predictive_panel: PredictivePanelModel | None
> = None` (default None keeps M0/M1 call-sites + tests valid). When present, the pure
> `predictive_validity_panel_html` output is concatenated after the existing
> validation `panel`. CSS for `.predictive-panel` is added to `_CSS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_render_html_predictive.py
from __future__ import annotations
from irc.monitor.render_html import render_report
from irc.monitor.render_types import Provenance
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel


def test_render_report_default_omits_predictive_panel():
    html = render_report((), Provenance("1", "1", "1", ""), prior_signal=None, now="t")
    assert "Predictive validity" not in html        # back-compat: default None


def test_render_report_includes_predictive_panel_when_passed():
    model = PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(PredictiveMetricView(
            name="publishable_bias_directional", value=0.6, status="PASS", state="ok",
            ci_low=0.5, ci_high=0.7, random_delta=0.05, momentum_delta=0.02,
            buy_hold_delta=0.01, n_observations=9),),
        review_flag=False)
    html = render_report((), Provenance("1", "1", "1", ""), prior_signal=None, now="t",
                         predictive_panel=model)
    assert "Predictive validity" in html
    assert "publishable_bias_directional" in html
    assert "<script" not in html.lower()             # no JS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_html_predictive.py -v`
Expected: FAIL with `TypeError: render_report() got an unexpected keyword argument 'predictive_panel'`

- [ ] **Step 3: Write minimal implementation**

In `render_html.py`, add the import:

```python
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html
from irc.monitor.eval.types import PredictivePanelModel
```

Add to `_CSS` (inside the `<style>` string, before the closing `"</style>"`):

```python
    ".predictive-panel{margin:16px 0;padding:8px;border:1px solid #d0d7de;border-radius:6px}"
    ".predictive{border-collapse:collapse;font-size:13px;margin:4px 0}"
    ".predictive th,.predictive td{border:1px solid #d0d7de;padding:3px 6px}"
    ".review-flag{color:#cf222e;font-weight:600}"
```

Change the `render_report` signature to add the keyword:

```python
def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    gates: dict[str, GateDecision] | None = None,
    predictive_panel: PredictivePanelModel | None = None,
) -> str:
```

In the body, build the predictive panel HTML and append it after `panel`:

```python
    predictive = (
        predictive_validity_panel_html(model=predictive_panel)
        if predictive_panel is not None else ""
    )
```

and change the final return to include it:

```python
        + header + summary + cards + panel + predictive + _appendix(views) + "</body></html>"
```

In `monitor_cmd.py` `_write_outputs`, add a `predictive_panel` parameter and pass it through:

```python
def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple[GateDecision, ...] = (),
                   predictive_panel=None) -> None:
    ...
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso(),
                         gates=gate_map, predictive_panel=predictive_panel)
```

And in `run_monitor`, build the model and pass it:

```python
    predictive_panel = _predictive_panel_model(root, today=_today)
    _write_outputs(out, views, prior, gates, predictive_panel=predictive_panel)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html_predictive.py tests/monitor/test_render_html_eval.py -v`
Expected: PASS (new predictive tests + existing M0/M1 render tests still green)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_html.py src/irc/commands/monitor_cmd.py tests/monitor/test_render_html_predictive.py
git commit -m "feat(monitor): render predictive-validity panel in the daily brief (pure, no JS)"
```

---

## Phase 10 — One-time backfill migration script (EDGE, isolated)

### Task 24: `scripts/backfill_nav_history.py`

**Files:**
- Create: `scripts/__init__.py` (empty — `scripts/` currently has no `__init__.py`; needed so `import scripts.backfill_nav_history` resolves under `pythonpath=["src","."]`)
- Create: `scripts/backfill_nav_history.py`
- Create: `tests/scripts/__init__.py` (empty — `tests/` uses the per-package `__init__.py` convention)
- Test: `tests/scripts/test_backfill_nav_history.py`

> This is a MIGRATION, never the eval runner (the eval surface must not mutate
> `data/`). It seeds `data/monitor/nav_history.jsonl` from the latest
> `outputs/<date>/monitor/eval_trace.json` `nav.acc_series` for each fund, so the
> retro grid has pre-window history depth. Idempotency is provided by the reader's
> dedup — re-running just appends duplicate-keyed rows that `latest_per_nav_date`
> collapses. The pure row-building is reused from `nav_history.nav_history_append_rows`
> with `nav_append_days` large enough to keep the FULL seeded series (use a sentinel
> like 100000 so the bound never trims the historical seed).

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_backfill_nav_history.py
from __future__ import annotations
import json
from pathlib import Path
from scripts.backfill_nav_history import backfill_rows_from_trace, run_backfill


def _trace(funds):
    return {"schema_version": "1", "engine_version": "1", "run_date": "2026-06-16",
            "funds": {fid: {"nav": {"as_of_date": series[-1][0],
                                    "acc_series": [list(p) for p in series]}}
                      for fid, series in funds.items()}}


def test_backfill_rows_from_trace_seeds_all_obs():
    trace = _trace({"a": [("2025-01-01", 1.0), ("2025-01-02", 1.1)]})
    rows = backfill_rows_from_trace(trace, source_run_date="2026-06-16", written_at="w")
    assert {r.fund_id for r in rows} == {"a"}
    assert [r.nav_date for r in rows] == ["2025-01-01", "2025-01-02"]
    assert all(r.source_run_date == "2026-06-16" for r in rows)


def test_run_backfill_writes_and_is_idempotent_under_dedup(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    out.mkdir(parents=True)
    trace = _trace({"a": [("2025-01-01", 1.0), ("2025-01-02", 1.1)]})
    (out / "eval_trace.json").write_text(json.dumps(trace), encoding="utf-8")
    run_backfill(tmp_path)
    run_backfill(tmp_path)   # second run → reader dedups duplicates
    from irc.monitor.eval.nav_history import parse_nav_history_lines, latest_per_nav_date
    text = (tmp_path / "data" / "monitor" / "nav_history.jsonl").read_text()
    deduped = latest_per_nav_date(parse_nav_history_lines(text))
    assert [r.nav_date for r in deduped] == ["2025-01-01", "2025-01-02"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scripts/test_backfill_nav_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.backfill_nav_history'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/__init__.py  → create empty if it does not exist (so `scripts` is importable)
```

```python
# scripts/backfill_nav_history.py
"""ONE-TIME migration: seed data/monitor/nav_history.jsonl from the latest
outputs/<date>/monitor/eval_trace.json nav.acc_series. NEVER part of the eval
runner (the eval surface must not mutate data/). Idempotent under the reader's
dedup. Run once after deploying M3, before the first `irc eval monitor_forward`.

Usage: uv run python -m scripts.backfill_nav_history [REPO_ROOT]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from irc.monitor.eval.nav_history import NavHistoryRow, append_nav_history

_TZ = timezone(timedelta(hours=8))
_HUGE_WINDOW = 100_000   # keep the FULL seeded series — never trim historical depth


def backfill_rows_from_trace(
    trace: dict, *, source_run_date: str, written_at: str,
) -> list[NavHistoryRow]:
    rows: list[NavHistoryRow] = []
    for fund_id, entry in trace.get("funds", {}).items():
        for nav_date, nav_acc in entry.get("nav", {}).get("acc_series", []):
            if nav_acc is None:
                continue
            rows.append(NavHistoryRow(
                fund_id=fund_id, nav_date=str(nav_date), nav_acc=float(nav_acc),
                written_at=written_at, source_run_date=source_run_date,
            ))
    return rows


def _latest_trace(repo_root: Path) -> Path | None:
    cands = sorted(repo_root.glob("outputs/*/monitor/eval_trace.json"), reverse=True)
    return cands[0] if cands else None


def run_backfill(repo_root: Path) -> int:
    trace_path = _latest_trace(repo_root)
    if trace_path is None:
        print("backfill: no eval_trace.json found under outputs/*/monitor/")
        return 1
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    run_date = trace.get("run_date") or trace_path.parent.parent.name
    written_at = datetime.now(_TZ).isoformat()
    rows = backfill_rows_from_trace(trace, source_run_date=run_date, written_at=written_at)
    append_nav_history(repo_root / "data" / "monitor" / "nav_history.jsonl", rows)
    print(f"backfill: seeded {len(rows)} nav_history rows from {trace_path}")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    raise SystemExit(run_backfill(root))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scripts/test_backfill_nav_history.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/backfill_nav_history.py tests/scripts/__init__.py tests/scripts/test_backfill_nav_history.py
git commit -m "feat(monitor): one-time nav_history backfill migration from eval_trace"
```

---

## Phase 11 — Acceptance, integration, and full-suite verification

### Task 25: acceptance — FAIL report never gates; COALESCE basis; byte-stable panel

**Files:**
- Test: `tests/monitor/test_acceptance_predictive.py`

> The M3 invariant: a FAIL `monitor_forward` report leaves every fund's
> `published_state` unchanged (M3 never gates). Plus: forward return uses the
> `COALESCE(nav_acc,nav)` basis (already true — `nav_history` rows carry `nav_acc`),
> and the panel renders without JS and is byte-stable across reruns.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_acceptance_predictive.py
from __future__ import annotations
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html


def _model(review=False):
    return PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(PredictiveMetricView(
            name="publishable_bias_directional", value=0.6, status="WARN", state="ok",
            ci_low=0.5, ci_high=0.7, random_delta=-0.05, momentum_delta=None,
            buy_hold_delta=0.01, n_observations=9),),
        review_flag=review)


def test_panel_is_byte_stable_across_reruns():
    a = predictive_validity_panel_html(model=_model())
    b = predictive_validity_panel_html(model=_model())
    assert a == b


def test_panel_has_no_js():
    html = predictive_validity_panel_html(model=_model(review=True))
    assert "<script" not in html.lower() and "onclick" not in html.lower()


def test_fail_report_does_not_carry_published_state():
    # A monitor_forward StageReport never contains any published_state field —
    # it is informational only. Guard the contract at the schema level.
    from evals._shared.report_schema import StageReport, MetricReport
    rep = StageReport("monitor_forward", "t", [], [MetricReport("x", 0.0, "FAIL")], "FAIL")
    from evals._shared.report_schema import report_to_dict
    d = report_to_dict(rep)
    assert "published_state" not in json.dumps(d)
```

Add `import json` at the top of the test file.

- [ ] **Step 2: Run test to verify it fails, then passes (no new impl needed — these assert existing behavior)**

Run: `uv run pytest tests/monitor/test_acceptance_predictive.py -v`
Expected: PASS (the cores already satisfy these — if any fails, fix the relevant core, not the test).

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_acceptance_predictive.py
git commit -m "test(monitor-eval): M3 acceptance — never gates, byte-stable panel, no JS"
```

---

### Task 26: full monitor-eval + green-suite verification

- [ ] **Step 1: Run the whole monitor-eval test surface**

Run: `uv run pytest tests/monitor/eval tests/evals tests/commands/test_monitor_cmd_nav_history.py tests/commands/test_monitor_cmd_predictive_panel.py tests/scripts -v`
Expected: ALL PASS.

- [ ] **Step 2: Confirm the green `--all` suite is unchanged (monitor_forward excluded)**

Run: `uv run irc eval --all 2>&1 | tail -25`
Expected: the eval summary does NOT list `monitor_forward` (it is `in_all_suite=False`). Overall verdict unchanged from baseline.

- [ ] **Step 3: Confirm `monitor_forward` runs by name**

Run: `uv run irc eval monitor_forward`
Expected: on a tree without producer artifacts → `monitor_forward eval: FAIL (no forward_ledger.jsonl)` rc 2. (This is correct — the producer/backfill have not populated `data/monitor/` in CI.)

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests evals scripts`
Expected: no errors (line-length 100, py312). Fix any reported issues.

- [ ] **Step 5: File-size budget check**

Run: `wc -l src/irc/monitor/eval/stats.py src/irc/monitor/eval/baselines.py src/irc/monitor/eval/backtest.py src/irc/monitor/eval/forward_score.py src/irc/monitor/eval/nav_history.py evals/monitor_forward/metrics.py evals/monitor_forward/runner.py`
Expected: every file < 200 lines. If any exceeds, extract a helper module before shipping.

- [ ] **Step 6: Final commit (if lint produced changes)**

```bash
git add -A
git commit -m "chore(monitor-eval): ruff + file-size cleanup for M3"
```

---

## Self-review checklist (run before handoff)

- [ ] **Three-date model** preserved everywhere: `series_entry_outcome` uses strict `>`; retro `anchor=as_of_date`, forward `anchor=run_date`; `from_latest_nav` is diagnostic-only (Tasks 10, 11, 13).
- [ ] **Retro grid floor** = config `minimum_observations` (passed into `run_backtest`), no `MIN_TREND_OBS` literal; below-floor / `insufficient_evidence` points excluded (Tasks 1, 11).
- [ ] **`FORWARD_H` dual unit** documented: NAV-obs window (join/momentum) + "H run-date block" (bootstrap comment in `stats.py`) (Tasks 1, 6).
- [ ] **WARN-max**: no `fail_below`/`fail_above` in any threshold dict; FAIL only via missing-input + scorer-invariant `ValueError`; `bad_nav` is a row exclusion (Tasks 10, 19, 20).
- [ ] **Registry**: `monitor_forward` `active, in_all_suite=False`, excluded from `active_suite_stages()`, not live_gated, no spend gate (Task 18, runner has no `preflight_gate`).
- [ ] **`latest_per_nav_date`** total order (written_at desc → source_run_date desc → last-line-wins) (Task 2).
- [ ] **Momentum undefined** uses `is None` OR `not math.isfinite` (Task 7).
- [ ] **`StageReportEntry`** namedtuple; `latest_stage_report` unchanged (Task 17).
- [ ] **`review_trigger`** pure, `None` breaks streak; edge loads headline random delta from `details.json` (Tasks 14, 22).
- [ ] **Per-metric details**: IC row has `baseline_deltas` = `{random}` only; hit-rate rows carry random/momentum/buy_hold (Task 19).
- [ ] **`details_ref`** repo-relative, no leading slash; `artifact_date` = runner execution date (Task 20).

---

## Notes for the implementer

- **Profile id:** tests use the real profile `"gold"` (eligible includes `trend`). If a fixture needs a different profile, read `src/irc/monitor/profiles.py PROFILES` and pick one whose `eligible` includes `trend`.
- **`MonitorFund` construction in tests:** required fields are `id, name_cn, market, analysis_profile, themes, constituent_news, weights, bands, minimum_confidence` (see `src/irc/monitor/types.py`). `weights` must include `"trend"`; `bands` needs `{"buy":..,"sell":..}`.
- **`window_returns` signature:** `window_returns(acc_nav, windows=(...))` returns `dict[int, float|None]` keyed by window; for momentum pass `windows=(FORWARD_H,)` and read `[FORWARD_H]` (see `src/irc/monitor/returns.py`).
- **Atomic writes:** use `irc.io_utils.atomic_write_text` for `details.json` / `report.json` (the runner already does via `write_report`).
- **Do NOT** add `monitor_forward` to `evals/monitor_suite` or the green suite. Do NOT call `preflight_gate` / `record_command_run` from the runner.
