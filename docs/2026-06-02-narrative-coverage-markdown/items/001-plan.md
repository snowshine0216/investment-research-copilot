# Active-fund autobuild in `narrative --analyze` + fix misleading error string — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build-and-cache an `ActiveFundSnapshot` for narrative-discovered `cn_equity_fund` shortlist funds (in the command layer of `irc narrative --analyze`) so the existing read-only `analyze_fund` loads it and produces a real thesis instead of `position_risk_level = insufficient`; and correct the misleading `irc fundamentals snapshot` error string.

**Architecture:** Effects-at-edges. A new thin helper module `src/irc/commands/narrative_autobuild.py` owns the fetch/build/cache-write I/O (mirroring `opportunity_cmd.py:840`). It is invoked from `_run_analyze` in `narrative_cmd.py` just ahead of the per-fund `analyze_fund` loop. `analyze_fund` stays untouched and read-only — its existing `load_active_fund_cache(iid, quarter, data_dir)` call transparently picks up the freshly-written cache. The probe uses the **resolved analyze-context quarter** (the exact quarter `analyze_fund` reads) for idempotence. `FetchBudgetExceeded` / `_fetch_budget` are reused from `opportunity_cmd.py`; a new independent kill-switch `IRC_NARRATIVE_AUTOBUILD` (default `"1"`) disables it. The narrative path stays Policy-B-free (supply the snapshot only).

**Tech Stack:** Python 3.12, uv, pytest, frozen dataclasses + `dataclasses.replace`, DuckDB, Click. No live network in unit tests (monkeypatch the builder edge).

---

## Background facts (verified by reading the code — do NOT re-derive)

- `narrative_cmd.run_narrative` → `_run_analyze(root, shortlist, *, db_path, quarter, role)` →
  `_open_analyze_context(root, db_path, quarter)` returns `(con, provider, resolved_quarter, instr_index)` or `None`.
  (`src/irc/commands/narrative_cmd.py:86-116`, `:71-83`.)
- `analyze_fund(shortlist_row, *, instr, con, provider, quarter, data_dir, role)` is **read-only**; it calls
  `load_active_fund_cache(iid, quarter, data_dir)` (`src/irc/narrative/analyze.py:92-109`). **Do not modify it.**
- `ShortlistRow` exposes `.instrument_id`, `.name_cn`, `.asset_class` (`src/irc/narrative/schemas.py:66-72`).
- Cache probe (public): `load_active_fund_cache(fund_id: str, quarter: str, root: Path) -> ActiveFundSnapshot | None`
  (`src/irc/fundamentals/snapshot_cache.py:234-246`). `root` is the `data/` dir.
- Cache write (public): `write_active_fund_cache(snap: ActiveFundSnapshot, root: Path) -> Path`
  (`src/irc/fundamentals/snapshot_cache.py:221-231`). Path is `root/"fundamentals"/quarter/"active_fund"/f"fund_{fund_id}.json"`; an empty `source_report_quarter` collapses the path → must skip the write.
- Builder (public): `build_snapshot(target, *, top_n=10, as_of_iso="", provider=None) -> ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot`
  (`src/irc/fundamentals/snapshot.py:242-280`). For `target.kind == "active_fund"` it returns `ActiveFundSnapshot`.
- Look-through target: `map_lookthrough(inp: OpportunityInput) -> LookthroughTarget`
  (`src/irc/opportunity/lookthrough.py:80`); for `inp.asset_class == "cn_equity_fund"` it returns
  `LookthroughTarget(kind="active_fund", key=f"fund_{iid}", display_cn=name_cn, provider_symbol=iid)`
  (`:88-95`). For the autobuild we build this target **directly** (no `_build_input`/DB needed) — see Task 2.
- `LookthroughTarget(kind, key, display_cn, provider_symbol="")` (frozen) — `src/irc/fundamentals/types.py:41-45`.
- `ActiveFundSnapshot` fields: `fund_id, source_report_date, source_report_quarter, cache_probed_at, constituent_analyses, failure_reasons_by_symbol, fund_level_failure_reasons=(), fund_level_evidence=()` (frozen) — `src/irc/fundamentals/types.py:232-244`.
- Reusable budget seam in `opportunity_cmd.py`: `TOP_N_DEFAULT = 10` (`:84`), `class FetchBudgetExceeded(RuntimeError)`
  (`:110`), `def _fetch_budget() -> int` reading `IRC_FETCH_BUDGET` default `2000` (`:219-223`),
  `class FetchPlan` with `.total_calls()` (`:89-107`) — `per_active = 1 + top_n*3 + 4`.
- Opportunity kill-switch pattern: `os.environ.get("IRC_OPPORTUNITY_AUTOBUILD", "1") != "0"` (`:208-209`).
- Existing narrative tests live at `tests/narrative/test_narrative_cmd.py` and `tests/narrative/test_analyze.py`
  (the `narrative_cmd` source is under `commands/` but its tests are under `tests/narrative/`). New
  narrative_cmd / autobuild tests go under `tests/narrative/` to match.

---

## File Structure

- **Create:** `src/irc/commands/narrative_autobuild.py` — the effects-at-edges autobuild helper module
  (env reader, budget guard, per-fund build/cache-write, batch driver). Keeps `narrative_cmd.py` under 200 lines.
- **Create:** `tests/narrative/test_narrative_autobuild.py` — unit tests for the helper (AC1, AC2, AC4, AC5, AC6, AC7, AC10).
- **Modify:** `src/irc/commands/narrative_cmd.py` — call the batch driver in `_run_analyze` before the per-fund loop; correct the error string at `:157-161`.
- **Modify:** `tests/narrative/test_narrative_cmd.py` — wiring + idempotence + error-string + behavioural tests (AC3, AC8, AC9, AC11).

---

## Task 1: New module skeleton + env kill-switch reader (AC4 partial)

**Files:**
- Create: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

- [ ] **Step 1: Write the failing test for the env kill-switch reader**

Create `tests/narrative/test_narrative_autobuild.py`:

```python
from __future__ import annotations

from irc.commands import narrative_autobuild as NA


def test_autobuild_on_default_true(monkeypatch) -> None:
    monkeypatch.delenv("IRC_NARRATIVE_AUTOBUILD", raising=False)
    assert NA._narrative_autobuild_on() is True


def test_autobuild_off_when_env_zero(monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    assert NA._narrative_autobuild_on() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_autobuild_on_default_true -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.commands.narrative_autobuild'`.

- [ ] **Step 3: Create the module with the env reader**

Create `src/irc/commands/narrative_autobuild.py`:

```python
from __future__ import annotations

import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from irc.commands.opportunity_cmd import (
    TOP_N_DEFAULT,
    FetchBudgetExceeded,
    FetchPlan,
    _fetch_budget,
)
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot, LookthroughTarget
from irc.narrative.schemas import ShortlistRow

_log = logging.getLogger(__name__)


def _narrative_autobuild_on() -> bool:
    """Independent kill-switch; default-on, IRC_NARRATIVE_AUTOBUILD=0 disables."""
    return os.environ.get("IRC_NARRATIVE_AUTOBUILD", "1") != "0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(narrative): IRC_NARRATIVE_AUTOBUILD kill-switch reader"
```

---

## Task 2: Eligibility + look-through target builder (AC1)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

Eligibility is decided **before** any I/O. A row is eligible iff `asset_class == "cn_equity_fund"`.
We build the look-through target directly (it is equal to what `map_lookthrough` returns for
`cn_equity_fund`, but effect-free and DB-free): `LookthroughTarget(kind="active_fund",
key=f"fund_{iid}", display_cn=name_cn, provider_symbol=iid)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
from irc.fundamentals.types import LookthroughTarget  # noqa: E402
from irc.narrative.schemas import Holding, OverlapResult, ShortlistRow  # noqa: E402


def _shortlist_row(iid: str, asset_class: str = "cn_equity_fund") -> ShortlistRow:
    ov = OverlapResult(basket_weight_pct=22.0, overlap_count=3,
                       matched_symbols=(), industry_credit_symbols=())
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class=asset_class,
        overlap=ov,
        holdings=(Holding(symbol="601899", name_cn="紫金矿业", weight_pct=38.0),),
    )


def test_eligible_only_for_cn_equity_fund() -> None:
    assert NA._is_eligible(_shortlist_row("000A", "cn_equity_fund")) is True
    assert NA._is_eligible(_shortlist_row("000B", "cn_etf")) is False
    assert NA._is_eligible(_shortlist_row("000C", "qdii_us")) is False


def test_target_for_row_matches_active_fund_shape() -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    assert target == LookthroughTarget(
        kind="active_fund", key="fund_000A", display_cn="fund-000A",
        provider_symbol="000A",
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_eligible_only_for_cn_equity_fund -v`
Expected: FAIL — `AttributeError: module 'irc.commands.narrative_autobuild' has no attribute '_is_eligible'`.

- [ ] **Step 3: Implement the two pure helpers**

Add to `src/irc/commands/narrative_autobuild.py` (after `_narrative_autobuild_on`):

```python
_ACTIVE_ASSET_CLASS = "cn_equity_fund"


def _is_eligible(row: ShortlistRow) -> bool:
    """Eligibility gate decided before any I/O (AC1)."""
    return row.asset_class == _ACTIVE_ASSET_CLASS


def _target_for_row(row: ShortlistRow) -> LookthroughTarget:
    """Effect-free; equals map_lookthrough(inp) for a cn_equity_fund row."""
    iid = row.instrument_id
    return LookthroughTarget(
        kind="active_fund", key=f"fund_{iid}",
        display_cn=row.name_cn, provider_symbol=iid,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(narrative): eligibility gate + active_fund target builder"
```

---

## Task 3: Per-fund build + cache-write helper (AC5, AC6 partial)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

This is the only place that touches the builder + cache write. Shape mirrors
`opportunity_cmd.py:868-884`: `build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)`,
`isinstance(..., ActiveFundSnapshot)` guard, write only when `source_report_quarter` is non-empty
(skip on empty quarter to avoid path-collapse), stamp `cache_probed_at` via `replace(...)`.
A build that raises, returns non-`ActiveFundSnapshot`, or yields empty `source_report_quarter`
is degraded (logged, no write) — never crashes (AC6). `today_iso` is passed in (no hidden clock).

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
from irc.fundamentals.types import ActiveFundSnapshot  # noqa: E402


def _snap(fund_id: str, quarter: str) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )


def test_build_one_writes_cache_with_probed_at(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, top_n, provider: _snap("000A", "2026Q1"))
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append((snap, root)))
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert len(written) == 1
    snap, root = written[0]
    assert snap.cache_probed_at == "2026-06-02"
    assert root == tmp_path


def test_build_one_skips_write_on_empty_quarter(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, top_n, provider: _snap("000A", ""))
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert written == []  # empty quarter → no write (path-collapse guard)


def test_build_one_swallows_builder_exception(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))

    def _boom(t, *, top_n, provider):
        raise RuntimeError("akshare down")

    monkeypatch.setattr(NA, "build_snapshot", _boom)
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append(snap))
    # must NOT raise
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert written == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_build_one_writes_cache_with_probed_at -v`
Expected: FAIL — `AttributeError: ... has no attribute '_build_and_cache_one'`.

- [ ] **Step 3: Implement the per-fund helper**

Add to `src/irc/commands/narrative_autobuild.py`:

```python
def _build_and_cache_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Effects edge: build one ActiveFundSnapshot and cache-write it.

    Degrades on any failure (logged, no write); never raises. Mirrors
    opportunity_cmd.py:868-884. Skips the write on empty source_report_quarter
    to avoid the data/fundamentals//active_fund path-collapse.
    """
    try:
        snap = build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)
    except Exception as exc:  # degrade — never crash the run (AC6)
        _log.warning("narrative_autobuild: build failed for %s — %s",
                     target.provider_symbol, exc)
        return
    if not isinstance(snap, ActiveFundSnapshot):
        return
    if not snap.source_report_quarter:
        _log.warning("narrative_autobuild: empty quarter for %s — skip write",
                     target.provider_symbol)
        return
    to_cache = replace(snap, cache_probed_at=today_iso)
    try:
        write_active_fund_cache(to_cache, data_dir)
    except Exception as cache_exc:  # disk error is environmental — degrade
        sys.stderr.write(
            f"cache_write_failed:{target.provider_symbol}:"
            f"{type(cache_exc).__name__}\n"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(narrative): per-fund build + cache-write helper (degrade, never crash)"
```

---

## Task 4: Batch driver — cache-presence gate + budget guard (AC1, AC2, AC4, AC7)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

The public entry point. Signature:
`autobuild_active_funds(shortlist, *, provider, quarter, data_dir, today_iso) -> None`.

Behaviour (in order):
1. If kill-switch off → return immediately (no I/O).
2. Compute `eligible_missing` = rows that are `_is_eligible` AND have **no** cached snapshot for the
   **resolved quarter** via `load_active_fund_cache(iid, quarter, data_dir)` (AC2 — same quarter the
   consumer reads; no `_load_latest_active_fund_cached` import).
3. **Pre-build budget guard** (AC7): estimate `FetchPlan(active_fund_misses=len(eligible_missing),
   active_fund_stale=0, passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT).total_calls()`; if it
   exceeds `_fetch_budget()`, raise `FetchBudgetExceeded(plan, total, budget)` **before** any build.
   The `fetch_budget_exhausted` sentinel is NEVER written into a row.
4. For each `eligible_missing` row → `_build_and_cache_one(...)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
import pytest  # noqa: E402


def test_skips_etf_rows_builds_only_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    shortlist = (
        _shortlist_row("000A", "cn_equity_fund"),
        _shortlist_row("000B", "cn_etf"),
    )
    NA.autobuild_active_funds(shortlist, provider=object(), quarter="2026Q1",
                              data_dir=tmp_path, today_iso="2026-06-02")
    assert built == ["000A"]  # cn_etf never built (AC1)


def test_skips_when_resolved_quarter_cache_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    # cache hit for the resolved quarter → zero builds (AC2)
    monkeypatch.setattr(NA, "load_active_fund_cache",
                        lambda iid, q, root: _snap(iid, q))
    NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                              quarter="2026Q1", data_dir=tmp_path,
                              today_iso="2026-06-02")
    assert built == []


def test_kill_switch_disables_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                              quarter="2026Q1", data_dir=tmp_path,
                              today_iso="2026-06-02")
    assert built == []  # AC4


def test_budget_guard_raises_before_any_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "1")  # per_active = 1 + 10*3 + 4 = 35 > 1
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                                  quarter="2026Q1", data_dir=tmp_path,
                                  today_iso="2026-06-02")
    assert built == []  # raised BEFORE any build (AC7)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_skips_etf_rows_builds_only_active -v`
Expected: FAIL — `AttributeError: ... has no attribute 'autobuild_active_funds'`.

- [ ] **Step 3: Implement the batch driver**

Add to `src/irc/commands/narrative_autobuild.py`:

```python
def _eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *, quarter: str, data_dir: Path,
) -> tuple[ShortlistRow, ...]:
    """Eligible rows with NO cached snapshot for the RESOLVED quarter (AC2)."""
    out: list[ShortlistRow] = []
    for row in shortlist:
        if not _is_eligible(row):
            continue
        if load_active_fund_cache(row.instrument_id, quarter, data_dir) is None:
            out.append(row)
    return tuple(out)


def autobuild_active_funds(
    shortlist: tuple[ShortlistRow, ...], *, provider: object, quarter: str,
    data_dir: Path, today_iso: str,
) -> None:
    """Command-layer narrative active-fund autobuild (effects edge).

    No-op when IRC_NARRATIVE_AUTOBUILD=0. Builds + caches an ActiveFundSnapshot
    for each eligible cn_equity_fund row missing a resolved-quarter cache.
    Raises FetchBudgetExceeded BEFORE any fetch when the estimate exceeds budget.
    """
    if not _narrative_autobuild_on():
        return
    missing = _eligible_missing(shortlist, quarter=quarter, data_dir=data_dir)
    if not missing:
        return
    plan = FetchPlan(
        active_fund_misses=len(missing), active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT,
    )
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for row in missing:
        _build_and_cache_one(
            _target_for_row(row), provider=provider, data_dir=data_dir,
            today_iso=today_iso,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Verify the module is under 200 lines and lints**

Run: `uv run ruff check src/irc/commands/narrative_autobuild.py`
Expected: no errors.
Run: `python -c "print(sum(1 for _ in open('src/irc/commands/narrative_autobuild.py')))"`
Expected: a number < 200.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(narrative): batch autobuild driver — cache-presence gate + budget guard"
```

---

## Task 5: Wire the autobuild into `_run_analyze` (AC3, AC11 wiring)

**Files:**
- Modify: `src/irc/commands/narrative_cmd.py:86-116` (the `_run_analyze` body)
- Test: `tests/narrative/test_narrative_cmd.py`

`_run_analyze` already opens the context `(con, provider, resolved_quarter, instr_index)`. Call
`autobuild_active_funds(...)` with the resolved quarter **before** the per-fund `analyze_fund` loop.
`analyze_fund` is unchanged — its `load_active_fund_cache(iid, resolved_quarter, data_dir)` picks up the
freshly-written cache (AC3). Use the existing `_today()` for `today_iso`.

- [ ] **Step 1: Write the failing wiring test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
def test_analyze_invokes_autobuild_with_resolved_quarter(tmp_path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    calls: list = []
    monkeypatch.setattr(
        narrative_cmd, "autobuild_active_funds",
        lambda shortlist, *, provider, quarter, data_dir, today_iso:
        calls.append((tuple(r.instrument_id for r in shortlist), provider, quarter)),
    )
    # analyze_fund stays read-only; stub it to a known report
    expensive = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金", position_risk_level="high",
        risk_rationale="r", risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review", falsification_triggers=(), trim_triggers=(),
        review_cadence="weekly_light_monthly_full", evidence_gaps=(),
        thesis_evidence=(_evidence("000A"),),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund", lambda row, **k: expensive)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 0
    assert len(calls) == 1
    ids, provider, quarter = calls[0]
    assert ids == ("000A",)
    assert provider == "PROV"
    assert quarter == "2026Q1"  # resolved-context quarter, not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_invokes_autobuild_with_resolved_quarter -v`
Expected: FAIL — `AttributeError: <module 'irc.commands.narrative_cmd'> does not have the attribute 'autobuild_active_funds'`.

- [ ] **Step 3: Import and call the driver in `_run_analyze`**

In `src/irc/commands/narrative_cmd.py`, add the import after the existing `from irc.narrative.analyze import ...` block (around line 15):

```python
from irc.commands.narrative_autobuild import autobuild_active_funds
```

Then modify `_run_analyze` (`:90-94`) — after unpacking the context, before the `for row in shortlist:` loop:

```python
    ctx = _open_analyze_context(root, db_path, quarter)
    if ctx is None:
        return None
    con, provider, resolved_quarter, instr_index = ctx
    autobuild_active_funds(
        shortlist, provider=provider, quarter=resolved_quarter,
        data_dir=root / "data", today_iso=_today(),
    )
    reports: list[NarrativeFundReport] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_invokes_autobuild_with_resolved_quarter -v`
Expected: PASS.

- [ ] **Step 5: Verify existing narrative_cmd + analyze tests still pass (AC3)**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py tests/narrative/test_analyze.py -v`
Expected: ALL PASS (the existing suites are unmodified by the wiring; AC3 = `analyze_fund` untouched).

Note: existing tests that monkeypatch `_open_analyze_context` to a tuple but do NOT stub
`autobuild_active_funds` will now invoke the real driver. That is safe — the real driver calls
`load_active_fund_cache` (returns `None` for the empty temp repo) then `build_snapshot`, which hits
AkShare. **To keep those green and network-free, also stub `autobuild_active_funds` in them.** Add a
no-op stub to the two existing analyze tests that set up a tuple context:
`test_analyze_renders_real_citations` and `test_analyze_per_fund_error_yields_partial_results`:

```python
    monkeypatch.setattr(narrative_cmd, "autobuild_active_funds",
                        lambda *a, **k: None)
```

Insert that line right after each `monkeypatch.setattr(narrative_cmd, "_open_analyze_context", ...)`
in those two tests. Re-run:
Run: `uv run pytest tests/narrative/test_narrative_cmd.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(narrative): run active-fund autobuild before --analyze per-fund loop"
```

---

## Task 6: Correct the misleading error string (AC9)

**Files:**
- Modify: `src/irc/commands/narrative_cmd.py:156-162`
- Test: `tests/narrative/test_narrative_cmd.py`

The error fires when `_open_analyze_context` returns `None` (no `data/local.duckdb` or no discoverable
quarter — autobuild cannot even start). The new message must: name `irc ingest` (DuckDB) and a snapshot
quarter under `data/fundamentals/`; state active-fund snapshots are auto-built during a successful
`--analyze`; and **drop** the `irc fundamentals snapshot` instruction.

- [ ] **Step 1: Write the failing test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
def test_analyze_missing_db_error_string_is_corrected(tmp_path, monkeypatch, capsys) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: None)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "irc ingest" in err
    assert "data/fundamentals/" in err
    assert "auto-built" in err
    assert "fundamentals snapshot" not in err  # the bonus-bug instruction is gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_missing_db_error_string_is_corrected -v`
Expected: FAIL — current message contains `run \`irc fundamentals snapshot\`` so the `"fundamentals snapshot" not in err` assertion fails.

- [ ] **Step 3: Rewrite the error string**

In `src/irc/commands/narrative_cmd.py`, replace the `if reports is None:` block (`:156-162`):

```python
        if reports is None:
            print(
                f"ERROR: --analyze needs data/local.duckdb (run `irc ingest`) and a "
                f"snapshot quarter under data/fundamentals/. Active-fund snapshots are "
                f"auto-built during a successful --analyze (set IRC_NARRATIVE_AUTOBUILD=0 "
                f"to disable); if none exist yet, run `irc opportunity` once or re-run "
                f"--analyze online. Shortlist written to {out}.",
                file=sys.stderr,
            )
            return 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_missing_db_error_string_is_corrected -v`
Expected: PASS.

- [ ] **Step 5: Verify the existing missing-db test still passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_missing_db_writes_screen_then_errors -v`
Expected: PASS (still rc==2, screen written, no report).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git commit -m "fix(narrative): correct misleading --analyze prerequisite error string"
```

---

## Task 7: Idempotence — byte-identical report across two runs (AC8)

**Files:**
- Test: `tests/narrative/test_narrative_cmd.py`

This is a behavioural assertion over the wiring already built. Run 1 populates the cache (one build);
run 2 finds the resolved-quarter cache present and performs zero builds; both report JSONs are
byte-identical. We use the **real** `autobuild_active_funds` but stub only the `build_snapshot` edge so
no network is hit; the cache write/read is exercised end-to-end against `tmp_path`.

- [ ] **Step 1: Write the failing test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
def test_analyze_idempotent_second_run_zero_builds(tmp_path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    # analyze_fund stays read-only; deterministic report regardless of cache
    expensive = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金", position_risk_level="high",
        risk_rationale="r", risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review", falsification_triggers=(), trim_triggers=(),
        review_cadence="weekly_light_monthly_full", evidence_gaps=(),
        thesis_evidence=(_evidence("000A"),),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund", lambda row, **k: expensive)

    # stub ONLY the builder edge inside the real autobuild module
    from irc.commands import narrative_autobuild as NA
    from irc.fundamentals.types import ActiveFundSnapshot
    build_count = {"n": 0}

    def _fake_build(target, *, top_n, provider):
        build_count["n"] += 1
        return ActiveFundSnapshot(
            fund_id="000A", source_report_date="2026-03-31",
            source_report_quarter="2026Q1", cache_probed_at="",
            constituent_analyses=(), failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(NA, "build_snapshot", _fake_build)

    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=True, out_dir=str(out_dir))
    first = (out_dir / "compute_metals_report.json").read_text()
    assert build_count["n"] == 1  # first run built once

    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=True, out_dir=str(out_dir))
    second = (out_dir / "compute_metals_report.json").read_text()
    assert build_count["n"] == 1  # second run: cache present → zero new builds (AC8)
    assert first == second  # byte-identical report JSON
```

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_idempotent_second_run_zero_builds -v`
Expected: PASS if Tasks 4-5 are correct (cache write/read + presence gate work). If it FAILS on
`build_count == 1` for the second run, the resolved-quarter presence gate is broken — fix
`_eligible_missing` / the quarter passed from `_run_analyze` (must be `resolved_quarter`, not `quarter`).

- [ ] **Step 3: Commit**

```bash
git add tests/narrative/test_narrative_cmd.py
git commit -m "test(narrative): idempotent --analyze (cache reuse, byte-identical report)"
```

---

## Task 8: Behavioural recovery — active fund deepened, not screened (AC11)

**Files:**
- Test: `tests/narrative/test_narrative_cmd.py`

Through the full `run_narrative(analyze=True)` path with a stubbed `build_snapshot` returning a
non-empty `ActiveFundSnapshot`, the produced report for the `cn_equity_fund` fund carries a non-empty
`thesis_evidence` and a `thesis_state != "evidence_insufficient"` — i.e. the fund is deepened, not
screened. Here we do **not** stub `analyze_fund`; we let it run for real against the cache the autobuild
wrote, exercising `load_active_fund_cache → build_opportunity_row → derive_thesis_from_evidence`.

This requires a real `OpportunityInput` build inside `analyze_fund` (it calls `_build_input(... con ...)`).
Since `con` is the stub `"CON"` string, stub `_build_input` and `build_opportunity_row` **inside the
analyze module** to keep it DB-free while still proving the snapshot flows through. Mirror
`tests/narrative/test_analyze.py::test_analyze_fund_wires_cache_and_builder`.

- [ ] **Step 1: Write the failing test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
def test_analyze_recovers_active_fund_with_real_thesis(tmp_path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))

    # autobuild edge: build a non-empty active-fund snapshot that gets cached
    from irc.commands import narrative_autobuild as NA
    from irc.fundamentals.types import (
        ActiveFundSnapshot, ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )

    def _fake_build(target, *, top_n, provider):
        ev = ThesisEvidence(
            type="filing", source="601899", url="", date="2026-03-31",
            summary="601899 2026Q1 财报已披露（口径未核实）", scope="constituent",
            citation_kind="data", owner_instrument_id="000A",
            parent_fund_id="000A", constituent_key="601899",
        )
        return ActiveFundSnapshot(
            fund_id="000A", source_report_date="2026-03-31",
            source_report_quarter="2026Q1", cache_probed_at="",
            constituent_analyses=(ConstituentAnalysis(
                symbol="601899", name_cn="紫金矿业", weight_pct=20.0,
                evidence=(ev,), failure_reasons=(), one_line_view="x"),),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(NA, "build_snapshot", _fake_build)

    # keep analyze_fund DB-free: stub its _build_input + build_opportunity_row so the
    # REAL cache load (load_active_fund_cache) is what supplies the snapshot.
    from irc.narrative import analyze as A

    def _fake_row(inp, tt, *, snapshot, theme_report):
        assert snapshot is not None  # the autobuilt cache must be loaded
        return _row("000A")  # local helper below

    monkeypatch.setattr(A, "_build_input", lambda *a, **k: object())
    monkeypatch.setattr(A, "build_opportunity_row", _fake_row)

    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                     analyze=True, out_dir=str(out_dir))
    assert rc == 0
    report = json.loads((out_dir / "compute_metals_report.json").read_text())
    fund = report["funds"][0]
    assert fund["thesis_state"] != "evidence_insufficient"
    assert fund.get("thesis_evidence")  # non-empty → deepened, not screened (AC11)
```

Add this `_row` + `LookthroughTarget`/`ConstituentAnalysis` import helper near the top of the test
file (after `_evidence`), mirroring `tests/narrative/test_analyze.py:18-32`:

```python
from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget  # noqa: E402
from irc.opportunity.types import OpportunityRow  # noqa: E402


def _row(iid: str) -> OpportunityRow:
    return OpportunityRow(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class="cn_equity_fund",
        theme="metals",
        lookthrough_target=LookthroughTarget(kind="active_fund", key=iid,
                                             display_cn=f"fund-{iid}"),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="small_watch",
        opportunity_reason="逻辑完整", evidence_gaps=(),
        thesis_evidence=(_evidence(iid),),
        constituent_analyses=(ConstituentAnalysis(
            symbol="601899", name_cn="紫金矿业", weight_pct=20.0,
            evidence=(), failure_reasons=(), one_line_view="x"),),
    )
```

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_recovers_active_fund_with_real_thesis -v`
Expected: PASS if the autobuilt cache is correctly written + loaded by the real `analyze_fund`. If the
inner `assert snapshot is not None` fails, the cache was not written (check `source_report_quarter` /
`data_dir` threading in Task 5) or `load_active_fund_cache` is reading a different quarter than the
autobuild wrote (AC2 idempotence bug).

- [ ] **Step 3: Commit**

```bash
git add tests/narrative/test_narrative_cmd.py
git commit -m "test(narrative): active fund recovered with real thesis end-to-end"
```

---

## Task 9: Forbidden-indicator + sentinel guards (AC10 grep posture; no-sentinel reaffirm)

**Files:**
- Test: `tests/narrative/test_narrative_autobuild.py`

Two cheap acceptance guards: (a) the new module must never reference the forbidden `基金概况` indicator;
(b) the new module must never write the `fetch_budget_exhausted` sentinel string into any output. Both
are source-grep tests in the spirit of the project's existing acceptance greps.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
from pathlib import Path as _Path  # noqa: E402


def test_module_has_no_forbidden_indicator() -> None:
    src = _Path("src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "基金概况" not in src


def test_module_never_writes_budget_exhausted_sentinel() -> None:
    src = _Path("src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "fetch_budget_exhausted" not in src
```

- [ ] **Step 2: Run tests to verify they pass (already green)**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_module_has_no_forbidden_indicator tests/narrative/test_narrative_autobuild.py::test_module_never_writes_budget_exhausted_sentinel -v`
Expected: PASS (the module written in Tasks 1-4 contains neither literal). If either FAILS, remove the
offending literal — neither belongs in this module.

- [ ] **Step 3: Commit**

```bash
git add tests/narrative/test_narrative_autobuild.py
git commit -m "test(narrative): guard against 基金概况 indicator + budget sentinel in autobuild"
```

---

## Task 10: Full-suite verification + lint (all ACs)

**Files:** none (verification only).

- [ ] **Step 1: Run the full narrative + commands test suites**

Run: `uv run pytest tests/narrative tests/commands/test_opportunity_cmd.py -q`
Expected: ALL PASS. (We touch the shared `opportunity_cmd` import surface only by importing public
symbols — `test_opportunity_cmd.py` is the regression canary for that seam.)

- [ ] **Step 2: Run the analyze unit suite (AC3 — analyze_fund unchanged)**

Run: `uv run pytest tests/narrative/test_analyze.py -v`
Expected: ALL PASS, unchanged from baseline.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100; if a long string in Task 6 / Task 1 trips E501, wrap it
across adjacent string literals — do not change wording).

- [ ] **Step 4: Confirm size budget**

Run: `python -c "import pathlib; [print(p, sum(1 for _ in open(p))) for p in ['src/irc/commands/narrative_autobuild.py','src/irc/commands/narrative_cmd.py']]"`
Expected: both files < 200 lines.

- [ ] **Step 5: Final commit (if any lint wraps were applied)**

```bash
git add -A
git commit -m "chore(narrative): lint + size-budget cleanup for autobuild"
```

---

## Acceptance Criteria → Test Map

| AC | Requirement | Test(s) |
|----|-------------|---------|
| 1 | Eligibility by active asset class (`cn_equity_fund` only) | `test_eligible_only_for_cn_equity_fund`, `test_skips_etf_rows_builds_only_active` |
| 2 | Cache-presence gate via **resolved quarter** (no refetch) | `test_skips_when_resolved_quarter_cache_present` |
| 3 | Effects at edges; `analyze_fund` unchanged | Task 5 Step 5 (`test_analyze.py` passes unmodified) + Task 10 Step 2 |
| 4 | Default-on with `IRC_NARRATIVE_AUTOBUILD` kill-switch | `test_autobuild_on_default_true`, `test_autobuild_off_when_env_zero`, `test_kill_switch_disables_build` |
| 5 | Build + cache-write shape mirrors opportunity; skip empty quarter | `test_build_one_writes_cache_with_probed_at`, `test_build_one_skips_write_on_empty_quarter` |
| 6 | Per-fund failure degrades, never crashes | `test_build_one_swallows_builder_exception`, `test_analyze_per_fund_error_yields_partial_results` (existing) |
| 7 | Fetch budget enforced pre-build; no row sentinel | `test_budget_guard_raises_before_any_build`, `test_module_never_writes_budget_exhausted_sentinel` |
| 8 | Determinism / idempotence (byte-identical, zero 2nd-run builds) | `test_analyze_idempotent_second_run_zero_builds` |
| 9 | Corrected error string | `test_analyze_missing_db_error_string_is_corrected` |
| 10 | No live network in unit tests; forbidden-indicator guard | All new tests monkeypatch the builder edge; `test_module_has_no_forbidden_indicator` |
| 11 | Recovers active funds end-to-end (behavioural) | `test_analyze_recovers_active_fund_with_real_thesis` |

---

## Constraints checklist (enforced by this plan)

- **Effects at edges:** all fetch/build/cache-write lives in `narrative_autobuild.py` + `_run_analyze`; `analyze_fund` stays read-only (AC3).
- **Frozen dataclasses + `replace`:** `cache_probed_at` stamped via `replace(snap, cache_probed_at=today_iso)` (Task 3) — never in-place.
- **No live network in unit tests:** every test monkeypatches `build_snapshot` / `_build_and_cache_one` / `autobuild_active_funds`; no `pytest.mark.live_akshare` test added (none needed for this item).
- **No `基金概况`:** Task 9 grep guard; this item reuses `build_snapshot` unchanged and adds no fetch calls.
- **No `fetch_budget_exhausted` in rows:** budget tripped via `FetchBudgetExceeded` raise before build; Task 9 grep guard.
- **Policy-B-free narrative path:** the autobuild supplies the snapshot only; it never imports/calls `evaluate_policy_b`, `_stamp_audit_errors_from_verdict`, or `_stamp_fund_level_evidence_from_verdict` (CONTEXT.md "Narrative path is Policy-B-free").
- **Size budget:** new module + modified `narrative_cmd.py` both verified < 200 lines (Task 4 Step 5, Task 10 Step 4); functions ≤ ~15 lines each.
- **Reused seams:** `TOP_N_DEFAULT`, `FetchBudgetExceeded`, `FetchPlan`, `_fetch_budget` imported from `opportunity_cmd.py` (the legitimate shared budget seam per grill Q-G8); the private `_load_latest_active_fund_cached` is **not** imported (grill Q-G7).

## Spec-gap judgment calls (flagged for reviewer)

1. **`FetchPlan`/`_fetch_budget`/`FetchBudgetExceeded` import from `opportunity_cmd.py`** (Constraints §,
   grill Q-G8): the grill resolves to *reuse the public symbols*. They live in `opportunity_cmd.py`, so
   the new module imports from there. This creates a `narrative_autobuild → opportunity_cmd` dependency.
   It is acceptable (public symbols, same as importing any shared module) and explicitly endorsed by
   Q-G8, in contrast to the *private* `_load_latest_active_fund_cached` which Q-G7 forbids importing.
2. **Target built directly, not via `map_lookthrough(_build_input(...))`** (spec AC5 / resolved-Q #8 say
   "`target = map_lookthrough(inp)`"): the spec text references `map_lookthrough(inp)`, but `inp` requires
   a DuckDB `con` and `_build_input` (effectful). Since `map_lookthrough` for `cn_equity_fund` is a pure,
   total function of `(instrument_id, asset_class, name_cn)` (lookthrough.py:88-95, confirmed by grill
   Q-G5 as unconditional routing), building the identical `LookthroughTarget` directly in
   `_target_for_row` is byte-equivalent and avoids dragging the DB/`_build_input` into the budget-gated
   pre-loop. Verified equal by `test_target_for_row_matches_active_fund_shape`. Flagged in case the
   reviewer prefers calling `map_lookthrough` on a hand-built `OpportunityInput` skeleton instead.
3. **Existing analyze tests need a no-op `autobuild_active_funds` stub** (Task 5 Step 5): not an AC, but a
   consequence of wiring the real driver into `_run_analyze`. Two existing tests that build a tuple
   context without stubbing the driver would otherwise reach `build_snapshot` (network). The plan adds the
   no-op stub to keep them network-free; this is a test-hygiene change, not a behaviour change.
