# P0 Ingest Halt Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic "stage exit code 1" halt message with a preflight canary plus a structured `HaltReason` payload, so an ingest failure reports its `kind`, per-source stats, and a truncated `first_error` in one read.

**Architecture:** A new `HaltReason` dataclass + sidecar JSON file (`outputs/<date>/.halt_reason.json`) acts as an in-process hand-off between `run_ingest` (which detects the failure) and `run_pipeline` (which writes `PIPELINE_HALTED.md`). `_ingest_preflight()` runs one cheap akshare call before the main fetch loop; if it raises a transient network error, the run halts immediately instead of burning the retry budget. The existing `write_halted()` keeps its 5-arg signature for back-compat; a new `write_halted_structured()` renders the richer markdown.

**Tech Stack:** Python 3.11, dataclasses, pytest, `unittest.mock.patch`, `tmp_path`. Reuse the existing `_is_transient_network_error` classifier from `src/irc/data/akshare_client.py:76-101`.

**Reference spec:** `docs/superpowers/specs/2026-05-17-ingest-halt-diagnostics-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/irc/pipeline_halt.py` | Halt artifact rendering + `HaltReason` dataclass + sidecar JSON serde | Modify |
| `src/irc/commands/ingest_cmd.py` | Add `_ingest_preflight`, write sidecar on failure paths, stale-guard on entry | Modify |
| `src/irc/commands/run_cmd.py` | After rc != 0, consume sidecar JSON if present | Modify |
| `tests/test_pipeline_halt.py` | Cover `HaltReason` round-trip + structured rendering | Modify |
| `tests/commands/test_ingest_cmd.py` | Cover preflight halt + post-ingest halt sidecar | Modify |
| `tests/commands/test_run_cmd.py` | Cover sidecar consumption + legacy fallback | Modify |

Total: 3 source files, 3 test files, no new files.

---

## Task 1: `HaltReason` dataclass + JSON serde

**Files:**
- Modify: `src/irc/pipeline_halt.py`
- Test: `tests/test_pipeline_halt.py`

### Step 1.1: Write the failing test for HaltReason round-trip
- [ ] Add to `tests/test_pipeline_halt.py`:

```python
from irc.pipeline_halt import HaltReason


def test_halt_reason_round_trips_through_sidecar(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_empty",
        stage="ingest",
        detail="every fetch returned 0 rows",
        stats={"price_attempts": 198, "price_successes": 0,
               "nav_attempts": 50, "nav_successes": 0},
        first_error="requests.ConnectionError: HTTPSConnectionPool(...): Max retries exceeded",
    )
    sidecar = tmp_path / ".halt_reason.json"
    HaltReason.write_sidecar(sidecar, reason)
    loaded = HaltReason.read_sidecar(sidecar)
    assert loaded == reason


def test_halt_reason_read_sidecar_returns_none_when_missing(tmp_path: Path):
    assert HaltReason.read_sidecar(tmp_path / "missing.json") is None


def test_halt_reason_read_sidecar_returns_none_on_corrupt_json(tmp_path: Path):
    sidecar = tmp_path / ".halt_reason.json"
    sidecar.write_text("{not valid json", encoding="utf-8")
    assert HaltReason.read_sidecar(sidecar) is None


def test_halt_reason_truncates_first_error():
    long_msg = "x" * 1000
    reason = HaltReason(kind="akshare_unreachable", stage="ingest",
                        detail="preflight failed", first_error=long_msg)
    assert reason.first_error is not None
    assert len(reason.first_error) <= 500
```

### Step 1.2: Run tests to verify they fail
- [ ] Run: `pytest tests/test_pipeline_halt.py -v`
- [ ] Expected: 4 FAILs with `ImportError: cannot import name 'HaltReason'`

### Step 1.3: Add the dataclass + serde to `pipeline_halt.py`
- [ ] Replace the current content of `src/irc/pipeline_halt.py` with:

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from typing import Mapping
from irc.io_utils import atomic_write_text

_MAX_FIRST_ERROR_CHARS = 500


@dataclass(frozen=True)
class HaltReason:
    kind: str
    stage: str
    detail: str
    stats: Mapping[str, int] = field(default_factory=dict)
    first_error: str | None = None

    def __post_init__(self) -> None:
        if self.first_error is not None and len(self.first_error) > _MAX_FIRST_ERROR_CHARS:
            object.__setattr__(self, "first_error",
                               self.first_error[:_MAX_FIRST_ERROR_CHARS])

    @staticmethod
    def write_sidecar(path: Path, reason: "HaltReason") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(reason)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    @staticmethod
    def read_sidecar(path: Path) -> "HaltReason | None":
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return HaltReason(
                kind=str(raw["kind"]),
                stage=str(raw["stage"]),
                detail=str(raw["detail"]),
                stats=dict(raw.get("stats") or {}),
                first_error=raw.get("first_error"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


def write_halted(
    repo_root: Path, date: str, stage: str, reason: str, remediation: str,
) -> Path:
    out_dir = repo_root / "outputs" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Pipeline Halted — {date}\n\n"
        f"**Stopped at stage:** `{stage}`\n\n"
        f"**Reason:** {reason}\n\n"
        f"**Remediation:**\n{remediation}\n\n"
        f"**Generated at:** {datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "PIPELINE_HALTED.md"
    atomic_write_text(path, body)
    return path
```

### Step 1.4: Run tests to verify they pass
- [ ] Run: `pytest tests/test_pipeline_halt.py -v`
- [ ] Expected: 4 new tests PASS, existing `test_write_halted_creates_md` still PASSes.

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/pipeline_halt.py tests/test_pipeline_halt.py
git commit -m "feat(pipeline-halt): add HaltReason dataclass with sidecar JSON serde"
```

---

## Task 2: `write_halted_structured` renders the richer markdown

**Files:**
- Modify: `src/irc/pipeline_halt.py`
- Test: `tests/test_pipeline_halt.py`

### Step 2.1: Write the failing test for structured rendering
- [ ] Add to `tests/test_pipeline_halt.py`:

```python
from irc.pipeline_halt import write_halted_structured


def test_write_halted_structured_renders_all_fields(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_empty",
        stage="ingest",
        detail="every akshare fetch returned 0 rows",
        stats={"price_attempts": 198, "price_successes": 0,
               "nav_attempts": 50, "nav_successes": 0},
        first_error="requests.ConnectionError: Max retries exceeded with url: ...",
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "ingest" in body
    assert "akshare_empty" in body
    assert "every akshare fetch returned 0 rows" in body
    assert "price_attempts" in body and "198" in body
    assert "price_successes" in body and "0" in body
    assert "requests.ConnectionError" in body
    assert "Diagnostics" in body


def test_write_halted_structured_omits_stats_section_when_empty(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_unreachable", stage="ingest",
        detail="preflight canary failed",
        first_error="ConnectionResetError: [Errno 54] Connection reset by peer",
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "akshare_unreachable" in body
    assert "preflight canary failed" in body
    assert "ConnectionResetError" in body
    assert "| Metric | Value |" not in body  # no stats table


def test_write_halted_structured_includes_remediation_for_known_kind(tmp_path: Path):
    reason = HaltReason(kind="akshare_unreachable", stage="ingest",
                        detail="preflight canary failed")
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "network" in body.lower() or "connectivity" in body.lower()
```

### Step 2.2: Run tests to verify they fail
- [ ] Run: `pytest tests/test_pipeline_halt.py::test_write_halted_structured_renders_all_fields -v`
- [ ] Expected: FAIL with `ImportError: cannot import name 'write_halted_structured'`

### Step 2.3: Add `write_halted_structured` + remediation map
- [ ] Append to `src/irc/pipeline_halt.py`:

```python
_REMEDIATION_BY_KIND: dict[str, str] = {
    "akshare_unreachable": (
        "Akshare/EastMoney was unreachable during the preflight network "
        "check. Verify outbound connectivity to push2.eastmoney.com and "
        "fund.eastmoney.com (e.g., `curl -I https://push2.eastmoney.com`), "
        "then re-run `irc ingest --repo-root .`."
    ),
    "akshare_empty": (
        "Every akshare fetch attempt failed (see the Diagnostics section "
        "for per-source attempt/success counts and the first error). "
        "Inspect the stage stdout for the per-instrument failure pattern, "
        "then re-run `irc ingest --repo-root .` after the upstream is healthy."
    ),
    "akshare_error": (
        "The akshare preflight call raised a non-network error (likely a "
        "schema change or upstream API change). Re-run with `DEBUG=1 irc "
        "ingest --repo-root .` to capture the full traceback."
    ),
    "preflight_unexpected": (
        "The ingest preflight crashed with an unexpected exception type. "
        "Re-run with `DEBUG=1 irc ingest --repo-root .` to capture the "
        "traceback and report the failure mode."
    ),
}


def _render_stats_table(stats: Mapping[str, int]) -> str:
    if not stats:
        return ""
    lines = ["| Metric | Value |", "|---|---:|"]
    for key, value in stats.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _render_diagnostics(reason: HaltReason) -> str:
    parts = [
        "## Diagnostics\n",
        f"- **kind:** `{reason.kind}`",
        f"- **detail:** {reason.detail}",
    ]
    stats_table = _render_stats_table(reason.stats)
    if stats_table:
        parts.append("\n" + stats_table)
    if reason.first_error:
        parts.append("\n**First error:**\n\n```\n" + reason.first_error + "\n```")
    return "\n".join(parts) + "\n"


def write_halted_structured(
    repo_root: Path, date: str, reason: HaltReason,
) -> Path:
    out_dir = repo_root / "outputs" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    remediation = _REMEDIATION_BY_KIND.get(
        reason.kind,
        f"Inspect the stage output and re-run `irc {reason.stage} "
        f"--repo-root .` after fixing.",
    )
    body = (
        f"# Pipeline Halted — {date}\n\n"
        f"**Stopped at stage:** `{reason.stage}`\n\n"
        f"**Reason:** {reason.kind} — {reason.detail}\n\n"
        f"**Remediation:**\n{remediation}\n\n"
        f"{_render_diagnostics(reason)}\n"
        f"**Generated at:** {datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "PIPELINE_HALTED.md"
    atomic_write_text(path, body)
    return path
```

### Step 2.4: Run tests to verify they pass
- [ ] Run: `pytest tests/test_pipeline_halt.py -v`
- [ ] Expected: all 8 tests PASS.

### Step 2.5: Commit
- [ ] Run:

```bash
git add src/irc/pipeline_halt.py tests/test_pipeline_halt.py
git commit -m "feat(pipeline-halt): render structured HaltReason as markdown with diagnostics"
```

---

## Task 3: `_ingest_preflight()` helper

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py`
- Test: `tests/commands/test_ingest_cmd.py`

### Step 3.1: Write the failing tests for the preflight helper
- [ ] Add to `tests/commands/test_ingest_cmd.py`:

```python
from irc.commands.ingest_cmd import _ingest_preflight
from irc.pipeline_halt import HaltReason


def test_preflight_returns_none_on_success(monkeypatch):
    monkeypatch.setattr(
        "irc.commands.ingest_cmd._preflight_call",
        lambda: None,
    )
    assert _ingest_preflight() is None


def test_preflight_returns_unreachable_on_transient_error(monkeypatch):
    def boom() -> None:
        raise ConnectionResetError("[Errno 54] Connection reset by peer")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    reason = _ingest_preflight()
    assert isinstance(reason, HaltReason)
    assert reason.kind == "akshare_unreachable"
    assert reason.stage == "ingest"
    assert "Connection reset" in (reason.first_error or "")


def test_preflight_returns_error_on_non_transient_exception(monkeypatch):
    def boom() -> None:
        raise ValueError("unexpected schema: missing column 'nav'")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    reason = _ingest_preflight()
    assert isinstance(reason, HaltReason)
    assert reason.kind == "akshare_error"
    assert "unexpected schema" in (reason.first_error or "")


def test_preflight_returns_unexpected_on_baseexception(monkeypatch):
    def boom() -> None:
        raise KeyboardInterrupt()
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    # KeyboardInterrupt should NOT be caught — it must propagate.
    import pytest
    with pytest.raises(KeyboardInterrupt):
        _ingest_preflight()
```

### Step 3.2: Run tests to verify they fail
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py -k preflight -v`
- [ ] Expected: 4 FAILs with `ImportError: cannot import name '_ingest_preflight'`

### Step 3.3: Implement the preflight helper
- [ ] In `src/irc/commands/ingest_cmd.py`, add near the top of the module (after existing imports — add `from irc.pipeline_halt import HaltReason` and `from irc.data.akshare_client import _is_transient_network_error, fetch_fund_nav_history` if not already imported):

```python
def _preflight_call() -> None:
    """One cheap akshare call exercising the HTTP pathway. Overridable in tests.

    Uses 510300 (CSI300 ETF) as the canary symbol — it is one of the oldest
    and most stable funds, so a successful return implies broad akshare
    reachability. We discard the returned frame; only the network outcome
    matters here.
    """
    fetch_fund_nav_history("510300")


def _ingest_preflight() -> HaltReason | None:
    """Run the preflight canary. Returns a HaltReason on failure, None on success.

    KeyboardInterrupt and SystemExit propagate (BaseException, not Exception).
    """
    try:
        _preflight_call()
        return None
    except Exception as exc:  # noqa: BLE001 — we re-classify below
        first_error = f"{type(exc).__name__}: {exc}"
        if _is_transient_network_error(exc):
            return HaltReason(
                kind="akshare_unreachable",
                stage="ingest",
                detail="preflight canary failed with a transient network error",
                first_error=first_error,
            )
        return HaltReason(
            kind="akshare_error",
            stage="ingest",
            detail="preflight canary raised a non-network exception",
            first_error=first_error,
        )
```

### Step 3.4: Run tests to verify they pass
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py -k preflight -v`
- [ ] Expected: 4 PASS.

### Step 3.5: Commit
- [ ] Run:

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_cmd.py
git commit -m "feat(ingest): add _ingest_preflight canary with HaltReason classification"
```

---

## Task 4: Wire preflight + post-ingest sidecar into `run_ingest`

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py:371` (top of `run_ingest`) and `:524-536` (existing 0-success guard)
- Test: `tests/commands/test_ingest_cmd.py`

### Step 4.1: Write the failing tests for the sidecar writes
- [ ] Add to `tests/commands/test_ingest_cmd.py`:

```python
def test_run_ingest_preflight_failure_writes_sidecar(repo: Path, monkeypatch):
    def boom() -> None:
        raise ConnectionResetError("[Errno 54] Connection reset by peer")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)

    rc = run_ingest(str(repo))

    assert rc == 1
    sidecar = repo / "outputs" / date.today().isoformat() / ".halt_reason.json"
    assert sidecar.exists()
    reason = HaltReason.read_sidecar(sidecar)
    assert reason is not None
    assert reason.kind == "akshare_unreachable"
    assert reason.stage == "ingest"


def test_run_ingest_preflight_clears_stale_sidecar(repo: Path, monkeypatch):
    today = date.today().isoformat()
    out_dir = repo / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / ".halt_reason.json"
    stale.write_text('{"kind":"old","stage":"ingest","detail":"old run"}',
                     encoding="utf-8")

    # Successful preflight, then short-circuit the rest by raising in a place
    # that returns rc=1 cleanly. Easiest: monkeypatch load_repo_configs to
    # signal a fake-but-bounded failure so we exit early after the stale guard
    # has run.
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", lambda: None)
    monkeypatch.setattr(
        "irc.commands.ingest_cmd.load_repo_configs",
        lambda root: (_ for _ in ()).throw(RuntimeError("stop early")),
    )
    import pytest
    with pytest.raises(RuntimeError):
        run_ingest(str(repo))

    assert not stale.exists(), "stale sidecar must be deleted on entry"
```

### Step 4.2: Run tests to verify they fail
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py -k "preflight_failure_writes_sidecar or preflight_clears_stale" -v`
- [ ] Expected: both FAIL — the sidecar isn't written / the stale file isn't deleted.

### Step 4.3: Wire the preflight + stale guard at the top of `run_ingest`
- [ ] In `src/irc/commands/ingest_cmd.py`, modify `run_ingest(repo_root: str) -> int` to start with:

```python
def run_ingest(repo_root: str) -> int:
    root = Path(repo_root)
    # Stale-guard: remove any sidecar from a prior run for today.
    today_iso = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    sidecar_path = root / "outputs" / today_iso / ".halt_reason.json"
    if sidecar_path.exists():
        sidecar_path.unlink()

    # Preflight: one cheap akshare call to fail fast on outages.
    preflight = _ingest_preflight()
    if preflight is not None:
        HaltReason.write_sidecar(sidecar_path, preflight)
        print(f"ERROR: ingest preflight failed: {preflight.kind} — {preflight.detail}")
        return 1

    bundle = load_repo_configs(root)
    # ... rest of run_ingest unchanged ...
```

Make sure `datetime, timezone, timedelta` are imported at the top of `ingest_cmd.py` (they may already be).

### Step 4.4: Run the new tests
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py -k "preflight_failure_writes_sidecar or preflight_clears_stale" -v`
- [ ] Expected: both PASS.

### Step 4.5: Write the failing test for the post-ingest 0-success sidecar
- [ ] Add to `tests/commands/test_ingest_cmd.py`:

```python
def test_run_ingest_zero_success_writes_sidecar(repo: Path, monkeypatch):
    """When every price fetch fails, ingest must write a structured sidecar.

    Ingest calls `fetch_etf_price_history` per instrument (ingest_cmd.py:421)
    and `fetch_fund_nav_history` per fund (ingest_cmd.py:498). Both are
    imported into `irc.commands.ingest_cmd` at module load, so we patch the
    local bindings to force every attempt to fail transiently. The preflight
    is also patched to a no-op so it doesn't short-circuit the run.
    """
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", lambda: None)

    def fail_price(*_a, **_kw):
        raise ConnectionResetError("simulated outage (price)")
    def fail_nav(*_a, **_kw):
        raise ConnectionResetError("simulated outage (nav)")

    monkeypatch.setattr("irc.commands.ingest_cmd.fetch_etf_price_history", fail_price)
    monkeypatch.setattr("irc.commands.ingest_cmd.fetch_fund_nav_history", fail_nav)

    rc = run_ingest(str(repo))

    assert rc == 1
    sidecar = repo / "outputs" / date.today().isoformat() / ".halt_reason.json"
    assert sidecar.exists()
    reason = HaltReason.read_sidecar(sidecar)
    assert reason is not None
    assert reason.kind == "akshare_empty"
    assert reason.stats.get("price_attempts", 0) > 0
    assert reason.stats.get("price_successes", -1) == 0
    assert reason.first_error  # non-empty
```

### Step 4.6: Run the new test to verify it fails
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py::test_run_ingest_zero_success_writes_sidecar -v`
- [ ] Expected: FAIL — sidecar not written by the existing 0-success guard.

### Step 4.7: Extend the 0-success guard to write the sidecar
- [ ] In `src/irc/commands/ingest_cmd.py`, replace the existing block at lines 524-536:

```python
    fatal_failures: list[str] = []
    if price_attempts and price_successes == 0:
        fatal_failures.append("prices")
    if nav_attempts and nav_successes == 0:
        fatal_failures.append("nav")
    if fatal_failures:
        first_error = ""
        if price_failures:
            first_error = str(price_failures[0])
        elif nav_failures:
            first_error = str(nav_failures[0])
        halt = HaltReason(
            kind="akshare_empty",
            stage="ingest",
            detail=f"no successful {', '.join(fatal_failures)} ingest",
            stats={
                "price_attempts": price_attempts,
                "price_successes": price_successes,
                "nav_attempts": nav_attempts,
                "nav_successes": nav_successes,
            },
            first_error=first_error or None,
        )
        HaltReason.write_sidecar(sidecar_path, halt)
        print(f"ERROR: ingest failed: {halt.detail}")
        if price_failures or nav_failures:
            print(
                f"  skipped due to upstream errors — prices: {price_failures or 'none'}; "
                f"nav: {nav_failures or 'none'}"
            )
        return 1
```

> **Note:** `sidecar_path` is defined at the top of `run_ingest` (step 4.3). It's in scope here.

### Step 4.8: Run the post-ingest sidecar test
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py::test_run_ingest_zero_success_writes_sidecar -v`
- [ ] Expected: PASS.

### Step 4.9: Run the full ingest test suite to confirm no regressions
- [ ] Run: `pytest tests/commands/test_ingest_cmd.py -v`
- [ ] Expected: all existing tests still PASS, new tests PASS.

### Step 4.10: Commit
- [ ] Run:

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_cmd.py
git commit -m "feat(ingest): write HaltReason sidecar on preflight + 0-success failures"
```

---

## Task 5: `run_pipeline` consumes the sidecar

**Files:**
- Modify: `src/irc/commands/run_cmd.py:71-80` (the `rc != 0` branch)
- Test: `tests/commands/test_run_cmd.py`

### Step 5.1: Write the failing test for sidecar consumption
- [ ] Add to `tests/commands/test_run_cmd.py`:

```python
from datetime import date as _date
from pathlib import Path
from irc.pipeline_halt import HaltReason


def test_run_pipeline_consumes_halt_reason_sidecar(tmp_path: Path):
    """When a stage fails and writes a sidecar, the halt markdown reflects
    the structured reason and the sidecar is deleted afterward."""
    today = _date.today().isoformat()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / ".halt_reason.json"

    def failing_ingest(_repo_root: str) -> int:
        HaltReason.write_sidecar(sidecar, HaltReason(
            kind="akshare_empty", stage="ingest",
            detail="every fetch returned 0 rows",
            stats={"price_attempts": 198, "price_successes": 0},
            first_error="ConnectionResetError: simulated",
        ))
        return 1

    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["ingest"] = failing_ingest
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="ingest")

    assert rc == 1
    halt_md = (out_dir / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "akshare_empty" in halt_md
    assert "every fetch returned 0 rows" in halt_md
    assert "price_attempts" in halt_md and "198" in halt_md
    assert "ConnectionResetError" in halt_md
    assert not sidecar.exists(), "sidecar must be deleted after consumption"


def test_run_pipeline_falls_back_when_no_sidecar(tmp_path: Path):
    """When a stage fails without writing a sidecar, the halt markdown uses
    the legacy generic message — preserves back-compat for other stages."""
    def failing_score(_repo_root: str) -> int:
        return 7  # arbitrary non-zero
    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["score"] = failing_score
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="score")

    assert rc == 7
    today = _date.today().isoformat()
    halt_md = (tmp_path / "outputs" / today / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "stage exit code 7" in halt_md
    assert "score" in halt_md
```

### Step 5.2: Run tests to verify they fail
- [ ] Run: `pytest tests/commands/test_run_cmd.py -k "consumes_halt_reason or falls_back_when_no_sidecar" -v`
- [ ] Expected: `consumes_halt_reason` FAILs (markdown lacks the structured fields); `falls_back_when_no_sidecar` may PASS already since fallback is the current behavior.

### Step 5.3: Wire the sidecar consumer in `run_pipeline`
- [ ] In `src/irc/commands/run_cmd.py`, replace the block at lines 71-80:

```python
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
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
```

### Step 5.4: Run the tests to verify they pass
- [ ] Run: `pytest tests/commands/test_run_cmd.py -v`
- [ ] Expected: both new tests PASS, all existing tests still PASS.

### Step 5.5: Commit
- [ ] Run:

```bash
git add src/irc/commands/run_cmd.py tests/commands/test_run_cmd.py
git commit -m "feat(run): consume HaltReason sidecar to render structured PIPELINE_HALTED.md"
```

---

## Task 6: Full-suite verification + manual smoke

**Files:**
- No code changes; verification only.

### Step 6.1: Run the full test suite
- [ ] Run: `pytest -x -q`
- [ ] Expected: zero failures. If something unrelated broke, fix it before continuing (do not skip).

### Step 6.2: Manual smoke — preflight outage path
- [ ] In a Python REPL from the repo root, simulate a preflight outage and confirm the halt markdown shape:

```bash
python -c "
import tempfile, pathlib, sys
from unittest.mock import patch
from irc.commands.init_cmd import run_init
from irc.commands.ingest_cmd import run_ingest

with tempfile.TemporaryDirectory() as td:
    run_init(td, force=False)
    with patch('irc.commands.ingest_cmd._preflight_call',
               side_effect=ConnectionResetError('simulated outage')):
        rc = run_ingest(td)
    print('rc =', rc)
    from datetime import date
    halt = pathlib.Path(td) / 'outputs' / date.today().isoformat() / '.halt_reason.json'
    print('sidecar exists:', halt.exists())
    print(halt.read_text())
"
```

- [ ] Expected output: `rc = 1`, sidecar exists, JSON contains `\"kind\": \"akshare_unreachable\"`.

### Step 6.3: Manual smoke — orchestrator end-to-end
- [ ] Same approach via `run_pipeline`:

```bash
python -c "
import tempfile, pathlib
from unittest.mock import patch
from irc.commands.init_cmd import run_init
from irc.commands.run_cmd import run_pipeline

with tempfile.TemporaryDirectory() as td:
    run_init(td, force=False)
    with patch('irc.commands.ingest_cmd._preflight_call',
               side_effect=ConnectionResetError('simulated outage')):
        rc = run_pipeline(td, only_stage='ingest')
    print('rc =', rc)
    from datetime import date
    md = pathlib.Path(td) / 'outputs' / date.today().isoformat() / 'PIPELINE_HALTED.md'
    print(md.read_text())
"
```

- [ ] Expected output: `rc = 1`, markdown contains `akshare_unreachable`, `preflight canary failed`, the `ConnectionResetError` line, and the network-remediation text from `_REMEDIATION_BY_KIND`.

### Step 6.4: Run the discipline checks the project uses
- [ ] Run: `pytest tests/ -q` (one more time, top-level) and any type/lint commands the project defines. Inspect `pyproject.toml` for a `[tool.ruff]` / `[tool.mypy]` block and run what's configured.

### Step 6.5: Final commit (only if Task 6 surfaced any fixes)
- [ ] If steps 6.1–6.4 surfaced regressions that required code changes, commit them with:

```bash
git add -A
git commit -m "fix(pipeline-halt): address regressions surfaced during full-suite verification"
```

Otherwise, skip this step.

---

## Self-review checklist (for the implementing engineer)

After Task 6, sanity-check the change set against the spec (`docs/superpowers/specs/2026-05-17-ingest-halt-diagnostics-design.md`):

- [ ] **Spec requirement: preflight canary** → Tasks 3, 4.3 implement it.
- [ ] **Spec requirement: typed `kind` field** → Task 1 defines it; Tasks 3, 4 populate `akshare_unreachable`, `akshare_error`, `akshare_empty`; spec also mentions `preflight_unexpected` — implementation chose to let `KeyboardInterrupt`/`SystemExit` propagate (BaseException is not caught), so `preflight_unexpected` is not emitted in practice. Acceptable simplification — note it in the commit message if you remove the kind from `_REMEDIATION_BY_KIND`.
- [ ] **Spec requirement: per-source stats** → Task 4.7 populates `price_attempts`, `price_successes`, `nav_attempts`, `nav_successes`.
- [ ] **Spec requirement: truncated `first_error` (500 chars)** → Task 1 enforces in `__post_init__`.
- [ ] **Spec requirement: stale-guard on entry** → Task 4.3, covered by `test_run_ingest_preflight_clears_stale_sidecar`.
- [ ] **Spec requirement: orchestrator consumes sidecar + deletes** → Task 5, covered by `test_run_pipeline_consumes_halt_reason_sidecar`.
- [ ] **Spec requirement: back-compat for `write_halted(repo_root, date, stage, reason, remediation)`** → not modified; `write_halted_structured` is a sibling. Task 5.3 falls back to `write_halted` when no sidecar exists.
- [ ] **Spec non-goal: no stale-data fallback mode** → confirmed; nothing in this plan introduces one.
- [ ] **Spec non-goal: no proxy config** → confirmed.
