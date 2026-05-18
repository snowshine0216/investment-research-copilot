# Eval Truthfulness Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the eval framework runnable from the installed CLI and truthful against the pipeline artifacts that exist today, without trying to make the active suite green yet.

**Architecture:** Keep the existing top-level `evals` package for this rescue pass, package it correctly, and add two small shared units: a stage registry for active-vs-inactive eval semantics and a dated-artifact locator for consistent source selection/report placement. Modernize the runners that can be made truthful immediately; where the live artifact schema no longer supports the historical metric contract, emit an explicit contract-gap FAIL so Phase 2 starts from honest signal rather than fabricated PASSes.

**Tech Stack:** Python 3.13, Click, Hatchling packaging, pytest, pandas, PyYAML, existing `evals._shared` report schema utilities.

---

## Scope boundary

This plan implements **Phase 1 only** from `docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md`.

Phase 2 should be planned only after Phase 1 is complete and fresh reports have been regenerated, because the exact remaining failures depend on the repaired framework's output.

## File map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package the top-level `evals` package so the installed `irc` entrypoint can import it. |
| `tests/commands/test_eval_entrypoint.py` | Regression coverage for the installed CLI import failure. |
| `evals/_shared/registry.py` | Single source of truth for eval stage lifecycle and `--all` membership. |
| `evals/_shared/artifacts.py` | Pure lookup of dated artifact sets and latest dated output directories. |
| `evals/_shared/contract_gap.py` | Pure builder for explicit “metric contract no longer matches live artifact” FAIL reports. |
| `src/irc/commands/eval_cmd.py` | Resolve stages through the registry and exclude inactive stages from `--all`. |
| `evals/discovery/{metrics.py,runner.py}` | Read the live discovery CSV contract. |
| `evals/architecture/{metrics.py,runner.py}` | Measure the current output set and current memo filename. |
| `evals/gold_score/runner.py` | Read the live dated gold artifact pair and surface the unsupported historical metric contract honestly. |
| `evals/allocation/runner.py` | Read the live dated allocation YAML and surface the unsupported historical metric contract honestly. |
| `evals/trade_plan/runner.py` | Read the live dated trade-plan YAML and surface the unsupported historical metric contract honestly. |
| `evals/memo/runner.py` | Read the live dated memo artifact and surface the unsupported historical metric contract honestly. |
| `tests/evals/test_*_runner.py`, `tests/evals/test_discovery_metrics.py`, `tests/evals/test_architecture.py`, `tests/commands/test_eval_cmd.py` | Contract and regression coverage for the changes above. |

---

### Task 1: Package `evals` and lock in the installed-entrypoint regression

**Files:**
- Create: `tests/commands/test_eval_entrypoint.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing installed-entrypoint test**

Create `tests/commands/test_eval_entrypoint.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _research_status_payload() -> dict:
    themes = [
        {"theme": theme, "citation_count": 4, "failure_reason": ""}
        for theme in (
            "us_monetary",
            "us_fiscal_politics",
            "cn_monetary",
            "cn_equity_property_policy",
            "geopolitics",
            "gold_drivers",
            "holdings_sector",
        )
    ]
    return {"themes": themes}


def test_installed_eval_entrypoint_can_import_eval_package(tmp_path: Path) -> None:
    status = tmp_path / "data" / "research" / "research_status.json"
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps(_research_status_payload()), encoding="utf-8")

    irc_bin = Path(sys.executable).with_name("irc")
    assert irc_bin.exists(), f"installed irc entrypoint missing at {irc_bin}"

    result = subprocess.run(
        [str(irc_bin), "eval", "research", "--repo-root", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "research eval: PASS" in result.stdout
```

- [ ] **Step 2: Run the test to verify it fails for the reported reason**

Run:

```bash
uv run pytest tests/commands/test_eval_entrypoint.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'evals'` from the installed `irc` entrypoint subprocess.

- [ ] **Step 3: Package the top-level eval package**

Update the Hatch wheel package list in `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/irc", "evals"]
```

- [ ] **Step 4: Run the regression test again**

Run:

```bash
uv run pytest tests/commands/test_eval_entrypoint.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/commands/test_eval_entrypoint.py
git commit -m "fix(evals): package eval runners for installed cli"
```

---

### Task 2: Add an eval registry and make `--all` mean “all active evals”

**Files:**
- Create: `evals/_shared/registry.py`
- Modify: `src/irc/commands/eval_cmd.py`
- Modify: `tests/commands/test_eval_cmd.py`

- [ ] **Step 1: Write the failing registry-behavior tests**

Append to `tests/commands/test_eval_cmd.py`:

```python
def test_run_eval_all_skips_inactive_stages(tmp_path, monkeypatch):
    from irc.commands import eval_cmd

    seen: list[str] = []

    def _fake_get_runner(stage: str):
        seen.append(stage)
        return lambda _root: 0

    monkeypatch.setattr(eval_cmd, "_get_runner", _fake_get_runner)

    rc = eval_cmd.run_eval(str(tmp_path), stage=None, all_stages=True)

    assert rc == 0
    assert "news" not in seen
    assert "queries" not in seen
    assert "triggers" in seen


def test_eval_inactive_stage_errors_with_reason(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "queries", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0
    assert "inactive_uninstrumented" in r.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/commands/test_eval_cmd.py -q
```

Expected: FAIL because `run_eval(... --all)` still includes `news` and `queries`, and direct `queries` invocation still tries to run the old runner.

- [ ] **Step 3: Create the registry**

Create `evals/_shared/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Lifecycle = Literal[
    "active",
    "unimplemented_active",
    "inactive_legacy",
    "inactive_uninstrumented",
]


@dataclass(frozen=True)
class EvalStageSpec:
    name: str
    runner_module: str
    lifecycle: Lifecycle
    include_in_all: bool
    reason: str = ""


class InactiveEvalStageError(ValueError):
    """Raised when a known eval stage is intentionally inactive."""


_STAGES: tuple[EvalStageSpec, ...] = (
    EvalStageSpec("data", "evals.data.runner", "active", True),
    EvalStageSpec(
        "news",
        "evals.news.runner",
        "inactive_legacy",
        False,
        "no current producer or live artifact contract",
    ),
    EvalStageSpec("research", "evals.research.runner", "active", True),
    EvalStageSpec("discovery", "evals.discovery.runner", "active", True),
    EvalStageSpec("scoring", "evals.scoring.runner", "active", True),
    EvalStageSpec("gold_score", "evals.gold_score.runner", "active", True),
    EvalStageSpec("allocation", "evals.allocation.runner", "active", True),
    EvalStageSpec("trade_plan", "evals.trade_plan.runner", "active", True),
    EvalStageSpec("memo", "evals.memo.runner", "active", True),
    EvalStageSpec(
        "queries",
        "evals.queries.runner",
        "inactive_uninstrumented",
        False,
        "`irc ask` writes no persisted artifact to evaluate",
    ),
    EvalStageSpec(
        "triggers",
        "evals.triggers.runner",
        "unimplemented_active",
        True,
        "real trigger metrics are not implemented yet",
    ),
    EvalStageSpec("architecture", "evals.architecture.runner", "active", True),
    EvalStageSpec("opportunity", "evals.opportunity.runner", "active", True),
)

_BY_NAME: dict[str, EvalStageSpec] = {stage.name: stage for stage in _STAGES}


def get_stage_spec(stage: str) -> EvalStageSpec:
    if stage not in _BY_NAME:
        raise KeyError(f"unknown eval stage: {stage}")
    spec = _BY_NAME[stage]
    if spec.lifecycle.startswith("inactive_"):
        raise InactiveEvalStageError(
            f"eval stage '{stage}' is {spec.lifecycle}: {spec.reason}"
        )
    return spec


def active_stage_names() -> tuple[str, ...]:
    return tuple(stage.name for stage in _STAGES if stage.include_in_all)
```

Replace the hardcoded mapping and hardcoded `stages = (...)` tuple in `src/irc/commands/eval_cmd.py` with:

```python
from evals._shared.registry import (
    InactiveEvalStageError,
    active_stage_names,
    get_stage_spec,
)


def _get_runner(stage: str) -> Callable[[Path], int]:
    spec = get_stage_spec(stage)
    mod = importlib.import_module(spec.runner_module)
    return mod.run
```

and:

```python
    if all_stages:
        by_stage: dict[str, int] = {}
        for s in active_stage_names():
            try:
                rc = _get_runner(s)(root)
            except Exception as e:
                print(f"eval {s} raised: {e}")
                rc = 2
            by_stage[s] = rc
        _print_eval_summary(by_stage)
        return max(by_stage.values())
```

Update the single-stage exception handling:

```python
    try:
        return _get_runner(stage)(root)
    except (KeyError, InactiveEvalStageError) as e:
        print(f"ERROR: {e}")
        return 2
```

- [ ] **Step 4: Re-run the registry tests**

Run:

```bash
uv run pytest tests/commands/test_eval_cmd.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/registry.py src/irc/commands/eval_cmd.py tests/commands/test_eval_cmd.py
git commit -m "feat(evals): add active-stage registry"
```

---

### Task 3: Add shared dated-artifact lookup

**Files:**
- Create: `evals/_shared/artifacts.py`
- Create: `tests/evals/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact-locator tests**

Create `tests/evals/test_artifacts.py`:

```python
from __future__ import annotations

from pathlib import Path

from evals._shared.artifacts import (
    latest_dated_output_dir,
    locate_dated_artifacts,
)


def test_locate_dated_artifacts_prefers_today(tmp_path: Path) -> None:
    past = tmp_path / "outputs" / "2026-05-17"
    today = tmp_path / "outputs" / "2026-05-18"
    past.mkdir(parents=True)
    today.mkdir(parents=True)
    (past / "scoring.json").write_text("{}", encoding="utf-8")
    (today / "scoring.json").write_text("{}", encoding="utf-8")

    found = locate_dated_artifacts(
        tmp_path,
        ("scoring.json",),
        today="2026-05-18",
    )

    assert found is not None
    assert found.date_str == "2026-05-18"
    assert found.paths == (today / "scoring.json",)


def test_locate_dated_artifacts_falls_back_to_latest_complete_set(tmp_path: Path) -> None:
    older = tmp_path / "outputs" / "2026-05-16"
    newer_partial = tmp_path / "outputs" / "2026-05-17"
    older.mkdir(parents=True)
    newer_partial.mkdir(parents=True)
    (older / "gold_regime.json").write_text("{}", encoding="utf-8")
    (older / "gold_band.yaml").write_text("{}", encoding="utf-8")
    (newer_partial / "gold_regime.json").write_text("{}", encoding="utf-8")

    found = locate_dated_artifacts(
        tmp_path,
        ("gold_regime.json", "gold_band.yaml"),
        today="2026-05-18",
    )

    assert found is not None
    assert found.date_str == "2026-05-16"


def test_locate_dated_artifacts_returns_none_when_no_complete_set(tmp_path: Path) -> None:
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    (out / "gold_regime.json").write_text("{}", encoding="utf-8")

    assert locate_dated_artifacts(
        tmp_path,
        ("gold_regime.json", "gold_band.yaml"),
        today="2026-05-18",
    ) is None


def test_latest_dated_output_dir_returns_latest_even_when_partial(tmp_path: Path) -> None:
    older = tmp_path / "outputs" / "2026-05-16"
    newer = tmp_path / "outputs" / "2026-05-17"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    found = latest_dated_output_dir(tmp_path, today="2026-05-18")

    assert found is not None
    assert found.date_str == "2026-05-17"
    assert found.path == newer
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/evals/test_artifacts.py -q
```

Expected: FAIL because `evals._shared.artifacts` does not exist yet.

- [ ] **Step 3: Implement the pure artifact locator**

Create `evals/_shared/artifacts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re


_TZ = timezone(timedelta(hours=8))
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DatedArtifactSet:
    date_str: str
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class DatedOutputDir:
    date_str: str
    path: Path


def _dated_dirs(repo_root: Path) -> tuple[Path, ...]:
    outputs = repo_root / "outputs"
    if not outputs.exists():
        return ()
    return tuple(
        sorted(
            (
                path for path in outputs.iterdir()
                if path.is_dir() and _DATE_RE.match(path.name)
            ),
            key=lambda path: path.name,
        )
    )


def locate_dated_artifacts(
    repo_root: Path,
    names: tuple[str, ...],
    *,
    today: str | None = None,
) -> DatedArtifactSet | None:
    today = today or datetime.now(_TZ).date().isoformat()
    dated_dirs = _dated_dirs(repo_root)
    today_dir = repo_root / "outputs" / today
    search_order = (
        ((today_dir,) if today_dir in dated_dirs else ())
        + tuple(path for path in reversed(dated_dirs) if path != today_dir)
    )
    for directory in search_order:
        paths = tuple(directory / name for name in names)
        if all(path.exists() for path in paths):
            return DatedArtifactSet(date_str=directory.name, paths=paths)
    return None


def latest_dated_output_dir(
    repo_root: Path,
    *,
    today: str | None = None,
) -> DatedOutputDir | None:
    today = today or datetime.now(_TZ).date().isoformat()
    dated_dirs = _dated_dirs(repo_root)
    today_dir = repo_root / "outputs" / today
    if today_dir in dated_dirs:
        return DatedOutputDir(date_str=today_dir.name, path=today_dir)
    if not dated_dirs:
        return None
    latest = dated_dirs[-1]
    return DatedOutputDir(date_str=latest.name, path=latest)
```

- [ ] **Step 4: Re-run the artifact tests**

Run:

```bash
uv run pytest tests/evals/test_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/artifacts.py tests/evals/test_artifacts.py
git commit -m "feat(evals): add dated artifact locator"
```

---

### Task 4: Modernize discovery and architecture contracts

**Files:**
- Modify: `evals/discovery/metrics.py`
- Modify: `evals/discovery/runner.py`
- Modify: `tests/evals/test_discovery_metrics.py`
- Modify: `tests/evals/test_discovery_runner.py`
- Modify: `evals/architecture/metrics.py`
- Modify: `evals/architecture/runner.py`
- Modify: `tests/evals/test_architecture.py`

- [ ] **Step 1: Write the failing current-contract tests**

Update the discovery metric fixture in `tests/evals/test_discovery_metrics.py` so it mirrors the live CSV contract:

```python
def _make_watchlist() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN", "META", "NVDA", "AMD", "INTC", "QCOM"],
        "role": ["growth"] * 5 + ["value"] * 5,
        "reason_text": ["reason"] * 10,
        "cited_refs": ["ref1", "ref2", "", "ref4", "ref5", "", "ref7", "ref8", "ref9", ""],
    })


def test_filter_integrity_with_nulls():
    wl = _make_watchlist()
    wl.loc[0, "reason_text"] = None
    rate = filter_integrity(wl)
    assert abs(rate - 9 / 10) < 1e-9
```

Append to `tests/evals/test_discovery_runner.py`:

```python
def test_discovery_runner_reads_dated_current_csv(tmp_path: Path) -> None:
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    rows = [
        "instrument_id,ticker,role,reason_text,cited_refs",
        *[
            f"{i},T{i},core,reason,ref_{i}"
            for i in range(8)
        ],
    ]
    (out / "discovered_watchlist.csv").write_text("\n".join(rows), encoding="utf-8")

    rc = run(tmp_path)

    assert rc == 0
    report = json.loads(
        (out / "evals" / "discovery" / "report.json").read_text(encoding="utf-8")
    )
    assert report["based_on"] == [str(out / "discovered_watchlist.csv")]
```

Update `tests/evals/test_architecture.py`:

```python
def test_output_files_present(tmp_path: Path):
    out_dir = tmp_path / "outputs/2026-05-07"
    out_dir.mkdir(parents=True)
    for name in ("discovered_watchlist.csv", "scoring.json", "gold_regime.json",
                 "gold_band.yaml", "proposed_allocation.yaml", "trade_plan.yaml",
                 "memo.md"):
        (out_dir / name).touch()
    out = output_files_present(out_dir)
    assert out["completeness"] == 1.0


def test_architecture_runner_uses_latest_dated_output_dir(tmp_path: Path):
    out_dir = tmp_path / "outputs" / "2026-05-17"
    out_dir.mkdir(parents=True)
    for name in ("discovered_watchlist.csv", "scoring.json", "gold_regime.json",
                 "gold_band.yaml", "proposed_allocation.yaml", "trade_plan.yaml",
                 "memo.md"):
        (out_dir / name).touch()

    rc = run(tmp_path)

    assert rc in (0, 1, 2)
    assert (out_dir / "evals" / "architecture" / "report.json").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/evals/test_discovery_metrics.py tests/evals/test_discovery_runner.py tests/evals/test_architecture.py -q
```

Expected: FAIL because discovery still reads the retired JSON path, architecture still expects `research_memo.md`, and architecture writes under today's date instead of the evaluated output directory.

- [ ] **Step 3: Update discovery to the live CSV contract**

Change `evals/discovery/metrics.py`:

```python
def filter_integrity(
    watchlist: pd.DataFrame,
    required_cols: tuple[str, ...] = ("ticker", "role", "reason_text", "cited_refs"),
) -> float:
```

Replace the start of `evals/discovery/runner.py::run` with:

```python
from evals._shared.artifacts import locate_dated_artifacts


def run(repo_root: Path) -> int:
    artifacts = locate_dated_artifacts(repo_root, ("discovered_watchlist.csv",))
    if artifacts is None:
        report = missing_input_report(
            stage="discovery",
            reason="outputs/<date>/discovered_watchlist.csv is missing — discovery stage did not run",
            based_on_path="outputs/<date>/discovered_watchlist.csv",
        )
        write_missing_input_report(repo_root, report)
        print(f"discovery eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    watchlist_file = artifacts.paths[0]
    wl = pd.read_csv(watchlist_file)
```

and change the final write call/helper to:

```python
    _write(repo_root, report, artifacts.date_str)


def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Update architecture to the current output names and evaluated directory**

Change `_REQUIRED_OUTPUTS` in `evals/architecture/metrics.py`:

```python
_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "discovered_watchlist.csv",
    "scoring.json",
    "gold_regime.json",
    "gold_band.yaml",
    "proposed_allocation.yaml",
    "trade_plan.yaml",
    "memo.md",
)
```

Replace the date/output-dir selection block in `evals/architecture/runner.py` with:

```python
from evals._shared.artifacts import latest_dated_output_dir


def run(repo_root: Path) -> int:
    dag_ok = dag_acyclic_check(repo_root / "src" / "irc")
    max_loc = max_file_loc(repo_root / "src" / "irc")
    latest = latest_dated_output_dir(repo_root)

    if latest is None:
        report = missing_input_report(
            stage="architecture",
            reason="outputs/<date>/ is missing — no dated pipeline output exists",
            based_on_path="outputs/<date>/",
        )
        write_missing_input_report(repo_root, report)
        print(f"architecture eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    files = output_files_present(latest.path)
```

and replace the output path block with:

```python
    out_eval = latest.path / "evals" / "architecture"
    out_eval.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_eval / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 5: Re-run the tests and commit**

Run:

```bash
uv run pytest tests/evals/test_discovery_metrics.py tests/evals/test_discovery_runner.py tests/evals/test_architecture.py -q
```

Expected: PASS.

```bash
git add evals/discovery/metrics.py evals/discovery/runner.py tests/evals/test_discovery_metrics.py \
        tests/evals/test_discovery_runner.py \
        evals/architecture/metrics.py evals/architecture/runner.py tests/evals/test_architecture.py
git commit -m "fix(evals): align discovery and architecture contracts"
```

---

### Task 5: Add explicit contract-gap reports and wire `gold_score`

**Files:**
- Create: `evals/_shared/contract_gap.py`
- Create: `tests/evals/test_contract_gap.py`
- Modify: `evals/gold_score/runner.py`
- Modify: `tests/evals/test_gold_score_runner.py`

- [ ] **Step 1: Write the failing contract-gap tests**

Create `tests/evals/test_contract_gap.py`:

```python
from __future__ import annotations

from evals._shared.contract_gap import unsupported_contract_report


def test_unsupported_contract_report_is_explicit_fail() -> None:
    report = unsupported_contract_report(
        stage="memo",
        based_on_paths=["outputs/2026-05-17/memo.md"],
        reason="memo metric contract needs redesign",
    )

    assert report.overall == "FAIL"
    assert report.based_on == ["outputs/2026-05-17/memo.md"]
    assert "needs redesign" in report.notes
```

Append to `tests/evals/test_gold_score_runner.py`:

```python
def test_gold_score_runner_reads_live_artifacts_and_reports_contract_gap(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    (out / "gold_regime.json").write_text(
        json.dumps({"regime": "range_bound", "score": 50, "tilt": "neutral"}),
        encoding="utf-8",
    )
    (out / "gold_band.yaml").write_text("median: 1\n", encoding="utf-8")

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads(
        (out / "evals" / "gold_score" / "report.json").read_text(encoding="utf-8")
    )
    assert report["based_on"] == [
        str(out / "gold_regime.json"),
        str(out / "gold_band.yaml"),
    ]
    assert "metric contract" in report["notes"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/evals/test_contract_gap.py tests/evals/test_gold_score_runner.py -q
```

Expected: FAIL because the helper does not exist and `gold_score` still looks for the retired JSON path.

- [ ] **Step 3: Implement the pure contract-gap helper**

Create `evals/_shared/contract_gap.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from evals._shared.report_schema import StageReport


_TZ = timezone(timedelta(hours=8))


def unsupported_contract_report(
    *,
    stage: str,
    based_on_paths: list[str],
    reason: str,
) -> StageReport:
    return StageReport(
        stage=stage,
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=based_on_paths,
        metrics=[],
        overall="FAIL",
        notes=reason,
    )
```

- [ ] **Step 4: Wire `gold_score` to the live artifact pair**

Replace `evals/gold_score/runner.py::run` with:

```python
import yaml
from evals._shared.artifacts import locate_dated_artifacts
from evals._shared.contract_gap import unsupported_contract_report


def run(repo_root: Path) -> int:
    artifacts = locate_dated_artifacts(
        repo_root,
        ("gold_regime.json", "gold_band.yaml"),
    )
    if artifacts is None:
        report = missing_input_report(
            stage="gold_score",
            reason="outputs/<date>/gold_regime.json + gold_band.yaml are missing — gold stage did not run",
            based_on_path="outputs/<date>/gold_regime.json + gold_band.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"gold_score eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    json.loads(artifacts.paths[0].read_text(encoding="utf-8"))
    yaml.safe_load(artifacts.paths[1].read_text(encoding="utf-8"))
    report = unsupported_contract_report(
        stage="gold_score",
        based_on_paths=[str(path) for path in artifacts.paths],
        reason=(
            "gold_score metric contract still expects retired fields "
            "`drivers`, `regime_history`, and `preferences_band`; "
            "Phase 2 must redesign metrics for gold_regime.json/gold_band.yaml"
        ),
    )
    _write(repo_root, report, artifacts.date_str)
    print(f"gold_score eval: {report.overall} (metric contract gap)")
    return EVAL_RC_FAIL
```

and update `_write`:

```python
def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "gold_score"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 5: Re-run the tests and commit**

Run:

```bash
uv run pytest tests/evals/test_contract_gap.py tests/evals/test_gold_score_runner.py -q
```

Expected: PASS.

```bash
git add evals/_shared/contract_gap.py tests/evals/test_contract_gap.py \
        evals/gold_score/runner.py tests/evals/test_gold_score_runner.py
git commit -m "fix(evals): expose gold metric contract gap"
```

---

### Task 6: Wire `allocation` to the live YAML contract

**Files:**
- Modify: `evals/allocation/runner.py`
- Modify: `tests/evals/test_allocation_runner.py`

- [ ] **Step 1: Write the failing current-contract test**

Append to `tests/evals/test_allocation_runner.py`:

```python
def test_allocation_runner_reads_live_yaml_and_reports_contract_gap(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    (out / "proposed_allocation.yaml").write_text(
        "target_weights_per_class:\n"
        "  gold: 0.2\n"
        "selected_instruments: []\n"
        "diagnostics:\n"
        "  total_weight: 0.2\n",
        encoding="utf-8",
    )

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads(
        (out / "evals" / "allocation" / "report.json").read_text(encoding="utf-8")
    )
    assert report["based_on"] == [str(out / "proposed_allocation.yaml")]
    assert "metric contract" in report["notes"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/evals/test_allocation_runner.py -q
```

Expected: FAIL because allocation still looks for `outputs/allocation/allocation.json`.

- [ ] **Step 3: Replace the runner body with the truthful current-contract version**

Update `evals/allocation/runner.py`:

```python
import yaml
from evals._shared.artifacts import locate_dated_artifacts
from evals._shared.contract_gap import unsupported_contract_report


def run(repo_root: Path) -> int:
    artifacts = locate_dated_artifacts(repo_root, ("proposed_allocation.yaml",))
    if artifacts is None:
        report = missing_input_report(
            stage="allocation",
            reason="outputs/<date>/proposed_allocation.yaml is missing — allocation stage did not run",
            based_on_path="outputs/<date>/proposed_allocation.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"allocation eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    allocation_file = artifacts.paths[0]
    yaml.safe_load(allocation_file.read_text(encoding="utf-8"))
    report = unsupported_contract_report(
        stage="allocation",
        based_on_paths=[str(allocation_file)],
        reason=(
            "allocation metric contract still expects retired artifact fields "
            "`class_bands`, `currency_targets`, and `correlation_matrix_1y`; "
            "Phase 2 must redesign metrics for proposed_allocation.yaml"
        ),
    )
    _write(repo_root, report, artifacts.date_str)
    print(f"allocation eval: {report.overall} (metric contract gap)")
    return EVAL_RC_FAIL
```

and update `_write`:

```python
def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "allocation"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Re-run the test**

Run:

```bash
uv run pytest tests/evals/test_allocation_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/allocation/runner.py tests/evals/test_allocation_runner.py
git commit -m "fix(evals): expose allocation metric contract gap"
```

---

### Task 7: Wire `trade_plan` to the live YAML contract

**Files:**
- Modify: `evals/trade_plan/runner.py`
- Modify: `tests/evals/test_trade_plan_runner.py`

- [ ] **Step 1: Write the failing current-contract test**

Append to `tests/evals/test_trade_plan_runner.py`:

```python
def test_trade_plan_runner_reads_live_yaml_and_reports_contract_gap(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    (out / "trade_plan.yaml").write_text(
        "mode: build\n"
        "trades:\n"
        "- target: '518880'\n"
        "  asset_class: gold\n"
        "  buy_method: gold_anchor_plus_band\n"
        "  venue_compatible: false\n"
        "  triggers: []\n",
        encoding="utf-8",
    )

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads(
        (out / "evals" / "trade_plan" / "report.json").read_text(encoding="utf-8")
    )
    assert report["based_on"] == [str(out / "trade_plan.yaml")]
    assert "metric contract" in report["notes"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/evals/test_trade_plan_runner.py -q
```

Expected: FAIL because trade-plan still reads `outputs/trade_plan/trades.json`.

- [ ] **Step 3: Replace the runner body with the truthful current-contract version**

Update `evals/trade_plan/runner.py`:

```python
import yaml
from evals._shared.artifacts import locate_dated_artifacts
from evals._shared.contract_gap import unsupported_contract_report


def run(repo_root: Path) -> int:
    artifacts = locate_dated_artifacts(repo_root, ("trade_plan.yaml",))
    if artifacts is None:
        report = missing_input_report(
            stage="trade_plan",
            reason="outputs/<date>/trade_plan.yaml is missing — trade-plan stage did not run",
            based_on_path="outputs/<date>/trade_plan.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"trade_plan eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    plan_file = artifacts.paths[0]
    yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    report = unsupported_contract_report(
        stage="trade_plan",
        based_on_paths=[str(plan_file)],
        reason=(
            "trade_plan metric contract still expects retired fields "
            "`venue`, `instrument_class`, and scalar `trigger`; "
            "Phase 2 must redesign metrics for trade_plan.yaml"
        ),
    )
    _write(repo_root, report, artifacts.date_str)
    print(f"trade_plan eval: {report.overall} (metric contract gap)")
    return EVAL_RC_FAIL
```

and update `_write`:

```python
def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "trade_plan"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Re-run the test**

Run:

```bash
uv run pytest tests/evals/test_trade_plan_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/trade_plan/runner.py tests/evals/test_trade_plan_runner.py
git commit -m "fix(evals): expose trade-plan metric contract gap"
```

---

### Task 8: Wire `memo` to the live dated memo contract

**Files:**
- Modify: `evals/memo/runner.py`
- Modify: `tests/evals/test_memo_runner.py`

- [ ] **Step 1: Write the failing current-contract test**

Append to `tests/evals/test_memo_runner.py`:

```python
def test_memo_runner_reads_live_memo_and_reports_contract_gap(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-05-17"
    out.mkdir(parents=True)
    (out / "memo.md").write_text("# memo\n", encoding="utf-8")
    (out / "memo_audit.txt").write_text("# audit\n", encoding="utf-8")
    (out / "memo_traceability.json").write_text(
        '{"n_refs_provided": 1, "n_refs_quoted_verbatim": 0, "n_refs": 1}',
        encoding="utf-8",
    )

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads(
        (out / "evals" / "memo" / "report.json").read_text(encoding="utf-8")
    )
    assert report["based_on"] == [str(out / "memo.md")]
    assert "metric contract" in report["notes"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/evals/test_memo_runner.py -q
```

Expected: FAIL because memo still reads `outputs/memo/memo.md`.

- [ ] **Step 3: Replace the runner body with the truthful current-contract version**

Update `evals/memo/runner.py`:

```python
from evals._shared.artifacts import locate_dated_artifacts
from evals._shared.contract_gap import unsupported_contract_report


def run(repo_root: Path) -> int:
    artifacts = locate_dated_artifacts(repo_root, ("memo.md",))
    if artifacts is None:
        report = missing_input_report(
            stage="memo",
            reason="outputs/<date>/memo.md is missing — memo stage did not run",
            based_on_path="outputs/<date>/memo.md",
        )
        write_missing_input_report(repo_root, report)
        print(f"memo eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    memo_file = artifacts.paths[0]
    memo_file.read_text(encoding="utf-8")
    report = unsupported_contract_report(
        stage="memo",
        based_on_paths=[str(memo_file)],
        reason=(
            "memo metric contract still expects retired sidecars "
            "`audit.json`, `refs.json`, and `baseline_chars.txt`; "
            "Phase 2 must redesign metrics for memo.md/memo_audit.txt/memo_traceability.json"
        ),
    )
    _write(repo_root, report, artifacts.date_str)
    print(f"memo eval: {report.overall} (metric contract gap)")
    return EVAL_RC_FAIL
```

and update `_write`:

```python
def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "memo"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Re-run the test**

Run:

```bash
uv run pytest tests/evals/test_memo_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/memo/runner.py tests/evals/test_memo_runner.py
git commit -m "fix(evals): expose memo metric contract gap"
```

---

### Task 9: Verify the whole Phase-1 repair against current outputs

**Files:**
- Modify only if needed after verification: `tests/commands/test_eval_cmd.py`, runner tests touched above

- [ ] **Step 1: Run the focused Phase-1 regression set**

Run:

```bash
uv run pytest \
  tests/commands/test_eval_entrypoint.py \
  tests/commands/test_eval_cmd.py \
  tests/evals/test_artifacts.py \
  tests/evals/test_contract_gap.py \
  tests/evals/test_discovery_runner.py \
  tests/evals/test_architecture.py \
  tests/evals/test_gold_score_runner.py \
  tests/evals/test_allocation_runner.py \
  tests/evals/test_trade_plan_runner.py \
  tests/evals/test_memo_runner.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run the full eval test suite**

Run:

```bash
uv run pytest tests/evals tests/commands/test_eval_cmd.py tests/commands/test_eval_entrypoint.py -q
```

Expected: PASS.

- [ ] **Step 3: Re-run the installed CLI against the real repo artifacts**

Run:

```bash
uv run irc eval research
uv run irc eval --all
```

Expected:

- `research` runs instead of raising `ModuleNotFoundError`;
- `news` and `queries` do **not** appear in the `--all` summary;
- dated stages write reports beside the artifact date they actually evaluated;
- remaining FAILs are truthful categories such as contract gaps, missing live artifacts, `triggers` unimplemented, or real architecture/product issues.

- [ ] **Step 4: Inspect the regenerated reports before planning Phase 2**

Run:

```bash
for f in outputs/*/evals/*/report.json; do
  echo "--- $f ---"
  jq '{stage, overall, notes, based_on, metrics: [.metrics[]? | {name, value, status}]}' "$f"
done
```

Expected: every non-PASS can be classified as one of:

1. real product/data issue,
2. metric contract gap,
3. intentionally unfinished active stage,
4. retained warning.

- [ ] **Step 5: Commit only if verification required a cleanup**

If verification exposed a small test/doc correction:

```bash
git add <touched-files>
git commit -m "test(evals): tighten phase-1 verification"
```

If no cleanup was needed, do not create an empty commit.

---

## Phase-2 handoff after this plan

After Task 9, create a **new** implementation plan from the regenerated reports. The most likely Phase-2 candidates are:

- redesign `gold_score`, `allocation`, `trade_plan`, and `memo` metrics for the live artifacts;
- correct `opportunity.same_theme_distinct_index_limit`;
- replace `scoring.score_distribution_stability` with a real distribution-stability measure;
- implement real `triggers` eval metrics;
- decide whether `queries` should persist artifacts and rejoin the active suite;
- address true product issues such as stale ingest data or the oversized `ingest_cmd.py`.
