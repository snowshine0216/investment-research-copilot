# 005 — Plan

## Step 1 — failing tests (Red)

### 1a. Update existing `tests/evals/test_discovery_runner.py`

Replace the JSON fixture with CSV. New shape:

```python
"""Discovery runner tests against the current CSV contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/005-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from evals.discovery.runner import run


_CSV_COLUMNS: tuple[str, ...] = (
    "instrument_id", "ticker", "market", "name_cn", "asset_class", "currency",
    "tracked_index", "venue_required", "role", "reason_text", "cited_refs", "relaxed",
)


def _watchlist(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in _CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[list(_CSV_COLUMNS)]


def _write_csv(repo_root: Path, date_iso: str, df: pd.DataFrame) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    path = out / "discovered_watchlist.csv"
    df.to_csv(path, index=False)
    return path


def test_discovery_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    # missing-input report lands under today's run date
    candidates = list((tmp_path / "outputs").rglob("evals/discovery/report.json"))
    assert candidates
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_discovery_runner_reads_dated_csv(tmp_path: Path) -> None:
    rows = [
        {"instrument_id": f"X{i}", "ticker": f"T{i}", "role": "core",
         "cited_refs": "ref-a,ref-b"}
        for i in range(10)
    ]
    date_iso = "2026-05-17"
    _write_csv(tmp_path, date_iso, _watchlist(rows))
    rc = run(tmp_path)
    assert rc in (0, 1)
    report_path = tmp_path / "outputs" / date_iso / "evals" / "discovery" / "report.json"
    assert report_path.exists()
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert {m["name"] for m in body["metrics"]} == {
        "candidates_per_role_min",
        "filter_integrity",
        "dedup",
        "llm_reason_grounding",
    }


def test_discovery_runner_fails_when_required_column_missing(tmp_path: Path) -> None:
    """When discovered_watchlist.csv lacks a contract-required column, the
    runner FAILs and the report.notes names the missing column — it does NOT
    silently return 1.0."""
    rows = [{"ticker": "T1", "role": "core", "cited_refs": "ref"}]
    df = pd.DataFrame(rows)  # missing instrument_id intentionally
    _write_csv(tmp_path, "2026-05-17", df)
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "discovery" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert body["overall"] == "FAIL"
    assert "instrument_id" in body["notes"]


def test_discovery_runner_prefers_today_over_yesterday(tmp_path: Path, monkeypatch) -> None:
    import evals._shared.locator as loc
    fixed = "2026-05-18"
    monkeypatch.setattr(loc, "_today_iso", lambda: fixed)
    today_rows = [
        {"instrument_id": f"X{i}", "ticker": f"T{i}", "role": "core", "cited_refs": "ref"}
        for i in range(10)
    ]
    yesterday_rows = [{"instrument_id": "STALE", "ticker": "STALE", "role": "core",
                       "cited_refs": "ref"}]
    _write_csv(tmp_path, "2026-05-17", _watchlist(yesterday_rows))
    _write_csv(tmp_path, fixed, _watchlist(today_rows))
    rc = run(tmp_path)
    assert rc in (0, 1)
    today_report = tmp_path / "outputs" / fixed / "evals" / "discovery" / "report.json"
    yesterday_report = tmp_path / "outputs" / "2026-05-17" / "evals" / "discovery" / "report.json"
    assert today_report.exists()
    assert not yesterday_report.exists()
```

### 1b. Update `tests/evals/test_discovery_metrics.py`

The `test_filter_integrity_with_nulls` test currently sets `score=None` and expects `0.9`. After we change the default `required_cols` to `("instrument_id", "ticker", "role")`, `score` is no longer required. Replace the null target with `role`:

```python
def test_filter_integrity_with_nulls():
    wl = _make_watchlist()
    wl.loc[0, "role"] = None
    rate = filter_integrity(wl)
    assert abs(rate - 9 / 10) < 1e-9
```

The other tests do not depend on the default and stay as-is.

Run: `uv run pytest tests/evals/test_discovery_runner.py tests/evals/test_discovery_metrics.py -x` — FAIL (runner still reads JSON; missing-column test asserts new runner behavior).

## Step 2 — implementation (Green)

### 2a. `evals/discovery/metrics.py` — update default

```python
def filter_integrity(
    watchlist: pd.DataFrame,
    required_cols: tuple[str, ...] = ("instrument_id", "ticker", "role"),
) -> float:
    ...  # body unchanged
```

### 2b. `evals/discovery/runner.py` — rewrite

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from evals._shared.locator import locate
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    EVAL_RC_PASS,
    EVAL_RC_WARN,
    missing_input_report,
    write_missing_input_report,
)
from evals._shared.report_paths import write_report
from evals._shared.report_schema import MetricReport, StageReport
from evals._shared.status import classify_status, worst_status
from evals.discovery.metrics import (
    candidates_per_role,
    dedup,
    filter_integrity,
    llm_reason_grounding,
)


_TZ = timezone(timedelta(hours=8))
_CAND_TH = {"warn_below": 8, "fail_below": 5}
_GROUND_TH = {"warn_below": 0.9, "fail_below": 0.7}
_INTEGRITY_TH = {"warn_below": 0.99, "fail_below": 0.9}
_DEDUP_TH = {"warn_below": 0.99, "fail_below": 0.9}

_REQUIRED_COLUMNS: tuple[str, ...] = ("instrument_id", "ticker", "role", "cited_refs")


def _missing_required(wl: pd.DataFrame) -> tuple[str, ...]:
    return tuple(c for c in _REQUIRED_COLUMNS if c not in wl.columns)


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("discovered_watchlist.csv",))
    if located is None:
        report = missing_input_report(
            stage="discovery",
            reason="outputs/<date>/discovered_watchlist.csv is missing — discovery stage did not run",
            based_on_path="outputs/<date>/discovered_watchlist.csv",
        )
        write_missing_input_report(repo_root, report)
        print(f"discovery eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    wl = pd.read_csv(source)

    missing = _missing_required(wl)
    if missing:
        report = StageReport(
            stage="discovery",
            ran_at=datetime.now(_TZ).isoformat(),
            based_on=[str(source)],
            metrics=[],
            overall="FAIL",
            notes=f"discovered_watchlist.csv missing required columns: {', '.join(missing)}",
        )
        write_report(repo_root, report, artifact_date=located.artifact_date)
        print(f"discovery eval: FAIL (schema mismatch — missing {', '.join(missing)})")
        return EVAL_RC_FAIL

    cpr = candidates_per_role(wl)
    min_cpr = min(cpr.values(), default=0)
    fi = filter_integrity(wl)
    dp = dedup(wl)
    gr = llm_reason_grounding(wl)

    metrics: list[MetricReport] = [
        MetricReport(
            name="candidates_per_role_min", value=float(min_cpr),
            status=classify_status(float(min_cpr), _CAND_TH, "higher_is_better"),
            n_observations=len(cpr), threshold=_CAND_TH,
        ),
        MetricReport(
            name="filter_integrity", value=fi,
            status=classify_status(fi, _INTEGRITY_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_INTEGRITY_TH,
        ),
        MetricReport(
            name="dedup", value=dp,
            status=classify_status(dp, _DEDUP_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_DEDUP_TH,
        ),
        MetricReport(
            name="llm_reason_grounding", value=gr,
            status=classify_status(gr, _GROUND_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_GROUND_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="discovery",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"discovery eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
```

Run targeted tests; all PASS.

## Step 3 — full suite + ruff

```
uv run pytest tests/evals -x
uv run ruff check evals/discovery tests/evals/test_discovery_runner.py tests/evals/test_discovery_metrics.py
```

## Step 4 — commit

```
feat(evals): modernize discovery runner to dated CSV contract (005)
```

## Notes / pitfalls

- `pd.read_csv` will keep `relaxed` as the literal `True`/`False` strings unless converted — but discovery metrics don't read `relaxed`, so leave it as-is.
- `cited_refs` is required because `llm_reason_grounding` reads it; treating it as a contract column makes the schema check loud.
- The today-vs-yesterday test must monkeypatch `_today_iso` because the runner depends on real system time.
- For the missing-input test, the report lands under today (run date) since there is no artifact date to anchor to.
- Existing `test_discovery_runner_fails_when_input_missing` already asserts `rc == 2` + a written FAIL report — the only change is replacing `rglob("evals/discovery/report.json")` instead of expecting a specific path (since today's date depends on the test clock).
