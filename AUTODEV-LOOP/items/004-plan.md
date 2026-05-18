# 004 — Plan

## Step 1 — failing tests (Red)

`tests/evals/test_report_paths.py`:

```python
"""Report-path helper tests.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/004-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

from evals._shared.report_paths import report_dir, write_report
from evals._shared.report_schema import StageReport


def _report(stage: str = "demo") -> StageReport:
    return StageReport(
        stage=stage, ran_at="2026-05-18T08:00:00+08:00",
        based_on=["src"], metrics=[], overall="PASS",
    )


def test_report_dir_under_artifact_date(tmp_path: Path) -> None:
    expected = tmp_path / "outputs" / "2026-05-17" / "evals" / "demo"
    assert report_dir(tmp_path, "demo", "2026-05-17") == expected


def test_write_report_creates_parents_and_returns_path(tmp_path: Path) -> None:
    path = write_report(tmp_path, _report(), artifact_date="2026-05-17")
    assert path == tmp_path / "outputs" / "2026-05-17" / "evals" / "demo" / "report.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["stage"] == "demo"
    assert body["overall"] == "PASS"


def test_write_report_overwrites_existing(tmp_path: Path) -> None:
    first = write_report(tmp_path, _report(), artifact_date="2026-05-17")
    first.write_text("stale", encoding="utf-8")
    write_report(tmp_path, _report(), artifact_date="2026-05-17")
    body = json.loads(first.read_text(encoding="utf-8"))
    assert body["stage"] == "demo"


def test_write_missing_input_report_still_lands_under_run_date(tmp_path: Path, monkeypatch) -> None:
    """write_missing_input_report keeps its run-date default behavior."""
    from evals._shared import missing_input

    monkeypatch.setattr(
        missing_input,
        "datetime",
        _FrozenDatetime,
    )
    rep = missing_input.missing_input_report(
        stage="demo", reason="absent", based_on_path="some/path",
    )
    path = missing_input.write_missing_input_report(tmp_path, rep)
    assert path.parent == tmp_path / "outputs" / "2099-01-02" / "evals" / "demo"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_write_missing_input_report_accepts_explicit_date(tmp_path: Path) -> None:
    from evals._shared import missing_input

    rep = missing_input.missing_input_report(
        stage="demo", reason="absent", based_on_path=None,
    )
    path = missing_input.write_missing_input_report(tmp_path, rep, date_str="2026-04-01")
    assert path.parent == tmp_path / "outputs" / "2026-04-01" / "evals" / "demo"


class _FrozenDatetime:
    """Stand-in for datetime in missing_input that produces a known 'today'."""

    @classmethod
    def now(cls, tz):  # noqa: D401
        from datetime import datetime as _real_dt, timezone, timedelta
        return _real_dt(2099, 1, 2, 0, 0, 0, tzinfo=timezone(timedelta(hours=8)))
```

Run: `uv run pytest tests/evals/test_report_paths.py -x` — all FAIL (module not found).

## Step 2 — implementation (Green)

### 2a. `evals/_shared/report_paths.py`

```python
"""Shared report-path helpers."""
from __future__ import annotations

import json
from pathlib import Path

from evals._shared.report_schema import StageReport, report_to_dict
from irc.io_utils import atomic_write_text


def report_dir(repo_root: Path, stage: str, artifact_date: str) -> Path:
    return repo_root / "outputs" / artifact_date / "evals" / stage


def write_report(
    repo_root: Path,
    report: StageReport,
    *,
    artifact_date: str,
) -> Path:
    out_dir = report_dir(repo_root, report.stage, artifact_date)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "report.json"
    atomic_write_text(out, json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    return out
```

### 2b. `evals/_shared/missing_input.py` — delegate

Replace the body of `write_missing_input_report`:

```python
def write_missing_input_report(
    repo_root: Path, report: StageReport, *, date_str: str | None = None,
) -> Path:
    if date_str is None:
        date_str = datetime.now(_TZ).date().isoformat()
    from evals._shared.report_paths import write_report
    return write_report(repo_root, report, artifact_date=date_str)
```

(Import-inside-function avoids any future circular-import risk between missing_input ↔ report_paths.)

### 2c. `evals/scoring/runner.py` — migrate

- Replace `_load_scores` with `locate(repo_root, ("scoring.json",))`.
- On `None`, write missing-input via existing helper, return FAIL.
- On hit, parse `paths[0]`; report's `based_on` = `[str(paths[0])]`; `_write(repo_root, report, source_date)` → `write_report(repo_root, report, artifact_date=located.artifact_date)`.
- Drop the local `_write` function.

### 2d. `evals/opportunity/runner.py` — migrate

- Replace `_locate_inputs` with: `loc = locate(repo_root, ("opportunity_report.json",))`.
- On `None`, write missing-input, return FAIL.
- On hit, derive `target_dir = loc.paths[0].parent`. The two sidecars (`thesis_cards.yaml`, `discipline_report.md`) are looked up under `target_dir` as today (so a date with only `opportunity_report.json` still runs metrics that don't need sidecars).
- Use `write_report(repo_root, report, artifact_date=loc.artifact_date)`.

## Step 3 — full suite + ruff

```
uv run pytest -x
uv run ruff check evals tests
```

Both exit 0. Existing scoring + opportunity runner tests must pass unchanged.

## Step 4 — commit

```
feat(evals): centralize report-date policy and migrate scoring + opportunity (004)
```

## Notes / pitfalls

- The `_FrozenDatetime` test stub must mimic `datetime.now(tz).date().isoformat()`; the `datetime` symbol inside `missing_input.py` is the `datetime` class (not the module), so the stub class is patched in place of it.
- The existing scoring test fixtures use `_today()` to compute a date — they will still pass after migration because the locator picks today's directory when present.
- The opportunity test fixture uses `2026-05-14` (not today); after migration, the locator still returns the latest valid date and the report still lands under `2026-05-14`.
- Keep `missing_input.input_age_days` as-is; only `write_missing_input_report` changes internally.
- Do not change the runner's `print(f"<stage> eval: ...")` lines; downstream tests assert on those.
