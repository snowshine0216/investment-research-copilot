# Pipeline Required-Outputs Validation + Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `irc run` pipeline fail-fast when a stage exits `rc=0` but does not produce its required output artifacts, and add `irc run --resume` to pick up automatically from the last halted stage.

**Architecture:** Two new pure-data modules — `pipeline_outputs.py` (declarative manifest of required output files per stage + a pure check function) and `pipeline_state.py` (frozen dataclass + boundary-I/O for a persistent `outputs/<date>/.pipeline_state.json` file). `run_pipeline` is extended to (a) call the missing-output check after every successful stage, halting through the existing `HaltReason` sidecar path when artifacts are missing, and (b) accept a `resume: bool` parameter that reads the persisted state and derives `from_stage`. A new `--resume` flag is added to the `irc run` CLI subcommand. On full pipeline success, stale `PIPELINE_HALTED.md` and `.pipeline_state.json` are removed.

**Tech Stack:** Python 3.10+, click, pytest, pytest-mock; functional-style modules (frozen dataclasses, no module-level mutable state); existing `irc.io_utils.atomic_write_text` for durable writes; existing `irc.pipeline_halt.HaltReason` sidecar mechanism.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/irc/pipeline_outputs.py` | **NEW.** Declarative `STAGE_REQUIRED_OUTPUTS` manifest + pure `missing_outputs(out_dir, stage) -> tuple[str, ...]`. Memo special-cased: success if either `memo.md` or `memo_blocked.md` exists. |
| `src/irc/pipeline_state.py` | **NEW.** Frozen `PipelineState` dataclass + `write_state`, `read_state`, `clear_state` boundary helpers for `outputs/<date>/.pipeline_state.json`. |
| `src/irc/pipeline_halt.py` | Modified. Add `"missing_required_outputs"` entry to `_REMEDIATION_BY_KIND`. |
| `src/irc/commands/run_cmd.py` | Modified. Post-stage output check, persistent state write on halt, `resume: bool` parameter, state+halt-md cleanup on success. |
| `src/irc/cli.py` | Modified. Add `--resume` flag to `irc run`. |
| `tests/test_pipeline_outputs.py` | **NEW.** Unit tests for the pure check function. |
| `tests/test_pipeline_state.py` | **NEW.** Unit tests for the state I/O helpers. |
| `tests/commands/test_run_cmd.py` | Extended. Integration tests for output check + resume flow. |

---

### Task 1: Pure missing-outputs check module

**Files:**
- Create: `src/irc/pipeline_outputs.py`
- Test: `tests/test_pipeline_outputs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_outputs.py`:

```python
from __future__ import annotations
from pathlib import Path
import pytest
from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS, missing_outputs


def test_manifest_covers_all_writing_stages():
    # Ingest is intentionally excluded (covered by freshness check).
    # Research is intentionally excluded (optional, off by default).
    must_have = {"discover", "score", "gold", "allocate", "plan", "opportunity", "memo"}
    assert must_have.issubset(set(STAGE_REQUIRED_OUTPUTS.keys()))


def test_missing_outputs_returns_empty_when_all_present(tmp_path: Path):
    (tmp_path / "scoring.json").write_text("{}", encoding="utf-8")
    assert missing_outputs(tmp_path, "score") == ()


def test_missing_outputs_returns_missing_names(tmp_path: Path):
    # gold requires gold_regime.json AND gold_band.yaml
    (tmp_path / "gold_regime.json").write_text("{}", encoding="utf-8")
    result = missing_outputs(tmp_path, "gold")
    assert result == ("gold_band.yaml",)


def test_missing_outputs_returns_all_when_none_present(tmp_path: Path):
    result = missing_outputs(tmp_path, "opportunity")
    assert set(result) == {
        "opportunity_report.json",
        "thesis_cards.yaml",
        "discipline_report.md",
    }


def test_unknown_stage_returns_empty(tmp_path: Path):
    # Stages we deliberately don't validate (ingest, research) must not error.
    assert missing_outputs(tmp_path, "ingest") == ()
    assert missing_outputs(tmp_path, "research") == ()
    assert missing_outputs(tmp_path, "nonexistent") == ()


def test_memo_satisfied_by_memo_md(tmp_path: Path):
    (tmp_path / "memo.md").write_text("memo body", encoding="utf-8")
    assert missing_outputs(tmp_path, "memo") == ()


def test_memo_satisfied_by_memo_blocked_md(tmp_path: Path):
    # Audit-block is a valid memo outcome — do not flag as missing.
    (tmp_path / "memo_blocked.md").write_text("blocked body", encoding="utf-8")
    assert missing_outputs(tmp_path, "memo") == ()


def test_memo_flagged_when_neither_present(tmp_path: Path):
    result = missing_outputs(tmp_path, "memo")
    assert result == ("memo.md or memo_blocked.md",)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pipeline_outputs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.pipeline_outputs'`

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/pipeline_outputs.py`:

```python
from __future__ import annotations
from pathlib import Path


STAGE_REQUIRED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "discover":    ("discovered_watchlist.csv",),
    "score":       ("scoring.json",),
    "gold":        ("gold_regime.json", "gold_band.yaml"),
    "allocate":    ("proposed_allocation.yaml",),
    "plan":        ("trade_plan.yaml",),
    "opportunity": ("opportunity_report.json", "thesis_cards.yaml", "discipline_report.md"),
    "memo":        (),
}


def missing_outputs(out_dir: Path, stage: str) -> tuple[str, ...]:
    """Return the names of required outputs that do not yet exist in `out_dir`.

    Returns an empty tuple for stages not in the manifest (ingest, research,
    unknown stages) — those are validated by other mechanisms (freshness
    gates, opt-in flags) rather than file-existence.

    The `memo` stage is satisfied by either `memo.md` (audit pass) or
    `memo_blocked.md` (audit block). When neither exists, this returns the
    single literal token `"memo.md or memo_blocked.md"`.
    """
    if stage == "memo":
        if (out_dir / "memo.md").exists() or (out_dir / "memo_blocked.md").exists():
            return ()
        return ("memo.md or memo_blocked.md",)
    required = STAGE_REQUIRED_OUTPUTS.get(stage, ())
    return tuple(name for name in required if not (out_dir / name).exists())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pipeline_outputs.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Lint check**

Run: `.venv/bin/ruff check src/irc/pipeline_outputs.py tests/test_pipeline_outputs.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/pipeline_outputs.py tests/test_pipeline_outputs.py
git commit -m "feat(pipeline): add required-outputs manifest + missing_outputs check"
```

---

### Task 2: Persistent pipeline state module

**Files:**
- Create: `src/irc/pipeline_state.py`
- Test: `tests/test_pipeline_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_state.py`:

```python
from __future__ import annotations
from pathlib import Path
from irc.pipeline_state import (
    PipelineState,
    STATE_FILENAME,
    clear_state,
    read_state,
    write_state,
)


def test_state_file_name_constant():
    assert STATE_FILENAME == ".pipeline_state.json"


def test_write_then_read_round_trip(tmp_path: Path):
    state = PipelineState(
        status="halted",
        failed_stage="memo",
        halted_at="2026-05-20T10:36:44+08:00",
        reason_kind="missing_required_outputs",
    )
    write_state(tmp_path, state)

    loaded = read_state(tmp_path)
    assert loaded == state


def test_read_state_returns_none_when_absent(tmp_path: Path):
    assert read_state(tmp_path) is None


def test_read_state_returns_none_on_malformed_json(tmp_path: Path):
    (tmp_path / STATE_FILENAME).write_text("{not json", encoding="utf-8")
    assert read_state(tmp_path) is None


def test_read_state_returns_none_on_missing_keys(tmp_path: Path):
    (tmp_path / STATE_FILENAME).write_text('{"status": "halted"}', encoding="utf-8")
    assert read_state(tmp_path) is None


def test_clear_state_removes_file(tmp_path: Path):
    state = PipelineState(
        status="halted", failed_stage="score",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    )
    write_state(tmp_path, state)
    assert (tmp_path / STATE_FILENAME).exists()

    clear_state(tmp_path)
    assert not (tmp_path / STATE_FILENAME).exists()


def test_clear_state_is_idempotent(tmp_path: Path):
    clear_state(tmp_path)  # no file — must not raise
    clear_state(tmp_path)


def test_pipeline_state_is_frozen():
    state = PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    )
    import dataclasses
    assert dataclasses.is_dataclass(state)
    try:
        state.failed_stage = "score"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("PipelineState must be frozen")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pipeline_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.pipeline_state'`

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/pipeline_state.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
from irc.io_utils import atomic_write_text


STATE_FILENAME = ".pipeline_state.json"


@dataclass(frozen=True)
class PipelineState:
    status: str
    failed_stage: str
    halted_at: str
    reason_kind: str


def write_state(out_dir: Path, state: PipelineState) -> Path:
    """Persist `state` as JSON in `out_dir/.pipeline_state.json` and return the path."""
    path = out_dir / STATE_FILENAME
    atomic_write_text(path, json.dumps(asdict(state), ensure_ascii=False, indent=2))
    return path


def read_state(out_dir: Path) -> PipelineState | None:
    """Return the persisted state, or None if absent / malformed / missing keys."""
    path = out_dir / STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PipelineState(
            status=str(raw["status"]),
            failed_stage=str(raw["failed_stage"]),
            halted_at=str(raw["halted_at"]),
            reason_kind=str(raw["reason_kind"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def clear_state(out_dir: Path) -> None:
    """Remove the state file if it exists. Idempotent."""
    (out_dir / STATE_FILENAME).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pipeline_state.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Lint check**

Run: `.venv/bin/ruff check src/irc/pipeline_state.py tests/test_pipeline_state.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/pipeline_state.py tests/test_pipeline_state.py
git commit -m "feat(pipeline): add persistent .pipeline_state.json for resume"
```

---

### Task 3: Add remediation entry for missing-outputs halt kind

**Files:**
- Modify: `src/irc/pipeline_halt.py:65-83` (the `_REMEDIATION_BY_KIND` dict)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline_state.py` (or create a new short file `tests/test_pipeline_halt_remediation.py` — pick whichever exists; we'll use a new file to keep test scopes tidy):

Create `tests/test_pipeline_halt_remediation.py`:

```python
from __future__ import annotations
from pathlib import Path
from irc.pipeline_halt import HaltReason, write_halted_structured


def test_missing_required_outputs_remediation_mentions_files(tmp_path: Path):
    reason = HaltReason(
        kind="missing_required_outputs",
        stage="opportunity",
        detail="stage exited 0 but did not produce: opportunity_report.json",
        stats={},
        first_error=None,
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-20", reason=reason)
    body = (tmp_path / "outputs" / "2026-05-20" / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    # Remediation must reference the artifact contract, not the generic fallback.
    assert "did not produce" in body
    assert "opportunity_report.json" in body
    assert "irc opportunity" in body  # remediation points the user at the right rerun command
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline_halt_remediation.py -v`
Expected: FAIL — the generic fallback remediation is used; "irc opportunity" appears (via the generic template), but the assertion that the **specific** missing-outputs remediation runs requires a new entry. The detail is in the body but the wording check below will catch it.

Replace the assertion block above with a stricter wording check to make the failure unambiguous. Final test body:

```python
def test_missing_required_outputs_remediation_mentions_files(tmp_path: Path):
    reason = HaltReason(
        kind="missing_required_outputs",
        stage="opportunity",
        detail="stage exited 0 but did not produce: opportunity_report.json",
        stats={},
        first_error=None,
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-20", reason=reason)
    body = (tmp_path / "outputs" / "2026-05-20" / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "did not produce" in body
    assert "opportunity_report.json" in body
    # New, specific remediation language (added in this task):
    assert "expected output artifact(s) were not written" in body
```

Run: `.venv/bin/pytest tests/test_pipeline_halt_remediation.py -v`
Expected: FAIL — "expected output artifact(s) were not written" is not in the body yet.

- [ ] **Step 3: Add the new remediation entry**

Edit `src/irc/pipeline_halt.py`. Find the `_REMEDIATION_BY_KIND` dict (currently ends around line 83) and add a new entry **before** the closing `}`:

```python
    "missing_required_outputs": (
        "The stage exited with code 0 but the expected output artifact(s) "
        "were not written to `outputs/<today>/`. This usually indicates a "
        "silent failure inside the stage (e.g., an exception swallowed by "
        "a try/except, or a code path that returned 0 without producing "
        "results). Inspect the stage stdout above for warnings, then re-run "
        "`irc <stage> --repo-root .` after fixing. Once the stage produces "
        "its outputs, resume the pipeline with `irc run --resume`."
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline_halt_remediation.py -v`
Expected: PASS.

- [ ] **Step 5: Lint check**

Run: `.venv/bin/ruff check src/irc/pipeline_halt.py tests/test_pipeline_halt_remediation.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/pipeline_halt.py tests/test_pipeline_halt_remediation.py
git commit -m "feat(pipeline-halt): add remediation copy for missing_required_outputs kind"
```

---

### Task 4: Post-stage output validation in `run_pipeline`

**Files:**
- Modify: `src/irc/commands/run_cmd.py:44-93` (the body of `run_pipeline`)
- Test: `tests/commands/test_run_cmd.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/commands/test_run_cmd.py`:

```python
def test_pipeline_halts_when_stage_returns_zero_but_writes_no_outputs(tmp_path: Path):
    """A stage that returns rc=0 without producing its required outputs
    must halt the pipeline and write a halt reason explaining which artifacts
    were missing — this is the C1 regression class from the audit tracker."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    call_order: list[str] = []

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            call_order.append(stage)
            return 0  # success but writes nothing
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 1
    # Pipeline must halt at the first stage with required outputs that's missing them.
    # discover is the first such stage in STAGE_NAMES order; ingest (no required outputs)
    # and research (off by default) precede it.
    assert "discover" in call_order
    assert "score" not in call_order  # downstream stages must not run

    halt_md = (out_dir / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "missing_required_outputs" in halt_md
    assert "discovered_watchlist.csv" in halt_md


def test_pipeline_continues_when_stage_writes_required_outputs(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stub runners that "produce" their required outputs.
    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0


def test_pipeline_accepts_memo_blocked_as_memo_success(tmp_path: Path):
    """`memo_blocked.md` is the legitimate audit-block outcome — must not be flagged."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo_blocked.md").write_text("blocked", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_pipeline_halts_when_stage_returns_zero_but_writes_no_outputs tests/commands/test_run_cmd.py::test_pipeline_continues_when_stage_writes_required_outputs tests/commands/test_run_cmd.py::test_pipeline_accepts_memo_blocked_as_memo_success -v`
Expected: the first test FAILs (rc is 0, not 1 — output check not yet enforced); the others may pass coincidentally.

- [ ] **Step 3: Wire the output check into `run_pipeline`**

Edit `src/irc/commands/run_cmd.py`. Replace the entire body of `run_pipeline` (lines 44-93) with the version below, which adds the post-stage check. The diff vs. the current file is small — the new logic sits between "stage returned rc" and "if rc != 0".

Replace:

```python
def run_pipeline(repo_root: str, from_stage: str | None = None, only_stage: str | None = None) -> int:
    if only_stage is not None:
        if only_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{only_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        stages = [only_stage]
    elif from_stage is not None:
        if from_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{from_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        idx = STAGE_NAMES.index(from_stage)
        stages = list(STAGE_NAMES[idx:])
    else:
        stages = list(STAGE_NAMES)
    stages = _without_disabled_optional_stages(stages, from_stage, only_stage)
    total = len(stages)
    from irc.observability import stage_banner

    class _StageFailed(Exception):
        pass

    for index, stage in enumerate(stages, start=1):
        rc = 0
        try:
            with stage_banner(stage, index, total):
                fn = _runners_map()[stage]
                rc = fn(repo_root)
                if rc != 0:
                    raise _StageFailed(stage, rc)
        except _StageFailed:
            pass  # stage_banner already printed FAILED; rc is set correctly
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            today = _china_today()
            sidecar = Path(repo_root) / "outputs" / today / ".halt_reason.json"
            structured = HaltReason.read_sidecar(sidecar)
            if structured is not None:
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=structured)
                sidecar.unlink(missing_ok=True)
            else:
                write_halted(
                    repo_root=Path(repo_root), date=today, stage=stage,
                    reason=f"stage exit code {rc}",
                    remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
                )
            return rc
    print(f"pipeline OK: ran {stages}")
    return 0
```

With:

```python
def run_pipeline(repo_root: str, from_stage: str | None = None, only_stage: str | None = None) -> int:
    if only_stage is not None:
        if only_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{only_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        stages = [only_stage]
    elif from_stage is not None:
        if from_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{from_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        idx = STAGE_NAMES.index(from_stage)
        stages = list(STAGE_NAMES[idx:])
    else:
        stages = list(STAGE_NAMES)
    stages = _without_disabled_optional_stages(stages, from_stage, only_stage)
    total = len(stages)
    from irc.observability import stage_banner
    from irc.pipeline_outputs import missing_outputs

    class _StageFailed(Exception):
        pass

    today = _china_today()
    out_dir = Path(repo_root) / "outputs" / today

    for index, stage in enumerate(stages, start=1):
        rc = 0
        try:
            with stage_banner(stage, index, total):
                fn = _runners_map()[stage]
                rc = fn(repo_root)
                if rc != 0:
                    raise _StageFailed(stage, rc)
        except _StageFailed:
            pass  # stage_banner already printed FAILED; rc is set correctly
        if rc == 0:
            missing = missing_outputs(out_dir, stage)
            if missing:
                from irc.pipeline_halt import HaltReason
                sidecar = out_dir / ".halt_reason.json"
                HaltReason.write_sidecar(sidecar, HaltReason(
                    kind="missing_required_outputs",
                    stage=stage,
                    detail=(
                        f"stage exited 0 but did not produce: "
                        f"{', '.join(missing)}"
                    ),
                    stats={"missing_count": len(missing)},
                    first_error=None,
                ))
                rc = 1
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            sidecar = out_dir / ".halt_reason.json"
            structured = HaltReason.read_sidecar(sidecar)
            if structured is not None:
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=structured)
                sidecar.unlink(missing_ok=True)
            else:
                write_halted(
                    repo_root=Path(repo_root), date=today, stage=stage,
                    reason=f"stage exit code {rc}",
                    remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
                )
            return rc
    print(f"pipeline OK: ran {stages}")
    return 0
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_pipeline_halts_when_stage_returns_zero_but_writes_no_outputs tests/commands/test_run_cmd.py::test_pipeline_continues_when_stage_writes_required_outputs tests/commands/test_run_cmd.py::test_pipeline_accepts_memo_blocked_as_memo_success -v`
Expected: all 3 PASS.

- [ ] **Step 5: Run the full `test_run_cmd.py` to make sure existing tests still pass**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py -v`
Expected: all tests PASS (existing + new).

- [ ] **Step 6: Lint check**

Run: `.venv/bin/ruff check src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py
git commit -m "feat(pipeline): fail-fast when stage exits 0 but writes no required outputs"
```

---

### Task 5: Persist `.pipeline_state.json` on halt; clear on success

**Files:**
- Modify: `src/irc/commands/run_cmd.py` (extend the halt path + success path)
- Test: `tests/commands/test_run_cmd.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/commands/test_run_cmd.py`:

```python
def test_halt_writes_pipeline_state_file(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today

    def fail_score(_repo_root: str) -> int:
        return 1

    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["score"] = fail_score
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="score")

    assert rc == 1
    from irc.pipeline_state import read_state
    state = read_state(out_dir)
    assert state is not None
    assert state.status == "halted"
    assert state.failed_stage == "score"
    assert state.reason_kind  # some non-empty string


def test_successful_pipeline_clears_state_and_halt_markdown(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pre-seed stale halt + state files from a hypothetical prior run.
    (out_dir / "PIPELINE_HALTED.md").write_text("stale", encoding="utf-8")
    from irc.pipeline_state import PipelineState, STATE_FILENAME, write_state
    write_state(out_dir, PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    ))

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0
    assert not (out_dir / STATE_FILENAME).exists()
    assert not (out_dir / "PIPELINE_HALTED.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_halt_writes_pipeline_state_file tests/commands/test_run_cmd.py::test_successful_pipeline_clears_state_and_halt_markdown -v`
Expected: both FAIL — state file not written yet; success path does not clean up.

- [ ] **Step 3: Update `run_pipeline` to write state on halt and clear on success**

Edit `src/irc/commands/run_cmd.py`. State-module imports stay local to the branches that use them (matches the existing pattern for `pipeline_halt` imports). `datetime`/`timezone`/`timedelta` are already imported at module-top (line 3) and don't need re-importing. Make two changes:

**Change 3a** — in the halt branch, **after** writing the halt markdown and **before** `return rc`, add the state write. Replace the structured-branch and generic-branch tails so both record a `reason_kind` and then write state.

Locate (after Task 4's changes):

```python
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            sidecar = out_dir / ".halt_reason.json"
            structured = HaltReason.read_sidecar(sidecar)
            if structured is not None:
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=structured)
                sidecar.unlink(missing_ok=True)
            else:
                write_halted(
                    repo_root=Path(repo_root), date=today, stage=stage,
                    reason=f"stage exit code {rc}",
                    remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
                )
            return rc
```

Replace with:

```python
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            from irc.pipeline_state import PipelineState, write_state
            sidecar = out_dir / ".halt_reason.json"
            structured = HaltReason.read_sidecar(sidecar)
            if structured is not None:
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=structured)
                sidecar.unlink(missing_ok=True)
                reason_kind = structured.kind
            else:
                write_halted(
                    repo_root=Path(repo_root), date=today, stage=stage,
                    reason=f"stage exit code {rc}",
                    remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
                )
                reason_kind = "generic"
            write_state(out_dir, PipelineState(
                status="halted",
                failed_stage=stage,
                halted_at=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                reason_kind=reason_kind,
            ))
            return rc
```

**Change 3b** — in the success branch, replace:

```python
    print(f"pipeline OK: ran {stages}")
    return 0
```

With:

```python
    from irc.pipeline_state import clear_state
    clear_state(out_dir)
    (out_dir / "PIPELINE_HALTED.md").unlink(missing_ok=True)
    print(f"pipeline OK: ran {stages}")
    return 0
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_halt_writes_pipeline_state_file tests/commands/test_run_cmd.py::test_successful_pipeline_clears_state_and_halt_markdown -v`
Expected: both PASS.

- [ ] **Step 5: Run the full `test_run_cmd.py` to confirm no regressions**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Lint check**

Run: `.venv/bin/ruff check src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py
git commit -m "feat(pipeline): persist .pipeline_state.json on halt; clear on success"
```

---

### Task 6: `resume=True` parameter in `run_pipeline`

**Files:**
- Modify: `src/irc/commands/run_cmd.py` (extend `run_pipeline` signature + entry logic)
- Test: `tests/commands/test_run_cmd.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/commands/test_run_cmd.py`:

```python
def test_resume_with_no_state_file_returns_error(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), resume=True)
    assert rc == 1


def test_resume_rejects_combined_from_stage(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), from_stage="memo", resume=True)
    assert rc == 1


def test_resume_rejects_combined_only_stage(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), only_stage="memo", resume=True)
    assert rc == 1


def test_resume_derives_from_stage_from_state_file(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    from irc.pipeline_state import PipelineState, write_state
    write_state(out_dir, PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    ))

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS
    called: list[str] = []

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            called.append(stage)
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), resume=True)

    assert rc == 0
    # Resume must start at the recorded failed_stage and run only downstream stages.
    # `memo` is the last stage, so only it should have run.
    assert called == ["memo"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py -k "resume" -v`
Expected: all 4 new tests FAIL with `TypeError: run_pipeline() got an unexpected keyword argument 'resume'`.

- [ ] **Step 3: Add `resume` parameter to `run_pipeline`**

Edit `src/irc/commands/run_cmd.py`. Change the function signature and add the resume-resolution block **before** the existing stage-selection logic.

Replace:

```python
def run_pipeline(repo_root: str, from_stage: str | None = None, only_stage: str | None = None) -> int:
    if only_stage is not None:
```

With:

```python
def run_pipeline(
    repo_root: str,
    from_stage: str | None = None,
    only_stage: str | None = None,
    resume: bool = False,
) -> int:
    if resume:
        if from_stage is not None or only_stage is not None:
            print("ERROR: --resume cannot be combined with --from or --only.")
            return 1
        from irc.pipeline_state import read_state
        today = _china_today()
        out_dir = Path(repo_root) / "outputs" / today
        state = read_state(out_dir)
        if state is None:
            print(
                f"ERROR: no halted pipeline state found for {today}; "
                f"nothing to resume. Run `irc run --repo-root {repo_root}` to start a new pipeline."
            )
            return 1
        if state.failed_stage not in STAGE_NAMES:
            print(
                f"ERROR: state file references unknown stage '{state.failed_stage}'. "
                f"Delete `outputs/{today}/.pipeline_state.json` and start over."
            )
            return 1
        from_stage = state.failed_stage
        print(
            f"resuming from stage '{from_stage}' (halted at {state.halted_at}, "
            f"reason: {state.reason_kind})"
        )
    if only_stage is not None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py -k "resume" -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Run full test suite for `test_run_cmd.py`**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Lint check**

Run: `.venv/bin/ruff check src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py
git commit -m "feat(pipeline): add resume=True to run_pipeline (reads .pipeline_state.json)"
```

---

### Task 7: `--resume` CLI flag on `irc run`

**Files:**
- Modify: `src/irc/cli.py:70-77` (the `run_command` definition)
- Test: add a CLI-level test using `click.testing.CliRunner`

- [ ] **Step 1: Write the failing test**

Append to `tests/commands/test_run_cmd.py`:

```python
def test_cli_run_resume_flag_invokes_run_pipeline_with_resume_true(tmp_path: Path):
    """The CLI must pass `resume=True` through to run_pipeline when --resume is given."""
    from click.testing import CliRunner
    from irc.cli import main

    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_pipeline(repo_root, from_stage=None, only_stage=None, resume=False):
        captured["repo_root"] = repo_root
        captured["from_stage"] = from_stage
        captured["only_stage"] = only_stage
        captured["resume"] = resume
        return 0

    with patch("irc.commands.run_cmd.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(main, ["run", "--repo-root", str(tmp_path), "--resume"])

    assert result.exit_code == 0
    assert captured["resume"] is True
    assert captured["from_stage"] is None
    assert captured["only_stage"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_cli_run_resume_flag_invokes_run_pipeline_with_resume_true -v`
Expected: FAIL — `--resume` is not yet a click option, so click emits `Error: No such option: --resume`.

- [ ] **Step 3: Add the `--resume` click option**

Edit `src/irc/cli.py`. Replace:

```python
@main.command(name="run", help="Run the default pipeline; include research when RESEARCH_ENABLED=true.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--from", "from_stage", type=str, default=None, help="Resume from this stage.")
@click.option("--only", "only_stage", type=str, default=None, help="Run only this stage.")
def run_command(repo_root: str, from_stage: str | None, only_stage: str | None) -> None:
    from irc.commands.run_cmd import run_pipeline
    rc = run_pipeline(repo_root=repo_root, from_stage=from_stage, only_stage=only_stage)
    raise SystemExit(rc)
```

With:

```python
@main.command(name="run", help="Run the default pipeline; include research when RESEARCH_ENABLED=true.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--from", "from_stage", type=str, default=None, help="Resume from this stage.")
@click.option("--only", "only_stage", type=str, default=None, help="Run only this stage.")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from the stage that halted in the most recent failed run (today only).")
def run_command(repo_root: str, from_stage: str | None, only_stage: str | None, resume: bool) -> None:
    from irc.commands.run_cmd import run_pipeline
    rc = run_pipeline(repo_root=repo_root, from_stage=from_stage, only_stage=only_stage, resume=resume)
    raise SystemExit(rc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_cli_run_resume_flag_invokes_run_pipeline_with_resume_true -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `.venv/bin/pytest tests/commands/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Manual smoke-test (CLI help)**

Run: `.venv/bin/irc run --help`
Expected: output contains `--resume` with the help string.

- [ ] **Step 7: Lint check**

Run: `.venv/bin/ruff check src/irc/cli.py tests/commands/test_run_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add src/irc/cli.py tests/commands/test_run_cmd.py
git commit -m "feat(cli): add --resume flag to \`irc run\`"
```

---

### Task 8: Final integration test + documentation note

**Files:**
- Modify: `tests/commands/test_run_cmd.py` (one end-to-end test)
- Modify: `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` (mark this enhancement)

- [ ] **Step 1: Write the end-to-end integration test**

Append to `tests/commands/test_run_cmd.py`:

```python
def test_end_to_end_halt_then_resume_recovers_pipeline(tmp_path: Path):
    """Simulate the C1 failure mode: stage X returns 0 but writes no outputs.
    Pipeline halts; a follow-up `--resume` after the stage is "fixed" picks up
    from X and completes."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    # Phase 1: opportunity returns 0 but writes nothing -> halt.
    def runner_broken(stage: str):
        def _run(_repo_root: str) -> int:
            if stage == "opportunity":
                return 0  # silent failure: no outputs written
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            return 0
        return _run

    runners_broken = {s: runner_broken(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners_broken):
        rc1 = run_pipeline(str(tmp_path))
    assert rc1 == 1

    from irc.pipeline_state import STATE_FILENAME, read_state
    state = read_state(out_dir)
    assert state is not None and state.failed_stage == "opportunity"
    assert (out_dir / "PIPELINE_HALTED.md").exists()

    # Phase 2: "fix" opportunity -> resume.
    def runner_fixed(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners_fixed = {s: runner_fixed(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners_fixed):
        rc2 = run_pipeline(str(tmp_path), resume=True)
    assert rc2 == 0
    assert not (out_dir / STATE_FILENAME).exists()
    assert not (out_dir / "PIPELINE_HALTED.md").exists()
    assert (out_dir / "opportunity_report.json").exists()
    assert (out_dir / "memo.md").exists()
```

- [ ] **Step 2: Run the integration test**

Run: `.venv/bin/pytest tests/commands/test_run_cmd.py::test_end_to_end_halt_then_resume_recovers_pipeline -v`
Expected: PASS.

- [ ] **Step 3: Run the full test suite for one last regression check**

Run: `.venv/bin/pytest -v`
Expected: all previously-passing tests still PASS. New tests all PASS.

- [ ] **Step 4: Update `AUDIT_FIXES_TRACKER.md` to mention the new safety net**

Edit `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md`. Under the "Current status snapshot" → "Done now" section, append one line at the end of that bullet list:

```markdown
- **Pipeline safety**: `irc run` now fails fast when a stage exits `rc=0` without producing its required outputs, and `irc run --resume` picks up from the halted stage automatically (state stored in `outputs/<date>/.pipeline_state.json`).
```

- [ ] **Step 5: Lint check (whole module surface)**

Run: `.venv/bin/ruff check src/irc/pipeline_outputs.py src/irc/pipeline_state.py src/irc/pipeline_halt.py src/irc/commands/run_cmd.py src/irc/cli.py tests/test_pipeline_outputs.py tests/test_pipeline_state.py tests/test_pipeline_halt_remediation.py tests/commands/test_run_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add tests/commands/test_run_cmd.py outputs/2026-05-20/AUDIT_FIXES_TRACKER.md
git commit -m "test(pipeline): end-to-end halt-then-resume regression; tracker note"
```

---

## Verification commands

After all 8 tasks land, the following should all succeed:

```bash
.venv/bin/pytest tests/test_pipeline_outputs.py tests/test_pipeline_state.py tests/test_pipeline_halt_remediation.py tests/commands/test_run_cmd.py -v
.venv/bin/ruff check src/irc/pipeline_outputs.py src/irc/pipeline_state.py src/irc/pipeline_halt.py src/irc/commands/run_cmd.py src/irc/cli.py
.venv/bin/irc run --help | grep -- --resume
```

And the CLI demo:

```bash
# Simulate the C1 regression by removing opportunity_report.json from today's outputs and re-running.
rm -f outputs/$(date -u +%Y-%m-%d)/opportunity_report.json
.venv/bin/irc run --repo-root .
# Expected: pipeline halts at opportunity with kind=missing_required_outputs.
# Inspect PIPELINE_HALTED.md, fix the underlying stage, then:
.venv/bin/irc run --resume --repo-root .
# Expected: pipeline resumes from opportunity and runs through to memo.
```
