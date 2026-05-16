# Target Registry Expansion + Discovery Rejection Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) surface per-instrument discovery rejections to `outputs/<date>/discovery_rejections.csv`; (2) extend `_TARGET_REGISTRY` so HK QDII indices, CSI sector indices, and US extras resolve to real constituent fetches instead of empty `evidence_insufficient` snapshots.

**Architecture:** PR 1 adds one pure-function module (`src/irc/discovery/rejections.py`) that joins existing `Rejection` records with `UniverseRow` rows, extended into `DiscoveryRunResult`, written as CSV by `discover_cmd`. PR 2 adds an `hk_index` spec kind to `snapshot.py`, a new `fetch_hk_index_constituents` adapter, and ten new sector-index registry entries; the `sector_proxy.py` broad-fallback layer is deleted.

**Tech Stack:** Python 3.14, pandas, pydantic, pytest, AkShare (CN + HK + ETF data), EDGAR (US filings), DuckDB.

**Spec:** [`docs/superpowers/specs/2026-05-16-target-registry-and-rejection-log-design.md`](../specs/2026-05-16-target-registry-and-rejection-log-design.md)

---

# PR 1 — `discovery_rejections.csv`

Tasks 1–5 ship as a single PR. The PR opens after Task 5's commit, before Task 6 begins.

## Task 1: Pure-function `build_discovery_rejections`

**Files:**
- Create: `src/irc/discovery/rejections.py`
- Create: `tests/discovery/test_rejections.py`

- [ ] **Step 1.1: Write failing test for hard-filter rejection row**

Create `tests/discovery/test_rejections.py`:

```python
from __future__ import annotations

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.rejections import build_discovery_rejections
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


def _row(iid: str, asset_class: str, theme: str | None = None, name: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid,
        ticker=iid,
        market="cn_on_exchange",
        name_cn=name or iid,
        asset_class=asset_class,
        currency="cny",
        tracked_index=None,
        theme=theme,
        venue_required=(),
    )


def test_build_discovery_rejections_hard_filter_rows() -> None:
    universe = (
        _row("159352", "cn_etf", "broad", "A500ETF南方"),
        _row("510300", "cn_etf", "broad", "华泰柏瑞沪深300ETF"),
    )
    hard = HardFilterResult(
        passed=(universe[1],),
        rejected=(Rejection("159352", ("inception 1.6y < 3.0y",)),),
    )
    quality = HardFilterResult(passed=(universe[1],), rejected=())
    bucketed = RoleBucketResult(
        buckets={"core_cn_equity": (universe[1],)},
        relaxed_roles=(),
        failed_roles=(),
    )

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    assert list(out.columns) == [
        "stage", "instrument_id", "ticker", "name_cn",
        "asset_class", "theme", "role", "reasons",
    ]
    records = out.to_dict("records")
    assert {
        "stage": "hard_filter",
        "instrument_id": "159352",
        "ticker": "159352",
        "name_cn": "A500ETF南方",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reasons": "inception 1.6y < 3.0y",
    } in records
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.discovery.rejections'`.

- [ ] **Step 1.3: Implement minimal module to pass**

Create `src/irc/discovery/rejections.py`:

```python
from __future__ import annotations

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


REJECTION_COLUMNS = (
    "stage", "instrument_id", "ticker", "name_cn",
    "asset_class", "theme", "role", "reasons",
)


def _index_universe(rows: tuple[UniverseRow, ...]) -> dict[str, UniverseRow]:
    return {r.instrument_id: r for r in rows}


def _row_for_rejection(stage: str, rej: Rejection, universe_by_id: dict[str, UniverseRow]) -> dict[str, str]:
    row = universe_by_id.get(rej.instrument_id)
    return {
        "stage": stage,
        "instrument_id": rej.instrument_id,
        "ticker": row.ticker if row else rej.instrument_id,
        "name_cn": row.name_cn if row else "",
        "asset_class": row.asset_class if row else "",
        "theme": (row.theme if row and row.theme is not None else ""),
        "role": "",
        "reasons": "; ".join(rej.reasons),
    }


def build_discovery_rejections(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame:
    universe_by_id = _index_universe(universe)
    rows: list[dict[str, str]] = []
    rows.extend(_row_for_rejection("hard_filter", rej, universe_by_id) for rej in hard.rejected)
    rows.extend(_row_for_rejection("quality_filter", rej, universe_by_id) for rej in quality.rejected)
    return pd.DataFrame(rows, columns=list(REJECTION_COLUMNS))
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: PASS.

- [ ] **Step 1.5: Commit**

```bash
git add src/irc/discovery/rejections.py tests/discovery/test_rejections.py
git commit -m "feat(discovery): per-instrument rejection records (hard_filter stage)"
```

## Task 2: Quality-filter stage rows

**Files:**
- Modify: `tests/discovery/test_rejections.py`

- [ ] **Step 2.1: Add failing test for quality_filter stage**

Append to `tests/discovery/test_rejections.py`:

```python
def test_build_discovery_rejections_quality_filter_rows() -> None:
    universe = (_row("588000", "cn_etf", "broad", "科创50ETF华夏"),)
    hard = HardFilterResult(passed=universe, rejected=())
    quality = HardFilterResult(
        passed=(),
        rejected=(Rejection("588000", ("drawdown_3y 0.388 > 0.28",)),),
    )
    bucketed = RoleBucketResult(buckets={}, relaxed_roles=(), failed_roles=())

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    records = out.to_dict("records")
    assert {
        "stage": "quality_filter",
        "instrument_id": "588000",
        "ticker": "588000",
        "name_cn": "科创50ETF华夏",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reasons": "drawdown_3y 0.388 > 0.28",
    } in records
```

- [ ] **Step 2.2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: PASS (the implementation from Task 1 already handles `quality_filter`).

- [ ] **Step 2.3: Commit**

```bash
git add tests/discovery/test_rejections.py
git commit -m "test(discovery): cover quality_filter rejection rows"
```

## Task 3: Multi-reason joining + role_bucket no-role-match rows

**Files:**
- Modify: `tests/discovery/test_rejections.py`
- Modify: `src/irc/discovery/rejections.py`

- [ ] **Step 3.1: Add failing test for multi-reason joining**

Append to `tests/discovery/test_rejections.py`:

```python
def test_build_discovery_rejections_joins_multiple_reasons() -> None:
    universe = (_row("000001", "cn_equity_fund"),)
    hard = HardFilterResult(
        passed=(),
        rejected=(
            Rejection("000001", ("missing inception_years", "missing aum_cny")),
        ),
    )
    quality = HardFilterResult(passed=(), rejected=())
    bucketed = RoleBucketResult(buckets={}, relaxed_roles=(), failed_roles=())

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    record = next(r for r in out.to_dict("records") if r["instrument_id"] == "000001")
    assert record["reasons"] == "missing inception_years; missing aum_cny"
```

- [ ] **Step 3.2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: PASS (already covered by `_row_for_rejection`'s `"; ".join`).

- [ ] **Step 3.3: Add failing test for role_bucket no-role-match**

Append to `tests/discovery/test_rejections.py`:

```python
def test_build_discovery_rejections_role_bucket_no_match() -> None:
    universe = (
        _row("005051", "cn_equity_fund", "defense", "诺安成长"),
        _row("510300", "cn_etf", "broad", "华泰柏瑞沪深300ETF"),
    )
    hard = HardFilterResult(passed=universe, rejected=())
    quality = HardFilterResult(passed=universe, rejected=())
    bucketed = RoleBucketResult(
        buckets={"core_cn_equity": (universe[1],)},
        relaxed_roles=(),
        failed_roles=(),
    )

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    records = out.to_dict("records")
    assert {
        "stage": "role_bucket",
        "instrument_id": "005051",
        "ticker": "005051",
        "name_cn": "诺安成长",
        "asset_class": "cn_equity_fund",
        "theme": "defense",
        "role": "",
        "reasons": "no_role_match",
    } in records
```

- [ ] **Step 3.4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: FAIL — the role_bucket no-match row is missing.

- [ ] **Step 3.5: Extend `build_discovery_rejections` to emit role_bucket rows**

Edit `src/irc/discovery/rejections.py`. Replace the body of `build_discovery_rejections` with:

```python
def build_discovery_rejections(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame:
    universe_by_id = _index_universe(universe)
    rows: list[dict[str, str]] = []
    rows.extend(_row_for_rejection("hard_filter", rej, universe_by_id) for rej in hard.rejected)
    rows.extend(_row_for_rejection("quality_filter", rej, universe_by_id) for rej in quality.rejected)
    bucketed_ids: set[str] = {
        r.instrument_id for items in bucketed.buckets.values() for r in items
    }
    quality_passed_ids = {r.instrument_id for r in quality.passed}
    for orphan_id in sorted(quality_passed_ids - bucketed_ids):
        row = universe_by_id.get(orphan_id)
        rows.append({
            "stage": "role_bucket",
            "instrument_id": orphan_id,
            "ticker": row.ticker if row else orphan_id,
            "name_cn": row.name_cn if row else "",
            "asset_class": row.asset_class if row else "",
            "theme": (row.theme if row and row.theme is not None else ""),
            "role": "",
            "reasons": "no_role_match",
        })
    return pd.DataFrame(rows, columns=list(REJECTION_COLUMNS))
```

- [ ] **Step 3.6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/discovery/test_rejections.py -v`
Expected: PASS for all four tests.

- [ ] **Step 3.7: Commit**

```bash
git add src/irc/discovery/rejections.py tests/discovery/test_rejections.py
git commit -m "feat(discovery): include role_bucket no-match instruments in rejections"
```

## Task 4: Wire `rejections` into `DiscoveryRunResult`

**Files:**
- Modify: `src/irc/discovery/pipeline.py`
- Modify: `tests/discovery/test_pipeline.py`

- [ ] **Step 4.1: Add failing test asserting rejections DataFrame is in run result**

Open `tests/discovery/test_pipeline.py` and find the existing happy-path test for `run_discovery_with_diagnostics`. Append after it:

```python
def test_run_discovery_with_diagnostics_returns_rejections_dataframe() -> None:
    import pandas as pd
    from irc.discovery.pipeline import run_discovery_with_diagnostics
    from irc.discovery.universe import UniverseRow

    universe = (
        UniverseRow(
            instrument_id="159352", ticker="159352", market="cn_on_exchange",
            name_cn="A500ETF南方", asset_class="cn_etf", currency="cny",
            tracked_index=None, theme="broad", venue_required=(),
        ),
    )
    metadata = pd.DataFrame([{
        "instrument_id": "159352", "inception_date": "2024-09-25",
        "aum_cny": 1e10, "expense_ratio": 0.002, "daily_volume_cny": 1e8,
        "manager_tenure_years": 0.0,
    }])
    metrics = pd.DataFrame(columns=["instrument_id", "drawdown_3y", "tracking_error", "manager_tenure_years"])

    res = run_discovery_with_diagnostics(
        universe=universe, metadata=metadata, metrics=metrics,
        risk_band_max_dd_upper=0.20, cfg_overrides=None, cfg_discovery=None,
        route=lambda *_a, **_kw: None, peer_summary="", macro_snapshot="",
        raw_ref_pool=(), excluded_themes=(),
    )

    assert hasattr(res, "rejections")
    assert "instrument_id" in res.rejections.columns
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/discovery/test_pipeline.py::test_run_discovery_with_diagnostics_returns_rejections_dataframe -v`
Expected: FAIL with `AttributeError: 'DiscoveryRunResult' object has no attribute 'rejections'`.

- [ ] **Step 4.3: Extend `DiscoveryRunResult` and `run_discovery_with_diagnostics`**

Edit `src/irc/discovery/pipeline.py`. At the top, add the import:

```python
from irc.discovery.rejections import build_discovery_rejections
```

Change the `DiscoveryRunResult` dataclass to include rejections:

```python
@dataclass(frozen=True)
class DiscoveryRunResult:
    watchlist: pd.DataFrame
    diagnostics: pd.DataFrame
    rejections: pd.DataFrame
```

At the bottom of `run_discovery_with_diagnostics`, just before the return, add:

```python
    rejections = build_discovery_rejections(universe, hard, quality, bucketed)
```

Update the return statement:

```python
    return DiscoveryRunResult(
        watchlist=pd.DataFrame(rows, columns=list(_WATCHLIST_COLUMNS)),
        diagnostics=diagnostics,
        rejections=rejections,
    )
```

- [ ] **Step 4.4: Run pipeline tests to verify they pass**

Run: `.venv/bin/pytest tests/discovery/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add src/irc/discovery/pipeline.py tests/discovery/test_pipeline.py
git commit -m "feat(discovery): expose per-instrument rejections via DiscoveryRunResult"
```

## Task 5: Write `discovery_rejections.csv` from `discover_cmd`

**Files:**
- Modify: `src/irc/commands/discover_cmd.py`
- Modify: `tests/commands/test_discover_cmd.py`

- [ ] **Step 5.1: Add failing test that the CSV file is written**

Open `tests/commands/test_discover_cmd.py` and locate the end-to-end discovery test (search for `discovery_diagnostics.csv`). Append a new test that mirrors that fixture:

```python
def test_run_discover_writes_discovery_rejections_csv(tmp_repo, monkeypatch) -> None:
    from irc.commands.discover_cmd import run_discover

    # tmp_repo fixture must already produce a discovery run; reuse its setup
    rc = run_discover(str(tmp_repo))
    assert rc == 0

    rejections_path = next((tmp_repo / "outputs").rglob("discovery_rejections.csv"))
    text = rejections_path.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert header == "stage,instrument_id,ticker,name_cn,asset_class,theme,role,reasons"
```

> **Note:** if `tests/commands/test_discover_cmd.py` does not already have a `tmp_repo` fixture matching this shape, use the fixture name and setup the existing happy-path test uses. Do not invent a fixture — adapt this test body to the conventions present in that file.

- [ ] **Step 5.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/commands/test_discover_cmd.py::test_run_discover_writes_discovery_rejections_csv -v`
Expected: FAIL — file does not exist.

- [ ] **Step 5.3: Wire the CSV write in `discover_cmd`**

Edit `src/irc/commands/discover_cmd.py`. Locate the block (around line 146):

```python
    diagnostics_path = out_dir / "discovery_diagnostics.csv"
    atomic_write_text(watchlist_path, result.watchlist.to_csv(index=False))
    atomic_write_text(diagnostics_path, result.diagnostics.to_csv(index=False))
```

Replace with:

```python
    diagnostics_path = out_dir / "discovery_diagnostics.csv"
    rejections_path = out_dir / "discovery_rejections.csv"
    atomic_write_text(watchlist_path, result.watchlist.to_csv(index=False))
    atomic_write_text(diagnostics_path, result.diagnostics.to_csv(index=False))
    atomic_write_text(rejections_path, result.rejections.to_csv(index=False))
```

Update the print summary line directly after (around line 150):

```python
    print(f"diagnostics OK: {len(result.diagnostics)} rows → {diagnostics_path}")
    print(f"rejections OK: {len(result.rejections)} rows → {rejections_path}")
```

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/commands/test_discover_cmd.py -v`
Expected: PASS.

- [ ] **Step 5.5: Run full discovery test suite**

Run: `.venv/bin/pytest tests/discovery/ tests/commands/test_discover_cmd.py -v`
Expected: PASS.

- [ ] **Step 5.6: Commit**

```bash
git add src/irc/commands/discover_cmd.py tests/commands/test_discover_cmd.py
git commit -m "feat(discover): write discovery_rejections.csv alongside diagnostics"
```

- [ ] **Step 5.7: PR 1 boundary — open PR**

Run the broader test suite to catch unexpected regressions:

```bash
.venv/bin/pytest tests/ -x -q
```

Expected: PASS. Then push and open PR for tasks 1–5. PR title:

> feat(discover): per-instrument rejection log for traceability

PR body should reference the spec section "PR 1 — `discovery_rejections.csv`".

---

# PR 2 — `_TARGET_REGISTRY` expansion

Tasks 6–13 ship as a second PR. Begin only after PR 1 is merged (or open both PRs concurrently if your workflow supports it; the implementations are independent).

## Task 6: Verify CSI sector index codes against AkShare

**Files:**
- Create: `scripts/verify_sector_index_codes.py` (one-shot verification script)

- [ ] **Step 6.1: Create the verification script**

Create `scripts/verify_sector_index_codes.py`:

```python
"""One-shot verification: confirm each tentative CSI sector index code
returns constituents via fetch_cn_index_constituents. Run once before
locking codes into _TARGET_REGISTRY. Not part of the test suite.

Usage:
    .venv/bin/python scripts/verify_sector_index_codes.py
"""
from __future__ import annotations

from irc.fundamentals.akshare_fundamentals import fetch_cn_index_constituents


_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("半导体", "中证全指半导体", "H30184"),
    ("医药", "中证医药卫生", "000933"),
    ("新能源", "中证新能源", "399808"),
    ("消费", "中证主要消费", "000932"),
    ("金融", "中证金融", "000934"),
    ("军工", "中证军工", "399967"),
    ("有色金属", "中证有色金属", "H30202"),
    ("房地产", "中证全指房地产", "000952"),
    ("国企改革", "央企创新驱动", "000861"),
    ("科技", "中证科技龙头", "931087"),
)


def main() -> int:
    failures: list[tuple[str, str, str]] = []
    for theme, name, code in _CANDIDATES:
        constituents = fetch_cn_index_constituents(code, top_n=10)
        status = "OK" if constituents else "EMPTY"
        print(f"{theme:8s} {name:14s} {code:8s} {status:6s} (got {len(constituents)} names)")
        if not constituents:
            failures.append((theme, name, code))
    if failures:
        print("\nFailures:")
        for theme, name, code in failures:
            print(f"  {theme} → {name} ({code})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6.2: Run the verification script**

Run: `.venv/bin/python scripts/verify_sector_index_codes.py`

Expected: every line shows `OK`. If any line shows `EMPTY`, update the code in the script and the registry mapping (Task 9) before continuing. Save the final verified mapping into a comment block at the top of the script for future reference.

- [ ] **Step 6.3: Commit the verification script with the verified mapping**

```bash
git add scripts/verify_sector_index_codes.py
git commit -m "chore(scripts): verify CSI sector index codes for registry expansion"
```

## Task 7: Extend the drift-coverage test to fail loudly

**Files:**
- Modify: `tests/opportunity/test_lookthrough.py`

- [ ] **Step 7.1: Replace the broad-only drift test with a full-coverage version**

Open `tests/opportunity/test_lookthrough.py`. Find:

```python
def test_target_registry_covers_broad_index_display_table() -> None:
    from irc.fundamentals.snapshot import _TARGET_REGISTRY
    from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY

    missing = sorted(set(_BROAD_INDEX_DISPLAY.values()) - set(_TARGET_REGISTRY))
    assert missing == [], f"missing broad-index registry entries: {missing}"
```

Replace it with:

```python
def test_target_registry_covers_every_lookthrough_display() -> None:
    from irc.fundamentals.snapshot import _TARGET_REGISTRY
    from irc.opportunity.lookthrough import (
        _BROAD_INDEX_DISPLAY,
        _QDII_HK_DISPLAY,
        _QDII_US_DISPLAY,
        _SECTOR_THEME_DISPLAY,
    )

    required = (
        set(_BROAD_INDEX_DISPLAY.values())
        | set(_QDII_US_DISPLAY.values())
        | set(_QDII_HK_DISPLAY.values())
        | {display for key, display in _SECTOR_THEME_DISPLAY.items() if key != "broad"}
    )
    missing = sorted(required - set(_TARGET_REGISTRY))
    assert missing == [], f"missing registry entries for display names: {missing}"
```

- [ ] **Step 7.2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_every_lookthrough_display -v`
Expected: FAIL with a sorted list of every display name missing from the registry — sector themes, HK QDII, plus 道琼斯/美国50/美股大盘.

- [ ] **Step 7.3: Commit the failing drift test**

> The next tasks make this test pass by adding registry entries. Committing the failing test first locks the spec in.

```bash
git add tests/opportunity/test_lookthrough.py
git commit -m "test(opportunity): require registry coverage for every lookthrough display"
```

## Task 8: Add `hk_index` spec kind + dispatcher

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Modify: `tests/fundamentals/test_snapshot.py`

- [ ] **Step 8.1: Write failing test for `hk_index` dispatch**

Open `tests/fundamentals/test_snapshot.py`. After `test_build_snapshot_hk_symbols_dispatches_to_hkex`, append:

```python
def test_build_snapshot_hk_index_dispatches_to_hk_constituents(monkeypatch):
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "HSI-test",
        snapshot._TargetSpec(kind="hk_index", code="HSI"),
    )
    constituents = (
        Constituent(symbol="00700.HK", name="腾讯控股", weight=0.10, market="hk"),
        Constituent(symbol="09988.HK", name="阿里巴巴-W", weight=0.08, market="hk"),
    )
    digest = FilingDigest(
        symbol="00700.HK", fiscal_period="2026Q1", filed_at_iso="2026-03-31",
        revenue_yoy=0.22, net_income_yoy=0.14, gross_margin=0.57,
    )
    monkeypatch.setattr(
        snapshot, "fetch_hk_index_constituents",
        lambda code, *, top_n=10: constituents if code == "HSI" else (),
    )
    monkeypatch.setattr(
        snapshot, "fetch_hk_filing_digest",
        lambda sym: digest if sym == "00700.HK" else None,
    )

    snap = build_snapshot("HSI-test", top_n=2, as_of_iso="2026-05-15")

    assert snap.lookthrough_target == "HSI-test"
    assert snap.constituents == constituents
    assert snap.filings == (digest,)
    assert any("09988.HK" in r for r in snap.failure_reasons)
```

- [ ] **Step 8.2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/fundamentals/test_snapshot.py::test_build_snapshot_hk_index_dispatches_to_hk_constituents -v`
Expected: FAIL — `snapshot` has no attribute `fetch_hk_index_constituents`, and there is no `hk_index` dispatch branch.

- [ ] **Step 8.3: Add the dispatch + builder + import stub**

Edit `src/irc/fundamentals/snapshot.py`. Update the import block to add the new fetcher (which will be implemented in Task 9):

```python
from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_index_constituents,
    fetch_hk_index_constituents,
)
```

In the dispatch section of `build_snapshot`, add a branch above the final fall-through:

```python
    if spec.kind == "hk_index":
        return _build_hk_index_snapshot(lookthrough_target, spec, top_n, timestamp)
```

After `_build_hk_snapshot`, append:

```python
def _build_hk_index_snapshot(
    target: str, spec: _TargetSpec, top_n: int, as_of_iso: str,
) -> ConstituentSnapshot:
    constituents = fetch_hk_index_constituents(spec.code, top_n=top_n)
    if not constituents:
        return ConstituentSnapshot(
            lookthrough_target=target, as_of_iso=as_of_iso,
            constituents=(), filings=(), broker_reports=(),
            failure_reasons=(f"hk_index {spec.code} returned no constituents",),
        )
    filings, failures = [], []
    for c in constituents:
        digest = fetch_hk_filing_digest(c.symbol)
        if digest is None:
            failures.append(f"missing filing digest: {c.symbol}")
        else:
            filings.append(digest)
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=(),
        failure_reasons=tuple(failures),
    )
```

- [ ] **Step 8.4: Run the test to verify it passes (after Task 9 lands the adapter)**

This test cannot pass until `fetch_hk_index_constituents` exists in `akshare_fundamentals.py`. Do not run it yet; proceed to Task 9. The import will currently fail.

> **Note:** if test execution is required between tasks, define a temporary stub at the bottom of `src/irc/fundamentals/akshare_fundamentals.py`:
> ```python
> def fetch_hk_index_constituents(code: str, *, top_n: int = 10):
>     return ()
> ```
> and replace it in Task 9. Otherwise this is fine.

- [ ] **Step 8.5: Commit (with the import stub if needed)**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_snapshot.py
git commit -m "feat(snapshot): hk_index spec kind for top-N HK index constituents"
```

## Task 9: Implement `fetch_hk_index_constituents` adapter

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Modify: `tests/fundamentals/test_akshare_fundamentals.py`

- [ ] **Step 9.1: Confirm the AkShare HK index endpoint**

Inspect available AkShare HK index constituent functions. Run a one-off shell to discover the correct call:

```bash
.venv/bin/python -c "import akshare as ak; print([n for n in dir(ak) if 'hk' in n.lower() and ('index' in n.lower() or 'constituent' in n.lower() or 'cons' in n.lower())])"
```

Pick the function that returns a DataFrame of HK index constituents. Most likely candidate: `stock_hk_index_constituent_em` or `index_stock_hk_em`. Confirm column names with:

```bash
.venv/bin/python -c "import akshare as ak; df = ak.<picked_function>(symbol='HSI'); print(df.head().to_string())"
```

Record the exact column names (typically `代码`, `名称`, possibly `权重`).

- [ ] **Step 9.2: Write failing tests**

Open `tests/fundamentals/test_akshare_fundamentals.py` (create the file if missing). Append:

```python
from __future__ import annotations

import pandas as pd

from irc.fundamentals import akshare_fundamentals
from irc.fundamentals.akshare_fundamentals import fetch_hk_index_constituents
from irc.fundamentals.types import Constituent


def test_fetch_hk_index_constituents_happy_path(monkeypatch):
    # Substitute the column names below for whatever Task 9.1 confirmed.
    fake_df = pd.DataFrame([
        {"代码": "00700", "名称": "腾讯控股", "权重": 10.0},
        {"代码": "09988", "名称": "阿里巴巴-W", "权重": 8.0},
        {"代码": "01299", "名称": "友邦保险", "权重": 6.0},
    ])
    monkeypatch.setattr(
        akshare_fundamentals, "_ak_call",
        lambda fn, **_kw: fake_df,
    )

    out = fetch_hk_index_constituents("HSI", top_n=2)

    assert out == (
        Constituent(symbol="00700.HK", name="腾讯控股", weight=0.10, market="hk"),
        Constituent(symbol="09988.HK", name="阿里巴巴-W", weight=0.08, market="hk"),
    )


def test_fetch_hk_index_constituents_returns_empty_on_failure(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("akshare network error")
    monkeypatch.setattr(akshare_fundamentals, "_ak_call", boom)
    assert fetch_hk_index_constituents("HSI", top_n=10) == ()
```

> Adjust the column names (`代码` / `名称` / `权重`) to match what Task 9.1 confirmed. Adjust the symbol-format expectation (`00700.HK`) if the endpoint already returns suffixed symbols.

- [ ] **Step 9.3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/fundamentals/test_akshare_fundamentals.py -v`
Expected: FAIL with `ImportError` or `AttributeError`.

- [ ] **Step 9.4: Implement the adapter**

Edit `src/irc/fundamentals/akshare_fundamentals.py`. Add helpers and the public function:

```python
def _to_qualified_hk_symbol(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return f"{digits.zfill(5)}.HK" if digits else ""


def _parse_hk_index_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    # Substitute the actual column names confirmed in Task 9.1.
    code_col, name_col, weight_col = "代码", "名称", "权重"
    needed = {code_col, name_col}
    if not needed.issubset(df.columns):
        return ()
    has_weight = weight_col in df.columns
    if has_weight:
        df = df.sort_values(weight_col, ascending=False)
    head = df.head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_hk_symbol(row[code_col]),
            name=str(row[name_col]),
            weight=(float(row[weight_col]) / 100) if has_weight else 0.0,
            market="hk",
        )
        for _, row in head.iterrows()
    )


def fetch_hk_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N HK index constituents by weight, market='hk'. Returns () on failure."""
    try:
        df = _ak_call("<picked_function_from_task_9_1>", symbol=index_code)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    return _parse_hk_index_frame(df, top_n)
```

> Substitute `<picked_function_from_task_9_1>` with the actual AkShare function name confirmed in Step 9.1.

- [ ] **Step 9.5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/fundamentals/test_akshare_fundamentals.py tests/fundamentals/test_snapshot.py -v`
Expected: PASS — including the `hk_index` dispatch test added in Task 8.

- [ ] **Step 9.6: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "feat(fundamentals): fetch_hk_index_constituents adapter for HK QDII coverage"
```

## Task 10: Register CSI sector indices

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`

- [ ] **Step 10.1: Run the drift test to see what's missing**

Run: `.venv/bin/pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_every_lookthrough_display -v`

Expected FAIL output (the full required set, minus broad-index entries already registered):

```
AssertionError: missing registry entries for display names: ['中概互联', '半导体', '军工', '医药', '国企改革', '恒生指数', '恒生科技', '房地产', '有色金属', '港股红利', '消费', '美国50', '美股大盘', '科技', '纳斯达克100', '道琼斯', '金融', '新能源']
```

> 纳斯达克100 is already registered today; the test sees it as present. Adapt the snapshot you see to actual current state.

- [ ] **Step 10.2: Add sector entries to `_TARGET_REGISTRY`**

Edit `src/irc/fundamentals/snapshot.py`. Locate the `_TARGET_REGISTRY` dict and add the verified sector codes (from Task 6's verification) below the existing broad-index entries:

```python
    # Sector indices — verified codes in scripts/verify_sector_index_codes.py
    "半导体":   _TargetSpec(kind="cn_index", code="H30184"),
    "医药":     _TargetSpec(kind="cn_index", code="000933"),
    "新能源":   _TargetSpec(kind="cn_index", code="399808"),
    "消费":     _TargetSpec(kind="cn_index", code="000932"),
    "金融":     _TargetSpec(kind="cn_index", code="000934"),
    "军工":     _TargetSpec(kind="cn_index", code="399967"),
    "有色金属": _TargetSpec(kind="cn_index", code="H30202"),
    "房地产":   _TargetSpec(kind="cn_index", code="000952"),
    "国企改革": _TargetSpec(kind="cn_index", code="000861"),
    "科技":     _TargetSpec(kind="cn_index", code="931087"),
```

> If Task 6 swapped any code for an alternative, use the swapped code here.

- [ ] **Step 10.3: Run the drift test — it should still fail for HK/US-extras**

Run: `.venv/bin/pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_every_lookthrough_display -v`
Expected: FAIL with a shorter missing list (sector themes gone; HK and US extras still missing).

- [ ] **Step 10.4: Commit**

```bash
git add src/irc/fundamentals/snapshot.py
git commit -m "feat(snapshot): register CSI sector indices for lookthrough coverage"
```

## Task 11: Register HK QDII indices

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`

- [ ] **Step 11.1: Confirm HK index symbols accepted by the new adapter**

Run a one-shot to confirm AkShare accepts these symbols (substitute the function name from Task 9.1):

```bash
.venv/bin/python -c "
from irc.fundamentals.akshare_fundamentals import fetch_hk_index_constituents
for code in ('HSI', 'HSTECH', 'HSHKDIV', 'HSCEI'):
    print(code, '→', len(fetch_hk_index_constituents(code, top_n=5)), 'names')
"
```

> Find a working HSI / HSTECH / 港股红利 / 中概互联 index code per the AkShare endpoint. If any returns 0 names, swap in an alternative (e.g. some HK index endpoints take English names like `Hang Seng Index` rather than `HSI`). Record the working codes.

- [ ] **Step 11.2: Add HK entries to `_TARGET_REGISTRY`**

Edit `src/irc/fundamentals/snapshot.py`. After the sector entries from Task 10, append:

```python
    # HK QDII indices via fetch_hk_index_constituents
    "恒生指数":   _TargetSpec(kind="hk_index", code="HSI"),
    "恒生科技":   _TargetSpec(kind="hk_index", code="HSTECH"),
    "港股红利":   _TargetSpec(kind="hk_index", code="HSHKDIV"),
    "中概互联":   _TargetSpec(kind="hk_index", code="HSCEI"),
```

> Substitute the codes confirmed in Step 11.1. If any HK target has no clean index, fall back to `hk_symbols` with a hardcoded top-10 tuple (same pattern as the existing US QDII entries) and note the fallback in a one-line comment.

- [ ] **Step 11.3: Commit**

```bash
git add src/irc/fundamentals/snapshot.py
git commit -m "feat(snapshot): register HK QDII indices for lookthrough coverage"
```

## Task 12: Register US extras (道琼斯 / 美国50 / 美股大盘)

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`

- [ ] **Step 12.1: Add US extras to `_TARGET_REGISTRY`**

Edit `src/irc/fundamentals/snapshot.py`. Append to `_TARGET_REGISTRY` after the existing 纳斯达克100 entry:

```python
    "道琼斯": _TargetSpec(kind="us_symbols", symbols=(
        # Top-10 DJIA by index weight as of 2026-05-16; update quarterly
        "UNH", "GS", "MSFT", "HD", "MCD", "CRM", "V", "CAT", "AMGN", "AXP",
    )),
    "美国50": _TargetSpec(kind="us_symbols", symbols=(
        # FTSE Russell US Large Cap 50 top-10 by weight as of 2026-05-16
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "GOOG", "AVGO", "TSLA",
    )),
    "美股大盘": _TargetSpec(kind="us_symbols", symbols=(
        # Mirrors 标普500 top-10
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "GOOG", "AVGO", "TSLA",
    )),
```

> The DJIA top-10 and FTSE US50 weights drift quarterly; the exact symbols here mirror the source-of-truth pattern already used for `标普500` / `纳斯达克100` and can be refreshed in the same way.

- [ ] **Step 12.2: Run the full drift test — it should now pass**

Run: `.venv/bin/pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_every_lookthrough_display -v`
Expected: PASS — every lookthrough display name is covered.

- [ ] **Step 12.3: Commit**

```bash
git add src/irc/fundamentals/snapshot.py
git commit -m "feat(snapshot): register 道琼斯 / 美国50 / 美股大盘 for lookthrough coverage"
```

## Task 13: Delete `sector_proxy.py` and its callers

**Files:**
- Delete: `src/irc/opportunity/sector_proxy.py`
- Modify: `src/irc/opportunity/thesis_evidence.py`
- Modify: `tests/opportunity/test_thesis_evidence.py` (if it tests proxy behaviour)

- [ ] **Step 13.1: Find every caller**

Run: `grep -rn "sector_proxy\|proxy_target_for_theme" src/ tests/`

Record each caller. Expect at least: `src/irc/opportunity/thesis_evidence.py` and whatever test file asserts proxy behaviour.

- [ ] **Step 13.2: Remove the proxy import and call site in `thesis_evidence.py`**

Open `src/irc/opportunity/thesis_evidence.py`. Locate the import:

```python
from irc.opportunity.sector_proxy import proxy_target_for_theme
```

and any branch that calls `proxy_target_for_theme(...)`. Remove both. The function that used the proxy should now rely solely on `map_lookthrough(...).display_cn` flowing through `_TARGET_REGISTRY` — which is now complete after Task 12.

Read the surrounding code carefully: if `proxy_target_for_theme` was called as a fallback after a primary path failed, document the change with a single-line comment only if the new flow is non-obvious; otherwise no comment.

- [ ] **Step 13.3: Update or remove proxy-specific tests**

Open `tests/opportunity/test_thesis_evidence.py` (and any other test file Step 13.1 flagged). For each test that asserted "theme=semiconductor proxies to 沪深300", rewrite or delete it. Examples:

- Tests verifying the proxy returned 沪深300 for semiconductor: **delete** — the behaviour is replaced by direct sector-index resolution.
- Tests verifying that `evidence_insufficient` was returned for an unmapped theme: **update** — sector themes now resolve successfully, so the test should assert successful resolution for at least one sector theme.

- [ ] **Step 13.4: Delete `sector_proxy.py`**

```bash
rm src/irc/opportunity/sector_proxy.py
```

- [ ] **Step 13.5: Run the full opportunity + fundamentals test suite**

Run: `.venv/bin/pytest tests/opportunity/ tests/fundamentals/ tests/discovery/ -v`
Expected: PASS.

- [ ] **Step 13.6: Run the entire test suite as a regression catch**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: PASS.

- [ ] **Step 13.7: Commit**

```bash
git add -A src/irc/opportunity/ tests/opportunity/
git commit -m "refactor(opportunity): drop sector_proxy in favor of direct sector registry"
```

- [ ] **Step 13.8: PR 2 boundary — open PR**

Push and open PR for tasks 6–13. PR title:

> feat(snapshot): expand _TARGET_REGISTRY (HK + sectors + US extras)

PR body should reference the spec section "PR 2 — `_TARGET_REGISTRY` expansion" and call out:
- 10 new CSI sector index entries verified against AkShare.
- 4 new HK QDII entries via the new `hk_index` spec kind.
- 3 new US QDII entries (道琼斯 / 美国50 / 美股大盘).
- `sector_proxy.py` deleted; thesis evidence now flows through real sector constituents.

---

# Self-review notes (kept for reviewers)

- **Spec coverage:**
  - PR 1 spec → Tasks 1–5. Output shape, column set, pure-function module, wiring, CSV write all addressed.
  - PR 2 spec → Tasks 6–13. New spec kind, new adapter, coverage matrix entries, sector_proxy removal all addressed.
- **No placeholders:** every code block contains the actual code to write; the only deferred decisions are the AkShare HK endpoint function name (Task 9.1) and the verified sector codes (Task 6) — both are explicit lookups, not "TBD" content.
- **Type consistency:** `REJECTION_COLUMNS` tuple matches the CSV header in Task 5.1. `DiscoveryRunResult.rejections` is consistently `pd.DataFrame` across pipeline definition, populating code, and CSV write site. `_TargetSpec.kind` values (`cn_index` / `us_symbols` / `hk_symbols` / `hk_index`) consistent across snapshot.py and tests.
- **Test isolation:** every new test patches AkShare via the existing `_ak_call` indirection (no network calls).
