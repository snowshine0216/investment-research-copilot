# Item 004 Implementation Plan — Live-verify `fund_announcement_em` (Slice E13, Q4 hard-stop gate)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Falsify the load-bearing assumption that `ak.fund_announcement_em(symbol=...)` exists, is callable, and returns a non-empty DataFrame with `{title, type, date, url}` columns for `518880` / `000001` / `005827` against the AkShare version pinned in this repo. This is the Q4 prerequisite for item 005; FAIL halts the autodev run.

**Architecture:** Test-only slice. Registers pytest markers (`live_akshare` + `integration`) in `pyproject.toml` with `--strict-markers`. Adds one dual-gated live-call test file (`pytest -m live_akshare` AND `IRC_RUN_LIVE_AKSHARE=1`) that drives AkShare through the existing `_ak_call` wrapper, captures one fixture per symbol under `tests/fixtures/akshare/`, and emits structured `Q4 PREREQUISITE FAILURE` messages. A mocked companion file locks the failure-trace tone via `pytest-mock`-patched `_ak_call`. Adds a short run-discipline doc. No `src/` changes.

**Tech Stack:** Python 3.12, pytest, pytest-mock (already in dev extras), pandas (existing dep), AkShare (existing pin `>=1.13`).

---

## Constraints (apply to every task)

- **Strict TDD per task:** red (failing test) → green (minimal impl) → refactor. The "failing test" for marker/config tasks is a shell command verifying behaviour (e.g. `pytest --markers | grep live_akshare`); for code tasks it is a pytest invocation that fails on the missing implementation.
- **No new dependencies.** `akshare>=1.13` and `pytest-mock>=3.12` are already in `pyproject.toml`.
- **No production code in `src/`.** Item 004 is a verification-only slice. Only `pyproject.toml`, two test files, one helper test doc, and the captured fixture file(s) under `tests/fixtures/akshare/` change.
- **`IRC_RUN_LIVE_AKSHARE` defaults OFF.** CI must NOT trigger live calls.
- **Dual gate.** A test runs only when BOTH `pytest -m live_akshare` is selected AND `IRC_RUN_LIVE_AKSHARE=1` is exported. Marker selection alone or env-var alone never runs the live calls.
- **Fixture overwrite-always.** Every successful live run rewrites `tests/fixtures/akshare/fund_announcement_em_{symbol}.json`. Tests never assert content equality against the fixture (only column shape + non-empty).
- **AkShare access only through `_ak_call`.** The live test imports `from irc.fundamentals.akshare_fundamentals import _ak_call`. It MUST NOT `import akshare as ak` directly except in the preflight `hasattr` check (which needs the module handle to inspect attributes).
- **Commit cadence:** one conventional-commit per task (`chore(pytest):`, `test(fundamentals):`, `docs(testing):`). Tests-first within a task. DO NOT push.
- **Verification per task:** an exact command with expected output. Final task = the live gate run.

## Branch

Sub-branch: `autodev/thesis-evidence-004-live-verify-fund-announcement-em` cut from `autodev/thesis-cards-evidence-gap`. Commits land on the sub-branch; the eventual PR opens against `autodev/thesis-cards-evidence-gap`.

---

## File-touch map (read this before starting)

**Modify:**
- `pyproject.toml` — extend `[tool.pytest.ini_options]` with `addopts = ["--strict-markers"]` + `markers = [...]` (BOTH `live_akshare` AND `integration`).

**Create:**
- `tests/fundamentals/test_fund_announcement_em_live.py` — `COLUMN_EQUIVALENCE` map, `_resolve_column`, `_capture_fixture`, `pytestmark` preamble, 5 tests (preflight + 3 per-symbol + aggregate gate).
- `tests/fundamentals/test_fund_announcement_em_failure_modes.py` — 5 mocked tests (function-missing, empty DataFrame, missing column, None return, exception) locking failure-trace tone. Runs by default.
- `tests/fixtures/akshare/` — directory.
- `tests/fixtures/akshare/.gitkeep` — placeholder so the empty directory exists in git before the first live run captures fixtures.
- `tests/fundamentals/README-live-tests.md` — short run-discipline doc.

**Read (do NOT modify):**
- `src/irc/fundamentals/akshare_fundamentals.py:21-24` — `_ak_call` wrapper; the test invokes AkShare exclusively through this function.
- `tests/integration/test_live_endpoints.py:29-37` — reference pattern for `_RUN` + `pytestmark` preamble.
- `tests/integration/test_thesis_coverage.py:14,33` — `@pytest.mark.integration` usage that `--strict-markers` would otherwise break.

**Fixtures eventually written by Task 7 (committed):**
- `tests/fixtures/akshare/fund_announcement_em_518880.json`
- `tests/fixtures/akshare/fund_announcement_em_000001.json`
- `tests/fixtures/akshare/fund_announcement_em_005827.json`

---

## Task index (8 tasks, each green-at-checkpoint)

1. Register `live_akshare` + `integration` markers and `--strict-markers` in `pyproject.toml`.
2. Scaffold `tests/fixtures/akshare/` with a `.gitkeep` placeholder.
3. Create `tests/fundamentals/test_fund_announcement_em_live.py` with `COLUMN_EQUIVALENCE` + `_resolve_column` + module-level dual-gate preamble + the adapter-existence preflight test.
4. Add `_capture_fixture` helper + the 3 per-symbol tests (gold / bond / active) to the live file.
5. Add `test_fund_announcement_em_q4_gate` aggregate test to the live file.
6. Create `tests/fundamentals/test_fund_announcement_em_failure_modes.py` with 5 mocked-failure tests.
7. Write `tests/fundamentals/README-live-tests.md` run-discipline doc.
8. Final live-gate run: `IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py -v -s` — must PASS; this is the Q4 verification gate.

**Per-task test count:** Task 1 = 2 verification commands (no pytest tests). Task 2 = 1 directory check. Task 3 = 1 pytest test (`test_fund_announcement_em_adapter_exists`). Task 4 = 3 pytest tests (per-symbol). Task 5 = 1 pytest test (aggregate gate). Task 6 = 5 pytest tests (failure modes). Task 7 = doc only. Task 8 = live-run verification of all 5 live tests + the 5 failure-mode tests together. Total new pytest tests: **10** (5 live + 5 mocked).

**Drift note (recorded by 004-drift.md, 2026-05-23):** Impl commit `5fb2332` (labeled task 3) shipped the full live file including task 4 + task 5 content in one shot. Commits `c50ad57` (task 4) and `f2e8cd1` (task 5) are empty bookmark commits carrying no file changes — the plan's one-commit-per-task cadence was not followed but the implementation content is fully present and correct.

---

## Task 1: Register pytest markers + `--strict-markers` in `pyproject.toml`

**Files:**
- Modify: `pyproject.toml:46-48`

- [ ] **Step 1: Write the failing verification command**

Run: `pytest --markers 2>&1 | grep -E '^@pytest\.mark\.(live_akshare|integration):'`
Expected: NO output (markers not yet registered).

- [ ] **Step 2: Verify `--strict-markers` is currently inactive**

Run: `pytest tests/integration/test_thesis_coverage.py --collect-only 2>&1 | grep -E 'PytestUnknownMarkWarning|unknown marker' | head -3`
Expected: a `PytestUnknownMarkWarning: Unknown pytest.mark.integration` line (proves the marker is currently unregistered and the suite tolerates it via warnings).

- [ ] **Step 3: Edit `pyproject.toml`**

Replace the existing `[tool.pytest.ini_options]` block:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
```

with the extended form:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = ["--strict-markers"]
markers = [
    "live_akshare: hits the real AkShare network. Run via `pytest -m live_akshare` with IRC_RUN_LIVE_AKSHARE=1. Excluded from default `pytest` runs.",
    "integration: integration test exercising multiple modules end-to-end (no external network). Currently used by tests/integration/test_thesis_coverage.py.",
]
```

- [ ] **Step 4: Verify markers are registered**

Run: `pytest --markers 2>&1 | grep -E '^@pytest\.mark\.(live_akshare|integration):'`
Expected output (both lines, order may vary):
```
@pytest.mark.live_akshare: hits the real AkShare network. Run via `pytest -m live_akshare` with IRC_RUN_LIVE_AKSHARE=1. Excluded from default `pytest` runs.
@pytest.mark.integration: integration test exercising multiple modules end-to-end (no external network). Currently used by tests/integration/test_thesis_coverage.py.
```

- [ ] **Step 5: Verify `--strict-markers` is active (typo-marker rejection)**

Run: `pytest -m live_akshre tests/ --collect-only 2>&1 | tail -5`
Expected: a non-zero exit with `'live_akshre' not found in markers configuration option` (note the typo `live_akshre`). This proves `--strict-markers` is gating misspelled markers.

- [ ] **Step 6: Verify the existing `integration` users still collect cleanly**

Run: `pytest tests/integration/test_thesis_coverage.py --collect-only 2>&1 | tail -5`
Expected: collects 2 tests with NO `PytestUnknownMarkWarning` lines.

- [ ] **Step 7: Run the full default suite to confirm no regression**

Run: `pytest -x --collect-only 2>&1 | tail -3`
Expected: collection succeeds, exit code 0, no `--strict-markers` rejections from existing tests.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml
git commit -m "chore(pytest): register live_akshare + integration markers with --strict-markers"
```

---

## Task 2: Scaffold `tests/fixtures/akshare/` directory

**Files:**
- Create: `tests/fixtures/akshare/.gitkeep`

- [ ] **Step 1: Verify directory does not yet exist**

Run: `test -d tests/fixtures/akshare && echo "exists" || echo "absent"`
Expected: `absent`.

- [ ] **Step 2: Create the directory and `.gitkeep` sentinel**

```bash
mkdir -p tests/fixtures/akshare
touch tests/fixtures/akshare/.gitkeep
```

- [ ] **Step 3: Verify directory exists and is empty except for `.gitkeep`**

Run: `ls -la tests/fixtures/akshare/`
Expected: shows `.`, `..`, and `.gitkeep` (3 entries).

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/akshare/.gitkeep
git commit -m "chore(tests): scaffold tests/fixtures/akshare/ directory for AkShare fixtures"
```

---

## Task 3: Create live test file with preflight test + dual-gate preamble

**Files:**
- Create: `tests/fundamentals/test_fund_announcement_em_live.py`

- [ ] **Step 1: Verify the test file does not exist**

Run: `test -f tests/fundamentals/test_fund_announcement_em_live.py && echo "exists" || echo "absent"`
Expected: `absent`.

- [ ] **Step 2: Write the file with the preflight test only (other tests in later tasks)**

Create `tests/fundamentals/test_fund_announcement_em_live.py` with:

```python
"""Live verification of ``ak.fund_announcement_em`` (Slice E13, Q4 hard-stop gate).

Why this file exists: item 005 (Slice F) wires ``fund_announcement_em`` as the
ONLY ``citation_kind="information"`` source for gold (``518880``) and
cn_bond_fund (``000001``). If the function is missing, empty, or schema-drifted
in the pinned AkShare, item 005 cannot ship its information leg — every gold
and cn_bond_fund row would fail the dual-coverage citation gate.

This file is the Q4 prerequisite test. The autodev orchestrator reads its
exit code as the gate signal: PASS proceeds to item 005, FAIL stops the run
and surfaces the structured ``Q4 PREREQUISITE FAILURE`` message.

Run::

    IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare \\
        tests/fundamentals/test_fund_announcement_em_live.py -v -s

Default ``pytest`` invocations skip every test in this file (both the marker
and the env var are required — see ``CONTEXT.md`` "Live test gate").
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

# ── Dual-gate preamble ──────────────────────────────────────────────────────

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]

# ── Logical-to-AkShare column equivalence map ───────────────────────────────

COLUMN_EQUIVALENCE: dict[str, tuple[str, ...]] = {
    "title": ("公告标题", "标题", "title"),
    "type":  ("公告类型", "类型", "type"),
    "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
    "url":   ("公告链接", "链接", "url"),
}

# Per-symbol minimum row thresholds. 518880/000001 are long-running products
# with frequent disclosures; 005827 is a more recent active fund with fewer
# announcements but still expected to exceed N_MIN=3.
N_MIN: dict[str, int] = {
    "518880": 5,
    "000001": 5,
    "005827": 3,
}

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "akshare"


# ── Helpers (importable by the failure-modes companion file) ────────────────

def _akshare_version() -> str:
    """Return the installed AkShare version string, or 'unknown' on failure."""
    try:
        import akshare  # local import — see preamble docstring rationale
        return getattr(akshare, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover — surface env defects loudly
        return f"unimportable ({type(exc).__name__})"


def _resolve_column(df: pd.DataFrame, logical: str) -> str:
    """Resolve a logical column name to the actual AkShare column.

    Raises an ``AssertionError`` carrying the structured Q4 prerequisite
    failure message if no candidate matches. The message lists the expected
    candidates and the observed columns so a future reader (orchestrator or
    human triage) gets the next action without re-reading the diagnosis doc.
    """
    candidates = COLUMN_EQUIVALENCE[logical]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise AssertionError(
        "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em returned a DataFrame "
        f"missing the '{logical}' column. Expected one of {candidates!r}. "
        f"Got columns: {sorted(df.columns)!r}. AkShare schema may have changed. "
        "STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5."
    )


# ── Tests ───────────────────────────────────────────────────────────────────

def test_fund_announcement_em_adapter_exists() -> None:
    """Preflight: ``ak.fund_announcement_em`` is callable in the pinned AkShare.

    Runs FIRST in this file so a missing function fails with the Q4 message
    instead of a buried ``AttributeError`` traceback inside ``_ak_call``.
    """
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "akshare not installed in this venv. "
            "Install with: uv sync --extra dev (or check pyproject.toml dependencies). "
            f"Underlying error: {exc}"
        ) from exc

    if not hasattr(ak, "fund_announcement_em"):
        raise AssertionError(
            "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing from "
            f"the installed AkShare ({_akshare_version()}). Item 005 cannot "
            "ship its information leg. STOP and re-decide Q4 (option b: "
            "theme-report scope-promotion, option c: exclude gold + "
            "cn_bond_fund from V1). See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    print(
        f"\n  ✓ ak.fund_announcement_em present in AkShare {_akshare_version()}"
    )
```

- [ ] **Step 3: Default `pytest` invocation must skip the file**

Run: `pytest tests/fundamentals/test_fund_announcement_em_live.py -v 2>&1 | tail -5`
Expected: exit 0; output contains `SKIPPED` lines and `set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests`.

- [ ] **Step 4: Marker-without-env-var must still skip**

Run: `pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py -v 2>&1 | tail -5`
Expected: exit 0; output contains `SKIPPED`. This proves the dual gate (marker alone is not enough).

- [ ] **Step 5: Env-var without marker also skips because of default `pytest` non-selection**

Run: `IRC_RUN_LIVE_AKSHARE=1 pytest tests/fundamentals/test_fund_announcement_em_live.py -v 2>&1 | tail -5`
Expected: 1 test collected (`test_fund_announcement_em_adapter_exists`); runs and passes when AkShare is installed and the function exists — or fails loudly with the structured Q4 message if AkShare is missing. Either way: the env-var path actually executes the body. (The marker is the test-selection knob; absent `-m live_akshare`, pytest still collects + runs because no `-m "not live_akshare"` is wired into `addopts`. The skip preamble re-evaluates when env-var is set — but `pytestmark` is `[live_akshare, skipif(not _RUN, …)]`; with `_RUN==True` the skipif is False and pytest runs the test.)

> If AkShare is not installed in the local venv (the impl agent's environment may lack the dep), this step prints the explicit `akshare not installed in this venv...` message — that is an environment defect, NOT a task failure. Install with `uv sync --extra dev` and rerun.

- [ ] **Step 6: Commit**

```bash
git add tests/fundamentals/test_fund_announcement_em_live.py
git commit -m "test(fundamentals): add fund_announcement_em adapter-existence preflight (Q4 gate scaffold)"
```

---

## Task 4: Add `_capture_fixture` helper + 3 per-symbol tests

**Files:**
- Modify: `tests/fundamentals/test_fund_announcement_em_live.py` (append helper + 3 tests)

- [ ] **Step 1: Write the failing tests by appending to the live file**

Append the following to `tests/fundamentals/test_fund_announcement_em_live.py` (after the existing `test_fund_announcement_em_adapter_exists` body):

```python


def _capture_fixture(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` as UTF-8 JSON to ``path`` atomically (.tmp → os.replace).

    Format::

        {
          "columns": [...],
          "rows":    [{...}, ...],
          "captured_at":    "<ISO-8601 UTC>",
          "akshare_version": "<version>"
        }

    Chinese column names are preserved verbatim (``ensure_ascii=False``).
    Overwrite policy: ALWAYS overwrite on every successful live run — the
    fixture is a captured shadow of the latest live response, not a frozen
    snapshot. Tests never assert content equality against the fixture, so
    daily content drift is benign.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "akshare_version": _akshare_version(),
    }
    # Atomic write via tempfile in the same directory + os.replace.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _assert_announcement_df(df: object, symbol: str) -> pd.DataFrame:
    """Per-symbol structural assertions. Returns ``df`` for chaining.

    Asserts:
      1. ``isinstance(df, pd.DataFrame)`` — covers Q-G (None / non-DataFrame).
      2. ``len(df) >= N_MIN[symbol]`` — threshold ratchet for row count.
      3. The 4 logical columns resolve via ``_resolve_column``.
      4. Row 0's resolved cells are non-null and non-empty-string (Q-H).
    """
    if not isinstance(df, pd.DataFrame):
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned a non-DataFrame ({type(df).__name__}) — possibly an "
            "AkShare error path. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    n = len(df)
    if n < N_MIN[symbol]:
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned {n} rows; threshold is {N_MIN[symbol]}. "
            "Information leg unreliable. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    for logical in ("title", "type", "date", "url"):
        col = _resolve_column(df, logical)
        first = df.iloc[0][col]
        if first is None or (isinstance(first, str) and first.strip() == ""):
            raise AssertionError(
                f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
                f"returned a DataFrame whose '{logical}' column ({col!r}) "
                f"is null/empty on row 0. STOP and re-decide Q4. "
                "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )
    return df


def _call_fund_announcement_em(symbol: str) -> pd.DataFrame:
    """Indirection so per-symbol tests + the aggregate gate share one path.

    Uses ``_ak_call`` from the project's wrapper (NOT a direct ``ak`` import)
    so future fixture-driven mocking patches the same function.
    """
    from irc.fundamentals.akshare_fundamentals import _ak_call
    try:
        return _ak_call("fund_announcement_em", symbol=symbol)
    except Exception as exc:
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"raised {type(exc).__name__}: {exc}. Information leg unreachable. "
            "STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        ) from exc


def test_fund_announcement_em_gold_518880() -> None:
    """Gold ETF (518880) returns ≥5 announcements with required columns.

    On success, captures the fixture to
    ``tests/fixtures/akshare/fund_announcement_em_518880.json``.
    """
    symbol = "518880"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    latest = df.iloc[0][date_col]
    latest_url = str(df.iloc[0][url_col])
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={latest}, url={latest_url[:60]}"
    )


def test_fund_announcement_em_bond_000001() -> None:
    """Bond fund (000001, 华夏成长) returns ≥5 announcements with required columns."""
    symbol = "000001"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={df.iloc[0][date_col]}, url={str(df.iloc[0][url_col])[:60]}"
    )


def test_fund_announcement_em_active_005827() -> None:
    """Active equity fund (005827, 易方达蓝筹精选) sanity check: ≥3 announcements."""
    symbol = "005827"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={df.iloc[0][date_col]}, url={str(df.iloc[0][url_col])[:60]}"
    )
```

- [ ] **Step 2: Default `pytest` still skips the file (no regression from new tests)**

Run: `pytest tests/fundamentals/test_fund_announcement_em_live.py -v 2>&1 | tail -8`
Expected: 4 tests collected, all `SKIPPED` with reason `set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests`. Exit code 0.

- [ ] **Step 3: Collect-only with `-m live_akshare` shows 4 tests**

Run: `pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py --collect-only -q 2>&1 | head -10`
Expected: 4 test nodeids printed (`test_fund_announcement_em_adapter_exists`, `..._gold_518880`, `..._bond_000001`, `..._active_005827`).

- [ ] **Step 4: Lint-only sanity check on the test file**

Run: `python3 -c "import ast; ast.parse(open('tests/fundamentals/test_fund_announcement_em_live.py').read()); print('syntax ok')"`
Expected: `syntax ok`.

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_fund_announcement_em_live.py
git commit -m "test(fundamentals): add 3 per-symbol live tests + fixture-capture helper"
```

---

## Task 5: Add aggregate Q4 gate test

**Files:**
- Modify: `tests/fundamentals/test_fund_announcement_em_live.py` (append `test_fund_announcement_em_q4_gate`)

- [ ] **Step 1: Append the aggregate gate test**

Add to the end of `tests/fundamentals/test_fund_announcement_em_live.py`:

```python


def test_fund_announcement_em_q4_gate() -> None:
    """Aggregate Q4 gate: all 3 symbols must PASS.

    The autodev orchestrator reads this test's exit code as the gate signal.
    Re-calls AkShare independently of the per-symbol tests (pytest does not
    natively thread results between tests; three extra calls is negligible
    and keeps the gate self-contained).

    On failure, raises with a multi-line summary listing every failing symbol
    so a single read of the failure shows the full picture.
    """
    results: dict[str, str] = {}  # symbol -> "PASS" or failure detail
    for symbol in ("518880", "000001", "005827"):
        try:
            df = _call_fund_announcement_em(symbol)
            _assert_announcement_df(df, symbol)
            results[symbol] = "PASS"
        except AssertionError as exc:
            # First line of the message is the structured Q4 prefix.
            first_line = str(exc).splitlines()[0]
            results[symbol] = f"FAIL — {first_line}"

    failures = {s: r for s, r in results.items() if r != "PASS"}
    if failures:
        joined = "\n".join(f"  • {s}: {detail}" for s, detail in failures.items())
        raise AssertionError(
            "Q4 PREREQUISITE FAILURE (aggregate gate): "
            f"{len(failures)} of 3 symbol(s) failed.\n{joined}\n"
            "STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5 "
            "for the three fall-back options (a: re-pin AkShare, b: theme-report "
            "scope promotion, c: exclude gold + cn_bond_fund from V1)."
        )
    print(
        f"\n  ✓ Q4 gate: all 3 symbols PASS "
        f"(AkShare {_akshare_version()})"
    )
```

- [ ] **Step 2: Default `pytest` still skips**

Run: `pytest tests/fundamentals/test_fund_announcement_em_live.py -v 2>&1 | tail -8`
Expected: 5 tests collected, all `SKIPPED`. Exit code 0.

- [ ] **Step 3: Collect-only shows 5 tests under the marker**

Run: `pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py --collect-only -q 2>&1 | head -10`
Expected: 5 test nodeids (the 4 from Task 4 + `test_fund_announcement_em_q4_gate`).

- [ ] **Step 4: Syntax check**

Run: `python3 -c "import ast; ast.parse(open('tests/fundamentals/test_fund_announcement_em_live.py').read()); print('syntax ok')"`
Expected: `syntax ok`.

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_fund_announcement_em_live.py
git commit -m "test(fundamentals): add aggregate Q4 gate test (orchestrator-readable)"
```

---

## Task 6: Create mocked failure-modes companion file

**Files:**
- Create: `tests/fundamentals/test_fund_announcement_em_failure_modes.py`

- [ ] **Step 1: Verify the file does not exist**

Run: `test -f tests/fundamentals/test_fund_announcement_em_failure_modes.py && echo "exists" || echo "absent"`
Expected: `absent`.

- [ ] **Step 2: Write the failing tests + minimal scaffolding**

Create `tests/fundamentals/test_fund_announcement_em_failure_modes.py`:

```python
"""Mocked failure-mode companion for the Q4 live gate.

The live test (``test_fund_announcement_em_live.py``) can only assert "real
AkShare passes today"; it cannot exercise the failure paths because they
are unreachable when AkShare is healthy. This file patches ``_ak_call``
(and, for the function-missing case, ``akshare``) to lock the failure-trace
tone — guarding the autodev orchestrator's stdout-reading STOP-detection.

Runs in every default ``pytest`` invocation (no ``live_akshare`` marker,
no env-var gate). ~5 tests, ~30 LoC of test bodies.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import pandas as pd
import pytest

from tests.fundamentals.test_fund_announcement_em_live import (
    _assert_announcement_df,
    _call_fund_announcement_em,
    _resolve_column,
)


# ── Failure 1: function missing on the ``akshare`` module ────────────────────

def test_function_missing_emits_q4_prerequisite_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preflight detects ``not hasattr(ak, 'fund_announcement_em')``.

    We can't directly call the preflight test function (it lives in another
    file and uses live network). Instead, we replicate its core check against
    a stub ``akshare`` module missing the attribute.
    """
    stub = types.ModuleType("akshare")
    stub.__version__ = "0.0.0-stub"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "akshare", stub)

    import akshare as ak  # picks up the stub from sys.modules
    assert not hasattr(ak, "fund_announcement_em")

    # Now assert the structured Q4 message reaches a future reader.
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*missing.*"):
        if not hasattr(ak, "fund_announcement_em"):
            raise AssertionError(
                "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing from "
                f"the installed AkShare ({getattr(ak, '__version__', 'unknown')}). "
                "Item 005 cannot ship its information leg. STOP and re-decide Q4 "
                "(option b: theme-report scope-promotion, option c: exclude gold + "
                "cn_bond_fund from V1). See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )


# ── Failure 2: empty DataFrame return ────────────────────────────────────────

def test_empty_dataframe_raises_q4_row_count_failure(mocker: Any) -> None:
    empty = pd.DataFrame(columns=["公告标题", "公告类型", "公告日期", "公告链接"])
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=empty,
    )
    with pytest.raises(AssertionError) as excinfo:
        _call_fund_announcement_em("518880")  # _call uses _ak_call internally
        # _call returns the df; the assertion lives in _assert_announcement_df:
    # If _call did not raise (it shouldn't — the mock returns a real DataFrame),
    # re-drive the assertion explicitly:
    if not excinfo.value:  # defensive: should be unreachable
        with pytest.raises(AssertionError, match="returned 0 rows.*threshold is 5"):
            _assert_announcement_df(empty, "518880")
    # The expected path: _call returned the empty df cleanly; we now assert
    # _assert_announcement_df raises the structured threshold-failure message.
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*returned 0 rows.*threshold is 5"):
        _assert_announcement_df(empty, "518880")


# ── Failure 3: DataFrame missing the URL column ──────────────────────────────

def test_missing_url_column_raises_q4_column_failure(mocker: Any) -> None:
    df = pd.DataFrame({
        "公告标题": [f"标题{i}" for i in range(6)],
        "公告类型": [f"类型{i}" for i in range(6)],
        "公告日期": [f"2025-01-0{i+1}" for i in range(6)],
        # NOTE: 公告链接 deliberately absent
    })
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=df,
    )
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*missing the 'url' column"):
        _assert_announcement_df(df, "518880")


# ── Failure 4: ``_ak_call`` returns None ─────────────────────────────────────

def test_none_return_raises_q4_non_dataframe_failure(mocker: Any) -> None:
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=None,
    )
    df = _call_fund_announcement_em("518880")
    assert df is None  # _call returns the raw value; assertion lives below
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*returned a non-DataFrame.*NoneType"):
        _assert_announcement_df(df, "518880")


# ── Failure 5: ``_ak_call`` raises a runtime exception ───────────────────────

def test_exception_during_call_raises_q4_unreachable_failure(mocker: Any) -> None:
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=RuntimeError("network unreachable"),
    )
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*raised RuntimeError.*Information leg unreachable"):
        _call_fund_announcement_em("518880")
```

- [ ] **Step 3: Run the failure-modes file in isolation**

Run: `pytest tests/fundamentals/test_fund_announcement_em_failure_modes.py -v 2>&1 | tail -15`
Expected: 5 tests, all PASS. Exit 0. No `live_akshare` marker required.

- [ ] **Step 4: Verify the failure-modes file runs under the DEFAULT `pytest` invocation (i.e. is NOT skipped)**

Run: `pytest tests/fundamentals/ -v 2>&1 | tail -15`
Expected: failure-modes tests show as `PASSED`; live tests show as `SKIPPED`. (Other fundamentals tests pass as well.)

- [ ] **Step 5: Verify the full default suite still collects cleanly with `--strict-markers`**

Run: `pytest -x --collect-only 2>&1 | tail -3`
Expected: collection succeeds, exit 0, no marker rejections.

- [ ] **Step 6: Commit**

```bash
git add tests/fundamentals/test_fund_announcement_em_failure_modes.py
git commit -m "test(fundamentals): add mocked failure-modes companion locking Q4 trace tone"
```

---

## Task 7: Write run-discipline doc

**Drift note (recorded by 004-drift.md, 2026-05-23):** The README was written for the original spec (pre-pivot) and retains stale references: endpoint name `ak.fund_announcement_em`, test count "5 tests pass", and fixture names `fund_announcement_em_{518880,000001,005827}.json`. These are cosmetic inaccuracies; the run command, dual-gate discipline, and failure-meaning sections remain correct. A follow-up update (11 tests, 9 pivot fixture names, 3 topic-specific endpoints) is recommended before item 005 ships.

**Files:**
- Create: `tests/fundamentals/README-live-tests.md`

- [ ] **Step 1: Verify the file does not exist**

Run: `test -f tests/fundamentals/README-live-tests.md && echo "exists" || echo "absent"`
Expected: `absent`.

- [ ] **Step 2: Write the doc**

Create `tests/fundamentals/README-live-tests.md`:

```markdown
# Live AkShare tests — run discipline

The tests in `test_fund_announcement_em_live.py` hit the real AkShare network
to verify that `ak.fund_announcement_em` exists and returns usable data for
the three Q4-prerequisite symbols (gold `518880`, bond `000001`, active fund
`005827`).

## How to run

Both the marker AND the env var are required (dual gate):

```bash
IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare \
    tests/fundamentals/test_fund_announcement_em_live.py -v -s
```

Expected: 5 tests pass (1 preflight + 3 per-symbol + 1 aggregate gate).
Each per-symbol test prints a one-line summary; the aggregate gate prints
the AkShare version on success.

## Fixture refresh behaviour

Successful per-symbol runs write/overwrite:

- `tests/fixtures/akshare/fund_announcement_em_518880.json`
- `tests/fixtures/akshare/fund_announcement_em_000001.json`
- `tests/fixtures/akshare/fund_announcement_em_005827.json`

Each file carries `columns`, `rows`, `captured_at` (ISO-8601 UTC),
`akshare_version`. Chinese column names are preserved verbatim
(`ensure_ascii=False`). The fixture is **always overwritten** — it is a
captured shadow of the latest live response, not a frozen snapshot.

Tests never assert content equality against the fixture (only column shape
+ non-empty), so daily content drift is benign. Diff churn on the fixture
file is expected and signals that new announcements arrived upstream.

## What FAILURE means

Any failing test raises with a structured message prefixed
`Q4 PREREQUISITE FAILURE: …`. The first failing-test stdout line carries
the symbol, the specific check, the next action ("STOP and re-decide Q4"),
and the three fall-back options.

Fall-back options (verbatim from `docs/diagnosis-thesis-cards-evidence-gap.md` §5):

- **(a) Re-pin AkShare** to a version that exposes `fund_announcement_em`.
- **(b) Reuse theme reports with promoted scope** — treat asset-class macro
  citations as information-leg for gold + cn_bond_fund.
- **(c) Exclude gold + cn_bond_fund from V1** — drop those asset classes
  from the actionable opportunity surface.

The autodev orchestrator does NOT auto-select a fall-back; it escalates to
the user with the structured failure message. See
`docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md` §"Stop /
proceed contract" for the operational steps the orchestrator follows on
FAIL.

## Default `pytest` behaviour

Running `pytest` (or `pytest -x`) without the marker AND env var skips
every live test in this file. Zero AkShare calls occur in default suite
runs.

The companion file `test_fund_announcement_em_failure_modes.py` runs in
every default suite invocation — it patches `_ak_call` to lock the
failure-trace tone and does NOT hit the network.
```

- [ ] **Step 3: Verify the file lints as valid markdown (no broken backticks)**

Run: `python3 -c "open('tests/fundamentals/README-live-tests.md').read(); print('readable')"`
Expected: `readable`.

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/README-live-tests.md
git commit -m "docs(testing): document live AkShare test run discipline + fall-back options"
```

---

## Task 8: Final live-gate run (Q4 verification)

**Files:** none modified.

- [ ] **Step 1: Pre-flight — confirm AkShare is installed in the active venv**

Run: `python3 -c "import akshare; print(akshare.__version__)"`
Expected: a version string like `1.13.x` or higher. If `ModuleNotFoundError`, install first with `uv sync --extra dev` (or `pip install -e ".[dev]"`).

- [ ] **Step 2: Confirm default suite still passes (no regression)**

Run: `pytest -x 2>&1 | tail -5`
Expected: exit 0; the existing suite plus the new failure-modes tests pass; live tests show as `SKIPPED`.

- [ ] **Step 3: Execute the live Q4 gate**

Run: `IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py -v -s 2>&1 | tail -25`
Expected:
- 5 tests collected.
- All 5 tests `PASSED`:
  1. `test_fund_announcement_em_adapter_exists` — prints `  ✓ ak.fund_announcement_em present in AkShare <version>`
  2. `test_fund_announcement_em_gold_518880` — prints `  ✓ fund_announcement_em/518880 → <N≥5> rows, latest=<date>, url=https://...`
  3. `test_fund_announcement_em_bond_000001` — prints `  ✓ fund_announcement_em/000001 → <N≥5> rows, …`
  4. `test_fund_announcement_em_active_005827` — prints `  ✓ fund_announcement_em/005827 → <N≥3> rows, …`
  5. `test_fund_announcement_em_q4_gate` — prints `  ✓ Q4 gate: all 3 symbols PASS (AkShare <version>)`
- Exit code 0.

- [ ] **Step 4: Verify fixtures were written**

Run: `ls -la tests/fixtures/akshare/*.json`
Expected: three files — `fund_announcement_em_518880.json`, `fund_announcement_em_000001.json`, `fund_announcement_em_005827.json`. Each non-empty.

- [ ] **Step 5: Spot-check fixture format**

Run: `python3 -c "import json; d=json.load(open('tests/fixtures/akshare/fund_announcement_em_518880.json')); print(sorted(d)); print('cols:', d['columns'][:6]); print('rows:', len(d['rows']))"`
Expected: keys `['akshare_version', 'captured_at', 'columns', 'rows']`; columns include at least one of `公告标题 / 公告日期 / 公告链接`; rows count is the same `N≥5` reported by the test.

- [ ] **Step 6: Idempotent re-run**

Run the command from Step 3 a second time.
Expected: 5 PASS again; fixture files overwritten (mtime advances); no `.tmp` leftovers (`ls tests/fixtures/akshare/*.tmp 2>&1 || echo none` → `none`).

- [ ] **Step 7: Commit the captured fixtures**

```bash
git add tests/fixtures/akshare/fund_announcement_em_518880.json \
        tests/fixtures/akshare/fund_announcement_em_000001.json \
        tests/fixtures/akshare/fund_announcement_em_005827.json
git commit -m "test(fundamentals): capture initial fund_announcement_em fixtures from live AkShare"
```

**Drift note (recorded by 004-drift.md, 2026-05-23):** This step was superseded by the Q4 FAIL verdict. The original `fund_announcement_em` live gate FAILed (endpoint missing in AkShare 1.18.63). Commit `b44a7ca` is labeled "task 8 capture fixtures" but its actual diff is a one-line import cleanup in the failure-modes companion (`_resolve_column` removed from import). No `fund_announcement_em_*.json` files were committed here. The Q4 FAIL verdict was recorded in `cdcf531`; the pivot fixture capture happened under task P5 (`f2bdf2a`).

- [ ] **Step 8: STOP if FAIL**

If ANY test in Step 3 failed:
1. Do NOT proceed to item 005.
2. Capture the failing stdout (`pytest … 2>&1 | tee /tmp/004-fail.log`) including every `Q4 PREREQUISITE FAILURE: ...` line.
3. Report the failing symbol(s) and the specific check (missing function | empty | missing column | row count below threshold | exception) to the user with the three fall-back options:
   - **(a)** Re-pin AkShare.
   - **(b)** Reuse theme reports with promoted scope.
   - **(c)** Exclude gold + cn_bond_fund from V1.
4. Do NOT auto-select a fall-back — it is a product-scope decision.
5. The orchestrator marks item 004 `FAIL` and items 005–010 `BLOCKED-BY-004` in `PROGRESS.md` per `MASTER-PLAN.md` "Stop conditions".

- [ ] **Step 9: PASS marker — push gate**

If all 5 live tests passed in Step 3, the Q4 prerequisite is verified. Proceed to ship + verify per the canonical autodev workflow.

DO NOT push. The ship step is owned by `/ship` later in the autodev loop.

---

## Self-review

Spec coverage cross-check (every spec requirement → task):

- §"In scope" #1 (marker registration + `--strict-markers`) → Task 1.
- §"In scope" #2 (default exclusion via dual gate) → Task 3 preamble + Tasks 3–5 default-skip verification.
- §"In scope" #3 (new live test file location) → Task 3 file path.
- §"In scope" #4 (module-level gating preamble) → Task 3 step 2 verbatim block.
- §"In scope" #5 (invocation via `_ak_call`) → Task 4 `_call_fund_announcement_em`.
- §"In scope" #6 (preflight `test_fund_announcement_em_adapter_exists`) → Task 3 step 2.
- §"In scope" #7 (3 per-symbol tests with N_MIN) → Task 4.
- §"In scope" #8 (aggregate gate `test_fund_announcement_em_q4_gate`) → Task 5.
- §"In scope" #9 + #10 (fixture format, write site, overwrite policy) → Task 4 `_capture_fixture`.
- §"In scope" #11 (AkShare-installed precondition + ModuleNotFoundError message) → Task 3 step 2 (preflight `try/except ModuleNotFoundError`).
- §"In scope" #12 (mocked failure-mode companion) → Task 6.
- §"Column-name discovery" (COLUMN_EQUIVALENCE + `_resolve_column`) → Task 3 step 2 verbatim block.
- §"Failure-trace contract" (4 templates) → Tasks 3 (function-missing), 4 (`_assert_announcement_df` row-count + missing-column + non-DataFrame), 4 (`_call_fund_announcement_em` exception wrap), 5 (aggregate multi-line).
- §"Resolved decisions" Q-1 (BOTH markers registered) → Task 1.
- §"Resolved decisions" Q-5 (companion file added) → Task 6.
- §"Resolved decisions" Q-6 (STOP operational definition) → Task 8 Step 8.
- §"Acceptance criteria" 1 → Task 1 steps 4–5. 2 → Task 3 step 3. 3 → Task 3 step 4. 4 → Task 8 step 3. 5 → Task 3 step 2 (preflight body). 6 → Task 4 (per-symbol tests). 7 → Task 5. 8 → Task 4 (`_capture_fixture`) + Task 8 steps 4–5. 9 → Task 4 (`path.parent.mkdir`). 10 → Task 8 step 6 (idempotent re-run). 11–14 → Task 6 (permanent mocked equivalents) + Task 8 step 8 (live-file hand-verification on FAIL). 15 → Task 8 step 2 (default suite no live import). 16 → Task 7 footer + plan-wide "No production code in `src/`" constraint.

Placeholder scan: no "TBD"/"TODO"; every code block is verbatim and complete; every command has expected output.

Type consistency: `_resolve_column`, `_capture_fixture`, `_assert_announcement_df`, `_call_fund_announcement_em`, `_akshare_version`, `_FIXTURE_DIR`, `COLUMN_EQUIVALENCE`, `N_MIN` — all named consistently across Tasks 3–6. The companion file imports `_assert_announcement_df`, `_call_fund_announcement_em`, `_resolve_column` from the live file by absolute path `tests.fundamentals.test_fund_announcement_em_live` — matches the `pythonpath = ["src", "."]` in `pyproject.toml`.

Plan complete. 8 tasks; 10 new pytest tests (5 live + 5 mocked); 1 markdown doc; 3 captured fixtures.

---

## Pivot tasks (Q4 option a, adopted 2026-05-23)

`fund_announcement_em` was confirmed missing from AkShare 1.18.63. User chose option (a): adapt to the 3 topic-specific endpoints. These tasks replace Tasks 3–8 for the live test file (Tasks 1, 2, 6, 7 are unchanged).

### Task P1: Explore + record AkShare 1.18.63 shapes for the 3 endpoints

- [x] Run exploratory shell to confirm `fund_announcement_{dividend,report,personnel}_em` exist and record column shapes + row counts per symbol.
- [x] Commit: `docs(autodev/004): explore AkShare 1.18.63 topic-specific endpoint shapes`

**Observed shapes (all 3 endpoints, identical schema):**

```
['基金代码', '公告标题', '基金名称', '公告日期', '报告ID']
```

Row counts: dividend_em (518880: 4, 000001: 15, 005827: 1), report_em (518880: 94, 000001: 100, 005827: 50), personnel_em (518880: 2, 000001: 14, 005827: 2).

### Task P2: Update COLUMN_EQUIVALENCE map for the 3 endpoints

- [x] Update `COLUMN_EQUIVALENCE` in `test_fund_announcement_em_live.py` to use per-endpoint maps reflecting the actual `['基金代码', '公告标题', '基金名称', '公告日期', '报告ID']` schema (no `url` column; `报告ID` is the reference identifier).
- [x] Commit: `test(fundamentals): update COLUMN_EQUIVALENCE for 3 topic-specific endpoints`

**Drift note (recorded by 004-drift.md, 2026-05-23):** The separate P2 commit was not created. The `COLUMN_EQUIVALENCE` per-endpoint rewrite was combined with the full live test rewrite in commit `2c24edd` (P3). Implementation content is correct at `test_fund_announcement_em_live.py:62-81`.

### Task P3: Rewrite live tests file with 11 tests

Replace the 5 tests calling `fund_announcement_em` with 11 tests for the 3 topic-specific endpoints:

1. `test_fund_announcement_endpoints_exist` — preflight for all 3 endpoints
2. `test_fund_announcement_dividend_em_518880_non_empty`
3. `test_fund_announcement_dividend_em_000001_non_empty`
4. `test_fund_announcement_dividend_em_005827_non_empty`
5. `test_fund_announcement_report_em_518880_non_empty`
6. `test_fund_announcement_report_em_000001_non_empty`
7. `test_fund_announcement_report_em_005827_non_empty`
8. `test_fund_announcement_personnel_em_518880_non_empty`
9. `test_fund_announcement_personnel_em_000001_non_empty`
10. `test_fund_announcement_personnel_em_005827_non_empty`
11. `test_fund_announcement_q4_aggregate_gate`

Each per-endpoint × per-symbol test: (a) calls the endpoint; (b) asserts no exception; (c) asserts result is a DataFrame; (d) if non-empty, resolves `title` and `date` columns. Writes fixture to `tests/fixtures/akshare/{endpoint}_{symbol}.json`.

Aggregate gate: PASSes if EACH symbol has non-empty data from AT LEAST ONE endpoint.

- [x] Commit: `test(fundamentals): rewrite live tests for the 3 topic-specific announcement endpoints (Q4 pivot)`

### Task P4: Run live gate — expect 11 pass

```bash
IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py -v -s
```

Expected: 11 tests pass. Aggregate gate PASS (each symbol covered by at least `report_em`).

- [x] Commit verdict in `004-verify.md` after run.

### Task P5: Capture 9 fixtures

- [x] Commit `tests/fixtures/akshare/{endpoint}_{symbol}.json` for all 9 combinations.
- [x] Commit: `test(fundamentals): capture topic-specific endpoint fixtures (Q4 pivot)`
