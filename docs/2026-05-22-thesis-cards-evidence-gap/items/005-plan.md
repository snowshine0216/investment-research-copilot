# Item 005 Implementation Plan — Per-asset-class citation coverage (Slice F, post-Q4-pivot)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the parallel **fund-level fetch engine** that emits NAV (data leg) + 3-endpoint-unioned announcements (information leg) for `gold` / `cn_bond_fund` / `cn_etf` / tracked CN ETF rows, stamps the QDII universal exclusion sentinel for `qdii_us` / `qdii_hk` / `qdii_global`, and wires both flows through `build_snapshot` dispatch + `_build_rows` autobuild — without touching item 003's active-fund flow.

**Architecture:** New frozen dataclasses (`FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot`) live in `src/irc/fundamentals/types.py`. Two new pure adapters (`fetch_fund_nav_report`, `fetch_fund_announcements`) in `akshare_fundamentals.py` degrade-to-empty per ADR 0002's "never raise" contract. `build_snapshot` dispatches by `LookthroughTarget.kind` to `_build_fund_level_snapshot` (NAV + announcements + ThesisEvidence composition) or `_build_qdii_sentinel_snapshot` (zero-fetch, in-process). `map_lookthrough` is patched to populate `provider_symbol=inp.instrument_id` for `gold`/`cn_bond_fund`/`cn_etf` so the dispatch resolves. NAV cache layout `data/fundamentals/{source_report_quarter}/nav/fund_{iid}.json` parallels item 003's `active_fund/`. `_build_rows` autobuild path extends to dispatch fund-level kinds with the same plan-hash semantics. Per grill Q3, no cheap freshness probe — stale → direct full refetch.

**Tech Stack:** Python 3.12, pandas, AkShare (mocked via `_ak_call`), pytest, ruff. No new third-party deps.

---

## Constraints (apply to every task)

- **Strict TDD per task:** red (failing test) → green (minimal impl) → refactor. No implementation code lands without a prior failing test.
- **All tests mock `_ak_call`.** NO new `live_akshare`-marked tests — item 004 already verified the 4 endpoints live.
- **Defaults locked:** `IRC_FETCH_BUDGET=2000`, `IRC_CACHE_FRESHNESS_DAYS=7`, `TOP_N_DEFAULT=10`.
- **Citation contract (ADR 0001 §2 unchanged):** fund announcements set `url=""` and `summary = f"[{report_id}] {title}"`; the preimage falls back to `f"{source}:{date}:{summary[:64]}"` and stays deterministic.
- **No `ThesisEvidenceKind` extension.** Per grill Q4, NAV evidence reuses the existing `"snapshot"` literal — no Literal change required.
- **Per-fund cost:** 4 AkShare calls (1 NAV + 3 announcement endpoints). V1 universe ≈ 20 funds × 4 = 80 calls; well under `IRC_FETCH_BUDGET=2000`.
- **Cache layout (ADR 0002 §5):** `data/fundamentals/{source_report_quarter}/nav/fund_{fund_id}.json`. Atomic write via `.tmp.{pid} → os.replace`. Disclosure quarter inferred from `latest_nav_date` via existing `infer_quarter`.
- **Static-profile invariant (F5):** `fund_open_fund_info_em(symbol, indicator="基金概况")` is NEVER called by item 005's production code. Locked by a grep-based test.
- **QDII sentinel is NOT cached on disk** (grill Q5). In-memory re-emission only.
- **Functional programming:** every new helper is a pure function; I/O isolated to adapters + cache module. New dataclasses are frozen, composed via `replace()` not mutation.
- **Dataclass location:** all new dataclasses live in `src/irc/fundamentals/types.py` (NOT `opportunity/types.py`). Item 003 fixed the cycle; we do not reintroduce it.
- **Commit cadence:** one conventional-commit per task (`feat(fundamentals):`, `feat(opportunity):`, `test(...):`, `refactor(...):`). Tests-first within a task. DO NOT push.
- **Verification per task:** an exact `pytest …` command with expected PASS/FAIL output. Final task = full `pytest -x` + `ruff check`.

## Branch

This plan executes on the existing autodev sub-branch `autodev/thesis-cards-evidence-gap` (or its child `autodev/thesis-evidence-005-per-asset-class-citation-coverage` if the orchestrator cuts one per Mode-A workflow). Commits land on whichever branch the impl agent is on. The PR opens against `autodev/thesis-cards-evidence-gap`.

---

## File-touch map (read this before starting)

**Source (modify):**
- `src/irc/fundamentals/types.py` — add `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot` dataclasses; extend `__all__`.
- `src/irc/fundamentals/akshare_fundamentals.py` — add `fetch_fund_nav_report(fund_id)` + `fetch_fund_announcements(fund_id)`. Both degrade-to-empty.
- `src/irc/fundamentals/snapshot.py` — extend `build_snapshot` dispatch with two new branches (QDII sentinel + fund-level) BEFORE the legacy fall-through; add `_build_fund_level_snapshot` + `_build_qdii_sentinel_snapshot`; widen return type union.
- `src/irc/fundamentals/snapshot_cache.py` — add `nav_cache_path`, `write_nav_cache`, `load_nav_cache`, dict (de)serializers parallel to `active_fund_cache_*`.
- `src/irc/opportunity/lookthrough.py` — surgical patch to populate `provider_symbol=inp.instrument_id` for `gold`, `cn_bond_fund`, and tracked_index/theme fall-through branches.
- `src/irc/commands/opportunity_cmd.py` — extend `_build_rows` autobuild path to dispatch fund-level + QDII kinds; route `FundLevelSnapshot` into `OpportunityRow.thesis_evidence`; extend `FetchPlan` accounting.

**Tests (create or modify):**
- `tests/fundamentals/test_types.py` — add `FundNavReport`/`FundAnnouncement`/`FundLevelSnapshot` construction + validation tests.
- `tests/fundamentals/test_fetch_fund_nav_report.py` (new) — adapter unit tests with mocked `_ak_call`.
- `tests/fundamentals/test_fetch_fund_announcements.py` (new) — 3-endpoint union/dedup/sort tests using item-004 fixtures + mocked `_ak_call`.
- `tests/fundamentals/test_fund_level_snapshot.py` (new) — `_build_fund_level_snapshot` + `_build_qdii_sentinel_snapshot` + citation_id determinism tests.
- `tests/fundamentals/test_snapshot_cache.py` (extend) — NAV cache I/O tests parallel to active-fund cache tests.
- `tests/fundamentals/test_static_profile_invariant.py` (new) — grep-based assertion that `"基金概况"` does NOT appear in production code.
- `tests/opportunity/test_lookthrough.py` (extend) — assert `provider_symbol` is populated for `gold`/`cn_bond_fund`/`cn_etf`.
- `tests/commands/test_opportunity_cmd_fund_level.py` (new) — `_build_rows` integration with mocked NAV + 3 announcement adapters; QDII sentinel + plan-hash + budget accounting.
- `tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json` (new) — NAV fixture (shape from item 004's `test_live_endpoints.py:50-56`).

---

## Task index (one slice per task, all green-at-checkpoint)

1. Add `FundNavReport` dataclass to `fundamentals/types.py`.
2. Add `FundAnnouncement` dataclass to `fundamentals/types.py`.
3. Add `FundLevelSnapshot` dataclass to `fundamentals/types.py`; extend `__all__`.
4. Patch `map_lookthrough` to populate `provider_symbol` for `gold`/`cn_bond_fund`/`cn_etf` (and tracked_index/theme fall-through).
5. Add `fetch_fund_nav_report` adapter in `akshare_fundamentals.py` (mocked tests).
6. Add `fetch_fund_announcements` adapter (3 endpoints, union, dedup, sort) in `akshare_fundamentals.py`.
7. Add NAV cache I/O (`nav_cache_path`, `write_nav_cache`, `load_nav_cache`) in `snapshot_cache.py`.
8. Add `_build_qdii_sentinel_snapshot` to `snapshot.py` (zero-fetch, in-process).
9. Add `_build_fund_level_snapshot` to `snapshot.py` (composes NAV + announcement evidence).
10. Extend `build_snapshot` dispatch with the two new branches BEFORE legacy fall-through.
11. Lock the F5 static-profile invariant via grep-based test.
12. Wire `_build_rows` autobuild to dispatch fund-level + QDII kinds; route `FundLevelSnapshot.evidence` into `OpportunityRow.thesis_evidence`.
13. Extend `FetchPlan` with fund-level cold/stale tally; integration test with mocked adapters.
14. Citation_id determinism + integration test (3-row fixture: gold + bond + cn_etf).
15. Final: full `pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q` + `ruff check src/ tests/` clean.

---

## Task 1: Add `FundNavReport` dataclass

**Files:**
- Modify: `src/irc/fundamentals/types.py`
- Test: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_types.py`:

```python
import pytest

from irc.fundamentals.types import FundNavReport


def test_fund_nav_report_construction_happy() -> None:
    r = FundNavReport(
        fund_id="518880",
        fund_name="华安黄金易ETF",
        latest_nav=4.5678,
        latest_nav_date="2026-03-15",
        nav_history=(("2026-03-14", 4.5500), ("2026-03-15", 4.5678)),
        source_report_quarter="2026Q1",
    )
    assert r.fund_id == "518880"
    assert r.latest_nav == 4.5678
    assert r.source_report_quarter == "2026Q1"


def test_fund_nav_report_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 1.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_non_positive_nav() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=0.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 0.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_malformed_date() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026/03/15",  # wrong separator
            nav_history=(("2026/03/15", 1.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_empty_history() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_history_mismatch_with_latest() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-14", 0.99),),  # last date != latest_nav_date
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_malformed_quarter() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 1.0),),
            source_report_quarter="2026-Q1",  # extra hyphen
        )
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_types.py::test_fund_nav_report_construction_happy -v`
Expected: FAIL with `ImportError: cannot import name 'FundNavReport' from 'irc.fundamentals.types'`.

- [ ] **Step 3: Implement `FundNavReport`**

Append to `src/irc/fundamentals/types.py` (BEFORE the closing if there's any; if no closing structure, append at end):

```python
import re as _re  # local alias to avoid clashing with any top-level re import


_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUARTER_RE_FNR = _re.compile(r"^\d{4}Q[1-4]$")


@dataclass(frozen=True)
class FundNavReport:
    """Fund-level NAV snapshot. `latest_nav_date` is ISO 8601 `str` — adapter
    converts AkShare's `datetime.date` via `.isoformat()`."""
    fund_id: str
    fund_name: str
    latest_nav: float
    latest_nav_date: str
    nav_history: tuple[tuple[str, float], ...]
    source_report_quarter: str

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundNavReport.fund_id must be non-empty")
        if self.latest_nav <= 0:
            raise ValueError(
                f"FundNavReport.latest_nav must be > 0; got {self.latest_nav}"
            )
        if not _ISO_DATE_RE.match(self.latest_nav_date):
            raise ValueError(
                f"FundNavReport.latest_nav_date must be ISO YYYY-MM-DD; "
                f"got {self.latest_nav_date!r}"
            )
        if not self.nav_history:
            raise ValueError("FundNavReport.nav_history must be non-empty")
        last_date, last_nav = self.nav_history[-1]
        if last_date != self.latest_nav_date:
            raise ValueError(
                f"FundNavReport.nav_history[-1][0]={last_date!r} must equal "
                f"latest_nav_date={self.latest_nav_date!r}"
            )
        if round(last_nav, 6) != round(self.latest_nav, 6):
            raise ValueError(
                f"FundNavReport.nav_history[-1][1]={last_nav} must equal "
                f"latest_nav={self.latest_nav} (to 6dp)"
            )
        if not _QUARTER_RE_FNR.match(self.source_report_quarter):
            raise ValueError(
                f"FundNavReport.source_report_quarter must match YYYYQ[1-4]; "
                f"got {self.source_report_quarter!r}"
            )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_types.py -k "fund_nav_report" -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): add FundNavReport dataclass with strict __post_init__ validation"
```

---

## Task 2: Add `FundAnnouncement` dataclass

**Files:**
- Modify: `src/irc/fundamentals/types.py`
- Test: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_types.py`:

```python
from irc.fundamentals.types import FundAnnouncement


def test_fund_announcement_construction_happy() -> None:
    a = FundAnnouncement(
        fund_id="518880",
        title="关于华安易富黄金交易型开放式证券投资基金基金份额折算日的公告",
        topic="dividend",
        date="2013-07-24",
        report_id="AN201307240003689710",
    )
    assert a.fund_id == "518880"
    assert a.topic == "dividend"
    assert a.report_id.startswith("AN")


def test_fund_announcement_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="", title="x", topic="dividend",
            date="2024-01-01", report_id="AN1",
        )


def test_fund_announcement_rejects_empty_title() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="", topic="dividend",
            date="2024-01-01", report_id="AN1",
        )


def test_fund_announcement_rejects_empty_report_id() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="x", topic="dividend",
            date="2024-01-01", report_id="",
        )


def test_fund_announcement_rejects_malformed_date() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="x", topic="dividend",
            date="20240101", report_id="AN1",  # missing hyphens
        )
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_types.py::test_fund_announcement_construction_happy -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `FundAnnouncement`**

Append to `src/irc/fundamentals/types.py`:

```python
@dataclass(frozen=True)
class FundAnnouncement:
    """One fund-specific announcement. `date` is ISO 8601 `str` — adapter
    normalises AkShare's `datetime.date` via `.isoformat()`. `report_id` is
    the opaque `报告ID` provider reference (no URL column in AkShare 1.18.63's
    topic-specific announcement endpoints)."""
    fund_id: str
    title: str
    topic: Literal["dividend", "report", "personnel"]
    date: str
    report_id: str

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundAnnouncement.fund_id must be non-empty")
        if not self.title:
            raise ValueError("FundAnnouncement.title must be non-empty")
        if not self.report_id:
            raise ValueError("FundAnnouncement.report_id must be non-empty")
        if not _ISO_DATE_RE.match(self.date):
            raise ValueError(
                f"FundAnnouncement.date must be ISO YYYY-MM-DD; got {self.date!r}"
            )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_types.py -k "fund_announcement" -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): add FundAnnouncement dataclass with ISO-date + non-empty-field validation"
```

---

## Task 3: Add `FundLevelSnapshot` dataclass + extend `__all__`

**Files:**
- Modify: `src/irc/fundamentals/types.py`
- Test: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_types.py`:

```python
from irc.fundamentals.types import FundLevelSnapshot, ThesisEvidence


def test_fund_level_snapshot_construction_minimal() -> None:
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
    )
    assert snap.fund_id == "518880"
    assert snap.fund_level_failure_reasons == ()
    assert snap.evidence_gaps == ()


def test_fund_level_snapshot_qdii_sentinel_shape() -> None:
    snap = FundLevelSnapshot(
        fund_id="qdii_us:sp500",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        evidence_gaps=("qdii_information_unavailable",),
    )
    assert snap.evidence_gaps == ("qdii_information_unavailable",)
    assert snap.nav_report is None


def test_fund_level_snapshot_carries_evidence_tuple() -> None:
    e = ThesisEvidence(
        type="snapshot", source="518880", url="",
        date="2026-03-15",
        summary="NAV=4.5678 @ 2026-03-15",
        scope="instrument", citation_kind="data",
        owner_instrument_id="518880",
        parent_fund_id=None, constituent_key=None,
    )
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(e,),
        source_report_quarter="2026Q1",
        cache_probed_at="2026-05-23",
    )
    assert len(snap.evidence) == 1
    assert snap.evidence[0].citation_kind == "data"


def test_fund_level_snapshot_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundLevelSnapshot(
            fund_id="",
            nav_report=None,
            announcements=(),
            evidence=(),
            source_report_quarter="",
            cache_probed_at="",
        )


def test_fund_level_snapshot_in_all() -> None:
    from irc.fundamentals import types as _t
    assert "FundLevelSnapshot" in _t.__all__
    assert "FundNavReport" in _t.__all__
    assert "FundAnnouncement" in _t.__all__
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_types.py::test_fund_level_snapshot_construction_minimal -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `FundLevelSnapshot` + extend `__all__`**

Append to `src/irc/fundamentals/types.py`:

```python
@dataclass(frozen=True)
class FundLevelSnapshot:
    """Full per-fund result for non-active V1 asset classes (gold, cn_bond_fund,
    cn_etf, tracked CN ETFs). Distinct from `ActiveFundSnapshot` (per-constituent
    analyses) and `ConstituentSnapshot` (legacy display-only). The QDII sentinel
    case sets `nav_report=None, announcements=(), evidence=(), evidence_gaps=
    ("qdii_information_unavailable",)` and is NOT cached on disk (grill Q5).

    See ADR 0002 §5 (Fund-level engine).
    """
    fund_id: str
    nav_report: FundNavReport | None
    announcements: tuple[FundAnnouncement, ...]
    evidence: tuple[ThesisEvidence, ...]
    source_report_quarter: str
    cache_probed_at: str
    fund_level_failure_reasons: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundLevelSnapshot.fund_id must be non-empty")
```

Edit `__all__` in `src/irc/fundamentals/types.py` — replace:

```python
__all__ = [
    "ActiveFundSnapshot",
    "BrokerReport",
    "CitationKind",
    "CitationScope",
    "Constituent",
    "ConstituentAnalysis",
    "ConstituentSnapshot",
    "FilingDigest",
    "FundHolding",
    "HoldingsResult",
    "LookthroughKind",
    "LookthroughTarget",
    "NewsItem",
    "ThesisEvidence",
    "ThesisEvidenceKind",
]
```

with:

```python
__all__ = [
    "ActiveFundSnapshot",
    "BrokerReport",
    "CitationKind",
    "CitationScope",
    "Constituent",
    "ConstituentAnalysis",
    "ConstituentSnapshot",
    "FilingDigest",
    "FundAnnouncement",
    "FundHolding",
    "FundLevelSnapshot",
    "FundNavReport",
    "HoldingsResult",
    "LookthroughKind",
    "LookthroughTarget",
    "NewsItem",
    "ThesisEvidence",
    "ThesisEvidenceKind",
]
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_types.py -v`
Expected: All pre-existing + 5 new FundLevelSnapshot tests + Task 1's 7 + Task 2's 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): add FundLevelSnapshot dataclass + export new types in __all__"
```

---

## Task 4: Patch `map_lookthrough` to populate `provider_symbol` for `gold`/`cn_bond_fund`/`cn_etf`

**Files:**
- Modify: `src/irc/opportunity/lookthrough.py`
- Test: `tests/opportunity/test_lookthrough.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_lookthrough.py`:

```python
def test_map_lookthrough_gold_populates_provider_symbol() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="518880", asset_class="gold", market="cn_off_exchange",
        name_cn="华安黄金易ETF",
    )
    t = map_lookthrough(inp)
    assert t.kind == "gold"
    assert t.provider_symbol == "518880"


def test_map_lookthrough_cn_bond_fund_populates_provider_symbol() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="000001", asset_class="cn_bond_fund", market="cn_off_exchange",
        name_cn="华夏债券",
    )
    t = map_lookthrough(inp)
    assert t.kind == "bond"
    assert t.provider_symbol == "000001"


def test_map_lookthrough_cn_etf_tracked_index_populates_provider_symbol() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_exchange", tracked_index="csi300",
        name_cn="华泰柏瑞沪深300ETF",
    )
    t = map_lookthrough(inp)
    assert t.kind == "broad_index"
    assert t.provider_symbol == "510300"


def test_map_lookthrough_cn_etf_theme_populates_provider_symbol() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="512480", asset_class="cn_etf",
        market="cn_exchange", theme="semiconductor",
        name_cn="国联安半导体ETF",
    )
    t = map_lookthrough(inp)
    assert t.kind == "sector_theme"
    assert t.provider_symbol == "512480"


def test_map_lookthrough_qdii_us_leaves_provider_symbol_empty() -> None:
    # QDII routes to qdii_us; provider_symbol stays empty (no fund-level dispatch).
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="513500", asset_class="us_etf",
        market="cn_exchange", tracked_index="sp500",
        name_cn="博时标普500ETF",
    )
    t = map_lookthrough(inp)
    assert t.kind == "qdii_us"
    assert t.provider_symbol == ""


def test_map_lookthrough_unknown_tracked_index_propagates_provider_symbol() -> None:
    # Unknown tracked_index falls through to broad_index branch — must still
    # populate provider_symbol so the dispatch can resolve.
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="159999", asset_class="cn_etf",
        market="cn_exchange", tracked_index="unknown_idx",
        name_cn="未知ETF",
    )
    t = map_lookthrough(inp)
    assert t.kind == "broad_index"
    assert t.provider_symbol == "159999"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_lookthrough.py::test_map_lookthrough_gold_populates_provider_symbol -v`
Expected: FAIL — `provider_symbol == ""` (current behaviour).

- [ ] **Step 3: Patch `map_lookthrough`**

Edit `src/irc/opportunity/lookthrough.py`. Replace these three lines/blocks:

```python
    if inp.asset_class == "gold":
        return LookthroughTarget("gold", "gold", "黄金")

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget("bond", "cn_bond", "中国债券")
```

with:

```python
    if inp.asset_class == "gold":
        return LookthroughTarget(
            "gold", "gold", "黄金", provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget(
            "bond", "cn_bond", "中国债券", provider_symbol=inp.instrument_id,
        )
```

Also replace the `tracked_index` block:

```python
    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget("broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked])
        if tracked in _QDII_US_KEYS:
            return LookthroughTarget("qdii_us", tracked, _QDII_US_DISPLAY[tracked])
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget("qdii_hk", tracked, _QDII_HK_DISPLAY[tracked])
        # Unknown index: classify as broad_index but keep the raw key
        return LookthroughTarget("broad_index", tracked, tracked)

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget("sector_theme", theme, _SECTOR_THEME_DISPLAY[theme])

    return LookthroughTarget("broad_index", "unknown", "未知底层")
```

with:

```python
    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget(
                "broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked],
                provider_symbol=inp.instrument_id,
            )
        if tracked in _QDII_US_KEYS:
            # QDII rows do NOT dispatch to fund-level; provider_symbol stays empty.
            return LookthroughTarget("qdii_us", tracked, _QDII_US_DISPLAY[tracked])
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget("qdii_hk", tracked, _QDII_HK_DISPLAY[tracked])
        # Unknown index: classify as broad_index but keep the raw key + provider_symbol.
        return LookthroughTarget(
            "broad_index", tracked, tracked, provider_symbol=inp.instrument_id,
        )

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget(
            "sector_theme", theme, _SECTOR_THEME_DISPLAY[theme],
            provider_symbol=inp.instrument_id,
        )

    return LookthroughTarget("broad_index", "unknown", "未知底层")
```

> Note: the `us_etf` / `hk_etf` / `qdii_global` branches (above the `tracked` block) are intentionally NOT patched — QDII rows route via the sentinel and do not need `provider_symbol`. The final `return LookthroughTarget("broad_index", "unknown", "未知底层")` line is also left empty-provider — that's the catch-all for un-mappable rows; legacy display path covers them.

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_lookthrough.py -v`
Expected: All pre-existing + 6 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough.py
git commit -m "feat(opportunity): map_lookthrough populates provider_symbol for gold/bond/cn_etf (item 005 F3 pre-req)"
```

---

## Task 5: Add `fetch_fund_nav_report` adapter

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Create: `tests/fundamentals/test_fetch_fund_nav_report.py`
- Create: `tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json`

- [ ] **Step 1: Create the NAV fixture**

Create `tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json`:

```json
{
  "columns": ["净值日期", "单位净值", "日增长率"],
  "rows": [
    {"净值日期": "2026-03-13", "单位净值": 4.5400, "日增长率": "0.12"},
    {"净值日期": "2026-03-14", "单位净值": 4.5500, "日增长率": "0.22"},
    {"净值日期": "2026-03-15", "单位净值": 4.5678, "日增长率": "0.39"}
  ],
  "captured_at": "2026-05-23T00:00:00Z",
  "akshare_version": "1.18.63"
}
```

- [ ] **Step 2: Write failing tests**

Create `tests/fundamentals/test_fetch_fund_nav_report.py`:

```python
"""Unit tests for fetch_fund_nav_report (mocked _ak_call)."""
from __future__ import annotations

import datetime as _dt
from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.akshare_fundamentals import fetch_fund_nav_report
from irc.fundamentals.types import FundNavReport


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [
            _dt.date(2026, 3, 13),
            _dt.date(2026, 3, 14),
            _dt.date(2026, 3, 15),
        ],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })


def test_fetch_fund_nav_report_happy_path() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    assert mocked.call_args[0][0] == "fund_open_fund_info_em"
    assert mocked.call_args[1] == {
        "symbol": "518880", "indicator": "单位净值走势",
    }
    assert isinstance(out, FundNavReport)
    assert out.fund_id == "518880"
    assert out.latest_nav == 4.5678
    assert out.latest_nav_date == "2026-03-15"
    assert out.source_report_quarter == "2026Q1"
    assert out.nav_history[-1] == ("2026-03-15", 4.5678)
    assert len(out.nav_history) == 3


def test_fetch_fund_nav_report_converts_datetime_date_to_iso() -> None:
    """`净值日期` arrives as datetime.date; adapter normalises via .isoformat()."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    for d, _v in out.nav_history:
        assert isinstance(d, str)
        assert len(d) == 10  # YYYY-MM-DD


def test_fetch_fund_nav_report_empty_frame_returns_none() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_fund_nav_report("999999")
    assert out is None


def test_fetch_fund_nav_report_missing_columns_returns_none() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame({"foo": [1, 2]})
        out = fetch_fund_nav_report("518880")
    assert out is None


def test_fetch_fund_nav_report_adapter_exception_returns_none() -> None:
    """Adapter never raises (matches fetch_cn_filing_digest contract)."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.side_effect = ConnectionError("eastmoney 502")
        out = fetch_fund_nav_report("518880")
    assert out is None


def test_fetch_fund_nav_report_uses_only_nav_indicator() -> None:
    """F5 invariant: adapter must NEVER consult '基金概况'."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        fetch_fund_nav_report("518880")
    indicators = [
        kw.get("indicator") for _args, kw in mocked.call_args_list
    ]
    assert "基金概况" not in indicators
    assert indicators == ["单位净值走势"]


def test_fetch_fund_nav_report_string_date_passthrough() -> None:
    """If AkShare returns 净值日期 as str instead of date, adapter still works."""
    df = pd.DataFrame({
        "净值日期": ["2026-03-13", "2026-03-14", "2026-03-15"],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = df
        out = fetch_fund_nav_report("518880")
    assert out is not None
    assert out.latest_nav_date == "2026-03-15"


def test_fetch_fund_nav_report_fund_name_fallback_when_absent() -> None:
    """The NAV走势 indicator does NOT carry fund_name; adapter sets it to fund_id."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    assert out is not None
    # The adapter falls back to fund_id when no fund_name column is present.
    assert out.fund_name == "518880"
```

- [ ] **Step 3: Run failing**

Run: `pytest tests/fundamentals/test_fetch_fund_nav_report.py -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_fund_nav_report'`.

- [ ] **Step 4: Implement `fetch_fund_nav_report`**

Append to `src/irc/fundamentals/akshare_fundamentals.py`:

```python
from irc.fundamentals.types import FundNavReport
from irc.fundamentals.snapshot_cache import infer_quarter as _infer_quarter_for_nav


def _normalize_nav_date(value: Any) -> str:
    """Convert AkShare's 净值日期 (datetime.date | str) to ISO YYYY-MM-DD."""
    if hasattr(value, "isoformat"):
        # datetime.date / datetime.datetime — emit ISO date.
        iso = value.isoformat()
        return iso[:10]
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else s


def fetch_fund_nav_report(fund_id: str) -> FundNavReport | None:
    """Fund-level NAV time series via `ak.fund_open_fund_info_em`.

    Returns `FundNavReport` on success; `None` on empty / adapter failure
    (matches `fetch_cn_filing_digest`'s degrade-to-None contract).

    F5 invariant: this adapter consults ONLY `indicator="单位净值走势"`.
    `基金概况` is NEVER consulted (would emit static metadata that must not
    satisfy the information leg — see ADR 0002 §5).
    """
    try:
        df = _ak_call(
            "fund_open_fund_info_em",
            symbol=fund_id,
            indicator="单位净值走势",
        )
    except Exception:
        return None
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    needed = {"净值日期", "单位净值"}
    if not needed.issubset(df.columns):
        return None
    history: list[tuple[str, float]] = []
    for _, row in df.iterrows():
        try:
            iso_date = _normalize_nav_date(row["净值日期"])
            nav = float(row["单位净值"])
        except (TypeError, ValueError):
            continue
        if not iso_date or nav <= 0:
            continue
        history.append((iso_date, nav))
    if not history:
        return None
    history.sort(key=lambda t: t[0])
    last_date, last_nav = history[-1]
    quarter = _infer_quarter_from_date(last_date)
    if not quarter:
        return None
    try:
        return FundNavReport(
            fund_id=fund_id,
            fund_name=fund_id,  # NAV走势 indicator does not carry fund_name.
            latest_nav=last_nav,
            latest_nav_date=last_date,
            nav_history=tuple(history),
            source_report_quarter=quarter,
        )
    except ValueError:
        return None


def _infer_quarter_from_date(iso_date: str) -> str:
    """Calendar-quarter for NAV (per ADR 0002 §5 — NAV is a daily series,
    not a provider-declared disclosure quarter)."""
    try:
        y, m, _d = iso_date.split("-")
        year = int(y)
        month = int(m)
    except (ValueError, AttributeError):
        return ""
    if not (1 <= month <= 12):
        return ""
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"
```

> Note: we intentionally do NOT reuse `_infer_quarter_for_nav` (which is the imported `infer_quarter` from snapshot_cache); that helper uses the earnings-season convention (Qx → Q(x-1)), which is wrong for NAV. The local `_infer_quarter_from_date` uses the calendar-quarter rule per ADR 0002 §5. Remove the unused import added above.

After the implementation lands, clean up — remove the unused import:

```python
from irc.fundamentals.snapshot_cache import infer_quarter as _infer_quarter_for_nav
```

(leave only the import line out; `_infer_quarter_from_date` is self-contained).

- [ ] **Step 5: Run green**

Run: `pytest tests/fundamentals/test_fetch_fund_nav_report.py -v`
Expected: 8 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_fetch_fund_nav_report.py tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json
git commit -m "feat(fundamentals): add fetch_fund_nav_report adapter (NAV走势, degrade-to-None, calendar-quarter)"
```

---

## Task 6: Add `fetch_fund_announcements` adapter (3 endpoints, union, dedup, sort)

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Create: `tests/fundamentals/test_fetch_fund_announcements.py`

- [ ] **Step 1: Write failing tests**

Create `tests/fundamentals/test_fetch_fund_announcements.py`:

```python
"""Unit tests for fetch_fund_announcements (mocked _ak_call against item-004 fixtures)."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.akshare_fundamentals import fetch_fund_announcements
from irc.fundamentals.types import FundAnnouncement


_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "akshare"


def _load_fixture(name: str) -> pd.DataFrame:
    body = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    rows = body["rows"]
    df = pd.DataFrame(rows)
    # Convert 公告日期 from ISO str (as captured in JSON) back to datetime.date,
    # matching AkShare's live behaviour.
    if "公告日期" in df.columns:
        df["公告日期"] = df["公告日期"].apply(
            lambda s: _dt.date.fromisoformat(s) if isinstance(s, str) and len(s) == 10 else s
        )
    return df


def _mock_3_endpoints_for(fund_id: str):
    """Return a side_effect callable for _ak_call that resolves the 3 endpoints."""
    dividend = _load_fixture(f"fund_announcement_dividend_em_{fund_id}.json")
    report = _load_fixture(f"fund_announcement_report_em_{fund_id}.json")
    personnel = _load_fixture(f"fund_announcement_personnel_em_{fund_id}.json")

    def _side(fn_name, **kw):
        if fn_name == "fund_announcement_dividend_em":
            return dividend
        if fn_name == "fund_announcement_report_em":
            return report
        if fn_name == "fund_announcement_personnel_em":
            return personnel
        raise AssertionError(f"unexpected _ak_call: {fn_name}")
    return _side


def test_fetch_fund_announcements_518880_union_shape() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ) as mocked:
        out = fetch_fund_announcements("518880")
    assert mocked.call_count == 3
    assert isinstance(out, tuple)
    for a in out:
        assert isinstance(a, FundAnnouncement)
        assert a.fund_id == "518880"
        assert a.topic in {"dividend", "report", "personnel"}
        # ISO date shape.
        assert len(a.date) == 10
        assert a.date[4] == "-" and a.date[7] == "-"
        assert a.report_id  # non-empty


def test_fetch_fund_announcements_calls_3_endpoints_in_order() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ) as mocked:
        fetch_fund_announcements("518880")
    fns = [args[0] for args, _kw in mocked.call_args_list]
    assert fns == [
        "fund_announcement_dividend_em",
        "fund_announcement_report_em",
        "fund_announcement_personnel_em",
    ]


def test_fetch_fund_announcements_sorted_by_date_desc_report_id_asc() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ) as mocked:
        out = fetch_fund_announcements("518880")
    # Date descending; tie-break by report_id ascending.
    for prev, curr in zip(out, out[1:]):
        if prev.date == curr.date:
            assert prev.report_id <= curr.report_id
        else:
            assert prev.date > curr.date


def test_fetch_fund_announcements_dedup_by_report_id() -> None:
    """If two endpoints return the same 报告ID, the unioned tuple keeps one entry,
    with topic determined by call order (dividend > report > personnel)."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["dup-via-dividend"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": ["DUP1"],
    })
    report = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["dup-via-report"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": ["DUP1"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["unique-personnel"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 2)],
        "报告ID": ["UNI1"],
    })

    def _side(fn_name, **kw):
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_report_em": report,
            "fund_announcement_personnel_em": personnel,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    by_id = {a.report_id: a for a in out}
    assert set(by_id.keys()) == {"DUP1", "UNI1"}
    # First-observed endpoint (dividend) wins.
    assert by_id["DUP1"].topic == "dividend"
    assert by_id["DUP1"].title == "dup-via-dividend"


def test_fetch_fund_announcements_endpoint_exception_degrades_to_empty() -> None:
    """Per-endpoint failure does NOT raise; remaining endpoints still queried."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)], "报告ID": ["AN1"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["y"], "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 2)], "报告ID": ["AN2"],
    })

    def _side(fn_name, **kw):
        if fn_name == "fund_announcement_report_em":
            raise ConnectionError("east 502")
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_personnel_em": personnel,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    assert len(out) == 2
    assert {a.report_id for a in out} == {"AN1", "AN2"}


def test_fetch_fund_announcements_all_endpoints_fail_returns_empty() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=RuntimeError("boom"),
    ):
        out = fetch_fund_announcements("518880")
    assert out == ()


def test_fetch_fund_announcements_string_date_passthrough() -> None:
    """If 公告日期 arrives as ISO str, adapter still produces ISO str output."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
        "公告日期": ["2024-04-15"], "报告ID": ["AN1"],
    })
    empty = pd.DataFrame()

    def _side(fn_name, **kw):
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_report_em": empty,
            "fund_announcement_personnel_em": empty,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    assert len(out) == 1
    assert out[0].date == "2024-04-15"


def test_fetch_fund_announcements_000001_fixture_shape() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("000001"),
    ):
        out = fetch_fund_announcements("000001")
    assert len(out) > 0
    assert all(a.fund_id == "000001" for a in out)


def test_fetch_fund_announcements_005827_fixture_shape() -> None:
    """Regression: active funds CAN call this adapter (shape-only check)."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("005827"),
    ):
        out = fetch_fund_announcements("005827")
    assert len(out) > 0
    assert all(a.fund_id == "005827" for a in out)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_fetch_fund_announcements.py::test_fetch_fund_announcements_518880_union_shape -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `fetch_fund_announcements`**

Append to `src/irc/fundamentals/akshare_fundamentals.py`:

```python
from irc.fundamentals.types import FundAnnouncement


_FUND_ANN_TOPIC_FNS: tuple[tuple[str, str], ...] = (
    ("fund_announcement_dividend_em", "dividend"),
    ("fund_announcement_report_em", "report"),
    ("fund_announcement_personnel_em", "personnel"),
)


def _normalize_ann_date(value: Any) -> str:
    """Convert AkShare's 公告日期 (datetime.date | str) to ISO YYYY-MM-DD."""
    if hasattr(value, "isoformat"):
        iso = value.isoformat()
        return iso[:10]
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else s


def _parse_announcements_frame(
    df: object, fund_id: str, topic: str,
) -> list[FundAnnouncement]:
    """Parse one endpoint's DataFrame to a list of FundAnnouncement.

    Per-row parse failures are skipped silently (degrade-to-empty contract).
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    needed = {"公告标题", "公告日期", "报告ID"}
    if not needed.issubset(df.columns):
        return []
    out: list[FundAnnouncement] = []
    for _, row in df.iterrows():
        try:
            title = str(row["公告标题"]).strip()
            iso_date = _normalize_ann_date(row["公告日期"])
            report_id = str(row["报告ID"]).strip()
            if not title or not iso_date or not report_id:
                continue
            out.append(FundAnnouncement(
                fund_id=fund_id,
                title=title,
                topic=topic,  # type: ignore[arg-type]
                date=iso_date,
                report_id=report_id,
            ))
        except (ValueError, TypeError):
            continue
    return out


def fetch_fund_announcements(fund_id: str) -> tuple[FundAnnouncement, ...]:
    """Topic-unioned fund announcements via 3 AkShare endpoints.

    Calls `fund_announcement_dividend_em`, `fund_announcement_report_em`,
    `fund_announcement_personnel_em` serially. Per-endpoint exceptions
    degrade to empty for that endpoint (remaining endpoints still called).

    Dedup key: `(fund_id, report_id)`; first-observed `topic` wins
    (call order: dividend → report → personnel — deterministic).

    Returns tuple sorted by `date desc, report_id asc`.

    Never raises. Empty union → caller stamps `fund_announcements_unavailable`.
    """
    seen: dict[str, FundAnnouncement] = {}
    for fn_name, topic in _FUND_ANN_TOPIC_FNS:
        try:
            df = _ak_call(fn_name, symbol=fund_id)
        except Exception:
            continue
        for ann in _parse_announcements_frame(df, fund_id, topic):
            # Dedup by report_id; first observed (per call order) wins.
            if ann.report_id not in seen:
                seen[ann.report_id] = ann
    items = list(seen.values())
    items.sort(key=lambda a: a.report_id)        # tie-break asc
    items.sort(key=lambda a: a.date, reverse=True)  # primary: date desc
    return tuple(items)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_fetch_fund_announcements.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_fetch_fund_announcements.py
git commit -m "feat(fundamentals): add fetch_fund_announcements (3-endpoint union, dedup by report_id, sort by date desc)"
```

---

## Task 7: Add NAV cache I/O in `snapshot_cache.py`

**Files:**
- Modify: `src/irc/fundamentals/snapshot_cache.py`
- Test: `tests/fundamentals/test_snapshot_cache.py` (extend or create)

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_snapshot_cache.py` (create the file if missing — base it on the active-fund cache pattern):

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.fundamentals.snapshot_cache import (
    nav_cache_path,
    load_nav_cache,
    write_nav_cache,
)
from irc.fundamentals.types import (
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
    ThesisEvidence,
)


def _make_snap(tmp_id: str = "518880") -> FundLevelSnapshot:
    nav = FundNavReport(
        fund_id=tmp_id,
        fund_name=tmp_id,
        latest_nav=4.5678,
        latest_nav_date="2026-03-15",
        nav_history=(
            ("2026-03-14", 4.5500),
            ("2026-03-15", 4.5678),
        ),
        source_report_quarter="2026Q1",
    )
    ann = FundAnnouncement(
        fund_id=tmp_id,
        title="x",
        topic="dividend",
        date="2024-01-01",
        report_id="AN1",
    )
    ev = ThesisEvidence(
        type="snapshot", source=tmp_id, url="",
        date="2026-03-15",
        summary="NAV=4.5678 @ 2026-03-15",
        scope="instrument", citation_kind="data",
        owner_instrument_id=tmp_id,
        parent_fund_id=None, constituent_key=None,
    )
    return FundLevelSnapshot(
        fund_id=tmp_id,
        nav_report=nav,
        announcements=(ann,),
        evidence=(ev,),
        source_report_quarter="2026Q1",
        cache_probed_at="2026-05-23",
    )


def test_nav_cache_path_layout(tmp_path: Path) -> None:
    p = nav_cache_path("518880", "2026Q1", tmp_path)
    assert p == tmp_path / "fundamentals" / "2026Q1" / "nav" / "fund_518880.json"


def test_write_and_load_nav_cache_roundtrip(tmp_path: Path) -> None:
    snap = _make_snap()
    written = write_nav_cache(snap, tmp_path)
    assert written.exists()
    loaded = load_nav_cache("518880", "2026Q1", tmp_path)
    assert loaded is not None
    assert loaded.fund_id == "518880"
    assert loaded.nav_report is not None
    assert loaded.nav_report.latest_nav == 4.5678
    assert loaded.announcements[0].report_id == "AN1"
    assert loaded.evidence[0].citation_kind == "data"
    # citation_id is content-addressed → recomputed on load — assert equality.
    assert loaded.evidence[0].citation_id == snap.evidence[0].citation_id


def test_load_nav_cache_missing_returns_none(tmp_path: Path) -> None:
    assert load_nav_cache("518880", "2026Q1", tmp_path) is None


def test_load_nav_cache_malformed_json_returns_none(tmp_path: Path) -> None:
    p = nav_cache_path("518880", "2026Q1", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json{", encoding="utf-8")
    assert load_nav_cache("518880", "2026Q1", tmp_path) is None


def test_write_nav_cache_atomic_tmp_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The .tmp.{pid} → os.replace pattern leaves no .tmp file behind."""
    snap = _make_snap()
    written = write_nav_cache(snap, tmp_path)
    leftover = list(written.parent.glob("*.tmp.*"))
    assert leftover == []
    assert written.exists()


def test_write_nav_cache_skips_qdii_sentinel(tmp_path: Path) -> None:
    """Per grill Q5: QDII sentinel (evidence_gaps == qdii_information_unavailable)
    is NOT serialized to disk."""
    sentinel = FundLevelSnapshot(
        fund_id="513500",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        evidence_gaps=("qdii_information_unavailable",),
    )
    written = write_nav_cache(sentinel, tmp_path)
    # Sentinel writers return a sentinel path (or None) — the file MUST NOT exist.
    assert not (tmp_path / "fundamentals").exists() or not any(
        (tmp_path / "fundamentals").rglob("fund_513500.json")
    )
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_snapshot_cache.py::test_nav_cache_path_layout -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement NAV cache I/O**

Append to `src/irc/fundamentals/snapshot_cache.py`:

```python
from irc.fundamentals.types import (
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
)


def nav_cache_path(fund_id: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / "nav" / f"fund_{fund_id}.json"


def _nav_report_to_dict(r: FundNavReport) -> dict[str, Any]:
    return {
        "fund_id": r.fund_id,
        "fund_name": r.fund_name,
        "latest_nav": r.latest_nav,
        "latest_nav_date": r.latest_nav_date,
        "nav_history": [list(t) for t in r.nav_history],
        "source_report_quarter": r.source_report_quarter,
    }


def _nav_report_from_dict(d: dict[str, Any]) -> FundNavReport:
    return FundNavReport(
        fund_id=str(d["fund_id"]),
        fund_name=str(d.get("fund_name", "")),
        latest_nav=float(d["latest_nav"]),
        latest_nav_date=str(d["latest_nav_date"]),
        nav_history=tuple(
            (str(item[0]), float(item[1]))
            for item in d.get("nav_history", [])
        ),
        source_report_quarter=str(d["source_report_quarter"]),
    )


def _ann_to_dict(a: FundAnnouncement) -> dict[str, Any]:
    return {
        "fund_id": a.fund_id,
        "title": a.title,
        "topic": a.topic,
        "date": a.date,
        "report_id": a.report_id,
    }


def _ann_from_dict(d: dict[str, Any]) -> FundAnnouncement:
    return FundAnnouncement(
        fund_id=str(d["fund_id"]),
        title=str(d["title"]),
        topic=str(d["topic"]),  # type: ignore[arg-type]
        date=str(d["date"]),
        report_id=str(d["report_id"]),
    )


def _fund_level_to_dict(snap: FundLevelSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "nav_report": (
            _nav_report_to_dict(snap.nav_report)
            if snap.nav_report is not None else None
        ),
        "announcements": [_ann_to_dict(a) for a in snap.announcements],
        "evidence": [_evidence_to_dict(e) for e in snap.evidence],
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
        "evidence_gaps": list(snap.evidence_gaps),
    }


def _fund_level_from_dict(body: dict[str, Any]) -> FundLevelSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "evidence"}
    if not needed.issubset(body):
        return None
    try:
        nav_report = (
            _nav_report_from_dict(body["nav_report"])
            if body.get("nav_report") is not None else None
        )
        announcements = tuple(
            _ann_from_dict(a) for a in body.get("announcements", [])
        )
        evidence = tuple(
            _evidence_from_dict(e) for e in body.get("evidence", [])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return FundLevelSnapshot(
        fund_id=str(body["fund_id"]),
        nav_report=nav_report,
        announcements=announcements,
        evidence=evidence,
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        fund_level_failure_reasons=tuple(
            body.get("fund_level_failure_reasons", ())
        ),
        evidence_gaps=tuple(body.get("evidence_gaps", ())),
    )


def write_nav_cache(snap: FundLevelSnapshot, root: Path) -> Path:
    """Atomic write of `FundLevelSnapshot` to NAV cache. Skips QDII sentinel
    (grill Q5: gap-only rows have nothing to cache)."""
    # Sentinel detection: QDII rows have this gap and nothing fetched.
    if "qdii_information_unavailable" in snap.evidence_gaps:
        return root / "fundamentals" / "qdii_sentinel_skipped.placeholder"
    path = nav_cache_path(snap.fund_id, snap.source_report_quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(_fund_level_to_dict(snap), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_nav_cache(
    fund_id: str, quarter: str, root: Path,
) -> FundLevelSnapshot | None:
    path = nav_cache_path(fund_id, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _fund_level_from_dict(body)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_snapshot_cache.py -v`
Expected: All pre-existing (if any) + 6 new NAV tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot_cache.py tests/fundamentals/test_snapshot_cache.py
git commit -m "feat(fundamentals): add nav_cache_path / write_nav_cache / load_nav_cache (NAV cache layout, QDII sentinel skip)"
```

---

## Task 8: Add `_build_qdii_sentinel_snapshot` in `snapshot.py`

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Create: `tests/fundamentals/test_fund_level_snapshot.py`

- [ ] **Step 1: Write failing tests**

Create `tests/fundamentals/test_fund_level_snapshot.py`:

```python
"""Unit tests for fund-level snapshot builders (item 005 F3/F4)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.snapshot import (
    _build_qdii_sentinel_snapshot,
    build_snapshot,
)
from irc.fundamentals.types import (
    FundLevelSnapshot,
    LookthroughTarget,
)


@pytest.mark.parametrize(
    "kind", ["qdii_us", "qdii_hk", "qdii_global"],
)
def test_qdii_sentinel_zero_fetch(kind: str) -> None:
    """No AkShare call should fire for any QDII kind."""
    target = LookthroughTarget(
        kind=kind, key=f"key_{kind}", display_cn="x",
        provider_symbol="ignored",
    )
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        snap = _build_qdii_sentinel_snapshot(target)
    assert mocked.call_count == 0
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.nav_report is None
    assert snap.announcements == ()
    assert snap.evidence == ()
    assert snap.evidence_gaps == ("qdii_information_unavailable",)


def test_qdii_sentinel_fund_id_fallback_to_key() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "qdii_us:sp500"


def test_qdii_sentinel_prefers_provider_symbol_when_present() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="513500",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "513500"


def test_build_snapshot_routes_all_qdii_kinds_to_sentinel() -> None:
    for kind in ("qdii_us", "qdii_hk", "qdii_global"):
        target = LookthroughTarget(kind=kind, key="x", display_cn="x")
        with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
            snap = build_snapshot(target)
        assert isinstance(snap, FundLevelSnapshot)
        assert snap.evidence_gaps == ("qdii_information_unavailable",)
        assert mocked.call_count == 0
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py::test_qdii_sentinel_zero_fetch -v`
Expected: FAIL with `ImportError` (function not yet defined).

- [ ] **Step 3: Implement `_build_qdii_sentinel_snapshot`**

Append to `src/irc/fundamentals/snapshot.py`:

```python
from irc.fundamentals.types import FundLevelSnapshot


def _build_qdii_sentinel_snapshot(target: LookthroughTarget) -> FundLevelSnapshot:
    """In-process sentinel for QDII V1 exclusion. ZERO AkShare calls.

    NOT cached on disk (grill Q5). Item 006's H3 universal-gap invariant
    reads `evidence_gaps=("qdii_information_unavailable",)` and routes the row
    to the discipline failure section. See ADR 0002 §5 F4.
    """
    fund_id = target.provider_symbol or target.key
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        fund_level_failure_reasons=(),
        evidence_gaps=("qdii_information_unavailable",),
    )
```

Now extend `build_snapshot` with the QDII branch only (the fund-level branch lands in Task 10). Edit `build_snapshot`:

```python
def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
) -> ActiveFundSnapshot | ConstituentSnapshot:
```

Change return-type union and dispatch:

```python
def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
) -> ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot:
    """Compose snapshot for a typed `LookthroughTarget`.

    `kind == "active_fund"` → `ActiveFundSnapshot` via _build_active_fund_snapshot.
    `kind in {"qdii_us", "qdii_hk", "qdii_global"}` → `FundLevelSnapshot` sentinel.
    All other kinds → legacy `ConstituentSnapshot` via the existing
    `display_cn`-keyed `_TARGET_REGISTRY`. (Fund-level dispatch lands in task 10.)
    """
    timestamp = as_of_iso or _today_iso()
    if target.kind == "active_fund":
        return _build_active_fund_snapshot(target, top_n=top_n)
    if target.kind in ("qdii_us", "qdii_hk", "qdii_global"):
        return _build_qdii_sentinel_snapshot(target)
    return _build_legacy_snapshot(target.display_cn, top_n=top_n, as_of_iso=timestamp)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_fund_level_snapshot.py
git commit -m "feat(fundamentals): add _build_qdii_sentinel_snapshot + dispatch QDII kinds in build_snapshot (F4)"
```

---

## Task 9: Add `_build_fund_level_snapshot` (composes NAV + announcement evidence)

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Test: `tests/fundamentals/test_fund_level_snapshot.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_fund_level_snapshot.py`:

```python
import datetime as _dt

from irc.fundamentals.snapshot import _build_fund_level_snapshot


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [
            _dt.date(2026, 3, 13),
            _dt.date(2026, 3, 14),
            _dt.date(2026, 3, 15),
        ],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })


def _ann_frames() -> dict[str, pd.DataFrame]:
    dividend = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["分红1", "分红2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 1, 1), _dt.date(2024, 2, 1)],
        "报告ID": ["AN1", "AN2"],
    })
    report = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["报告1", "报告2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 3, 1), _dt.date(2024, 4, 1)],
        "报告ID": ["AN3", "AN4"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["人事1", "人事2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 5, 1), _dt.date(2024, 6, 1)],
        "报告ID": ["AN5", "AN6"],
    })
    return {
        "fund_open_fund_info_em": _nav_frame(),
        "fund_announcement_dividend_em": dividend,
        "fund_announcement_report_em": report,
        "fund_announcement_personnel_em": personnel,
    }


def _make_side_effect(frames: dict[str, pd.DataFrame]):
    def _side(fn_name, **kw):
        return frames[fn_name]
    return _side


def test_build_fund_level_snapshot_emits_one_data_leg_and_announcements_info_leg() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.fund_id == "518880"
    assert snap.nav_report is not None
    assert snap.nav_report.latest_nav == 4.5678
    assert len(snap.announcements) == 6
    # Evidence: exactly one data-leg (NAV) + at most 3 info-leg (capped).
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert len(data) == 1
    assert data[0].type == "snapshot"
    assert data[0].scope == "instrument"
    assert data[0].owner_instrument_id == "518880"
    assert data[0].parent_fund_id is None
    assert data[0].constituent_key is None
    assert data[0].url == ""
    assert "NAV=4.5678 @ 2026-03-15" in data[0].summary
    assert data[0].holding_weight_pct is None
    assert len(info) == 3  # capped at 3
    for e in info:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == "518880"
        assert e.parent_fund_id is None
        assert e.constituent_key is None
        assert e.url == ""
        assert e.summary.startswith("[AN")  # [report_id] prefix
        assert e.type == "news"
        assert e.source.startswith("fund_announcement_") and e.source.endswith("_em")
    assert snap.source_report_quarter == "2026Q1"
    assert snap.evidence_gaps == ()
    assert snap.fund_level_failure_reasons == ()


def test_build_fund_level_snapshot_nav_only_stamps_announcement_gap() -> None:
    """NAV present but announcements all-empty → fund_announcements_unavailable."""
    target = LookthroughTarget(
        kind="bond", key="cn_bond", display_cn="中国债券",
        provider_symbol="000001",
    )
    frames = {
        "fund_open_fund_info_em": _nav_frame(),
        "fund_announcement_dividend_em": pd.DataFrame(),
        "fund_announcement_report_em": pd.DataFrame(),
        "fund_announcement_personnel_em": pd.DataFrame(),
    }
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(frames),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.nav_report is not None
    assert snap.announcements == ()
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert info == []
    assert "fund_announcements_unavailable" in snap.evidence_gaps


def test_build_fund_level_snapshot_nav_failure_stamps_nav_gap() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    frames = {
        "fund_open_fund_info_em": pd.DataFrame(),
        "fund_announcement_dividend_em": pd.DataFrame({
            "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
            "公告日期": [_dt.date(2024, 1, 1)], "报告ID": ["AN1"],
        }),
        "fund_announcement_report_em": pd.DataFrame(),
        "fund_announcement_personnel_em": pd.DataFrame(),
    }
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(frames),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.nav_report is None
    assert len(snap.announcements) == 1
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    assert data == []
    assert "fund_nav_unavailable" in snap.evidence_gaps


def test_build_fund_level_snapshot_announcement_info_summary_carries_report_id() -> None:
    """ADR 0001 §2: empty URL + summary "[{report_id}] {title}" makes citation_ids
    deterministic and unique."""
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    for e in info:
        # The bracketed report_id must appear in summary[:64] for ADR 0001 fallback.
        assert e.summary[:64].startswith("[AN")
        # Distinct entries → distinct citation_ids.
    ids = {e.citation_id for e in info}
    assert len(ids) == len(info)


def test_build_fund_level_snapshot_data_evidence_no_holding_weight() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    for e in data:
        assert e.holding_weight_pct is None
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py -k "build_fund_level" -v`
Expected: FAIL with `ImportError` (`_build_fund_level_snapshot` not defined).

- [ ] **Step 3: Implement `_build_fund_level_snapshot`**

Append to `src/irc/fundamentals/snapshot.py`. Add the imports at the top first if missing:

```python
from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_etf_holdings,
    fetch_cn_index_constituents,
    fetch_cn_stock_news,
    fetch_fund_announcements,
    fetch_fund_nav_report,
    fetch_hk_index_constituents,
)
```

(adding `fetch_fund_announcements` and `fetch_fund_nav_report` to the existing import block).

Then append the new builder:

```python
_FUND_LEVEL_INFO_CAP = 3


def _build_fund_level_snapshot(target: LookthroughTarget) -> FundLevelSnapshot:
    """Compose NAV (data leg) + announcements (information leg) for non-active
    V1 asset classes (gold, bond, broad_index, sector_theme — when the row IS
    itself a tradeable fund).

    See ADR 0002 §5 (Fund-level engine).
    """
    fund_id = target.provider_symbol
    nav = fetch_fund_nav_report(fund_id)
    anns = fetch_fund_announcements(fund_id)

    evidence: list[ThesisEvidence] = []
    gaps: list[str] = []
    failures: list[str] = []

    # Data leg: ONE evidence record per NAV (re-use existing "snapshot" literal
    # per grill Q4).
    if nav is not None:
        evidence.append(ThesisEvidence(
            type="snapshot",
            source=fund_id,
            url="",
            date=nav.latest_nav_date,
            summary=f"NAV={nav.latest_nav:.4f} @ {nav.latest_nav_date}",
            scope="instrument",
            citation_kind="data",
            owner_instrument_id=fund_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    else:
        gaps.append("fund_nav_unavailable")
        failures.append(f"fund_nav_fetch_failed:{fund_id}")

    # Information leg: up to N announcements (already date-desc / report_id-asc
    # from the adapter; capped at _FUND_LEVEL_INFO_CAP).
    if anns:
        for a in anns[:_FUND_LEVEL_INFO_CAP]:
            evidence.append(ThesisEvidence(
                type="news",
                source=f"fund_announcement_{a.topic}_em",
                url="",
                date=a.date,
                summary=f"[{a.report_id}] {a.title}",
                scope="instrument",
                citation_kind="information",
                owner_instrument_id=fund_id,
                parent_fund_id=None,
                constituent_key=None,
            ))
    else:
        gaps.append("fund_announcements_unavailable")
        failures.append(f"fund_announcements_fetch_failed:{fund_id}")

    quarter = nav.source_report_quarter if nav is not None else ""
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=nav,
        announcements=anns,
        evidence=tuple(evidence),
        source_report_quarter=quarter,
        cache_probed_at=_today_iso(),
        fund_level_failure_reasons=tuple(failures),
        evidence_gaps=tuple(gaps),
    )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py -v`
Expected: All Task 8 tests + 5 new builder tests = 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_fund_level_snapshot.py
git commit -m "feat(fundamentals): add _build_fund_level_snapshot (NAV data leg + announcements info leg, 3-cap)"
```

---

## Task 10: Extend `build_snapshot` dispatch with fund-level branch

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Test: `tests/fundamentals/test_fund_level_snapshot.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_fund_level_snapshot.py`:

```python
def test_build_snapshot_routes_gold_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.fund_id == "518880"


def test_build_snapshot_routes_bond_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="bond", key="cn_bond", display_cn="中国债券",
        provider_symbol="000001",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_broad_index_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="broad_index", key="csi300", display_cn="沪深300",
        provider_symbol="510300",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_sector_theme_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="sector_theme", key="semiconductor", display_cn="半导体",
        provider_symbol="512480",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_broad_index_without_provider_symbol_to_legacy() -> None:
    """Empty provider_symbol → falls through to legacy display-only path."""
    from irc.fundamentals.types import ConstituentSnapshot
    target = LookthroughTarget(
        kind="broad_index", key="csi300", display_cn="沪深300",
        provider_symbol="",
    )
    # Legacy path tries _build_cn_snapshot which calls fetch_cn_index_constituents.
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()  # legacy gets empty too
        snap = build_snapshot(target)
    # The legacy path returns ConstituentSnapshot, not FundLevelSnapshot.
    assert isinstance(snap, ConstituentSnapshot)


def test_build_snapshot_active_fund_path_unchanged() -> None:
    """Item 003 regression — active_fund kind still routes to _build_active_fund_snapshot."""
    from irc.fundamentals.types import ActiveFundSnapshot
    target = LookthroughTarget(
        kind="active_fund", key="fund_005827", display_cn="易方达蓝筹精选",
        provider_symbol="005827",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()  # holdings empty → empty snapshot
        snap = build_snapshot(target)
    assert isinstance(snap, ActiveFundSnapshot)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py::test_build_snapshot_routes_gold_with_provider_symbol_to_fund_level -v`
Expected: FAIL — currently routes to legacy `_build_legacy_snapshot` and returns `ConstituentSnapshot`.

- [ ] **Step 3: Wire the new dispatch branch**

Replace `build_snapshot` body in `src/irc/fundamentals/snapshot.py`:

```python
_FUND_LEVEL_KINDS: frozenset[str] = frozenset({
    "gold", "bond", "broad_index", "sector_theme",
})


def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
) -> ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot:
    """Compose snapshot for a typed `LookthroughTarget`.

    Dispatch keys off `target.kind` only (ADR 0002 §5):

    | kind                                | Branch                                    |
    |-------------------------------------|-------------------------------------------|
    | active_fund                         | _build_active_fund_snapshot (item 003)    |
    | qdii_us / qdii_hk / qdii_global     | _build_qdii_sentinel_snapshot (F4)        |
    | gold / bond / broad_index /         | _build_fund_level_snapshot (F3)           |
    |  sector_theme — w/ provider_symbol  |                                           |
    | (else / empty provider_symbol)      | _build_legacy_snapshot (display-only)     |
    """
    timestamp = as_of_iso or _today_iso()
    if target.kind == "active_fund":
        return _build_active_fund_snapshot(target, top_n=top_n)
    if target.kind in ("qdii_us", "qdii_hk", "qdii_global"):
        return _build_qdii_sentinel_snapshot(target)
    if target.kind in _FUND_LEVEL_KINDS and target.provider_symbol:
        return _build_fund_level_snapshot(target)
    return _build_legacy_snapshot(target.display_cn, top_n=top_n, as_of_iso=timestamp)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_fund_level_snapshot.py -v`
Expected: All Task 8 + 9 + 6 new routing tests = 16 PASS.

- [ ] **Step 5: Regression check**

Run: `pytest tests/fundamentals/ -v -x`
Expected: all pre-existing fundamentals tests + the new tests PASS. If `test_snapshot.py` references the old return-type union explicitly, those callers continue working because `FundLevelSnapshot` is added, not substituted. No active-fund regression.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_fund_level_snapshot.py
git commit -m "feat(fundamentals): dispatch fund-level kinds (gold/bond/broad_index/sector_theme) with provider_symbol to _build_fund_level_snapshot"
```

---

## Task 11: Lock F5 static-profile invariant via grep-based test

**Files:**
- Create: `tests/fundamentals/test_static_profile_invariant.py`

- [ ] **Step 1: Write failing test (or already-green if invariant holds)**

Create `tests/fundamentals/test_static_profile_invariant.py`:

```python
"""F5 static-profile invariant lock — see ADR 0002 §5.

`ak.fund_open_fund_info_em(symbol, indicator="基金概况")` MUST NOT be called
by item 005's production code. Fund profile text is static metadata, not a
time-bound communication; tagging it citation_kind="information" would
silently bypass the freshness intent of the information leg.

Enforcement is upstream at the adapter layer (no downstream gate can
distinguish indicator origin from ThesisEvidence). This test greps the
production module for the literal "基金概况" and asserts zero matches.
"""
from __future__ import annotations

from pathlib import Path


_PRODUCTION_FILE = (
    Path(__file__).resolve().parents[2]
    / "src" / "irc" / "fundamentals" / "akshare_fundamentals.py"
)


def test_static_profile_indicator_not_in_production() -> None:
    body = _PRODUCTION_FILE.read_text(encoding="utf-8")
    # Strict literal grep — comments and docstrings are EXEMPT only because
    # adding a documentation-only mention would still raise a false positive.
    # If a future slice needs to reference "基金概况" in a comment, qualify
    # it as e.g. "indicator='profile'" or "JIJIN_GAIKUANG_RAW" — never the
    # raw literal.
    assert "基金概况" not in body, (
        "F5 violated: production code references the '基金概况' indicator. "
        "See ADR 0002 §5 — static profile text must not satisfy the "
        "citation_kind='information' leg."
    )


def test_static_profile_indicator_not_in_snapshot() -> None:
    snapshot_file = (
        Path(__file__).resolve().parents[2]
        / "src" / "irc" / "fundamentals" / "snapshot.py"
    )
    assert "基金概况" not in snapshot_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run**

Run: `pytest tests/fundamentals/test_static_profile_invariant.py -v`
Expected: 2 PASS (the production code already complies — Task 5's adapter consults only `单位净值走势`).

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_static_profile_invariant.py
git commit -m "test(fundamentals): lock F5 static-profile invariant — grep '基金概况' in production code (ADR 0002 §5)"
```

---

## Task 12: Wire `_build_rows` autobuild to dispatch fund-level + QDII kinds

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Create: `tests/commands/test_opportunity_cmd_fund_level.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/test_opportunity_cmd_fund_level.py`:

```python
"""Integration tests: `_build_rows` autobuild dispatch for fund-level + QDII kinds."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# These fixtures stage minimal `_build_rows` inputs. They use the seam
# `irc.fundamentals.akshare_fundamentals._ak_call` for adapter mocking.


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [_dt.date(2026, 3, 15)],
        "单位净值": [4.5678],
        "日增长率": ["0.39"],
    })


def _ann_frame_with(report_id: str) -> pd.DataFrame:
    return pd.DataFrame({
        "基金代码": ["X"],
        "公告标题": [f"title-{report_id}"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": [report_id],
    })


def _make_universal_side_effect():
    """side_effect that returns NAV + 1 announcement per topic for any symbol."""

    def _side(fn_name, **kw):
        if fn_name == "fund_open_fund_info_em":
            return _nav_frame()
        if fn_name == "fund_announcement_dividend_em":
            return _ann_frame_with("ANDIV")
        if fn_name == "fund_announcement_report_em":
            return _ann_frame_with("ANREP")
        if fn_name == "fund_announcement_personnel_em":
            return _ann_frame_with("ANPER")
        # Fall through: legacy snapshot paths that may still be called.
        return pd.DataFrame()
    return _side


def test_build_snapshot_gold_row_emits_fund_level_evidence(tmp_path: Path) -> None:
    """End-to-end through build_snapshot for a gold target."""
    from irc.fundamentals.snapshot import build_snapshot
    from irc.fundamentals.types import FundLevelSnapshot, LookthroughTarget

    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_universal_side_effect(),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert len(data) == 1
    assert len(info) >= 1
    for e in snap.evidence:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == "518880"


def test_build_snapshot_qdii_row_emits_sentinel_zero_calls() -> None:
    from irc.fundamentals.snapshot import build_snapshot
    from irc.fundamentals.types import FundLevelSnapshot, LookthroughTarget

    target = LookthroughTarget(
        kind="qdii_global", key="global_equity", display_cn="qdii",
        provider_symbol="",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
    ) as mocked:
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.evidence_gaps == ("qdii_information_unavailable",)
    assert mocked.call_count == 0


def test_build_rows_routes_fund_level_evidence_into_opportunity_row(tmp_path: Path) -> None:
    """`_build_rows` integration: a gold row produces an OpportunityRow whose
    `thesis_evidence` carries the FundLevelSnapshot's evidence tuple."""
    from irc.commands.opportunity_cmd import _build_rows
    from irc.opportunity.types import OpportunityInput  # noqa: F401
    import duckdb

    # Minimal score row for gold.
    scores = [{
        "instrument_id": "518880", "asset_class": "gold",
        "role": "small_watch",
    }]
    instr_index: dict = {}
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = set()

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_universal_side_effect(),
    ):
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            rows, _positions, _q, _roles = _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    assert len(rows) == 1
    r = rows[0]
    assert r.instrument_id == "518880"
    # Fund-level evidence is forwarded into thesis_evidence.
    assert len(r.thesis_evidence) >= 2  # at least 1 data + 1 info
    kinds = {e.citation_kind for e in r.thesis_evidence}
    assert "data" in kinds
    assert "information" in kinds
    for e in r.thesis_evidence:
        assert e.owner_instrument_id == "518880"


def test_build_rows_qdii_row_carries_sentinel_gap(tmp_path: Path) -> None:
    from irc.commands.opportunity_cmd import _build_rows
    import duckdb

    scores = [{
        "instrument_id": "513500", "asset_class": "us_etf",
        "role": "small_watch",
    }]
    # Stub Instrument with us_etf class — populated via instr_index.
    from irc.schemas.universe import Instrument
    instr = Instrument(
        instrument_id="513500", name_cn="博时标普500ETF",
        asset_class="us_etf", market="cn_exchange",
        venue_required=("A股交易",),
        tracked_index="sp500",
    )
    instr_index = {"513500": instr}
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = {"A股交易"}

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
    ) as mocked:
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            rows, _positions, _q, _roles = _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    assert len(rows) == 1
    r = rows[0]
    assert "qdii_information_unavailable" in r.evidence_gaps
    # No AkShare call for QDII rows.
    assert mocked.call_count == 0
```

> Note: the `Instrument` constructor signature may have additional required fields. If construction fails in step 4, instantiate with only the fields the dataclass actually requires (read `src/irc/schemas/universe.py` for the canonical signature). The test's intent is to provide a `tracked_index="sp500"` so `map_lookthrough` routes to `qdii_us` and the dispatch produces the sentinel.

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_routes_fund_level_evidence_into_opportunity_row -v`
Expected: FAIL — `_build_rows` currently does not dispatch fund-level kinds. The autobuild branch only handles `active_fund`.

- [ ] **Step 3: Extend `_build_rows` autobuild path**

Edit `src/irc/commands/opportunity_cmd.py`. First, add the import:

```python
from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot
```

(extend the existing `from irc.fundamentals.types import ActiveFundSnapshot` line).

Locate the inner block in `_build_rows`:

```python
            target = map_lookthrough(inp)
            snap_obj: object | None = None
            if target.kind == "active_fund" and autobuild_on:
                ...
            else:
                target_name = target.display_cn
                if target_name not in snapshot_cache:
                    snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
                snap_obj = snapshot_cache[target_name]
```

Replace with:

```python
            target = map_lookthrough(inp)
            snap_obj: object | None = None
            if target.kind == "active_fund" and autobuild_on:
                # ── existing item 003 active-fund logic — UNTOUCHED ──
                if target.key in snapshot_cache:
                    snap_obj = snapshot_cache[target.key]
                else:
                    fund_id = target.provider_symbol
                    # P0-3: skip if already complete in resume state.
                    if fund_id in completed_ids:
                        snap_obj = _load_latest_active_fund_cached(fund_id, root / "data")
                    elif rebuild_fundamentals:
                        snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                        if isinstance(snap_obj, ActiveFundSnapshot):
                            snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                            if snap_to_cache.source_report_quarter:
                                try:
                                    write_active_fund_cache(snap_to_cache, root / "data")
                                except Exception as cache_exc:
                                    reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                    sys.stderr.write(reason + "\n")
                                    snap_obj = replace(
                                        snap_obj,
                                        fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                    )
                        _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                    else:
                        cached = _load_latest_active_fund_cached(fund_id, root / "data")
                        if cached is None:
                            snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                            if isinstance(snap_obj, ActiveFundSnapshot):
                                snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                                if snap_to_cache.source_report_quarter:
                                    try:
                                        write_active_fund_cache(snap_to_cache, root / "data")
                                    except Exception as cache_exc:
                                        reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                        sys.stderr.write(reason + "\n")
                                        snap_obj = replace(
                                            snap_obj,
                                            fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                        )
                            _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                        else:
                            probed, refresh = _maybe_freshness_probe(
                                cached, today=today, root=root / "data",
                            )
                            if refresh:
                                snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                                if isinstance(snap_obj, ActiveFundSnapshot):
                                    snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                                    if snap_to_cache.source_report_quarter:
                                        try:
                                            write_active_fund_cache(snap_to_cache, root / "data")
                                        except Exception as cache_exc:
                                            reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                            sys.stderr.write(reason + "\n")
                                            snap_obj = replace(
                                                snap_obj,
                                                fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                            )
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                            else:
                                snap_obj = probed
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                    snapshot_cache[target.key] = snap_obj
            elif autobuild_on and (
                target.kind in ("qdii_us", "qdii_hk", "qdii_global")
                or (target.kind in _FUND_LEVEL_KINDS_CMD and target.provider_symbol)
            ):
                # ── Item 005: fund-level + QDII sentinel dispatch ──
                cache_key = target.provider_symbol or target.key
                if cache_key in snapshot_cache:
                    snap_obj = snapshot_cache[cache_key]
                else:
                    snap_obj = _resolve_fund_level_snapshot(
                        target, root / "data",
                        rebuild=rebuild_fundamentals,
                        today=today,
                    )
                    snapshot_cache[cache_key] = snap_obj
            else:
                target_name = target.display_cn
                if target_name not in snapshot_cache:
                    snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
                snap_obj = snapshot_cache[target_name]
```

Add a module-level constant just above the `_build_rows` function:

```python
# Item 005: kinds that dispatch to the fund-level engine when provider_symbol
# is non-empty. Mirrors `_FUND_LEVEL_KINDS` in snapshot.py — kept local here
# to avoid an import cycle through commands.
_FUND_LEVEL_KINDS_CMD: frozenset[str] = frozenset({
    "gold", "bond", "broad_index", "sector_theme",
})
```

Add the new helper `_resolve_fund_level_snapshot` near the existing
`_maybe_freshness_probe`:

```python
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    load_nav_cache,
    write_active_fund_cache,
    write_nav_cache,
)


def _load_latest_nav_cached(
    fund_id: str, root: Path,
) -> FundLevelSnapshot | None:
    """Scan `root/fundamentals/*/nav/fund_{fund_id}.json` and return the
    most recent quarter's snapshot."""
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/nav/fund_{fund_id}.json"))
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        loaded = load_nav_cache(fund_id, quarter, root)
        if loaded is not None:
            return loaded
    return None


def _is_nav_stale(
    snap: FundLevelSnapshot, *, today: date_cls, threshold_days: int,
) -> bool:
    if not snap.cache_probed_at:
        return True
    try:
        probed = date_cls.fromisoformat(snap.cache_probed_at)
    except ValueError:
        return True
    days = (today - probed).days
    if days < 0:
        return True
    return days > threshold_days


def _resolve_fund_level_snapshot(
    target: "LookthroughTarget",
    root: Path,
    *,
    rebuild: bool,
    today: date_cls,
) -> FundLevelSnapshot:
    """Item 005 fund-level + QDII dispatch with cache reuse.

    - QDII kinds: returns the in-process sentinel (never cached).
    - Other fund-level kinds: load latest cached snapshot; if missing,
      stale (per `IRC_CACHE_FRESHNESS_DAYS`), or `--rebuild-fundamentals`,
      do a full refetch (no cheap probe per grill Q3) and write the cache.
    """
    if target.kind in ("qdii_us", "qdii_hk", "qdii_global"):
        return build_snapshot(target)  # type: ignore[return-value]

    fund_id = target.provider_symbol
    cached = None if rebuild else _load_latest_nav_cached(fund_id, root)
    if cached is not None and not _is_nav_stale(
        cached, today=today, threshold_days=_freshness_days(),
    ):
        return cached

    snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)  # narrow for type-checkers
    # Skip cache write for QDII sentinel (handled in write_nav_cache).
    if "qdii_information_unavailable" not in snap.evidence_gaps and snap.source_report_quarter:
        try:
            write_nav_cache(replace(snap, cache_probed_at=today.isoformat()), root)
        except Exception as cache_exc:
            reason = f"nav_cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
            sys.stderr.write(reason + "\n")
            snap = replace(
                snap,
                fund_level_failure_reasons=snap.fund_level_failure_reasons + (reason,),
            )
    return snap
```

Now wire `FundLevelSnapshot.evidence` into the row. The `build_opportunity_row` consumes the snapshot via `derive_thesis_from_evidence`. Read `src/irc/opportunity/states.py::build_opportunity_row` (Task 16 in item 003's plan rewires it for `ActiveFundSnapshot`). For item 005, we extend the propagation similarly. Add to `_build_rows` just before `row = build_opportunity_row(...)`:

```python
            # Item 005: route FundLevelSnapshot.evidence into thesis_evidence.
            # build_opportunity_row already handles ActiveFundSnapshot + legacy
            # ConstituentSnapshot; FundLevelSnapshot is a new shape, so we forward
            # the snapshot through and let derive_thesis_from_evidence handle it.
            # (The 5-tuple return contract is preserved — see Step 3b below.)
```

- [ ] **Step 3b: Extend `derive_thesis_from_evidence` to accept `FundLevelSnapshot`**

Edit `src/irc/opportunity/thesis_evidence.py`. Extend the imports:

```python
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    BrokerReport,
    ConstituentSnapshot,
    FilingDigest,
    FundLevelSnapshot,
)
```

Modify `derive_thesis_from_evidence`. Insert a new branch BEFORE the `isinstance(snapshot, ActiveFundSnapshot)` branch:

```python
    if isinstance(snapshot, FundLevelSnapshot):
        # Item 005: fund-level evidence is already composed by
        # _build_fund_level_snapshot (or zero-fetch QDII sentinel).
        evidence = snapshot.evidence
        gaps = snapshot.evidence_gaps
        if not evidence:
            return (
                "evidence_insufficient",
                "" if gaps else "基金层级证据未能加载。",
                evidence, gaps, (),
            )
        # Heuristic: if both legs present, thesis stays intact (downstream
        # gate validates per-driver coverage).
        has_data = any(e.citation_kind == "data" for e in evidence)
        has_info = any(e.citation_kind == "information" for e in evidence)
        if has_data and has_info:
            return (
                "intact",
                "基金层级 NAV 与公告证据完整。",
                evidence, gaps, (),
            )
        return (
            "evidence_insufficient",
            "基金层级仅获取到部分证据。",
            evidence, gaps, (),
        )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd_fund_level.py -v`
Expected: 4 PASS. If the `Instrument` constructor signature differs, fix the test fixture inline (the production code path under test is the focus).

- [ ] **Step 5: Regression check**

Run: `pytest tests/opportunity/ tests/commands/test_opportunity_cmd.py -v -x`
Expected: All pre-existing tests PASS. Item 003's `cn_equity_fund` flow remains untouched because the new dispatch is an `elif` branch.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py src/irc/opportunity/thesis_evidence.py tests/commands/test_opportunity_cmd_fund_level.py
git commit -m "feat(opportunity): _build_rows dispatches fund-level + QDII kinds; forward FundLevelSnapshot.evidence to thesis_evidence"
```

---

## Task 13: Extend `FetchPlan` with fund-level cold/stale tally

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/commands/test_opportunity_cmd_fund_level.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd_fund_level.py`:

```python
def test_fetch_plan_includes_fund_level_costs(tmp_path: Path) -> None:
    """FetchPlan now counts fund-level rows: 4 calls per cold/stale fund."""
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=0,
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=3,  # 3 fund-level rows × 4 calls = 12
        fund_level_stale=0,
    )
    assert plan.total_calls() == 3 * 4


def test_fetch_plan_combines_active_and_fund_level_costs() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=2,   # 2 × (1+10×3) = 62
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=5,    # 5 × 4 = 20
        fund_level_stale=0,
    )
    assert plan.total_calls() == 62 + 20


def test_preflight_does_not_exceed_budget_for_v1_universe() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    # V1: ~5 active funds + ~20 fund-level rows
    plan = FetchPlan(
        active_fund_misses=52,
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=20,
        fund_level_stale=0,
    )
    total = plan.total_calls()
    assert total < 2000, f"total={total} would exceed default budget"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd_fund_level.py::test_fetch_plan_includes_fund_level_costs -v`
Expected: FAIL — `FetchPlan.__init__` does not accept `fund_level_misses` / `fund_level_stale`.

- [ ] **Step 3: Extend `FetchPlan`**

Edit `src/irc/commands/opportunity_cmd.py`. Replace:

```python
@dataclass(frozen=True)
class FetchPlan:
    active_fund_misses: int
    active_fund_stale: int
    passive_misses: int
    passive_stale: int
    top_n: int

    def total_calls(self) -> int:
        per_active = 1 + self.top_n * 3
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + self.passive_misses * 2
            + self.passive_stale * 2
        )
```

with:

```python
@dataclass(frozen=True)
class FetchPlan:
    active_fund_misses: int
    active_fund_stale: int
    passive_misses: int
    passive_stale: int
    top_n: int
    fund_level_misses: int = 0  # Item 005: gold/bond/cn_etf rows w/ provider_symbol
    fund_level_stale: int = 0   # Item 005

    def total_calls(self) -> int:
        per_active = 1 + self.top_n * 3
        per_fund_level = 4  # 1 NAV + 3 announcement endpoints (ADR 0002 §5)
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + (self.fund_level_misses + self.fund_level_stale) * per_fund_level
            + self.passive_misses * 2
            + self.passive_stale * 2
        )
```

Also update `FetchBudgetExceeded.__init__` to reflect the new fields in the message:

```python
class FetchBudgetExceeded(RuntimeError):
    def __init__(self, plan: FetchPlan, total: int, budget: int) -> None:
        super().__init__(
            f"FetchBudgetExceeded: "
            f"active_fund_misses={plan.active_fund_misses} "
            f"active_fund_stale={plan.active_fund_stale} "
            f"fund_level_misses={plan.fund_level_misses} "
            f"fund_level_stale={plan.fund_level_stale} "
            f"passive_misses={plan.passive_misses} "
            f"passive_stale={plan.passive_stale} "
            f"cost={total} budget={budget}"
        )
        self.plan = plan
        self.total = total
        self.budget = budget
```

Add a classifier mirroring `_classify_active_fund_scores`. Append below it:

```python
def _classify_fund_level_scores(
    scores: list[dict],
    root: Path,
    *,
    today: date_cls,
    threshold_days: int,
    rebuild_fundamentals: bool,
) -> tuple[int, int]:
    """Count (misses, stale) among fund-level rows (gold/cn_bond_fund/cn_etf).

    QDII rows are NOT counted — they fire zero AkShare calls (sentinel).
    """
    misses = 0
    stale = 0
    seen: set[str] = set()
    for score in scores:
        cls = score.get("asset_class")
        if cls not in ("gold", "cn_bond_fund", "cn_etf"):
            continue
        iid = score.get("instrument_id", "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        if rebuild_fundamentals:
            misses += 1
            continue
        cached = _load_latest_nav_cached(iid, root)
        if cached is None:
            misses += 1
        elif _is_nav_stale(cached, today=today, threshold_days=threshold_days):
            stale += 1
    return misses, stale
```

Wire it into the preflight gate in `_build_rows`. Replace:

```python
        plan = FetchPlan(
            active_fund_misses=misses,
            active_fund_stale=stale,
            passive_misses=0,   # placeholder — item 005
            passive_stale=0,    # placeholder — item 005
            top_n=TOP_N_DEFAULT,
        )
```

with:

```python
        fl_misses, fl_stale = _classify_fund_level_scores(
            scores, root / "data",
            today=today, threshold_days=_freshness_days(),
            rebuild_fundamentals=rebuild_fundamentals,
        )
        plan = FetchPlan(
            active_fund_misses=misses,
            active_fund_stale=stale,
            passive_misses=0,
            passive_stale=0,
            top_n=TOP_N_DEFAULT,
            fund_level_misses=fl_misses,
            fund_level_stale=fl_stale,
        )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd_fund_level.py -v`
Expected: All Task 12 + 3 new FetchPlan tests = 7 PASS.

- [ ] **Step 5: Regression check**

Run: `pytest tests/commands/test_opportunity_cmd.py -v -x`
Expected: All pre-existing tests PASS (the new fields default to 0 and don't change existing FetchPlan instantiation behaviour).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd_fund_level.py
git commit -m "feat(opportunity): FetchPlan accounts for fund-level cold/stale (4 calls per fund per ADR 0002 §5)"
```

---

## Task 14: Citation_id determinism + integration test (3-row fixture)

**Files:**
- Create: `tests/fundamentals/test_fund_level_snapshot_citation_ids.py`
- Create: `tests/commands/test_opportunity_cmd_fund_level_integration.py`

- [ ] **Step 1: Write citation-id determinism test**

Create `tests/fundamentals/test_fund_level_snapshot_citation_ids.py`:

```python
"""Citation-id determinism for FundLevelSnapshot evidence (ADR 0001 §2).

Empty URL + summary "[{report_id}] {title}" → the preimage falls back to
`f"{source}:{date}:{summary[:64]}"`, putting the discriminating `report_id`
in the first ~24 chars (well within the 64-char window).
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.snapshot import _build_fund_level_snapshot
from irc.fundamentals.types import LookthroughTarget


def _frames(ids: list[str]):
    """Return _ak_call side_effect that returns one announcement per topic
    with given report_ids."""

    def _side(fn_name, **kw):
        if fn_name == "fund_open_fund_info_em":
            return pd.DataFrame({
                "净值日期": [_dt.date(2026, 3, 15)],
                "单位净值": [4.5678],
            })
        if fn_name == "fund_announcement_dividend_em":
            return pd.DataFrame({
                "基金代码": ["518880"], "公告标题": [f"title-{ids[0]}"],
                "基金名称": ["X"],
                "公告日期": [_dt.date(2024, 1, 1)],
                "报告ID": [ids[0]],
            })
        if fn_name == "fund_announcement_report_em":
            return pd.DataFrame()
        if fn_name == "fund_announcement_personnel_em":
            return pd.DataFrame()
        return pd.DataFrame()
    return _side


def _snap_for(ids: list[str]):
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金", provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_frames(ids),
    ):
        return _build_fund_level_snapshot(target)


def test_citation_id_is_deterministic_across_runs() -> None:
    snap1 = _snap_for(["AN001"])
    snap2 = _snap_for(["AN001"])
    ids1 = [e.citation_id for e in snap1.evidence]
    ids2 = [e.citation_id for e in snap2.evidence]
    assert ids1 == ids2


def test_citation_id_changes_when_report_id_changes() -> None:
    """Two announcements with same title + date but different report_id →
    distinct citation_ids (preimage's summary[:64] discriminates via [report_id])."""
    snap_a = _snap_for(["AN001"])
    snap_b = _snap_for(["AN002"])
    info_a = [e for e in snap_a.evidence if e.citation_kind == "information"]
    info_b = [e for e in snap_b.evidence if e.citation_kind == "information"]
    assert info_a and info_b
    assert info_a[0].citation_id != info_b[0].citation_id


def test_nav_citation_id_deterministic() -> None:
    snap1 = _snap_for(["AN001"])
    snap2 = _snap_for(["AN001"])
    nav1 = [e for e in snap1.evidence if e.citation_kind == "data"][0]
    nav2 = [e for e in snap2.evidence if e.citation_kind == "data"][0]
    assert nav1.citation_id == nav2.citation_id
```

- [ ] **Step 2: Write integration test (3-row fixture: gold + bond + cn_etf)**

Create `tests/commands/test_opportunity_cmd_fund_level_integration.py`:

```python
"""End-to-end: `_build_rows` over a 3-row fixture (gold + bond + cn_etf)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest


def _nav_frame_for(date_str: str = "2026-03-15", nav: float = 4.5678) -> pd.DataFrame:
    y, m, d = (int(x) for x in date_str.split("-"))
    return pd.DataFrame({
        "净值日期": [_dt.date(y, m, d)],
        "单位净值": [nav],
        "日增长率": ["0.39"],
    })


def _ann_frame_for(fund_id: str, report_id: str = "AN1") -> pd.DataFrame:
    return pd.DataFrame({
        "基金代码": [fund_id],
        "公告标题": [f"title-{fund_id}"],
        "基金名称": [fund_id],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": [report_id],
    })


def _universal_side(fund_ids: list[str]):
    """Return side_effect dispatching to the correct frame per (fn_name, symbol)."""

    def _side(fn_name, **kw):
        symbol = kw.get("symbol", "")
        if fn_name == "fund_open_fund_info_em":
            return _nav_frame_for()
        if fn_name == "fund_announcement_dividend_em":
            return _ann_frame_for(symbol, f"DIV-{symbol}")
        if fn_name == "fund_announcement_report_em":
            return _ann_frame_for(symbol, f"REP-{symbol}")
        if fn_name == "fund_announcement_personnel_em":
            return _ann_frame_for(symbol, f"PER-{symbol}")
        return pd.DataFrame()
    return _side


def test_three_row_integration_gold_bond_cn_etf_dual_coverage(tmp_path: Path) -> None:
    """Gold + cn_bond_fund + cn_etf all produce rows with dual-coverage evidence."""
    from irc.commands.opportunity_cmd import _build_rows
    from irc.schemas.universe import Instrument

    scores = [
        {"instrument_id": "518880", "asset_class": "gold", "role": "small_watch"},
        {"instrument_id": "000001", "asset_class": "cn_bond_fund", "role": "small_watch"},
        {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core_dca"},
    ]
    instr_index = {
        "510300": Instrument(
            instrument_id="510300", name_cn="华泰柏瑞沪深300ETF",
            asset_class="cn_etf", market="cn_exchange",
            venue_required=("A股交易",),
            tracked_index="csi300",
        ),
    }
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = {"A股交易"}

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_universal_side(["518880", "000001", "510300"]),
    ):
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            rows, _positions, _q, _roles = _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    assert len(rows) == 3
    by_id = {r.instrument_id: r for r in rows}
    for iid in ("518880", "000001", "510300"):
        r = by_id[iid]
        kinds = {e.citation_kind for e in r.thesis_evidence}
        assert "data" in kinds, f"{iid} missing data leg"
        assert "information" in kinds, f"{iid} missing information leg"
        for e in r.thesis_evidence:
            assert e.scope == "instrument"
            assert e.owner_instrument_id == iid


def test_three_row_integration_writes_cache(tmp_path: Path) -> None:
    """Cache write under data/fundamentals/2026Q1/nav/fund_{iid}.json."""
    from irc.commands.opportunity_cmd import _build_rows
    from irc.schemas.universe import Instrument

    scores = [
        {"instrument_id": "518880", "asset_class": "gold", "role": "small_watch"},
    ]
    instr_index: dict = {}
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = set()

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_universal_side(["518880"]),
    ):
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    cache_files = list((tmp_path / "data" / "fundamentals").rglob("fund_518880.json"))
    assert len(cache_files) == 1
    assert "/nav/" in str(cache_files[0]) or "\\nav\\" in str(cache_files[0])
```

- [ ] **Step 3: Run failing**

Run: `pytest tests/fundamentals/test_fund_level_snapshot_citation_ids.py tests/commands/test_opportunity_cmd_fund_level_integration.py -v`
Expected: The citation-id tests PASS (Task 9's adapter already produces deterministic IDs); the integration tests may FAIL if the cache path is rooted at `tmp_path` vs `tmp_path / "data"`. Inspect the actual path written and fix the test assertion to match `_build_rows`' convention (`root / "data"`).

- [ ] **Step 4: Iterate to green**

If any assertion fails because the path layout differs from what the test expects, adjust the test's path expectation — do NOT change production code unless the path differs from ADR 0002 §5's specification (`data/fundamentals/{source_report_quarter}/nav/fund_{fund_id}.json`).

Run: `pytest tests/fundamentals/test_fund_level_snapshot_citation_ids.py tests/commands/test_opportunity_cmd_fund_level_integration.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_fund_level_snapshot_citation_ids.py tests/commands/test_opportunity_cmd_fund_level_integration.py
git commit -m "test(fundamentals): citation_id determinism + 3-row integration (gold+bond+cn_etf) for fund-level engine"
```

---

## Task 15: Full suite green + ruff clean

**Files:**
- All previously touched.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q
```

Expected:
- All item-005-touched tests PASS.
- Pre-existing failures should match the baseline established by item 003's verify run (commit `5bc4b9c` / `cc93b34`). Per Master spec §"Test suite green", `pytest -x` may surface ~7 pre-existing failures unrelated to item 005's scope; do NOT attempt to fix them in this slice. Document in the verify phase that these are pre-existing and unchanged.

If item 005's changes introduce NEW failures, debug and fix them before continuing.

- [ ] **Step 2: Run ruff**

Run:

```bash
ruff check src/ tests/
```

Expected: clean. If any new files have lint issues (unused imports, missing type imports, etc.), fix them inline.

Common item-005 lint risks:
- Unused `_infer_quarter_for_nav` import in `akshare_fundamentals.py` — remove per Task 5 Step 4.
- The local `import re as _re` in `types.py` may collide with module-level `re`; if so, rename to `_re_types` and re-verify.

- [ ] **Step 3: Verify regression invariants explicitly**

Run these specifically to confirm item 003's flow is untouched:

```bash
pytest tests/fundamentals/test_akshare_fundamentals.py -v -x
pytest tests/opportunity/test_thesis_evidence.py -v -x
pytest tests/commands/test_opportunity_cmd.py -v -x
```

Expected: all PASS. If any item-003-specific test fails, item 005 has introduced a regression — STOP, diagnose, and fix.

- [ ] **Step 4: Commit (only if any lint fixes were needed)**

```bash
git add -p  # selectively stage lint fixes only
git commit -m "chore(item-005): ruff lint cleanup after fund-level engine implementation"
```

If no lint changes were needed, skip the commit.

---

## Acceptance criteria coverage

This plan implements all 16 acceptance criteria from `005-spec.md`:

| AC# | Implemented in task | Verified by test |
|-----|---------------------|------------------|
| 1   | Tasks 1-3            | `test_fund_nav_report_*`, `test_fund_announcement_*`, `test_fund_level_snapshot_*` |
| 2   | Task 5               | `test_fetch_fund_nav_report_*` |
| 3   | Task 6               | `test_fetch_fund_announcements_*` |
| 4   | Task 6               | `test_fetch_fund_announcements_dedup_by_report_id` |
| 5   | Task 9               | `test_build_fund_level_snapshot_emits_one_data_leg_and_announcements_info_leg` |
| 6   | Task 8               | `test_qdii_sentinel_zero_fetch` (parametrized over 3 kinds) |
| 7   | Task 7               | `test_nav_cache_path_layout`, `test_write_and_load_nav_cache_roundtrip`, `test_write_nav_cache_atomic_tmp_suffix` |
| 8   | Task 12              | `_resolve_fund_level_snapshot` cache-reuse path; `test_build_rows_routes_fund_level_evidence_into_opportunity_row` |
| 9   | Task 11              | `test_static_profile_indicator_not_in_production` |
| 10  | Task 13              | `test_preflight_does_not_exceed_budget_for_v1_universe` |
| 11  | Task 14              | `test_citation_id_is_deterministic_across_runs`, `test_citation_id_changes_when_report_id_changes` |
| 12  | Task 14              | `test_three_row_integration_gold_bond_cn_etf_dual_coverage` |
| 13  | Task 15 Step 3       | `pytest tests/fundamentals/test_akshare_fundamentals.py` regression run |
| 14  | Task 12              | `test_build_rows_qdii_row_carries_sentinel_gap` |
| 15  | Task 15 Step 3       | full-suite regression run; legacy `_TARGET_REGISTRY` path untouched |
| 16  | (no new ADR)         | ADR 0002 §5 already amended in grill phase |

---

## Spec-coverage self-review notes

- **Grill Q1 patch (provider_symbol propagation):** implemented in Task 4. All 3 branches (`gold`, `cn_bond_fund`, `cn_etf` tracked/theme/unknown) now populate `provider_symbol=inp.instrument_id`. QDII branches intentionally NOT patched (sentinel path doesn't need it).
- **Grill Q3 (no cheap probe):** Task 12's `_resolve_fund_level_snapshot` does NOT add a separate probe — stale → direct full refetch matches ADR 0002 §5 verbatim.
- **Grill Q4 (`type="snapshot"` for NAV):** Task 9 reuses the existing literal; no `ThesisEvidenceKind` change.
- **Grill Q5 (QDII sentinel not cached):** Task 7's `write_nav_cache` short-circuits on `evidence_gaps == ("qdii_information_unavailable",)`. Locked by `test_write_nav_cache_skips_qdii_sentinel`.
- **ADR 0001 §2 preimage:** Tasks 9 + 14 verify `url=""` + `summary="[{report_id}] {title}"` produces deterministic, unique citation_ids.
- **F5 invariant:** Task 5 only consults `indicator="单位净值走势"`; Task 11 locks via grep test.

## Mid-plan spec gaps and resolutions

While drafting this plan I encountered three points where the spec required a judgment call:

1. **Spec §F3 evidence-gap semantics on partial NAV/announcement failure.** The spec body specifies the happy path but does not name the gap codes for "NAV ok, announcements empty" vs "NAV failed, announcements ok". **Decision:** introduce two codes — `fund_nav_unavailable` and `fund_announcements_unavailable` — emitted by `_build_fund_level_snapshot` and surfaced in `evidence_gaps`. Pattern mirrors item 003's `holdings_quarter_parse_failed` / `holdings_fetch_failed`. Item 006's H3 invariant will treat these as gaps; the gate-routing behaviour is item 006's territory.

2. **Spec §F3 `_build_fund_level_snapshot` does NOT specify how to wire `FundLevelSnapshot` into `OpportunityRow.thesis_evidence`.** The spec mentions `OpportunityRow.thesis_evidence` should "carry the expected NAV + announcement entries" without naming the integration seam. **Decision:** extend `derive_thesis_from_evidence` (item 003's seam) with a new `isinstance(snapshot, FundLevelSnapshot)` branch that forwards `snap.evidence` + `snap.evidence_gaps` directly. The 5-tuple return contract is preserved. This is the lowest-friction integration; alternative was to bypass `derive_thesis_from_evidence` entirely, but that would require parallel wiring in `build_opportunity_row` — strictly worse.

3. **Spec §F3 "passive_misses/passive_stale" rename vs add.** The current `FetchPlan` has `passive_misses` / `passive_stale` placeholders from item 003. The spec says fund-level extends the tally with a categorical breakdown. **Decision:** ADD `fund_level_misses` / `fund_level_stale` rather than repurpose the passive_* fields. Rationale: legacy `_build_legacy_snapshot` still serves the `## 持仓明细` appendix and may eventually use `passive_*`; keeping them separate preserves future-extensibility without breaking existing FetchPlan constructor signatures.

---

**End of plan.** Ready for impl agent execution per `superpowers:subagent-driven-development`.
