# Item 002 — Passive-ETF fund-level + `theme_report` wiring into `analyze_fund` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover `robots_report`'s passive `cn_etf`/QDII funds in `irc narrative <name> --analyze` by autobuilding + caching fund-level `FundLevelSnapshot`s in the commands layer and teaching `analyze_fund` to read them (active vs fund-level dispatch on the resolved `LookthroughTarget.kind`).

**Architecture:** Effects stay at the edges. A new passive autobuild edge in `src/irc/commands/narrative_autobuild.py` (mirroring item 001's `autobuild_active_funds`) resolves each shortlist row's `LookthroughTarget` via `map_lookthrough(_build_input(...))` using the **instrument index**, gates fund-level-eligible+`provider_symbol` rows that lack a cached `nav/` snapshot (latest-`nav/`-quarter scan), and `build_snapshot → write_nav_cache`. `analyze_fund` gains a `< 20`-line read-only reader helper that dispatches on `target.kind`: `active_fund → load_active_fund_cache`; fund-level → latest-`nav/` `FundLevelSnapshot` load. Both feed `build_opportunity_row(snapshot=..., theme_report=None)`; the existing dual-leg gate (`derive_thesis_from_evidence` `FundLevelSnapshot` branch) yields the real `thesis_state`. `theme_report` stays `None` (the gate never reads it — RD-1). One shared preflight `FetchPlan` covers both autobuild edges (RD-7a). `build_opportunity_row`'s `snapshot` annotation is widened to include `FundLevelSnapshot` (RD-6a).

**Tech Stack:** Python 3.12, uv, pytest, ruff, frozen dataclasses + `dataclasses.replace`, DuckDB (read-only, stubbed in unit tests), AkShare (never hit — `build_snapshot`/cache edges monkeypatched).

---

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `src/irc/commands/narrative_autobuild.py` | Add the passive fund-level autobuild edge + shared-budget refactor. ~120 lines today → keep < 200. | Modify |
| `src/irc/narrative/analyze.py` | Add a read-only `_load_snapshot_for_row` reader dispatching on `target.kind`; wire it into `analyze_fund`. | Modify |
| `src/irc/commands/narrative_cmd.py` | Call `autobuild_fund_level_funds` alongside `autobuild_active_funds` in `_run_analyze`, after the shared-budget preflight. | Modify |
| `src/irc/opportunity/states.py` | Widen `build_opportunity_row`'s `snapshot` annotation to include `FundLevelSnapshot` (RD-6a). | Modify |
| `tests/narrative/test_narrative_autobuild.py` | Unit tests for the passive eligibility predicate, cache-presence gate, build+cache helper, budget. | Modify |
| `tests/narrative/test_analyze.py` | Unit tests for `analyze_fund`'s fund-level read-side dispatch. | Modify |
| `tests/narrative/test_narrative_cmd.py` | E2E `_run_analyze` tests: dual-leg recovery, partial-evidence, kill-switch, idempotence, active-path regression. | Modify |
| `tests/opportunity/test_states.py` | Annotation-widening regression (RD-6a). | Modify |

**Pattern anchors (read before editing):**
- Active autobuild to mirror: `src/irc/commands/narrative_autobuild.py:92-119` (`autobuild_active_funds`).
- Fund-level dispatch to mirror: `src/irc/commands/opportunity_cmd.py:909-924` (predicate) + `:342-384` (`_resolve_fund_level_snapshot`) + `:311-324` (`_load_latest_nav_cached`).
- Dispatch keys: `src/irc/fundamentals/snapshot.py:237-280` (`_FUND_LEVEL_KINDS`, `build_snapshot`).
- Gate: `src/irc/opportunity/thesis_evidence.py:348-373` (`FundLevelSnapshot` branch).
- Eligibility resolution: `src/irc/opportunity/lookthrough.py:80-164` (`map_lookthrough`) + `src/irc/opportunity/inputs_build.py:14-56` (`_build_input` reads `instr.theme`/`instr.tracked_index`).

---

## AC → Task/test map (14 ACs)

| AC | Task | Test(s) |
|----|------|---------|
| 1 Fund-level eligibility by resolved kind | T2 | `test_fund_level_eligible_only_for_provider_symbol_kinds` |
| 2 Eligibility before any I/O (instr-resolved) | T1, T2 | `test_fund_level_target_resolves_via_instr_no_io` |
| 3 Cache-presence gate (latest-`nav/` scan, no refetch) | T4 | `test_fund_level_skips_when_nav_cache_present` |
| 4 Effects at edges (`analyze_fund` reads only) | T6, T7 | `test_analyze_fund_fund_level_issues_no_build` |
| 5 `analyze_fund` dispatches on kind | T6 | `test_load_snapshot_for_row_dispatches_fund_level`, `test_load_snapshot_for_row_dispatches_active` |
| 6 Dual-leg gate → real `thesis_state` (Policy-B-free) | T8 | `test_analyze_recovers_passive_etf_with_real_thesis` |
| 7 Partial-evidence honesty | T8 | `test_analyze_passive_one_leg_is_insufficient` |
| 8 Default-on, shared kill-switch | T5 | `test_passive_kill_switch_disables_build` |
| 9 Build + cache-write shape mirrors opportunity | T3 | `test_fund_level_build_one_writes_nav_cache`, `test_fund_level_build_one_skips_qdii_sentinel` |
| 10 Per-fund failure degrades, never crashes | T3, T8 | `test_fund_level_build_one_swallows_exception`, `test_analyze_passive_build_failure_degrades` |
| 11 Fetch budget enforced pre-build (shared plan) | T5 | `test_shared_budget_guard_raises_before_any_build` |
| 12 Determinism / idempotence | T8 | `test_passive_analyze_idempotent_second_run_zero_builds` |
| 13 No live network in unit tests | all | every new test stubs `build_snapshot`/cache edges (no AkShare) |
| 14 Active path unchanged; suites green | T6, T9 | `test_load_snapshot_for_row_dispatches_active` + existing suites |

---

### Task 1 (RD-6a): Widen `build_opportunity_row`'s `snapshot` annotation

**Files:**
- Modify: `src/irc/opportunity/states.py:526`
- Test: `tests/opportunity/test_states.py`

The annotation at `states.py:526` is `ConstituentSnapshot | ActiveFundSnapshot | None` but production (`opportunity_cmd.py:930-935`) already passes a `FundLevelSnapshot` and the gate handles it. Widen so the narrative caller passes one cleanly. `FundLevelSnapshot` is already imported at `states.py:8`.

- [ ] **Step 1: Write the failing test**

Append to `tests/opportunity/test_states.py`:

```python
def test_build_opportunity_row_snapshot_annotation_includes_fund_level() -> None:
    """RD-6a: the snapshot param must declare FundLevelSnapshot (production passes one)."""
    import typing

    from irc.fundamentals.types import FundLevelSnapshot
    from irc.opportunity.states import build_opportunity_row

    hints = typing.get_type_hints(build_opportunity_row)
    assert FundLevelSnapshot in typing.get_args(hints["snapshot"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_states.py::test_build_opportunity_row_snapshot_annotation_includes_fund_level -v`
Expected: FAIL — `FundLevelSnapshot` not in the `Union` args.

- [ ] **Step 3: Widen the annotation**

In `src/irc/opportunity/states.py`, change line 526 from:

```python
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | None = None,
```

to:

```python
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | FundLevelSnapshot | None = None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_states.py::test_build_opportunity_row_snapshot_annotation_includes_fund_level -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "refactor(002): widen build_opportunity_row snapshot annotation to include FundLevelSnapshot (RD-6a)"
```

---

### Task 2: Passive fund-level eligibility predicate + instr-resolved target (AC1, AC2)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py` (add imports + two helpers)
- Test: `tests/narrative/test_narrative_autobuild.py`

`ShortlistRow` carries no `theme`/`tracked_index` (RD-3), so the predicate must resolve the target via `map_lookthrough(_build_input(...))`, deriving `(asset_class, theme, tracked_index)` from the in-memory `Instrument` — no DB round-trip, no fetch.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py` (after the existing imports / `_shortlist_row` helper):

```python
from irc.schemas.universe import Instrument  # noqa: E402


def _instr(iid: str, asset_class: str, *, tracked_index=None, theme=None) -> Instrument:
    return Instrument(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class=asset_class,
        market="cn_off_exchange", tracked_index=tracked_index, theme=theme,
    )


def test_fund_level_eligible_only_for_provider_symbol_kinds(monkeypatch) -> None:
    # us_etf → qdii_us with provider_symbol → eligible
    us = _instr("000U", "us_etf")
    assert NA._fund_level_eligible_target(_shortlist_row("000U", "us_etf"), us, con=object()) \
        is not None
    # cn_equity_fund → active_fund → NOT a fund-level kind → ineligible
    act = _instr("000A", "cn_equity_fund")
    assert NA._fund_level_eligible_target(_shortlist_row("000A", "cn_equity_fund"), act,
                                          con=object()) is None
    # qdii row WITHOUT a tracked_index/theme/provider_symbol → terminal default
    # (broad_index "unknown" carries no provider_symbol) → ineligible
    bare = _instr("000Z", "cn_etf")  # bare cn_etf → terminal default, no provider_symbol
    assert NA._fund_level_eligible_target(_shortlist_row("000Z", "cn_etf"), bare,
                                          con=object()) is None


def test_fund_level_target_resolves_via_instr_no_io() -> None:
    # tracked_index drives the resolution; instr carries the routing keys (RD-3).
    instr = _instr("000B", "cn_etf", tracked_index="csi300")
    target = NA._fund_level_eligible_target(_shortlist_row("000B", "cn_etf"), instr,
                                            con=object())
    assert target is not None
    assert target.provider_symbol == "000B"  # provider_symbol = instrument_id
    assert target.kind in NA._FUND_LEVEL_KINDS or target.kind in (
        "qdii_us", "qdii_hk", "qdii_global",
    )
```

> Note: `tracked_index="csi300"` must be a key recognised by `map_lookthrough` (`_BROAD_INDEX_DISPLAY`/`_QDII_*` at `lookthrough.py`). If `csi300` is not in those maps it falls to the unknown-index branch (`lookthrough.py:153-155`) which still sets `broad_index` + `provider_symbol` → eligible. Verify the chosen key resolves to a `provider_symbol`-bearing target before finalising the test value; any tracked index works because the unknown-index branch keeps `provider_symbol`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_fund_level_eligible_only_for_provider_symbol_kinds tests/narrative/test_narrative_autobuild.py::test_fund_level_target_resolves_via_instr_no_io -v`
Expected: FAIL — `AttributeError: module 'irc.commands.narrative_autobuild' has no attribute '_fund_level_eligible_target'`.

- [ ] **Step 3: Add imports + the predicate helper**

In `src/irc/commands/narrative_autobuild.py`, extend the existing import block. Replace:

```python
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot, LookthroughTarget
from irc.narrative.schemas import ShortlistRow
```

with:

```python
import duckdb

from irc.fundamentals.snapshot import _FUND_LEVEL_KINDS, build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
    write_nav_cache,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    FundLevelSnapshot,
    LookthroughTarget,
)
from irc.opportunity.inputs_build import _build_input
from irc.opportunity.lookthrough import map_lookthrough
from irc.narrative.schemas import ShortlistRow
from irc.schemas.universe import Instrument

_QDII_KINDS = ("qdii_us", "qdii_hk", "qdii_global")
```

Then add the predicate helper (place it just after `_target_for_row`, near line 45):

```python
def _fund_level_eligible_target(
    row: ShortlistRow, instr: Instrument | None,
    *, con: duckdb.DuckDBPyConnection,
) -> LookthroughTarget | None:
    """Resolve the row's LookthroughTarget via map_lookthrough; return it only
    when fund-level-eligible AND it carries a provider_symbol (AC1/AC2, RD-3).

    Effect-free apart from `_build_input` (in-memory `instr`-driven; no fetch).
    cn_equity_fund routes to active_fund (item 001's domain) → excluded.
    """
    score_row = {"instrument_id": row.instrument_id, "asset_class": row.asset_class}
    inp = _build_input(score_row, instr, None, None, 0.0, set(), con,
                       provider=None)  # type: ignore[arg-type]
    target = map_lookthrough(inp)
    eligible_kind = target.kind in _QDII_KINDS or target.kind in _FUND_LEVEL_KINDS
    if eligible_kind and target.provider_symbol:
        return target
    return None
```

> `_build_input` only uses `provider` to construct the `OpportunityInput` skeleton's downstream fields; the `map_lookthrough` decision reads only `asset_class`/`theme`/`tracked_index`/`instrument_id`/`name_cn`, all instr-derived. Passing `provider=None` is safe here because no provider-dependent field is consulted for the eligibility decision; if a future `_build_input` change touches the provider on this path, pass the real provider through (it is already available in `_run_analyze`). Confirm during green that `_build_input(..., provider=None)` does not raise for a fund-level instr.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_fund_level_eligible_only_for_provider_symbol_kinds tests/narrative/test_narrative_autobuild.py::test_fund_level_target_resolves_via_instr_no_io -v`
Expected: PASS (both).

> If `_build_input(..., provider=None)` raises, change the helper signature to take `provider` and thread it from the caller (T5), and update the test's `con=object()` calls to also pass `provider=object()`. Prefer threading the real provider over `None` if green is not clean.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(002): instr-resolved passive fund-level eligibility predicate (AC1/AC2)"
```

---

### Task 3: `_build_and_cache_fund_level_one` build+cache helper (AC9, AC10)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

Mirrors `opportunity_cmd._resolve_fund_level_snapshot:374-384` write-gate: write only when `source_report_quarter` is non-empty AND `"qdii_information_unavailable" not in snap.evidence_gaps`. Builds via `build_snapshot(target, provider=provider)` (no `top_n`). Degrades on any failure; re-raises `FetchBudgetExceeded`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
from irc.fundamentals.types import (  # noqa: E402
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
)


def _fund_level_snap(fund_id: str, quarter: str, *, sentinel: bool = False) -> FundLevelSnapshot:
    if sentinel:
        return FundLevelSnapshot(
            fund_id=fund_id, nav_report=None, announcements=(), evidence=(),
            source_report_quarter=quarter, cache_probed_at="",
            evidence_gaps=("qdii_information_unavailable",),
        )
    nav_ev = ThesisEvidence(
        type="snapshot", source=fund_id, url="", date="2026-03-15",
        summary="NAV=4.5 @ 2026-03-15", scope="instrument", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=None, constituent_key=None,
    )
    info_ev = ThesisEvidence(
        type="filing", source=fund_id, url="", date="2026-03-20",
        summary="分红公告", scope="instrument", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=None, constituent_key=None,
    )
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=FundNavReport(
            fund_id=fund_id, fund_name=fund_id, latest_nav=4.5,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 4.5),), source_report_quarter=quarter,
        ),
        announcements=(FundAnnouncement(
            fund_id=fund_id, title="x", topic="dividend", date="2026-03-20",
            report_id="AN1"),),
        evidence=(nav_ev, info_ev),
        source_report_quarter=quarter, cache_probed_at="",
    )


def _passive_target(iid: str) -> LookthroughTarget:
    return LookthroughTarget(kind="broad_index", key=iid, display_cn=f"etf-{iid}",
                             provider_symbol=iid)


def test_fund_level_build_one_writes_nav_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000B", "2026Q1"))
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append((snap, root)))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert len(written) == 1
    snap, root = written[0]
    assert snap.cache_probed_at == "2026-06-02"  # replace(), frozen-safe
    assert root == tmp_path


def test_fund_level_build_one_skips_qdii_sentinel(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000Q", "2026Q1",
                                                                sentinel=True))
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000Q"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # qdii_information_unavailable gap → no write


def test_fund_level_build_one_skips_empty_quarter(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000B", ""))
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # empty quarter → no write (path-collapse guard, AC9)


def test_fund_level_build_one_swallows_exception(tmp_path, monkeypatch) -> None:
    def _boom(t, *, provider):
        raise RuntimeError("akshare down")

    monkeypatch.setattr(NA, "build_snapshot", _boom)
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # AC10 — degrades, never raises


def test_fund_level_build_one_skips_non_fund_level_snapshot(tmp_path, monkeypatch) -> None:
    # builder returns the wrong type → no write, no crash
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _snap("000B", "2026Q1"))  # ActiveFundSnapshot
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []


def test_fund_level_build_one_reraises_fetch_budget(tmp_path, monkeypatch) -> None:
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan

    plan = FetchPlan(active_fund_misses=0, active_fund_stale=0, passive_misses=0,
                     passive_stale=0, top_n=10, fund_level_misses=1)

    def _budget_boom(t, *, provider):
        raise FetchBudgetExceeded(plan, 4, 1)

    monkeypatch.setattr(NA, "build_snapshot", _budget_boom)
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: None)
    with pytest.raises(FetchBudgetExceeded):
        NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                           data_dir=tmp_path, today_iso="2026-06-02")
```

> Ensure `ThesisEvidence` is imported at the top of the test file (add `from irc.fundamentals.types import ThesisEvidence` if absent).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k fund_level_build_one -v`
Expected: FAIL — `_build_and_cache_fund_level_one` not defined.

- [ ] **Step 3: Implement the helper**

Add to `src/irc/commands/narrative_autobuild.py` (after `_build_and_cache_one`):

```python
def _build_and_cache_fund_level_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Effects edge: build one FundLevelSnapshot and cache-write it under nav/.

    Mirrors opportunity_cmd._resolve_fund_level_snapshot:374-384. Skips the write
    on the QDII sentinel (qdii_information_unavailable gap) or an empty
    source_report_quarter (path-collapse guard). Degrades on any failure (logged,
    no write); re-raises FetchBudgetExceeded.
    """
    try:
        snap = build_snapshot(target, provider=provider)
    except FetchBudgetExceeded:
        raise
    except Exception as exc:  # degrade — never crash the run (AC10)
        _log.warning("narrative_autobuild: fund-level build failed for %s — %s",
                     target.provider_symbol, exc)
        return
    if not isinstance(snap, FundLevelSnapshot):
        return
    if "qdii_information_unavailable" in snap.evidence_gaps or not snap.source_report_quarter:
        _log.warning("narrative_autobuild: no cacheable fund-level snapshot for %s",
                     target.provider_symbol)
        return
    to_cache = replace(snap, cache_probed_at=today_iso)
    try:
        write_nav_cache(to_cache, data_dir)
    except Exception as cache_exc:  # disk error is environmental — degrade
        _log.error("narrative_autobuild: nav cache write failed for %s — %s",
                   target.provider_symbol, cache_exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k fund_level_build_one -v`
Expected: PASS (all six).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(002): _build_and_cache_fund_level_one (build + nav-cache write, AC9/AC10)"
```

---

### Task 4: `_fund_level_eligible_missing` — latest-`nav/`-quarter cache-presence gate (AC3)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

The presence probe is a latest-`nav/` scan (`root/fundamentals/*/nav/fund_{id}.json`), NOT a fixed-quarter `load_nav_cache(id, quarter)` — fund-level quarters are NAV-derived and unknowable pre-fetch (RD-4). Reuse `opportunity_cmd._load_latest_nav_cached`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
def test_fund_level_missing_excludes_cached_nav(tmp_path, monkeypatch) -> None:
    instr_idx = {
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
        "000C": _instr("000C", "cn_etf", tracked_index="csi300"),
    }
    shortlist = (_shortlist_row("000B", "cn_etf"), _shortlist_row("000C", "cn_etf"))
    # 000B has a cached nav snapshot; 000C does not.
    monkeypatch.setattr(
        NA, "_load_latest_nav_cached",
        lambda fund_id, root: _fund_level_snap("000B", "2026Q1") if fund_id == "000B" else None,
    )
    missing = NA._fund_level_eligible_missing(shortlist, instr_index=instr_idx,
                                              con=object(), data_dir=tmp_path)
    assert tuple(t.provider_symbol for _, t in missing) == ("000C",)


def test_fund_level_missing_excludes_active_and_bare_rows(tmp_path, monkeypatch) -> None:
    instr_idx = {
        "000A": _instr("000A", "cn_equity_fund"),
        "000Z": _instr("000Z", "cn_etf"),  # bare → terminal default, no provider_symbol
    }
    shortlist = (_shortlist_row("000A", "cn_equity_fund"), _shortlist_row("000Z", "cn_etf"))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    missing = NA._fund_level_eligible_missing(shortlist, instr_index=instr_idx,
                                              con=object(), data_dir=tmp_path)
    assert missing == ()  # active → item 001; bare cn_etf → no provider_symbol
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k fund_level_missing -v`
Expected: FAIL — `_fund_level_eligible_missing` not defined.

- [ ] **Step 3: Implement the gate + import `_load_latest_nav_cached`**

Extend the `irc.commands.opportunity_cmd` import in `narrative_autobuild.py`. Replace:

```python
from irc.commands.opportunity_cmd import (
    TOP_N_DEFAULT,
    FetchBudgetExceeded,
    FetchPlan,
    _fetch_budget,
)
```

with:

```python
from irc.commands.opportunity_cmd import (
    TOP_N_DEFAULT,
    FetchBudgetExceeded,
    FetchPlan,
    _fetch_budget,
    _load_latest_nav_cached,
)
```

Add the gate helper (after `_eligible_missing`):

```python
def _fund_level_eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *,
    instr_index: dict[str, Instrument], con: duckdb.DuckDBPyConnection,
    data_dir: Path,
) -> tuple[tuple[ShortlistRow, LookthroughTarget], ...]:
    """Fund-level-eligible rows with NO cached nav/ snapshot (latest-nav scan, AC3)."""
    out: list[tuple[ShortlistRow, LookthroughTarget]] = []
    for row in shortlist:
        target = _fund_level_eligible_target(
            row, instr_index.get(row.instrument_id), con=con,
        )
        if target is None:
            continue
        if _load_latest_nav_cached(target.provider_symbol, data_dir) is None:
            out.append((row, target))
    return tuple(out)
```

> `_load_latest_nav_cached(fund_id, root)` scans `root/fundamentals/...`. In `_run_analyze` the active autobuild already passes `data_dir=root / "data"`; pass the same `root / "data"` here so the scan hits `data/fundamentals/*/nav/`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k fund_level_missing -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(002): _fund_level_eligible_missing (latest-nav cache-presence gate, AC3)"
```

---

### Task 5 (RD-7a): `autobuild_fund_level_funds` + shared preflight `FetchPlan` (AC8, AC11)

**Files:**
- Modify: `src/irc/commands/narrative_autobuild.py`
- Test: `tests/narrative/test_narrative_autobuild.py`

Add the public passive autobuild and a shared-budget orchestrator so the active + passive misses are checked once (RD-7a): a combined run cannot pass two independent sub-budget checks that jointly exceed budget. The kill-switch is the existing `IRC_NARRATIVE_AUTOBUILD` (AC8).

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
def test_passive_autobuild_builds_eligible_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
        "000A": _instr("000A", "cn_equity_fund"),
    }
    shortlist = (_shortlist_row("000B", "cn_etf"), _shortlist_row("000A", "cn_equity_fund"))
    NA.autobuild_fund_level_funds(shortlist, provider=object(), instr_index=instr_idx,
                                  con=object(), data_dir=tmp_path, today_iso="2026-06-02")
    assert built == ["000B"]  # active row never built by the passive path (AC14)


def test_passive_kill_switch_disables_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                  instr_index=instr_idx, con=object(),
                                  data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC8


def test_passive_skips_when_nav_cache_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached",
                        lambda fund_id, root: _fund_level_snap(fund_id, "2026Q1"))
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                  instr_index=instr_idx, con=object(),
                                  data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC3 — cache present → zero builds


def test_shared_budget_guard_raises_before_any_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "1")  # per_fund_level = 4 > 1
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                      instr_index=instr_idx, con=object(),
                                      data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC11 — raised pre-build


def test_shared_budget_counts_active_and_fund_level_together(tmp_path, monkeypatch) -> None:
    # RD-7a: one shared plan. 1 active (35) + 1 fund_level (4) = 39; budget 38 → raise.
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "38")
    abuilt: list[str] = []
    fbuilt: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: abuilt.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: fbuilt.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {
        "000A": _instr("000A", "cn_equity_fund"),
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
    }
    shortlist = (_shortlist_row("000A", "cn_equity_fund"), _shortlist_row("000B", "cn_etf"))
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_narrative(shortlist, provider=object(), instr_index=instr_idx,
                               con=object(), quarter="2026Q1", data_dir=tmp_path,
                               today_iso="2026-06-02")
    assert abuilt == [] and fbuilt == []  # both sub-paths blocked pre-build
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k "passive_ or shared_budget" -v`
Expected: FAIL — `autobuild_fund_level_funds` / `autobuild_narrative` not defined.

- [ ] **Step 3: Implement the passive autobuild + shared orchestrator**

Refactor `narrative_autobuild.py` so the budget check is shared. Replace the existing `autobuild_active_funds` body's budget block by extracting the misses+plan, and add the passive + combined functions. First, add a small plan builder + the passive function (after `autobuild_active_funds`):

```python
def autobuild_fund_level_funds(
    shortlist: tuple[ShortlistRow, ...], *, provider: object,
    instr_index: dict[str, Instrument], con: duckdb.DuckDBPyConnection,
    data_dir: Path, today_iso: str,
) -> None:
    """Command-layer narrative passive fund-level autobuild (effects edge, AC8).

    No-op when IRC_NARRATIVE_AUTOBUILD=0. Builds + caches a FundLevelSnapshot for
    each fund-level-eligible row missing a cached nav/ snapshot. Raises
    FetchBudgetExceeded BEFORE any fetch when the estimate exceeds budget (AC11).
    """
    if not _narrative_autobuild_on():
        return
    missing = _fund_level_eligible_missing(
        shortlist, instr_index=instr_index, con=con, data_dir=data_dir,
    )
    if not missing:
        return
    plan = FetchPlan(
        active_fund_misses=0, active_fund_stale=0, passive_misses=0,
        passive_stale=0, top_n=TOP_N_DEFAULT, fund_level_misses=len(missing),
    )
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for _row, target in missing:
        _build_and_cache_fund_level_one(
            target, provider=provider, data_dir=data_dir, today_iso=today_iso,
        )
```

Then add the shared orchestrator (RD-7a) so a combined run is budget-checked once:

```python
def autobuild_narrative(
    shortlist: tuple[ShortlistRow, ...], *, provider: object,
    instr_index: dict[str, Instrument], con: duckdb.DuckDBPyConnection,
    quarter: str, data_dir: Path, today_iso: str,
) -> None:
    """Single shared-budget preflight over BOTH narrative autobuild edges (RD-7a).

    No-op when IRC_NARRATIVE_AUTOBUILD=0. Computes one combined FetchPlan
    (active_fund_misses=Na, fund_level_misses=Np), raises FetchBudgetExceeded once
    pre-fetch, then runs both build loops. Avoids two independent sub-budget checks
    that jointly exceed budget.
    """
    if not _narrative_autobuild_on():
        return
    active_missing = _eligible_missing(shortlist, quarter=quarter, data_dir=data_dir)
    fund_level_missing = _fund_level_eligible_missing(
        shortlist, instr_index=instr_index, con=con, data_dir=data_dir,
    )
    if not active_missing and not fund_level_missing:
        return
    plan = FetchPlan(
        active_fund_misses=len(active_missing), active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT,
        fund_level_misses=len(fund_level_missing),
    )
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for row in active_missing:
        _build_and_cache_one(
            _target_for_row(row), provider=provider, data_dir=data_dir,
            today_iso=today_iso,
        )
    for _row, target in fund_level_missing:
        _build_and_cache_fund_level_one(
            target, provider=provider, data_dir=data_dir, today_iso=today_iso,
        )
```

> `autobuild_active_funds` and `autobuild_fund_level_funds` stay as standalone functions for unit-test isolation; `autobuild_narrative` is the production entry point that shares one budget. This keeps each function < 20 lines. If `narrative_autobuild.py` approaches 200 lines after these additions, split the passive helpers into `narrative_autobuild_passive.py` (per the spec Constraints) and re-import; verify the line count in the final ruff/scope step.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py -k "passive_ or shared_budget" -v`
Expected: PASS (all five).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/narrative_autobuild.py tests/narrative/test_narrative_autobuild.py
git commit -m "feat(002): autobuild_fund_level_funds + shared-budget autobuild_narrative (AC8/AC11, RD-7a)"
```

---

### Task 6: `analyze_fund` read-side dispatch on `target.kind` (AC4, AC5, AC14)

**Files:**
- Modify: `src/irc/narrative/analyze.py`
- Test: `tests/narrative/test_analyze.py`

`analyze_fund` stays read-only. Extract a `< 20`-line `_load_snapshot_for_row` reader that dispatches on the resolved `target.kind`: `active_fund → load_active_fund_cache`; fund-level → latest-`nav/` `FundLevelSnapshot` load. The selected snapshot feeds `build_opportunity_row(snapshot=..., theme_report=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_analyze.py`:

```python
from irc.fundamentals.types import FundLevelSnapshot, FundNavReport  # noqa: E402
from irc.opportunity.types import OpportunityInput  # noqa: E402


def _inp(iid: str, asset_class: str, *, tracked_index=None, theme=None) -> OpportunityInput:
    return OpportunityInput(
        instrument_id=iid, asset_class=asset_class, market="cn_off_exchange",
        theme=theme, tracked_index=tracked_index, name_cn=f"fund-{iid}", role="r",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )


def _fund_level_snap(iid: str) -> FundLevelSnapshot:
    return FundLevelSnapshot(
        fund_id=iid, nav_report=FundNavReport(
            fund_id=iid, fund_name=iid, latest_nav=4.5, latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 4.5),), source_report_quarter="2026Q1"),
        announcements=(), evidence=(_evidence(iid),),
        source_report_quarter="2026Q1", cache_probed_at="2026-06-02",
    )


def test_load_snapshot_for_row_dispatches_active(monkeypatch) -> None:
    calls = {"active": 0, "nav": 0}
    monkeypatch.setattr(A, "load_active_fund_cache",
                        lambda iid, q, root: calls.__setitem__("active", calls["active"] + 1))
    monkeypatch.setattr(A, "_load_latest_nav_cached",
                        lambda iid, root: calls.__setitem__("nav", calls["nav"] + 1))
    inp = _inp("000A", "cn_equity_fund")
    A._load_snapshot_for_row(inp, quarter="2026Q1",
                             data_dir=__import__("pathlib").Path("/tmp"))
    assert calls == {"active": 1, "nav": 0}  # AC5/AC14 — active loader only


def test_load_snapshot_for_row_dispatches_fund_level(monkeypatch) -> None:
    calls = {"active": 0, "nav": 0}
    monkeypatch.setattr(A, "load_active_fund_cache",
                        lambda iid, q, root: calls.__setitem__("active", calls["active"] + 1))
    monkeypatch.setattr(A, "_load_latest_nav_cached",
                        lambda iid, root: (calls.__setitem__("nav", calls["nav"] + 1),
                                           _fund_level_snap("000B"))[1])
    inp = _inp("000B", "cn_etf", tracked_index="csi300")
    snap = A._load_snapshot_for_row(inp, quarter="2026Q1",
                                    data_dir=__import__("pathlib").Path("/tmp"))
    assert calls == {"active": 0, "nav": 1}  # fund-level loader only
    assert isinstance(snap, FundLevelSnapshot)


def test_analyze_fund_fund_level_issues_no_build(monkeypatch) -> None:
    """AC4 — analyze_fund reads only; never invokes build_snapshot."""
    import irc.fundamentals.snapshot as S

    def _no_build(*a, **k):
        raise AssertionError("analyze_fund must not build")

    monkeypatch.setattr(S, "build_snapshot", _no_build)
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_load_latest_nav_cached", lambda iid, root: _fund_level_snap("000B"))
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _inp("000B", "cn_etf",
                                                                tracked_index="csi300"))
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000B"))
    rpt = A.analyze_fund(
        _shortlist_row("000B"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"), role="r",
    )
    assert rpt.instrument_id == "000B"
```

> `_shortlist_row` in `test_analyze.py` hardcodes `asset_class="cn_equity_fund"`; for the fund-level test the dispatch is driven by the **`inp` from `_build_input`** (stubbed to `cn_etf`), so the existing `_shortlist_row` is fine. The `_row("000B")` helper builds an `OpportunityRow` (existing helper accepts an arbitrary iid).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_analyze.py -k "load_snapshot_for_row or fund_level_issues_no_build" -v`
Expected: FAIL — `_load_snapshot_for_row` / `_load_latest_nav_cached` not present in `analyze` module.

- [ ] **Step 3: Implement the reader + rewire `analyze_fund`**

In `src/irc/narrative/analyze.py`, extend the imports. Replace:

```python
from irc.fundamentals.provider import CnFundamentalsProvider
from irc.fundamentals.snapshot_cache import load_active_fund_cache
```

with:

```python
from irc.commands.opportunity_cmd import _load_latest_nav_cached
from irc.fundamentals.provider import CnFundamentalsProvider
from irc.fundamentals.snapshot import _FUND_LEVEL_KINDS
from irc.fundamentals.snapshot_cache import load_active_fund_cache
from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot
from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityInput
```

> Import cycle check: `analyze.py` already imports from `irc.opportunity.*`; `irc.commands.opportunity_cmd` imports from `irc.opportunity.*` and `irc.fundamentals.*` but NOT from `irc.narrative.*`, and `narrative_cmd` imports `analyze` lazily-after `opportunity_cmd`. Confirm `uv run python -c "import irc.narrative.analyze"` succeeds at green; if a cycle surfaces, move `_load_latest_nav_cached` into `irc/fundamentals/snapshot_cache.py` (its natural home) and import from there instead — it has no opportunity_cmd dependency.

Add the reader helper (before `analyze_fund`):

```python
_QDII_KINDS = ("qdii_us", "qdii_hk", "qdii_global")


def _load_snapshot_for_row(
    inp: OpportunityInput, *, quarter: str, data_dir: Path,
) -> ActiveFundSnapshot | FundLevelSnapshot | None:
    """Read-only snapshot loader; dispatches on the resolved lookthrough kind.

    active_fund → load_active_fund_cache(fixed analyze-context quarter).
    fund-level / QDII (w/ provider_symbol) → latest-nav/ FundLevelSnapshot scan.
    Performs NO fetch (AC4)."""
    target = map_lookthrough(inp)
    if target.kind == "active_fund":
        return load_active_fund_cache(inp.instrument_id, quarter, data_dir)
    if (target.kind in _QDII_KINDS or target.kind in _FUND_LEVEL_KINDS) and target.provider_symbol:
        return _load_latest_nav_cached(target.provider_symbol, data_dir)
    return None
```

Rewrite the body of `analyze_fund` (lines 104-109) — change only the snapshot load:

```python
    iid = shortlist_row.instrument_id
    score_row = {"instrument_id": iid, "asset_class": shortlist_row.asset_class, "role": role}
    inp = _build_input(score_row, instr, None, None, 0.0, set(), con, provider=provider)
    snapshot = _load_snapshot_for_row(inp, quarter=quarter, data_dir=data_dir)
    row = build_opportunity_row(inp, None, snapshot=snapshot, theme_report=None)
    return _report_from_card(row, shortlist_row, role=role)
```

> `_load_latest_nav_cached(fund_id, root)` scans `root/fundamentals/...`; `analyze_fund` receives `data_dir = root / "data"` from `_run_analyze`, so the scan resolves to `data/fundamentals/*/nav/`. This matches the autobuild's write path (T4 note) → same quarter, idempotent (RD-4).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_analyze.py -k "load_snapshot_for_row or fund_level_issues_no_build" -v`
Expected: PASS (three).

- [ ] **Step 5: Run the full analyze test file (active path regression, AC14)**

Run: `uv run pytest tests/narrative/test_analyze.py -v`
Expected: PASS — including the existing `test_analyze_fund_wires_cache_and_builder` (it stubs `load_active_fund_cache` + `build_opportunity_row`, and the new `_load_snapshot_for_row` still routes `cn_equity_fund` → `load_active_fund_cache`).

> The existing `test_analyze_fund_wires_cache_and_builder` stubs `A._build_input` to `object()`. `_load_snapshot_for_row` now calls `map_lookthrough(inp)` which needs a real `OpportunityInput`. UPDATE that test: change the `_build_input` stub to return a real `cn_equity_fund` `OpportunityInput` (use the new `_inp` helper) so `map_lookthrough` routes to `active_fund`. Make this edit in this step:

```python
def test_analyze_fund_wires_cache_and_builder(monkeypatch) -> None:
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _inp("000A", "cn_equity_fund"))
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000A"))
    rpt = A.analyze_fund(
        _shortlist_row("000A"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"),
        role="satellite_cn_metals",
    )
    assert rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id
```

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/analyze.py tests/narrative/test_analyze.py
git commit -m "feat(002): analyze_fund read-side dispatch on lookthrough kind (AC4/AC5/AC14)"
```

---

### Task 7: Wire `autobuild_narrative` into `_run_analyze` (AC4, AC8, AC11)

**Files:**
- Modify: `src/irc/commands/narrative_cmd.py:88-124`
- Test: `tests/narrative/test_narrative_cmd.py`

Replace the bare `autobuild_active_funds(...)` call in `_run_analyze` with the shared-budget `autobuild_narrative(...)` so both edges run under one preflight. The instr_index + con are already in scope (`_open_analyze_context` returns them).

- [ ] **Step 1: Write the failing test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
def test_analyze_invokes_shared_autobuild_with_instr_and_con(tmp_path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000B", "ETF", "cn_etf"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    instr_index = {"000B": object()}
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", instr_index))
    calls: list = []
    monkeypatch.setattr(
        narrative_cmd, "autobuild_narrative",
        lambda shortlist, *, provider, instr_index, con, quarter, data_dir, today_iso:
        calls.append((provider, con, quarter, instr_index)),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund",
                        lambda row, **k: _row("000B")
                        and narrative_cmd.NarrativeFundReport(
                            instrument_id="000B", name_cn="ETF",
                            position_risk_level="moderate", risk_rationale="r",
                            risk_drivers=(), valuation_state="fair", heat_state="normal",
                            thesis_state="intact", product_quality_state="acceptable",
                            opportunity_state="small_watch", dca_action="slow_dca",
                            risk_action="none", falsification_triggers=(),
                            trim_triggers=(), review_cadence="monthly",
                            evidence_gaps=(), thesis_evidence=()))
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                     analyze=True, out_dir=str(out_dir))
    assert rc == 0
    assert len(calls) == 1
    provider, con, quarter, idx = calls[0]
    assert provider == "PROV" and con == "CON" and quarter == "2026Q1" and idx is instr_index
```

> Simplify the `analyze_fund` stub to a module-level `NarrativeFundReport` builder if the inline lambda is awkward; the assertion only needs `autobuild_narrative` invoked once with the right kwargs.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_invokes_shared_autobuild_with_instr_and_con -v`
Expected: FAIL — `narrative_cmd` has no attribute `autobuild_narrative`.

- [ ] **Step 3: Rewire `_run_analyze`**

In `src/irc/commands/narrative_cmd.py`, update the import. Replace:

```python
from irc.commands.narrative_autobuild import autobuild_active_funds
```

with:

```python
from irc.commands.narrative_autobuild import autobuild_narrative
```

Replace the `autobuild_active_funds(...)` call inside `_run_analyze` (lines 98-101):

```python
        autobuild_active_funds(
            shortlist, provider=provider, quarter=resolved_quarter,
            data_dir=root / "data", today_iso=_today(),
        )
```

with:

```python
        autobuild_narrative(
            shortlist, provider=provider, instr_index=instr_index, con=con,
            quarter=resolved_quarter, data_dir=root / "data", today_iso=_today(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py::test_analyze_invokes_shared_autobuild_with_instr_and_con -v`
Expected: PASS

- [ ] **Step 5: Fix the existing autobuild-name tests**

The existing `test_narrative_cmd.py` tests monkeypatch `narrative_cmd.autobuild_active_funds` (e.g. `test_analyze_renders_real_citations:115`, `test_analyze_invokes_autobuild_with_resolved_quarter:347`, `test_run_narrative_returns_3_on_fetch_budget_exceeded:466`, `test_analyze_per_fund_error_yields_partial_results:249`, `test_run_narrative_returns_3_when_analyze_fund_raises_fetch_budget_exceeded:503`). Update each `monkeypatch.setattr(narrative_cmd, "autobuild_active_funds", ...)` to `monkeypatch.setattr(narrative_cmd, "autobuild_narrative", ...)`. For `test_analyze_invokes_autobuild_with_resolved_quarter`, also update the lambda signature to the new kwargs (`shortlist, *, provider, instr_index, con, quarter, data_dir, today_iso`). For `test_run_narrative_returns_3_on_fetch_budget_exceeded`, the throw-lambda needs no signature change.

> `test_analyze_idempotent_second_run_zero_builds` and `test_analyze_recovers_active_fund_with_real_thesis` stub `NA.build_snapshot` (the real builder edge) and do NOT stub the autobuild function — they exercise the real `autobuild_narrative`. Since their universe is `cn_equity_fund`, the active path still builds once; verify they pass unchanged after the rewire.

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -v`
Expected: PASS (all, after the renames).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(002): wire shared autobuild_narrative into _run_analyze (AC4/AC8/AC11)"
```

---

### Task 8: E2E recovery, partial-evidence, failure-degrade, idempotence (AC6, AC7, AC10, AC12)

**Files:**
- Test: `tests/narrative/test_narrative_cmd.py`

Full `_run_analyze` path with the real `autobuild_narrative` + real `analyze_fund` + real `build_opportunity_row`/gate; only the `build_snapshot` edge is stubbed (no AkShare). Mirrors `test_analyze_recovers_active_fund_with_real_thesis` for the passive path.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_narrative_cmd.py` (helpers reuse the file's `_evidence`):

```python
def _passive_universe(monkeypatch, iid="000B"):
    monkeypatch.setattr(narrative_cmd, "_enumerate_cn_funds",
                        lambda root: ((iid, "沪深300ETF", "cn_etf"),))
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),),
    )


def _instr_idx(iid="000B"):
    from irc.schemas.universe import Instrument
    return {iid: Instrument(instrument_id=iid, name_cn="沪深300ETF", asset_class="cn_etf",
                            market="cn_off_exchange", tracked_index="csi300")}


def _two_leg_fund_level(iid="000B"):
    from irc.fundamentals.types import FundAnnouncement, FundLevelSnapshot, FundNavReport
    nav_ev = ThesisEvidence(
        type="snapshot", source=iid, url="", date="2026-03-15",
        summary="NAV=4.5 @ 2026-03-15", scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None)
    info_ev = ThesisEvidence(
        type="filing", source=iid, url="", date="2026-03-20", summary="分红公告",
        scope="instrument", citation_kind="information",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None)
    return FundLevelSnapshot(
        fund_id=iid,
        nav_report=FundNavReport(fund_id=iid, fund_name=iid, latest_nav=4.5,
                                 latest_nav_date="2026-03-15",
                                 nav_history=(("2026-03-15", 4.5),),
                                 source_report_quarter="2026Q1"),
        announcements=(FundAnnouncement(fund_id=iid, title="x", topic="dividend",
                                        date="2026-03-20", report_id="AN1"),),
        evidence=(nav_ev, info_ev), source_report_quarter="2026Q1", cache_probed_at="")


def _one_leg_fund_level(iid="000B"):
    from irc.fundamentals.types import FundLevelSnapshot, FundNavReport
    nav_ev = ThesisEvidence(
        type="snapshot", source=iid, url="", date="2026-03-15",
        summary="NAV=4.5 @ 2026-03-15", scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None)
    return FundLevelSnapshot(
        fund_id=iid,
        nav_report=FundNavReport(fund_id=iid, fund_name=iid, latest_nav=4.5,
                                 latest_nav_date="2026-03-15",
                                 nav_history=(("2026-03-15", 4.5),),
                                 source_report_quarter="2026Q1"),
        announcements=(), evidence=(nav_ev,), source_report_quarter="2026Q1",
        cache_probed_at="")


def test_analyze_recovers_passive_etf_with_real_thesis(tmp_path, monkeypatch) -> None:
    """AC6 — two-leg FundLevelSnapshot → thesis_state intact, risk != insufficient."""
    repo = _wire_repo(tmp_path)
    _passive_universe(monkeypatch)
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", _instr_idx()))
    monkeypatch.setattr(narrative_cmd, "_build_input",
                        lambda *a, **k: None, raising=False)  # noop; analyze uses real _build_input
    from irc.commands import narrative_autobuild as NA
    monkeypatch.setattr(NA, "build_snapshot", lambda t, *, provider: _two_leg_fund_level())
    # analyze_fund's _build_input must yield a cn_etf input → stub at the analyze edge
    from irc.narrative import analyze as A
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _passive_inp())
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                     analyze=True, out_dir=str(out_dir))
    assert rc == 0
    fund = json.loads((out_dir / "compute_metals_report.json").read_text())["funds"][0]
    assert fund["thesis_state"] == "intact"
    assert fund["position_risk_level"] != "insufficient"


def test_analyze_passive_one_leg_is_insufficient(tmp_path, monkeypatch) -> None:
    """AC7 — NAV-only FundLevelSnapshot → evidence_insufficient → insufficient."""
    repo = _wire_repo(tmp_path)
    _passive_universe(monkeypatch)
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", _instr_idx()))
    from irc.commands import narrative_autobuild as NA
    from irc.narrative import analyze as A
    monkeypatch.setattr(NA, "build_snapshot", lambda t, *, provider: _one_leg_fund_level())
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _passive_inp())
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                     analyze=True, out_dir=str(out_dir))
    assert rc == 0
    fund = json.loads((out_dir / "compute_metals_report.json").read_text())["funds"][0]
    assert fund["thesis_state"] == "evidence_insufficient"
    assert fund["position_risk_level"] == "insufficient"


def test_analyze_passive_build_failure_degrades(tmp_path, monkeypatch) -> None:
    """AC10 — builder raises → no cache → insufficient; run still rc=0 with a report."""
    repo = _wire_repo(tmp_path)
    _passive_universe(monkeypatch)
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", _instr_idx()))
    from irc.commands import narrative_autobuild as NA
    from irc.narrative import analyze as A
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _passive_inp())
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                     analyze=True, out_dir=str(out_dir))
    assert rc == 0
    fund = json.loads((out_dir / "compute_metals_report.json").read_text())["funds"][0]
    assert fund["position_risk_level"] == "insufficient"


def test_passive_analyze_idempotent_second_run_zero_builds(tmp_path, monkeypatch) -> None:
    """AC12 — first run builds + caches; second run reuses nav/ cache, zero builds;
    byte-identical report JSON."""
    repo = _wire_repo(tmp_path)
    _passive_universe(monkeypatch)
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", _instr_idx()))
    from irc.commands import narrative_autobuild as NA
    from irc.narrative import analyze as A
    count = {"n": 0}

    def _build(t, *, provider):
        count["n"] += 1
        return _two_leg_fund_level()

    monkeypatch.setattr(NA, "build_snapshot", _build)
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _passive_inp())
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=True, out_dir=str(out_dir))
    first = (out_dir / "compute_metals_report.json").read_text()
    assert count["n"] == 1
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=True, out_dir=str(out_dir))
    second = (out_dir / "compute_metals_report.json").read_text()
    assert count["n"] == 1  # second run: latest-nav cache present → zero builds
    assert first == second  # byte-identical
```

Add the shared `_passive_inp` helper near the top of the test file (after `_row`):

```python
def _passive_inp(iid="000B"):
    from irc.opportunity.types import OpportunityInput
    return OpportunityInput(
        instrument_id=iid, asset_class="cn_etf", market="cn_off_exchange",
        theme=None, tracked_index="csi300", name_cn="沪深300ETF", role="r",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )
```

> The autobuild path uses the real `_fund_level_eligible_target` → `_build_input` with the real `instr` from `_instr_idx()` (a real `Instrument`), so `map_lookthrough` resolves `cn_etf + tracked_index=csi300 → broad_index` with `provider_symbol="000B"` → eligible. `analyze_fund`'s `_build_input` is stubbed to `_passive_inp()` so its `map_lookthrough` also routes fund-level → `_load_latest_nav_cached` reads the just-written cache. Both sides agree on `provider_symbol="000B"` → same `nav/` path (RD-4). Remove the stray `narrative_cmd._build_input` monkeypatch in the recovery test if `narrative_cmd` has no such symbol (it does not import `_build_input`); only `A._build_input` matters.

- [ ] **Step 2: Run tests to verify they fail (then pass once green from T1–T7)**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -k "passive" -v`
Expected at first authoring: these tests should already PASS once T1–T7 are merged (no new production code in T8 — it is the integration assertion layer). If any fail, the failure points to a real wiring bug in T5–T7 — fix there, not by weakening the test.

> Drop the stray `monkeypatch.setattr(narrative_cmd, "_build_input", ..., raising=False)` line from the recovery test (it references a non-existent symbol). Keep only the `A._build_input` stub.

- [ ] **Step 3: Run the passive E2E subset**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -k "passive" -v`
Expected: PASS (four).

- [ ] **Step 4: Commit**

```bash
git add tests/narrative/test_narrative_cmd.py
git commit -m "test(002): E2E passive recovery, partial-evidence, degrade, idempotence (AC6/AC7/AC10/AC12)"
```

---

### Task 9: Forbidden-indicator + sentinel guards on the passive path (AC13, constraints)

**Files:**
- Test: `tests/narrative/test_narrative_autobuild.py`

The existing `test_module_has_no_forbidden_indicator` / `test_module_never_writes_budget_exhausted_sentinel` already grep `narrative_autobuild.py`. The passive additions must keep both green. Add an explicit assertion that the passive path never writes `fetch_budget_exhausted` into a row.

- [ ] **Step 1: Confirm the existing grep guards still hold**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_module_has_no_forbidden_indicator tests/narrative/test_narrative_autobuild.py::test_module_never_writes_budget_exhausted_sentinel -v`
Expected: PASS — neither `基金概况` nor `fetch_budget_exhausted` appears in the module (the passive path adds no fetch indicator string and raises `FetchBudgetExceeded` rather than stamping a row).

- [ ] **Step 2: Add a passive-no-network assertion (AC13)**

Append to `tests/narrative/test_narrative_autobuild.py`:

```python
def test_passive_autobuild_no_live_network_marker() -> None:
    """AC13 — module contains no direct AkShare import (fetch goes via build_snapshot)."""
    src = (_REPO_ROOT / "src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "import akshare" not in src
    assert "akshare" not in src  # no direct akshare reference; fetch is via build_snapshot
```

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/narrative/test_narrative_autobuild.py::test_passive_autobuild_no_live_network_marker -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/narrative/test_narrative_autobuild.py
git commit -m "test(002): passive-path forbidden-indicator + no-network guards (AC13)"
```

---

### Task 10: Final verification — scope run + lint + size budget

**Files:** none (verification only)

- [ ] **Step 1: Run the two scope test directories**

Run: `uv run pytest tests/narrative tests/opportunity -q`
Expected: PASS — all narrative + opportunity tests green (active path unchanged, AC14).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100, py312). Fix any import-ordering / E402 issues (use `# noqa: E402` for mid-file test imports as the existing file does).

- [ ] **Step 3: Verify size budget + no import cycle**

Run:
```bash
wc -l src/irc/commands/narrative_autobuild.py src/irc/narrative/analyze.py
uv run python -c "import irc.narrative.analyze; import irc.commands.narrative_cmd; print('imports OK')"
```
Expected: `narrative_autobuild.py` < 200 lines; `analyze.py` < 200 lines; `imports OK` printed (no circular-import error). If `narrative_autobuild.py` ≥ 200, split the passive helpers into `src/irc/commands/narrative_autobuild_passive.py` and re-export `autobuild_fund_level_funds` / `_build_and_cache_fund_level_one` / `_fund_level_eligible_*` from `narrative_autobuild.py`, then re-run Steps 1-2.

- [ ] **Step 4: Run the broader suite (regression)**

Run: `uv run pytest -q`
Expected: PASS — no other module regressed (the only cross-module touch is `states.py:526`'s annotation widening, which is type-only).

- [ ] **Step 5: Commit (if any lint/size fixups were made)**

```bash
git add -A
git commit -m "chore(002): lint + size-budget fixups"
```

---

## Self-review notes

- **Spec coverage:** All 14 ACs mapped (table above). Non-goals respected: no `report.py` change (item 003), no triad suppression (item 004), no `theme_report` sourcing (passed `None`, RD-1), no `derive_position_risk_level`/gate change, no Policy B call, no staleness probe.
- **RD-6a** (annotation widening) → Task 1. **RD-7a** (single shared preflight `FetchPlan`) → Task 5 `autobuild_narrative` + Task 7 wiring.
- **RD-3 / RD-4** (instr-resolved eligibility; latest-`nav/` probe) are load-bearing and explicitly tested (T2, T4, T8-idempotence).
- **Judgment calls flagged for the executor:**
  1. **`_build_input(..., provider=None)` in the eligibility predicate (T2).** The spec (AC2) says the decision is effect-free and instr-derived. `_build_input` takes a required `provider` kwarg but `map_lookthrough` consumes only instr-derived fields. The plan passes `provider=None` with a fallback (thread the real provider) if green is not clean. Cited: AC2 / RD-3, `inputs_build.py:14-56`.
  2. **`_load_latest_nav_cached` import location (T6).** Imported from `irc.commands.opportunity_cmd` into `irc.narrative.analyze`. The plan includes an import-cycle check + a documented fallback (relocate the function to `snapshot_cache.py`). Cited: spec "read-only consumers" list naming `snapshot_cache.py`.
  3. **`theme_report=None` (RD-1/Q4).** Confirmed gate-independent; genuine sourcing is a documented follow-up, not in scope. Cited: spec Non-goals + Q4 + RD-1.
