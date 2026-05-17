# Item 004 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/004-spec.md`. Base: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-004-freshness-gate`.

**Goal:** Gate `gold` / `opportunity` / `memo` stages on ingest freshness. By default, if the akshare manifest's `last_run_at` is older than 24h, the stage refuses to run and writes `STALE_INGEST.md`. An opt-in env override (`IRC_ALLOW_STALE=1`) lets the stage proceed but tags every artifact with a "STALE INGEST" header.

**Architecture:** Reuse the existing `data/_manifest/akshare.json` (written by `ingest_cmd.py` on successful runs). A new pure helper `check_ingest_freshness(repo_root, max_age)` returns `(is_fresh, last_ingest_at, observed_age)`. A small wrapper `require_fresh_ingest(repo_root)` checks the env override and either passes through or writes a `STALE_INGEST.md` artifact and returns `False`. Stage entry points call the wrapper as the first action.

---

## Task 1: Freshness helper + `STALE_INGEST.md` writer

**Files:**
- `src/irc/data/freshness.py` (new)
- `tests/data/test_freshness.py` (new)

### Step 1.1: Write the failing test
- [ ] Create `tests/data/test_freshness.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from irc.data.freshness import (
    IngestFreshness,
    check_ingest_freshness,
    require_fresh_ingest,
)
from irc.data.manifest import ManifestEntry, write_manifest


def _write_akshare_manifest(repo_root: Path, last_run_at: str) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    entry = ManifestEntry(
        source="akshare", last_run_at=last_run_at,
        schema_version="v1", record_counts={"prices": 100},
    )
    write_manifest(repo_root / "data", entry)


def test_fresh_ingest_within_window(tmp_path: Path):
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_akshare_manifest(tmp_path, one_hour_ago)
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert isinstance(result, IngestFreshness)
    assert result.is_fresh is True
    assert result.last_ingest_at is not None


def test_stale_ingest_beyond_window(tmp_path: Path):
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    _write_akshare_manifest(tmp_path, two_days_ago)
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert result.is_fresh is False
    assert result.observed_age > timedelta(hours=24)


def test_missing_manifest_is_stale(tmp_path: Path):
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert result.is_fresh is False
    assert result.last_ingest_at is None


def test_require_fresh_passes_when_fresh(tmp_path: Path):
    _write_akshare_manifest(tmp_path,
                            datetime.now(timezone.utc).isoformat())
    assert require_fresh_ingest(tmp_path, "gold") is True
    assert not (tmp_path / "outputs").exists() or not list(
        (tmp_path / "outputs").rglob("STALE_INGEST.md")
    )


def test_require_fresh_writes_stale_marker_when_stale(tmp_path: Path):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    ok = require_fresh_ingest(tmp_path, "gold")
    assert ok is False
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1
    body = markers[0].read_text(encoding="utf-8")
    assert "gold" in body
    assert "24:00:00" in body or "1 day" in body or "max" in body.lower()
    assert "IRC_ALLOW_STALE" in body
    assert "STALE INGEST" in body.upper()


def test_allow_stale_env_lets_stage_proceed(tmp_path: Path, monkeypatch):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    assert require_fresh_ingest(tmp_path, "gold") is True
    # marker still written for transparency, just not blocking
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes", "on"])
def test_allow_stale_env_truthy_values(tmp_path: Path, monkeypatch, value):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", value)
    assert require_fresh_ingest(tmp_path, "gold") is True


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_allow_stale_env_falsy_values(tmp_path: Path, monkeypatch, value):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", value)
    assert require_fresh_ingest(tmp_path, "gold") is False
```

### Step 1.2: Run tests, expect failure
- [ ] Run: `uv run pytest tests/data/test_freshness.py -v`
- [ ] Expected: ImportError — module not yet defined.

### Step 1.3: Implement the helper
- [ ] Create `src/irc/data/freshness.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.data.manifest import read_manifest
from irc.io_utils import atomic_write_text


DEFAULT_MAX_AGE: timedelta = timedelta(hours=24)
"""Default ingest freshness window. Override via the `max_age` kwarg per stage.
Stages that depend on fresh prices/NAV (gold, opportunity, memo) gate on this.
"""

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y", "t"})


def _allow_stale_env() -> bool:
    return os.environ.get("IRC_ALLOW_STALE", "").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class IngestFreshness:
    is_fresh: bool
    last_ingest_at: datetime | None
    observed_age: timedelta
    max_age: timedelta
    source: str = "akshare"


def check_ingest_freshness(
    repo_root: Path, *, max_age: timedelta = DEFAULT_MAX_AGE,
    source: str = "akshare",
) -> IngestFreshness:
    """Pure read of the manifest. No I/O beyond reading the manifest file."""
    entry = read_manifest(repo_root / "data", source)
    if entry is None:
        return IngestFreshness(
            is_fresh=False, last_ingest_at=None,
            observed_age=timedelta.max, max_age=max_age, source=source,
        )
    try:
        last = datetime.fromisoformat(entry.last_run_at)
    except ValueError:
        return IngestFreshness(
            is_fresh=False, last_ingest_at=None,
            observed_age=timedelta.max, max_age=max_age, source=source,
        )
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = now - last
    return IngestFreshness(
        is_fresh=age <= max_age, last_ingest_at=last,
        observed_age=age, max_age=max_age, source=source,
    )


def _format_age(td: timedelta) -> str:
    if td == timedelta.max:
        return "unknown"
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def _write_stale_marker(
    repo_root: Path, stage: str, freshness: IngestFreshness,
) -> Path:
    """Write outputs/<date>/STALE_INGEST.md describing the freshness gap."""
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = repo_root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    last_str = (
        freshness.last_ingest_at.isoformat()
        if freshness.last_ingest_at is not None else "never"
    )
    body = (
        f"# STALE INGEST — {today}\n\n"
        f"**Stage:** `{stage}`\n\n"
        f"**Source:** `{freshness.source}`\n\n"
        f"**Max age:** {freshness.max_age}\n\n"
        f"**Last ingest at:** {last_str}\n\n"
        f"**Observed age:** {_format_age(freshness.observed_age)}\n\n"
        f"**Remediation:**\n"
        f"Re-run `irc ingest --repo-root .` to refresh prices/NAV. To proceed "
        f"with stale data (artifacts will still be tagged), set "
        f"`IRC_ALLOW_STALE=1` and re-run the stage.\n\n"
        f"**Generated at:** "
        f"{datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "STALE_INGEST.md"
    atomic_write_text(path, body)
    return path


def require_fresh_ingest(
    repo_root: Path, stage: str, *,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> bool:
    """Returns True iff the stage may proceed. Writes STALE_INGEST.md when stale.

    Default behavior: stale ingest blocks the stage (returns False after writing
    the marker). When IRC_ALLOW_STALE is truthy, the stage proceeds but the
    marker is still written for transparency.
    """
    freshness = check_ingest_freshness(repo_root, max_age=max_age)
    if freshness.is_fresh:
        return True
    _write_stale_marker(repo_root, stage, freshness)
    return _allow_stale_env()
```

### Step 1.4: Run tests, verify pass
- [ ] Run: `uv run pytest tests/data/test_freshness.py -v`
- [ ] Expected: all PASS.

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/data/freshness.py tests/data/test_freshness.py
git commit -m "feat(data): ingest freshness check + STALE_INGEST.md marker"
```

---

## Task 2: Wire `require_fresh_ingest` into the three stages

**Files:** `src/irc/commands/gold_cmd.py:40`, `opportunity_cmd.py:329`, `memo_cmd.py:81`

### Step 2.1: Write the failing test for gold_cmd
- [ ] Find the existing gold test pattern in `tests/commands/test_gold_cmd.py`. Add:

```python
def test_gold_refuses_to_run_when_ingest_is_stale(repo_with_gold_data, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, gold exits without producing
    artifacts and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    # Overwrite the manifest with a stale timestamp.
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))

    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_gold(str(repo))
    assert rc == 1
    markers = list((repo / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_gold_allow_stale_env_proceeds(repo_with_gold_data, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    rc = run_gold(str(repo))
    assert rc == 0  # proceeds with stale data
    assert (repo / "outputs" / next(iter((repo / "outputs").iterdir())).name
            / "STALE_INGEST.md").exists()
```

> If `repo_with_gold_data` doesn't exist as a fixture name, find the actual fixture used by the existing gold tests and adapt. The two assertions are the important part.

### Step 2.2: Run the new test, confirm failure
- [ ] Run: `uv run pytest tests/commands/test_gold_cmd.py -k "stale" -v`
- [ ] Expected: FAILs — gold currently does no freshness check.

### Step 2.3: Wire into `gold_cmd.py`
- [ ] In `src/irc/commands/gold_cmd.py`, add to imports:

```python
from irc.data.freshness import require_fresh_ingest
```

Then at the very top of `run_gold(repo_root: str) -> int` (line 40):

```python
def run_gold(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="gold"):
        print("ERROR: gold stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    # ... rest of existing body ...
```

### Step 2.4: Wire the same into `opportunity_cmd.py:329` and `memo_cmd.py:81`
- [ ] Same pattern — `require_fresh_ingest(root, stage="opportunity")` at top of `run_opportunity`, and `require_fresh_ingest(root, stage="memo")` at top of `run_memo`. Same error print + `return 1` when False.

### Step 2.5: Add analogous tests for opportunity_cmd and memo_cmd
- [ ] Mirror the gold test (stale → rc=1 + marker; allow-stale → rc=0 + marker). Use the existing test fixtures in `tests/commands/test_opportunity_cmd.py` and `tests/commands/test_memo_cmd.py`.

### Step 2.6: Run the new tests + existing stage tests
- [ ] Run: `uv run pytest tests/commands/test_gold_cmd.py tests/commands/test_opportunity_cmd.py tests/commands/test_memo_cmd.py -v`
- [ ] Expected: new tests PASS. Existing stage tests may now FAIL because their fixtures don't write a fresh manifest. Fix by either:
  - Having the existing fixtures write a fresh akshare manifest as part of setup, OR
  - Adding `monkeypatch.setenv("IRC_ALLOW_STALE", "1")` to existing tests that don't care about freshness.

Pick the first option where the fixture is shared (cleaner), the second for one-off tests.

### Step 2.7: Run full suite
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS after fixture adjustments.

### Step 2.8: Commit
- [ ] Run:

```bash
git add src/irc/commands/gold_cmd.py src/irc/commands/opportunity_cmd.py src/irc/commands/memo_cmd.py tests/commands/
git commit -m "feat(stages): gate gold/opportunity/memo on ingest freshness (IRC_ALLOW_STALE override)"
```

---

## Task 3: Ruff + final verification

### Step 3.1: Ruff
- [ ] Run: `uv run ruff check src/irc/data/freshness.py src/irc/commands/ tests/data/ tests/commands/`
- [ ] Expected: no new findings.

### Step 3.2: Full suite final
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS.
