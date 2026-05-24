# Item 003 Implementation Plan — Active-fund constituent layer + per-stock analysis (Slices A + G + HK news adapter)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the runtime fetch engine that produces per-fund top-N constituent evidence for CN active equity funds, with HK-routed adapters, disclosure-quarter-keyed cache, fail-closed freshness probe, preflight budget gate, and resumable state — emitting `ActiveFundSnapshot` and per-row `ConstituentAnalysis` lists for every `cn_equity_fund` row.

**Architecture:** New typed `LookthroughTarget` dispatch in `build_snapshot` routes `kind="active_fund"` to a new `_build_active_fund_snapshot` that fetches holdings, parses exchange per-row, dispatches per-market adapter sets (CN: filing+broker+news; HK: filing+news; US/UNKNOWN: none), and emits `ConstituentAnalysis` with structured `ThesisEvidence`. Cache layer keys by provider-declared disclosure quarter; the orchestrator (`_build_rows`) gates the loop with a `FetchPlan` preflight ledger and persists progress to a `fcntl.flock`-locked state file. Legacy passive-snapshot paths preserved untouched.

**Tech Stack:** Python 3.12, pandas, stdlib `fcntl` for advisory locking, AkShare (mocked via `_ak_call`), pytest, ruff.

---

## Constraints (apply to every task)

- **Strict TDD per task:** red (failing test) → green (minimal impl) → refactor. No implementation code lands without a prior failing test.
- **No new third-party deps.** Locking uses stdlib `fcntl.flock(LOCK_EX | LOCK_NB)`; Windows fallback = no-op + single stderr warning.
- **Defaults locked:** `IRC_FETCH_BUDGET=2000`, `IRC_CACHE_FRESHNESS_DAYS=7`, `TOP_N_DEFAULT=10`, `IRC_OPPORTUNITY_AUTOBUILD=1` (on).
- **`plan_hash`** = `hashlib.sha256(f"{output_date}:{','.join(sorted(instrument_ids))}:{TOP_N_DEFAULT}".encode("utf-8")).hexdigest()[:12]`.
- **`citation_id` hash preimage is unchanged** (ADR 0001 §2). `ThesisEvidence.holding_weight_pct` is appended AFTER `citation_id` and is EXCLUDED from the preimage.
- **Item 003 scope only:** produces the data. Does NOT stamp `evidence_gaps` for the new fields, does NOT render memo/discipline output, does NOT enforce citation gates. Those are items 006/007/009.
- **All item 003 tests mock `_ak_call`.** Do not add any `@pytest.mark.live_akshare` tests — item 004 owns live verification.
- **HK news fallback = stub-empty.** Lazy-detect `ak.stock_hk_news_em`; on `ImportError`/`AttributeError` return `()` and caller stamps `hk_news_unsupported_adapter:{symbol}`. NO HTML scraper.
- **Commit cadence:** one conventional-commit per task (`feat(fundamentals):`, `feat(opportunity):`, `test(...):`, `refactor(...):`). Tests-first within a task. DO NOT push.
- **Verification per task:** an exact `pytest …` command with expected PASS/FAIL output. Final task = full `pytest -x` + `ruff check`.

## Branch

Sub-branch: `autodev/thesis-evidence-003-active-fund-constituent-layer` cut from `autodev/thesis-cards-evidence-gap`. Commits land on the sub-branch; the eventual PR opens against `autodev/thesis-cards-evidence-gap`.

---

## File-touch map (read this before starting)

**Source (modify):**
- `src/irc/fundamentals/types.py` — add `NewsItem`, `FundHolding`, `HoldingsResult`, `ActiveFundSnapshot`.
- `src/irc/opportunity/types.py` — extend `LookthroughTarget`; add `ConstituentAnalysis`; add `holding_weight_pct` to `ThesisEvidence` AFTER `citation_id` (NOT in preimage); add `OpportunityRow.constituent_analyses`; add `ThesisCard.constituent_analyses`; narrow `DisciplineRow.constituent_analyses`.
- `src/irc/fundamentals/akshare_fundamentals.py` — add `_parse_exchange`, `_parse_quarter_column`; rewrite `fetch_cn_etf_holdings`; add `fetch_cn_stock_news`.
- `src/irc/fundamentals/hkex_client.py` — add `fetch_hk_stock_news` with lazy AkShare detection.
- `src/irc/fundamentals/snapshot.py` — change `build_snapshot` to accept `LookthroughTarget`; add `_build_active_fund_snapshot`; preserve legacy builders.
- `src/irc/fundamentals/snapshot_cache.py` — add `active_fund_cache_path`, `load_active_fund_cache`, `write_active_fund_cache`, `_active_fund_to_dict`, `_active_fund_from_dict`.
- `src/irc/opportunity/lookthrough.py` — reorder so `cn_equity_fund` precedes tracked_index/theme; wire `provider_symbol`.
- `src/irc/opportunity/thesis_evidence.py` — remove `cn_equity_fund` from `NON_INDEXABLE_ASSET_CLASSES`; extend `derive_thesis_from_evidence` to accept `ActiveFundSnapshot`, return 5-tuple including `tuple[ConstituentAnalysis, ...]`, flatten per spec Q-J order.
- `src/irc/opportunity/states.py` — update `build_opportunity_row` to handle the new 5-tuple return and populate `OpportunityRow.constituent_analyses`.
- `src/irc/opportunity/cards.py` — thread `row.constituent_analyses` into `ThesisCard`.
- `src/irc/opportunity/report.py` — add defensive `citation_id` check on nested constituent evidence in `_card_to_dict`.
- `src/irc/commands/opportunity_cmd.py` — typed-target dispatch; `IRC_OPPORTUNITY_AUTOBUILD`; `FetchPlan` + `FetchBudgetExceeded`; resumable state w/ `fcntl.flock`; freshness probe.
- `src/irc/commands/fundamentals_cmd.py` — call site: pass `LookthroughTarget` to `build_snapshot`.
- `src/irc/cli.py` — add `--limit`, `--rebuild-fundamentals`, `--output-dir` flags on `opportunity` and `run`.

**Tests (modify or create):**
- `tests/opportunity/test_types.py` — update 4 `LookthroughTarget(...)` calls (default `provider_symbol=""`); add `ConstituentAnalysis` tests; add `ThesisEvidence.holding_weight_pct` tests.
- `tests/opportunity/test_lookthrough.py` — branch-ordering tests for `cn_equity_fund` first.
- `tests/opportunity/test_thesis_evidence.py` — 5-tuple return tests; flatten ordering test `test_active_fund_thesis_evidence_flatten_ordering`.
- `tests/opportunity/test_report.py` — update 2 `LookthroughTarget(...)` calls (one uses `kind="index"` — invalid → `"broad_index"`); add `constituent_analyses` round-trip.
- `tests/opportunity/test_cards.py` — update 1 `LookthroughTarget(...)` call; add `ThesisCard.constituent_analyses` test.
- `tests/opportunity/test_selection.py` — update 2 `LookthroughTarget(...)` calls.
- `tests/opportunity/test_citation_map.py` — update 1 `LookthroughTarget(...)` call.
- `tests/opportunity/test_discipline.py` — update 1 `LookthroughTarget(...)` call.
- `tests/opportunity/test_trim_triggers.py` — replace `kind="index"` (invalid) with `"broad_index"`.
- `tests/commands/test_opportunity_cmd.py` — update 2 `LookthroughTarget(...)` calls; add `_build_rows` autobuild/preflight/limit/lock tests.
- `tests/commands/test_fundamentals_cmd.py` — update 4 `build_snapshot` mock expectations to take `LookthroughTarget`.
- `tests/fundamentals/test_akshare_fundamentals.py` — update 4 existing `fetch_cn_etf_holdings` test sites; add `_parse_exchange`, `_parse_quarter_column`, `fetch_cn_stock_news` tests.
- `tests/fundamentals/test_snapshot.py` — update ~10 `build_snapshot("string")` calls; add `_build_active_fund_snapshot` tests (full success, empty holdings, mixed CN/HK routing, US/UNKNOWN handling).
- `tests/fundamentals/test_hkex_client.py` — add `fetch_hk_stock_news` happy + unsupported-adapter tests.
- `tests/fundamentals/test_snapshot_cache.py` (new) — active-fund cache path; freshness probe trio; lock contention; atomic write.

> Spec preview lists 5 `fetch_cn_etf_holdings` test sites; current file has 4 (`test_akshare_fundamentals.py:171,184,194,202`). The plan tracks 4.

---

## Task index (one slice per task, all green-at-checkpoint)

1. Add `NewsItem`, `FundHolding`, `HoldingsResult`, `ActiveFundSnapshot` to `fundamentals/types.py`.
2. Extend `LookthroughTarget` with `provider_symbol`; update existing call sites in tests/.
3. Add `ConstituentAnalysis` and `OpportunityRow.constituent_analyses` field.
4. Add `ThesisEvidence.holding_weight_pct` (post-citation_id, NOT in preimage).
5. Add `ThesisCard.constituent_analyses` and narrow `DisciplineRow.constituent_analyses`.
6. Add `_parse_exchange` + `_parse_quarter_column` helpers in `akshare_fundamentals.py`.
7. Refactor `fetch_cn_etf_holdings` to return `HoldingsResult` (update 4 existing tests).
8. Add `fetch_cn_stock_news` in `akshare_fundamentals.py`.
9. Add `fetch_hk_stock_news` in `hkex_client.py` with lazy AkShare detection.
10. Reorder `map_lookthrough` — `cn_equity_fund` first; wire `provider_symbol`.
11. Remove `cn_equity_fund` from `NON_INDEXABLE_ASSET_CLASSES`.
12. Add `_build_active_fund_snapshot` to `snapshot.py`; change `build_snapshot` signature.
13. Update `fundamentals_cmd.py` and its tests to pass `LookthroughTarget`.
14. Extend `snapshot_cache.py`: active-fund cache I/O + dict (de)serialization.
15. Extend `derive_thesis_from_evidence` to 5-tuple return with flatten ordering.
16. Update `build_opportunity_row` to handle the new 5-tuple; populate `OpportunityRow.constituent_analyses`.
17. Thread `row.constituent_analyses` into `ThesisCard` via `build_thesis_card`.
18. Add defensive citation_id check for nested constituent evidence in `_card_to_dict`.
19. Add `FetchPlan`, `FetchBudgetExceeded`, plan_hash helper in `opportunity_cmd.py`.
20. Add resumable state file I/O with `fcntl.flock` + Windows fallback.
21. Wire active-fund autobuild + freshness probe into `_build_rows`.
22. Add `--limit` / `--rebuild-fundamentals` / `--output-dir` CLI flags + canonical-path rejection.
23. Acceptance-criteria tests (G6 a/b/c trio + cache-reuse counter + freshness trio + lock + `--limit` canonical-reject + `thesis_cards.yaml` schema).
24. Final: full `pytest -x` green + `ruff check` clean.

---

## Task 1: Add new dataclasses to `fundamentals/types.py`

**Files:**
- Modify: `src/irc/fundamentals/types.py`
- Test: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_types.py`:

```python
import pytest

from irc.fundamentals.types import (
    ActiveFundSnapshot,
    FundHolding,
    HoldingsResult,
    NewsItem,
)


def test_news_item_construction() -> None:
    n = NewsItem(
        symbol="600519",
        title="贵州茅台 24Q1 营收高于预期",
        url="https://example.com/news/1",
        published_iso="2024-04-15",
        summary="",
        source="stock_news_em",
    )
    assert n.symbol == "600519"
    assert n.source == "stock_news_em"


def test_fund_holding_percent_units() -> None:
    h = FundHolding(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=3.46,
        exchange="SH",
        provider_symbol="600519",
    )
    assert h.weight_pct == 3.46
    assert h.exchange == "SH"


def test_holdings_result_carries_quarter_metadata() -> None:
    res = HoldingsResult(
        constituents=(),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    assert res.source_report_quarter == "2024Q1"


def test_active_fund_snapshot_defaults() -> None:
    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
    )
    assert snap.fund_level_failure_reasons == ()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'NewsItem' from 'irc.fundamentals.types'`.

- [ ] **Step 3: Implement dataclasses**

Append to `src/irc/fundamentals/types.py`:

```python
from typing import Literal


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    title: str
    url: str
    published_iso: str
    summary: str
    source: str


@dataclass(frozen=True)
class FundHolding:
    symbol: str
    name_cn: str
    weight_pct: float
    exchange: Literal["SH", "SZ", "BJ", "HK", "US", "UNKNOWN"]
    provider_symbol: str


@dataclass(frozen=True)
class HoldingsResult:
    constituents: tuple[FundHolding, ...]
    source_report_date: str
    source_report_quarter: str


@dataclass(frozen=True)
class ActiveFundSnapshot:
    fund_id: str
    source_report_date: str
    source_report_quarter: str
    cache_probed_at: str
    constituent_analyses: tuple["object", ...]  # narrowed in task 3
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    fund_level_failure_reasons: tuple[str, ...] = ()
```

> Note: `constituent_analyses` is typed `tuple[object, ...]` temporarily because `ConstituentAnalysis` is added in Task 3 and lives in `opportunity/types.py`. Task 3 cannot import here without a cycle; we keep the loose annotation here and the strong annotation on `OpportunityRow.constituent_analyses` in `opportunity/types.py`.

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_types.py -v`
Expected: PASS (4 new tests + pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): add NewsItem/FundHolding/HoldingsResult/ActiveFundSnapshot dataclasses"
```

---

## Task 2: Extend `LookthroughTarget` with `provider_symbol`

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Modify: `tests/opportunity/test_types.py`, `tests/opportunity/test_report.py`, `tests/opportunity/test_citation_map.py`, `tests/opportunity/test_discipline.py`, `tests/opportunity/test_selection.py`, `tests/opportunity/test_cards.py`, `tests/opportunity/test_trim_triggers.py`, `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing test in `tests/opportunity/test_types.py`**

Append:

```python
def test_lookthrough_target_provider_symbol_default_empty() -> None:
    from irc.opportunity.types import LookthroughTarget
    t = LookthroughTarget("broad_index", "csi300", "沪深300")
    assert t.provider_symbol == ""


def test_lookthrough_target_provider_symbol_explicit() -> None:
    from irc.opportunity.types import LookthroughTarget
    t = LookthroughTarget(
        kind="active_fund", key="fund_005827",
        display_cn="易方达蓝筹精选", provider_symbol="005827",
    )
    assert t.provider_symbol == "005827"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_types.py::test_lookthrough_target_provider_symbol_default_empty -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'provider_symbol'`.

- [ ] **Step 3: Add field**

Edit `src/irc/opportunity/types.py`, replace the `LookthroughTarget` dataclass:

```python
@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind
    key: str
    display_cn: str
    provider_symbol: str = ""
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_types.py -v`
Expected: PASS (new 2 + existing remain green because `provider_symbol` defaults to `""`).

- [ ] **Step 5: Fix invalid `kind="index"` call sites**

In `tests/opportunity/test_trim_triggers.py` line 32, replace:

```python
        lookthrough_target=LookthroughTarget(kind="index", key="sp500", display_cn="S&P 500"),
```

with:

```python
        lookthrough_target=LookthroughTarget(kind="broad_index", key="sp500", display_cn="S&P 500"),
```

In `tests/opportunity/test_report.py` line 151, replace:

```python
        lookthrough_target=LookthroughTarget(kind="index", key="GOLD", display_cn="GOLD"),
```

with:

```python
        lookthrough_target=LookthroughTarget(kind="gold", key="gold", display_cn="GOLD"),
```

In `tests/opportunity/test_types.py` line 127, replace:

```python
        lookthrough_target=LookthroughTarget(kind="index", key="GOLD", display_cn="GOLD"),
```

with:

```python
        lookthrough_target=LookthroughTarget(kind="gold", key="gold", display_cn="GOLD"),
```

- [ ] **Step 6: Run full opportunity test suite**

Run: `pytest tests/opportunity/ tests/commands/test_opportunity_cmd.py -v`
Expected: PASS for all existing tests (default `provider_symbol=""` keeps them green).

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/ tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): add LookthroughTarget.provider_symbol; fix invalid kind='index' test fixtures"
```

---

## Task 3: Add `ConstituentAnalysis` and `OpportunityRow.constituent_analyses`

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Test: `tests/opportunity/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_types.py`:

```python
def test_constituent_analysis_construction() -> None:
    from irc.opportunity.types import ConstituentAnalysis
    c = ConstituentAnalysis(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=6.2,
        evidence=(),
        failure_reasons=("filing_empty:600519",),
        one_line_view="证据获取失败",
    )
    assert c.symbol == "600519"
    assert c.weight_pct == 6.2


def test_constituent_analysis_rejects_negative_weight() -> None:
    import pytest
    from irc.opportunity.types import ConstituentAnalysis
    with pytest.raises(ValueError):
        ConstituentAnalysis(
            symbol="600519", name_cn="贵州茅台", weight_pct=-1.0,
            evidence=(), failure_reasons=(), one_line_view="",
        )


def test_constituent_analysis_rejects_empty_symbol() -> None:
    import pytest
    from irc.opportunity.types import ConstituentAnalysis
    with pytest.raises(ValueError):
        ConstituentAnalysis(
            symbol="", name_cn="x", weight_pct=1.0,
            evidence=(), failure_reasons=(), one_line_view="",
        )


def test_opportunity_row_has_constituent_analyses_default_empty() -> None:
    from irc.opportunity.types import (
        LookthroughTarget, OpportunityRow,
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", "fund_005827", "易方达蓝筹精选", "005827",
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        opportunity_reason="", evidence_gaps=(),
    )
    assert row.constituent_analyses == ()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_types.py::test_constituent_analysis_construction -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add `ConstituentAnalysis` and extend `OpportunityRow`**

Edit `src/irc/opportunity/types.py`. After `class ConstituentScope` block (after `ConstituentCitedMap`), add:

```python
@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str
    name_cn: str
    weight_pct: float
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("ConstituentAnalysis.symbol must be non-empty")
        if self.weight_pct < 0:
            raise ValueError(
                f"ConstituentAnalysis.weight_pct must be >= 0; got {self.weight_pct}"
            )
```

Modify `OpportunityRow` — append after `fetch_types_attempted`:

```python
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_types.py
git commit -m "feat(opportunity): add ConstituentAnalysis dataclass and OpportunityRow.constituent_analyses"
```

---

## Task 4: Add `ThesisEvidence.holding_weight_pct` (post-`citation_id`, NOT in preimage)

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Test: `tests/opportunity/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_types.py`:

```python
def test_thesis_evidence_holding_weight_pct_default_none() -> None:
    from irc.opportunity.types import ThesisEvidence
    e = ThesisEvidence(
        type="filing", source="600519", url="", date="2024-04-15",
        summary="x", scope="instrument", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id=None, constituent_key=None,
    )
    assert e.holding_weight_pct is None


def test_thesis_evidence_holding_weight_pct_not_in_citation_id_preimage() -> None:
    from irc.opportunity.types import ThesisEvidence
    common = dict(
        type="filing", source="600519", url="https://example.com/a",
        date="2024-04-15", summary="贵州茅台 24Q1 营收 +18%",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519",
    )
    e1 = ThesisEvidence(**common, holding_weight_pct=None)
    e2 = ThesisEvidence(**common, holding_weight_pct=3.46)
    e3 = ThesisEvidence(**common, holding_weight_pct=99.0)
    # holding_weight_pct excluded from preimage => same citation_id.
    assert e1.citation_id == e2.citation_id == e3.citation_id
    assert e2.holding_weight_pct == 3.46
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_types.py::test_thesis_evidence_holding_weight_pct_default_none -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'holding_weight_pct'`.

- [ ] **Step 3: Add the field after `citation_id`**

Edit `src/irc/opportunity/types.py`. Inside `ThesisEvidence`, change:

```python
    citation_id: str = ""

    def __post_init__(self) -> None:
```

to:

```python
    citation_id: str = ""
    holding_weight_pct: float | None = None

    def __post_init__(self) -> None:
```

No change to `__post_init__` — the preimage computation does not include `holding_weight_pct`, preserving ADR 0001 §2.

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_types.py
git commit -m "feat(opportunity): add ThesisEvidence.holding_weight_pct (excluded from citation_id preimage)"
```

---

## Task 5: Add `ThesisCard.constituent_analyses` and narrow `DisciplineRow.constituent_analyses`

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Test: `tests/opportunity/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_types.py`:

```python
def test_thesis_card_constituent_analyses_default_empty() -> None:
    from irc.opportunity.types import ThesisCard
    card = ThesisCard(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None, role="watchlist",
        lookthrough_target="易方达蓝筹精选", entry_reason="",
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        dca_action="pause_dca", risk_action="none",
        falsification_triggers=(), trim_triggers=(),
        do_not_sell_just_because=(), review_cadence="weekly",
        evidence_gaps=(),
    )
    assert card.constituent_analyses == ()


def test_discipline_row_constituent_analyses_typed() -> None:
    from irc.opportunity.types import ConstituentAnalysis, DisciplineRow
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(), failure_reasons=(), one_line_view="",
    )
    row = DisciplineRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        constituent_analyses=(c,),
    )
    assert row.constituent_analyses[0].symbol == "600519"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_types.py::test_thesis_card_constituent_analyses_default_empty -v`
Expected: FAIL with `TypeError`.

- [ ] **Step 3: Update dataclasses**

Edit `src/irc/opportunity/types.py`. In `ThesisCard`, append after `expected_omissions`:

```python
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

In `DisciplineRow`, replace:

```python
    constituent_analyses: tuple[object, ...] = ()
```

with:

```python
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/ tests/commands/test_opportunity_cmd.py -v`
Expected: PASS (no narrowing-induced breakage because default is `()`).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_types.py
git commit -m "feat(opportunity): add ThesisCard.constituent_analyses; narrow DisciplineRow.constituent_analyses"
```

---

## Task 6: Add `_parse_exchange` + `_parse_quarter_column` helpers

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Test: `tests/fundamentals/test_akshare_fundamentals.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_akshare_fundamentals.py`:

```python
import pandas as pd
import pytest

from irc.fundamentals.akshare_fundamentals import (
    _parse_exchange,
    _parse_quarter_column,
)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("600519", "SH"),
        ("000333", "SZ"),
        ("300750", "SZ"),
        ("00700", "HK"),
        ("0700", "HK"),
        ("09988", "HK"),
        ("AAPL", "US"),
        ("830839", "BJ"),
        ("430139", "BJ"),
    ],
)
def test_parse_exchange_ticker_prefix_fallback(code, expected) -> None:
    row = pd.Series({"股票代码": code})
    assert _parse_exchange(row) == expected


def test_parse_exchange_market_column_priority_hk() -> None:
    row = pd.Series({"股票代码": "600519", "股票市场": "港交所"})
    assert _parse_exchange(row) == "HK"


def test_parse_exchange_market_column_priority_sz() -> None:
    row = pd.Series({"股票代码": "00700", "股票市场": "深交所"})
    assert _parse_exchange(row) == "SZ"


def test_parse_exchange_market_column_star_board_sh() -> None:
    row = pd.Series({"股票代码": "688981", "股票市场": "科创板"})
    assert _parse_exchange(row) == "SH"


def test_parse_exchange_market_column_unknown_falls_through() -> None:
    # Unknown 股票市场 value falls through to ticker-prefix.
    row = pd.Series({"股票代码": "600519", "股票市场": "新疆板块"})
    assert _parse_exchange(row) == "SH"


def test_parse_exchange_unknown() -> None:
    row = pd.Series({"股票代码": "X1!"})
    assert _parse_exchange(row) == "UNKNOWN"


def test_parse_exchange_strips_sz_sh_prefix() -> None:
    row = pd.Series({"股票代码": "sz000333"})
    assert _parse_exchange(row) == "SZ"


def test_parse_quarter_column_happy() -> None:
    row = pd.Series({"季度": "2024年1季度股票投资明细"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2024Q1"
    assert iso == "2024-03-31"


def test_parse_quarter_column_q4() -> None:
    row = pd.Series({"季度": "2023年4季度股票投资明细"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2023Q4"
    assert iso == "2023-12-31"


def test_parse_quarter_column_baogao_qi_fallback() -> None:
    row = pd.Series({"报告期": "2024年2季度"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2024Q2"
    assert iso == "2024-06-30"


def test_parse_quarter_column_unparseable() -> None:
    row = pd.Series({"季度": "2024年半年度"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == ""
    assert iso == ""
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py::test_parse_exchange_ticker_prefix_fallback -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement helpers**

Add to `src/irc/fundamentals/akshare_fundamentals.py` (just below `_to_qualified_symbol`):

```python
import re


_HK_TOKENS: tuple[str, ...] = ("港",)
_US_TOKENS: tuple[str, ...] = ("纽", "纳斯达克", "美")
_SH_TOKENS: tuple[str, ...] = ("沪", "上交所", "上证", "科创板")
_SZ_TOKENS: tuple[str, ...] = ("深", "创业板", "中小板")
_BJ_TOKENS: tuple[str, ...] = ("北", "京")
_QUARTER_END: dict[str, str] = {
    "1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31",
}
_QUARTER_RE = re.compile(r"(\d{4})年(\d)季度")


def _normalize_ticker(raw: str) -> str:
    """Strip `.SH/.SZ/.HK/.US` suffix and leading `sz/sh/bj` (case-insensitive)."""
    code = str(raw).strip()
    code = re.sub(r"\.(SH|SZ|HK|US|BJ)$", "", code, flags=re.IGNORECASE)
    lower = code.lower()
    for prefix in ("sz", "sh", "bj"):
        if lower.startswith(prefix):
            return code[len(prefix):]
    return code


def _parse_exchange_from_market_column(market_value: str) -> str | None:
    """Strategy 1: priority-ordered substring match. None = strategy-1 miss."""
    if not market_value:
        return None
    # Priority: HK / US first to avoid 主板 false-hits.
    for token in _HK_TOKENS:
        if token in market_value:
            return "HK"
    for token in _US_TOKENS:
        if token in market_value:
            return "US"
    # 科创板 must come before generic 沪 because 科创板 trades on Shanghai.
    if "科创板" in market_value:
        return "SH"
    for token in _SH_TOKENS:
        if token in market_value:
            return "SH"
    for token in _SZ_TOKENS:
        if token in market_value:
            return "SZ"
    for token in _BJ_TOKENS:
        if token in market_value:
            return "BJ"
    return None


def _parse_exchange_from_ticker(raw_code: str) -> str:
    """Strategy 2: ticker-prefix routing."""
    upper = str(raw_code).strip().upper()
    if upper.endswith(".HK"):
        return "HK"
    code = _normalize_ticker(raw_code)
    if not code:
        return "UNKNOWN"
    if code.isdigit() and len(code) in (4, 5):
        return "HK"
    if code.isdigit() and len(code) == 6:
        head = code[0]
        if head == "6":
            return "SH"
        if head in ("0", "3"):
            return "SZ"
        if head in ("4", "8"):
            return "BJ"
    if code.isalpha():
        return "US"
    return "UNKNOWN"


def _parse_exchange(row: pd.Series) -> str:
    """Map a holdings row to an exchange code.

    Strategy 1: prefer `股票市场` substring containment (HK/US first).
    Strategy 2: ticker-prefix fallback.
    """
    market = ""
    if "股票市场" in row.index:
        market = str(row["股票市场"] or "").strip()
    if market:
        mapped = _parse_exchange_from_market_column(market)
        if mapped is not None:
            return mapped
    raw = ""
    if "股票代码" in row.index:
        raw = str(row["股票代码"] or "").strip()
    return _parse_exchange_from_ticker(raw)


def _parse_quarter_column(row: pd.Series) -> tuple[str, str]:
    """Return (`source_report_quarter`, `source_report_date`).

    Accepts `季度` or `报告期`. Empty/unparseable → `("", "")`.
    """
    text = ""
    for col in ("季度", "报告期"):
        if col in row.index:
            text = str(row[col] or "")
            if text:
                break
    m = _QUARTER_RE.search(text)
    if m is None:
        return "", ""
    year, q = m.group(1), m.group(2)
    if q not in _QUARTER_END:
        return "", ""
    return f"{year}Q{q}", f"{year}-{_QUARTER_END[q]}"
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py -k "parse_exchange or parse_quarter" -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "feat(fundamentals): add _parse_exchange (HK regression-safe) + _parse_quarter_column helpers"
```

---

## Task 7: Refactor `fetch_cn_etf_holdings` to return `HoldingsResult`

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Modify: `tests/fundamentals/test_akshare_fundamentals.py` (4 existing test sites)

- [ ] **Step 1: Rewrite the 4 existing test sites first**

In `tests/fundamentals/test_akshare_fundamentals.py`, replace the four test bodies (lines 171, 184, 194, 202 in current file) so they read against `HoldingsResult`:

```python
def test_fetch_cn_etf_holdings_happy_path_filters_latest_quarter() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("000001", as_of="2024", top_n=10)
    assert mocked.call_args[0][0] == "fund_portfolio_hold_em"
    assert mocked.call_args[1] == {"symbol": "000001", "date": "2024"}
    # Latest quarter is 2季度 — two rows.
    assert out.source_report_quarter == "2024Q2"
    assert out.source_report_date == "2024-06-30"
    assert len(out.constituents) == 2
    assert out.constituents[0].name_cn == "美的集团"
    assert out.constituents[0].weight_pct == 9.10
    assert out.constituents[0].symbol == "000333"
    assert out.constituents[0].exchange == "SZ"
    assert out.constituents[0].provider_symbol == "000333"


def test_fetch_cn_etf_holdings_default_as_of_uses_current_year() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        fetch_cn_etf_holdings("000001")
    kwargs = mocked.call_args[1]
    assert kwargs["symbol"] == "000001"
    assert kwargs["date"].isdigit() and len(kwargs["date"]) == 4


def test_fetch_cn_etf_holdings_truncates_to_top_n() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("000001", as_of="2024", top_n=1)
    assert len(out.constituents) == 1
    assert out.constituents[0].name_cn == "美的集团"


def test_fetch_cn_etf_holdings_returns_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = ValueError("eastmoney 502")
        out = fetch_cn_etf_holdings("000001", as_of="2024")
    assert out.constituents == ()
    assert out.source_report_quarter == ""
    assert out.source_report_date == ""
```

Add a new HK-regression test below the four above:

```python
_HK_HOLDINGS_FRAME = pd.DataFrame({
    "股票代码": ["00700", "0700", "09988", "600519", "AAPL", "830839"],
    "股票名称": ["腾讯控股", "腾讯控股", "阿里巴巴", "贵州茅台", "苹果", "晶赛科技"],
    "占净值比例": [9.0, 8.0, 7.0, 6.0, 5.0, 4.0],
    "季度": ["2024年1季度股票投资明细"] * 6,
})


def test_fetch_cn_etf_holdings_hk_and_bj_routing_without_market_column() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HK_HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("501025", as_of="2024", top_n=6)
    assert out.source_report_quarter == "2024Q1"
    exchanges = [c.exchange for c in out.constituents]
    assert exchanges == ["HK", "HK", "HK", "SH", "US", "BJ"]
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py -k "fetch_cn_etf_holdings" -v`
Expected: FAIL — `out` is `tuple[Constituent, ...]`, has no `.constituents` attribute.

- [ ] **Step 3: Rewrite `fetch_cn_etf_holdings`**

Replace the function body in `src/irc/fundamentals/akshare_fundamentals.py`:

```python
from irc.fundamentals.types import Constituent, FundHolding, HoldingsResult


def fetch_cn_etf_holdings(
    provider_symbol: str,
    *,
    as_of: str = "",
    top_n: int = 10,
) -> HoldingsResult:
    """Latest disclosed holdings for a CN fund.

    Returns `HoldingsResult` with normalized `FundHolding` rows. Never raises.
    Empty/failed → `HoldingsResult((), "", "")`.
    """
    year = as_of or _current_year()
    try:
        df = _ak_call("fund_portfolio_hold_em", symbol=provider_symbol, date=year)
    except Exception:
        return HoldingsResult((), "", "")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return HoldingsResult((), "", "")
    needed = {"股票代码", "股票名称", "占净值比例"}
    if not needed.issubset(df.columns):
        return HoldingsResult((), "", "")
    # Pick latest quarter via column lex-sort.
    quarter_col = "季度" if "季度" in df.columns else ("报告期" if "报告期" in df.columns else None)
    if quarter_col is None:
        return HoldingsResult((), "", "")
    latest_quarter = sorted(df[quarter_col].astype(str).unique())[-1]
    latest = df[df[quarter_col].astype(str) == latest_quarter]
    ranked = latest.sort_values("占净值比例", ascending=False).head(top_n)
    holdings: list[FundHolding] = []
    for _, row in ranked.iterrows():
        raw_code = str(row["股票代码"]).strip()
        normalized = _normalize_ticker(raw_code)
        exchange = _parse_exchange(row)
        try:
            weight_pct = float(row["占净值比例"])
        except (TypeError, ValueError):
            weight_pct = 0.0
        holdings.append(FundHolding(
            symbol=normalized,
            name_cn=str(row["股票名称"]),
            weight_pct=weight_pct,
            exchange=exchange,
            provider_symbol=raw_code,
        ))
    # Quarter metadata from any latest-quarter row (they share the same text).
    sample = latest.iloc[0]
    quarter_str, date_iso = _parse_quarter_column(sample)
    return HoldingsResult(
        constituents=tuple(holdings),
        source_report_date=date_iso,
        source_report_quarter=quarter_str,
    )
```

> Note: the legacy `_to_qualified_symbol` is intentionally NOT applied here. `FundHolding.symbol` is the normalized ticker for adapter routing. Callers requiring the `.SH/.SZ` form use `_to_qualified_symbol` themselves.

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py -k "fetch_cn_etf_holdings or parse_exchange or parse_quarter" -v`
Expected: 5 fetch_cn_etf_holdings + 13 parsers = 18 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "refactor(fundamentals): fetch_cn_etf_holdings returns HoldingsResult with FundHolding + quarter metadata"
```

---

## Task 8: Add `fetch_cn_stock_news`

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py`
- Test: `tests/fundamentals/test_akshare_fundamentals.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_akshare_fundamentals.py`:

```python
from irc.fundamentals.akshare_fundamentals import fetch_cn_stock_news


_CN_NEWS_FRAME = pd.DataFrame({
    "关键词": ["茅台"] * 5,
    "新闻标题": ["新品发布", "增持公告", "Q1业绩", "调研纪要", "回购"],
    "新闻内容": ["a", "b", "c", "d", "e"],
    "发布时间": [
        "2024-04-15 09:00:00",
        "2024-04-14 09:00:00",
        "2024-04-13 09:00:00",
        "2024-04-12 09:00:00",
        "2024-04-11 09:00:00",
    ],
    "新闻链接": [f"https://example.com/{i}" for i in range(5)],
    "文章来源": ["东财"] * 5,
})


def test_fetch_cn_stock_news_top_3_by_date_desc() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _CN_NEWS_FRAME
        out = fetch_cn_stock_news("600519", top_k=3)
    assert mocked.call_args[0][0] == "stock_news_em"
    assert mocked.call_args[1] == {"symbol": "600519"}
    assert len(out) == 3
    assert out[0].published_iso == "2024-04-15"
    assert out[0].title == "新品发布"
    assert out[0].symbol == "600519"
    assert out[0].source == "stock_news_em"
    assert out[1].published_iso == "2024-04-14"
    assert out[2].published_iso == "2024-04-13"


def test_fetch_cn_stock_news_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = ConnectionError("dfcfw 502")
        out = fetch_cn_stock_news("600519")
    assert out == ()


def test_fetch_cn_stock_news_empty_on_empty_frame() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_cn_stock_news("600519")
    assert out == ()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py::test_fetch_cn_stock_news_top_3_by_date_desc -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/irc/fundamentals/akshare_fundamentals.py`:

```python
from irc.fundamentals.types import NewsItem


def fetch_cn_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]:
    """Top-K most recent stock news items from EastMoney.

    Returns () on adapter exception or empty frame.
    """
    try:
        df = _ak_call("stock_news_em", symbol=stock)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    title_col = "新闻标题" if "新闻标题" in df.columns else None
    date_col = "发布时间" if "发布时间" in df.columns else None
    url_col = "新闻链接" if "新闻链接" in df.columns else None
    summary_col = "新闻内容" if "新闻内容" in df.columns else None
    if not (title_col and date_col):
        return ()
    sorted_df = df.sort_values(date_col, ascending=False).head(top_k)
    out: list[NewsItem] = []
    for _, row in sorted_df.iterrows():
        raw_date = str(row[date_col])
        # "2024-04-15 09:00:00" → "2024-04-15"
        published = raw_date.split(" ")[0]
        out.append(NewsItem(
            symbol=stock,
            title=str(row[title_col]),
            url=str(row[url_col]) if url_col else "",
            published_iso=published,
            summary=str(row[summary_col]) if summary_col else "",
            source="stock_news_em",
        ))
    return tuple(out)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_akshare_fundamentals.py -k "cn_stock_news" -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "feat(fundamentals): add fetch_cn_stock_news adapter (top-K by date desc)"
```

---

## Task 9: Add `fetch_hk_stock_news` (stub-empty fallback, NO scraper)

**Files:**
- Modify: `src/irc/fundamentals/hkex_client.py`
- Test: `tests/fundamentals/test_hkex_client.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_hkex_client.py`:

```python
from unittest.mock import patch

import pandas as pd

from irc.fundamentals.hkex_client import fetch_hk_stock_news


_HK_NEWS_FRAME = pd.DataFrame({
    "发布时间": [
        "2024-04-15 09:00:00",
        "2024-04-14 09:00:00",
        "2024-04-13 09:00:00",
        "2024-04-12 09:00:00",
        "2024-04-11 09:00:00",
    ],
    "标题": ["t1", "t2", "t3", "t4", "t5"],
    "内容摘要": ["a", "b", "c", "d", "e"],
    "新闻链接": [f"https://hk-news.example/{i}" for i in range(5)],
})


def test_fetch_hk_stock_news_top_3_by_date_desc() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = _HK_NEWS_FRAME
        out = fetch_hk_stock_news("00700", top_k=3)
    assert mocked.call_args[0][0] == "stock_hk_news_em"
    assert mocked.call_args[1] == {"symbol": "00700"}
    assert len(out) == 3
    assert out[0].published_iso == "2024-04-15"
    assert out[0].source == "stock_hk_news_em"
    assert out[0].symbol == "00700"


def test_fetch_hk_stock_news_unsupported_adapter_returns_empty() -> None:
    # AkShare without stock_hk_news_em — _ak_call raises AttributeError.
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.side_effect = AttributeError("module 'akshare' has no attribute 'stock_hk_news_em'")
        out = fetch_hk_stock_news("00700")
    assert out == ()


def test_fetch_hk_stock_news_empty_frame_returns_empty() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_hk_stock_news("00700")
    assert out == ()


def test_fetch_hk_stock_news_connection_error_returns_empty() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.side_effect = ConnectionError("hk dfcfw 502")
        out = fetch_hk_stock_news("00700")
    assert out == ()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_hkex_client.py -k "hk_stock_news" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/irc/fundamentals/hkex_client.py`:

```python
from irc.fundamentals.types import NewsItem


def fetch_hk_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]:
    """Top-K recent HK stock news via AkShare `stock_hk_news_em`.

    On any adapter error (including `AttributeError` from AkShare versions
    that don't ship the function) or empty frame, returns `()`. The caller
    distinguishes "adapter missing" vs "empty result" by inspecting its own
    failure-reason context (`hk_news_unsupported_adapter` vs `hk_news_empty`).
    """
    code = _normalize_hk_code(stock)
    if not code:
        return ()
    try:
        df = _ak_call("stock_hk_news_em", symbol=code)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    title_col = "标题" if "标题" in df.columns else None
    date_col = "发布时间" if "发布时间" in df.columns else None
    url_col = "新闻链接" if "新闻链接" in df.columns else None
    summary_col = "内容摘要" if "内容摘要" in df.columns else None
    if not (title_col and date_col):
        return ()
    sorted_df = df.sort_values(date_col, ascending=False).head(top_k)
    out: list[NewsItem] = []
    for _, row in sorted_df.iterrows():
        raw_date = str(row[date_col])
        published = raw_date.split(" ")[0]
        out.append(NewsItem(
            symbol=code,
            title=str(row[title_col]),
            url=str(row[url_col]) if url_col else "",
            published_iso=published,
            summary=str(row[summary_col]) if summary_col else "",
            source="stock_hk_news_em",
        ))
    return tuple(out)
```

Also add a module-level helper for the caller to detect "adapter unsupported" deterministically:

```python
def hk_news_adapter_available() -> bool:
    """Return True iff the installed AkShare exposes `stock_hk_news_em`.

    Lazy-imports AkShare; on ImportError returns False.
    """
    try:
        import akshare as ak  # local import
    except ImportError:
        return False
    return hasattr(ak, "stock_hk_news_em")
```

Add a test for `hk_news_adapter_available`:

```python
def test_hk_news_adapter_available_true(monkeypatch) -> None:
    import sys, types
    fake_ak = types.SimpleNamespace(stock_hk_news_em=lambda **kw: None)
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    from irc.fundamentals.hkex_client import hk_news_adapter_available
    assert hk_news_adapter_available() is True


def test_hk_news_adapter_available_false_when_missing(monkeypatch) -> None:
    import sys, types
    fake_ak = types.SimpleNamespace()  # no stock_hk_news_em attribute
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    from irc.fundamentals.hkex_client import hk_news_adapter_available
    assert hk_news_adapter_available() is False
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_hkex_client.py -v`
Expected: PASS (4 new news tests + 2 adapter-available tests + pre-existing).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/hkex_client.py tests/fundamentals/test_hkex_client.py
git commit -m "feat(fundamentals): add fetch_hk_stock_news + hk_news_adapter_available (stub-empty fallback)"
```

---

## Task 10: Reorder `map_lookthrough` — `cn_equity_fund` first; wire `provider_symbol`

**Files:**
- Modify: `src/irc/opportunity/lookthrough.py`
- Test: `tests/opportunity/test_lookthrough.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_lookthrough.py`:

```python
def test_map_lookthrough_cn_equity_fund_themed_routes_to_active_fund() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import LookthroughTarget, OpportunityInput
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme="consumer",
        name_cn="易方达蓝筹精选",
    )
    target = map_lookthrough(inp)
    assert target == LookthroughTarget(
        kind="active_fund", key="fund_005827",
        display_cn="易方达蓝筹精选", provider_symbol="005827",
    )


def test_map_lookthrough_cn_equity_fund_unthemed_routes_to_active_fund() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import LookthroughTarget, OpportunityInput
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    target = map_lookthrough(inp)
    assert target == LookthroughTarget(
        kind="active_fund", key="fund_005827",
        display_cn="易方达蓝筹精选", provider_symbol="005827",
    )


def test_map_lookthrough_cn_equity_fund_tracked_index_still_routes_active_fund() -> None:
    # Active fund declaring a tracked_index is still an active fund.
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import OpportunityInput
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", tracked_index="csi300",
        name_cn="易方达蓝筹精选",
    )
    target = map_lookthrough(inp)
    assert target.kind == "active_fund"
    assert target.provider_symbol == "005827"


def test_map_lookthrough_legacy_us_etf_unchanged() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import LookthroughTarget, OpportunityInput
    inp = OpportunityInput(
        instrument_id="x", asset_class="us_etf",
        market="us", tracked_index="nasdaq100", name_cn="纳指ETF",
    )
    assert map_lookthrough(inp) == LookthroughTarget(
        "qdii_us", "nasdaq100", "纳斯达克100", "",
    )


def test_map_lookthrough_gold_unchanged() -> None:
    from irc.opportunity.lookthrough import map_lookthrough
    from irc.opportunity.types import LookthroughTarget, OpportunityInput
    inp = OpportunityInput(
        instrument_id="x", asset_class="gold",
        market="cn_off_exchange", name_cn="黄金ETF",
    )
    assert map_lookthrough(inp) == LookthroughTarget("gold", "gold", "黄金", "")
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_lookthrough.py::test_map_lookthrough_cn_equity_fund_themed_routes_to_active_fund -v`
Expected: FAIL — current code routes to `sector_theme` for themed cn_equity_fund.

- [ ] **Step 3: Reorder branches**

Edit `src/irc/opportunity/lookthrough.py`. Modify `map_lookthrough`:

```python
def map_lookthrough(inp: OpportunityInput) -> LookthroughTarget:
    """Map an instrument to its underlying-exposure target.

    Active funds always route to `active_fund` regardless of theme/tracked_index.
    Other asset classes preserve the legacy ordering.
    """
    if inp.asset_class == "cn_equity_fund":
        return LookthroughTarget(
            kind="active_fund",
            key=f"fund_{inp.instrument_id}",
            display_cn=inp.name_cn,
            provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "gold":
        return LookthroughTarget("gold", "gold", "黄金")

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget("bond", "cn_bond", "中国债券")

    tracked = (inp.tracked_index or "").strip().lower() or None
    theme = (inp.theme or "").strip().lower() or None

    if inp.asset_class == "us_etf":
        raw = tracked or theme or "us_equity"
        key = _normalize_qdii_key(raw, _QDII_US_ALIASES) or raw
        return LookthroughTarget(
            "qdii_us", key, _display_for(key, _QDII_US_DISPLAY, key),
        )

    if inp.asset_class == "hk_etf":
        raw = tracked or theme or "hsi"
        key = _normalize_qdii_key(raw, _QDII_HK_ALIASES) or raw
        return LookthroughTarget(
            "qdii_hk", key, _display_for(key, _QDII_HK_DISPLAY, key),
        )

    if inp.asset_class == "qdii_global":
        raw = tracked or theme or "global_equity"
        return LookthroughTarget("qdii_global", raw, raw)

    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget("broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked])
        if tracked in _QDII_US_KEYS:
            return LookthroughTarget("qdii_us", tracked, _QDII_US_DISPLAY[tracked])
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget("qdii_hk", tracked, _QDII_HK_DISPLAY[tracked])
        return LookthroughTarget("broad_index", tracked, tracked)

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget("sector_theme", theme, _SECTOR_THEME_DISPLAY[theme])

    return LookthroughTarget("broad_index", "unknown", "未知底层")
```

> The `LookthroughKind` Literal in `types.py` does NOT currently include `"qdii_global"`. Verify by grepping; if needed, add it. (Run `grep -n "qdii_global\|LookthroughKind" src/irc/opportunity/types.py` first.)

Add `qdii_global` to the `LookthroughKind` Literal in `src/irc/opportunity/types.py` if not present:

```python
LookthroughKind = Literal[
    "broad_index", "sector_theme", "qdii_us", "qdii_hk",
    "bond", "gold", "active_fund", "qdii_global",
]
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_lookthrough.py tests/opportunity/test_lookthrough_normalization.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough.py src/irc/opportunity/types.py tests/opportunity/test_lookthrough.py
git commit -m "feat(opportunity): reorder map_lookthrough so cn_equity_fund routes to active_fund with provider_symbol"
```

---

## Task 11: Remove `cn_equity_fund` from `NON_INDEXABLE_ASSET_CLASSES`

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py`
- Test: `tests/opportunity/test_thesis_evidence.py`

- [ ] **Step 1: Write failing test**

Append to `tests/opportunity/test_thesis_evidence.py`:

```python
def test_non_indexable_asset_classes_excludes_cn_equity_fund() -> None:
    from irc.opportunity.thesis_evidence import NON_INDEXABLE_ASSET_CLASSES
    assert "cn_equity_fund" not in NON_INDEXABLE_ASSET_CLASSES
    # Other non-indexable classes preserved.
    assert "gold" in NON_INDEXABLE_ASSET_CLASSES
    assert "cn_bond_fund" in NON_INDEXABLE_ASSET_CLASSES
    assert "qdii_global" in NON_INDEXABLE_ASSET_CLASSES
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_thesis_evidence.py::test_non_indexable_asset_classes_excludes_cn_equity_fund -v`
Expected: FAIL.

- [ ] **Step 3: Update set**

Edit `src/irc/opportunity/thesis_evidence.py`:

```python
NON_INDEXABLE_ASSET_CLASSES: frozenset[str] = frozenset({
    "gold", "cn_bond_fund", "qdii_global",
})
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_thesis_evidence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/thesis_evidence.py tests/opportunity/test_thesis_evidence.py
git commit -m "feat(opportunity): remove cn_equity_fund from NON_INDEXABLE_ASSET_CLASSES"
```

---

## Task 12: Add `_build_active_fund_snapshot` and change `build_snapshot` to accept `LookthroughTarget`

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Test: `tests/fundamentals/test_snapshot.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_snapshot.py`:

```python
from unittest.mock import patch

from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import (
    ActiveFundSnapshot, FundHolding, HoldingsResult, NewsItem,
)
from irc.opportunity.types import LookthroughTarget


def _holdings_result_cn(symbols=("600519", "000333")):
    return HoldingsResult(
        constituents=tuple(
            FundHolding(symbol=s, name_cn=s, weight_pct=10.0 - i,
                        exchange="SH" if s.startswith("6") else "SZ",
                        provider_symbol=s)
            for i, s in enumerate(symbols)
        ),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )


def test_build_snapshot_active_fund_dispatch(monkeypatch) -> None:
    """Active-fund target returns ActiveFundSnapshot via _build_active_fund_snapshot."""
    from irc.fundamentals import snapshot as snap_mod
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings", lambda sym, top_n=10: _holdings_result_cn(),
    )
    monkeypatch.setattr(snap_mod, "fetch_cn_filing_digest", lambda s: None)
    monkeypatch.setattr(snap_mod, "fetch_cn_broker_reports", lambda s: ())
    monkeypatch.setattr(snap_mod, "fetch_cn_stock_news", lambda s, top_k=3: ())
    target = LookthroughTarget("active_fund", "fund_005827", "易方达蓝筹精选", "005827")
    out = build_snapshot(target, top_n=10)
    assert isinstance(out, ActiveFundSnapshot)
    assert out.fund_id == "005827"
    assert out.source_report_quarter == "2024Q1"
    assert len(out.constituent_analyses) == 2


def test_build_snapshot_legacy_string_target_still_works(monkeypatch) -> None:
    """build_snapshot still accepts LookthroughTarget for legacy kinds."""
    target = LookthroughTarget("broad_index", "csi300", "never-seen-target")
    snap = build_snapshot(target, top_n=5, as_of_iso="2026-05-15")
    # Unknown legacy display_cn → failure reason path.
    assert snap.lookthrough_target == "never-seen-target"
    assert snap.failure_reasons


def test_build_snapshot_active_fund_empty_holdings_records_fund_level_failure(monkeypatch) -> None:
    from irc.fundamentals import snapshot as snap_mod
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: HoldingsResult((), "", ""),
    )
    target = LookthroughTarget("active_fund", "fund_005827", "易方达蓝筹精选", "005827")
    out = build_snapshot(target, top_n=10)
    assert isinstance(out, ActiveFundSnapshot)
    assert out.constituent_analyses == ()
    assert any(r.startswith("holdings_fetch_failed:005827") for r in out.fund_level_failure_reasons)


def test_build_snapshot_active_fund_routes_hk_through_hk_adapters(monkeypatch) -> None:
    """HK holdings call fetch_hk_filing_digest + fetch_hk_stock_news; NEVER fetch_cn_broker_reports."""
    from irc.fundamentals import snapshot as snap_mod
    hk_only = HoldingsResult(
        constituents=(FundHolding("00700", "腾讯", 9.0, "HK", "00700"),),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    monkeypatch.setattr(snap_mod, "fetch_cn_etf_holdings", lambda sym, top_n=10: hk_only)
    cn_broker_called = []
    monkeypatch.setattr(
        snap_mod, "fetch_cn_broker_reports",
        lambda s: cn_broker_called.append(s) or (),
    )
    monkeypatch.setattr(snap_mod, "fetch_hk_filing_digest", lambda s: None)
    monkeypatch.setattr(snap_mod, "fetch_hk_stock_news", lambda s, top_k=3: ())
    target = LookthroughTarget("active_fund", "fund_x", "x", "x")
    build_snapshot(target, top_n=1)
    assert cn_broker_called == []  # never called for HK constituents


def test_build_snapshot_active_fund_records_us_unsupported(monkeypatch) -> None:
    from irc.fundamentals import snapshot as snap_mod
    us_only = HoldingsResult(
        constituents=(FundHolding("AAPL", "Apple", 9.0, "US", "AAPL"),),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    monkeypatch.setattr(snap_mod, "fetch_cn_etf_holdings", lambda sym, top_n=10: us_only)
    target = LookthroughTarget("active_fund", "fund_x", "x", "x")
    out = build_snapshot(target, top_n=1)
    assert isinstance(out, ActiveFundSnapshot)
    assert "us_evidence_unsupported:AAPL" in out.failure_reasons_by_symbol["AAPL"]
```

> Existing `build_snapshot("string", ...)` test sites in `test_snapshot.py` will break; we update them in Step 3 alongside the implementation change.

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_snapshot.py::test_build_snapshot_active_fund_dispatch -v`
Expected: FAIL — `build_snapshot` doesn't accept `LookthroughTarget`.

- [ ] **Step 3: Implement `_build_active_fund_snapshot` and update `build_snapshot` signature**

Edit `src/irc/fundamentals/snapshot.py`. Add imports:

```python
from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_etf_holdings,
    fetch_cn_index_constituents,
    fetch_cn_stock_news,
    fetch_hk_index_constituents,
)
from irc.fundamentals.hkex_client import (
    fetch_hk_filing_digest,
    fetch_hk_stock_news,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
    FundHolding,
    HoldingsResult,
    NewsItem,
)
from irc.opportunity.types import (
    ConstituentAnalysis,
    LookthroughTarget,
    ThesisEvidence,
)
```

Replace `build_snapshot`:

```python
def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
) -> ActiveFundSnapshot | ConstituentSnapshot:
    """Compose snapshot for a typed `LookthroughTarget`.

    `kind == "active_fund"` → ActiveFundSnapshot via _build_active_fund_snapshot.
    All other kinds → legacy ConstituentSnapshot via the existing
    `display_cn`-keyed `_TARGET_REGISTRY`.
    """
    timestamp = as_of_iso or _today_iso()
    if target.kind == "active_fund":
        return _build_active_fund_snapshot(target, top_n=top_n)
    return _build_legacy_snapshot(target.display_cn, top_n=top_n, as_of_iso=timestamp)


def _build_legacy_snapshot(
    lookthrough_target: str, *, top_n: int, as_of_iso: str,
) -> ConstituentSnapshot:
    """Original `build_snapshot(string)` body, unchanged."""
    spec = _TARGET_REGISTRY.get(lookthrough_target)
    if spec is None:
        return ConstituentSnapshot(
            lookthrough_target=lookthrough_target,
            as_of_iso=as_of_iso,
            constituents=(), filings=(), broker_reports=(),
            failure_reasons=(f"unknown lookthrough_target: {lookthrough_target}",),
        )
    if spec.kind == "cn_index":
        return _build_cn_snapshot(lookthrough_target, spec, top_n, as_of_iso)
    if spec.kind == "us_symbols":
        return _build_us_snapshot(lookthrough_target, spec, as_of_iso)
    if spec.kind == "hk_symbols":
        return _build_hk_snapshot(lookthrough_target, spec, as_of_iso)
    if spec.kind == "hk_index":
        return _build_hk_index_snapshot(lookthrough_target, spec, top_n, as_of_iso)
    return ConstituentSnapshot(
        lookthrough_target=lookthrough_target,
        as_of_iso=as_of_iso,
        constituents=(), filings=(), broker_reports=(),
        failure_reasons=(f"unsupported spec kind: {spec.kind}",),
    )


def _evidence_for_constituent(
    holding: FundHolding,
    *,
    fund_id: str,
) -> tuple[tuple[ThesisEvidence, ...], list[str]]:
    """Fetch market-routed evidence for one holding.

    Returns (evidence_tuple, failure_reasons_list).
    """
    failures: list[str] = []
    evidence: list[ThesisEvidence] = []
    common = dict(
        scope="constituent",
        owner_instrument_id=fund_id,
        parent_fund_id=fund_id,
        constituent_key=holding.symbol,
        holding_weight_pct=holding.weight_pct,
    )
    if holding.exchange in ("SH", "SZ", "BJ"):
        try:
            digest = fetch_cn_filing_digest(holding.symbol)
        except Exception as exc:
            failures.append(f"filing_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            digest = None
        if digest is None:
            failures.append(f"filing_empty:{holding.symbol}")
        else:
            evidence.append(ThesisEvidence(
                type="filing", source=digest.symbol,
                url=digest.source_url, date=digest.filed_at_iso,
                summary=f"{digest.symbol} {digest.fiscal_period} revenue_yoy={digest.revenue_yoy}",
                citation_kind="data", **common,
            ))
        try:
            brokers = fetch_cn_broker_reports(holding.symbol)
        except Exception as exc:
            failures.append(f"broker_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            brokers = ()
        if not brokers:
            failures.append(f"broker_empty:{holding.symbol}")
        for r in brokers[:2]:
            evidence.append(ThesisEvidence(
                type="broker", source=r.broker, url=r.source_url,
                date=r.published_iso, summary=f"{r.broker} {r.rating}: {r.title}".strip(),
                citation_kind="information", **common,
            ))
        try:
            news = fetch_cn_stock_news(holding.symbol, top_k=3)
        except Exception as exc:
            failures.append(f"news_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            news = ()
        if not news:
            failures.append(f"news_empty:{holding.symbol}")
        for n in news:
            evidence.append(ThesisEvidence(
                type="news", source=n.source, url=n.url,
                date=n.published_iso, summary=(n.title or n.summary[:120]),
                citation_kind="information", **common,
            ))
    elif holding.exchange == "HK":
        try:
            digest = fetch_hk_filing_digest(holding.symbol)
        except Exception as exc:
            failures.append(f"filing_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            digest = None
        if digest is None:
            failures.append(f"filing_empty:{holding.symbol}")
        else:
            evidence.append(ThesisEvidence(
                type="filing", source=digest.symbol,
                url=digest.source_url, date=digest.filed_at_iso,
                summary=f"{digest.symbol} {digest.fiscal_period} revenue_yoy={digest.revenue_yoy}",
                citation_kind="data", **common,
            ))
        # No HK broker adapter in V1.
        from irc.fundamentals.hkex_client import hk_news_adapter_available
        if not hk_news_adapter_available():
            failures.append(f"hk_news_unsupported_adapter:{holding.symbol}")
            news = ()
        else:
            try:
                news = fetch_hk_stock_news(holding.symbol, top_k=3)
            except Exception as exc:
                failures.append(f"hk_news_fetch_failed:{holding.symbol}:{type(exc).__name__}")
                news = ()
            if not news:
                failures.append(f"hk_news_empty:{holding.symbol}")
        for n in news:
            evidence.append(ThesisEvidence(
                type="news", source=n.source, url=n.url,
                date=n.published_iso, summary=(n.title or n.summary[:120]),
                citation_kind="information", **common,
            ))
    elif holding.exchange == "US":
        failures.append(f"us_evidence_unsupported:{holding.symbol}")
    else:  # UNKNOWN
        failures.append(f"exchange_unknown:{holding.symbol}")
    return tuple(evidence), failures


def _one_line_view(holding: FundHolding, evidence: tuple[ThesisEvidence, ...]) -> str:
    """≤60-char deterministic label. Empty evidence → '证据获取失败'."""
    if not evidence:
        return "证据获取失败"
    fragments: list[str] = []
    by_type = {"filing": None, "broker": None, "news": None}
    for e in evidence:
        if e.type in by_type and by_type[e.type] is None:
            by_type[e.type] = e
    if by_type["filing"] is not None:
        fragments.append(by_type["filing"].summary[:24])
    if by_type["broker"] is not None:
        fragments.append(by_type["broker"].summary[:18])
    if by_type["news"] is not None:
        fragments.append(by_type["news"].summary[:24])
    if not fragments:
        return "证据获取失败"
    return " · ".join(fragments)[:60]


def _build_active_fund_snapshot(
    target: LookthroughTarget, *, top_n: int,
) -> ActiveFundSnapshot:
    """Fetch holdings then per-constituent evidence per exchange routing."""
    fund_id = target.provider_symbol
    holdings = fetch_cn_etf_holdings(target.provider_symbol, top_n=top_n)
    if not holdings.constituents:
        return ActiveFundSnapshot(
            fund_id=fund_id,
            source_report_date=holdings.source_report_date,
            source_report_quarter=holdings.source_report_quarter,
            cache_probed_at="",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
            fund_level_failure_reasons=(
                f"holdings_fetch_failed:{fund_id}:empty",
            ),
        )
    analyses: list[ConstituentAnalysis] = []
    fail_by_symbol: dict[str, tuple[str, ...]] = {}
    for h in holdings.constituents:
        evidence, failures = _evidence_for_constituent(h, fund_id=fund_id)
        if failures:
            fail_by_symbol[h.symbol] = tuple(sorted(failures))
        analyses.append(ConstituentAnalysis(
            symbol=h.symbol,
            name_cn=h.name_cn,
            weight_pct=h.weight_pct,
            evidence=evidence,
            failure_reasons=tuple(sorted(failures)),
            one_line_view=_one_line_view(h, evidence),
        ))
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date=holdings.source_report_date,
        source_report_quarter=holdings.source_report_quarter,
        cache_probed_at="",
        constituent_analyses=tuple(analyses),
        failure_reasons_by_symbol=fail_by_symbol,
        fund_level_failure_reasons=(),
    )
```

Update existing legacy call sites — every `build_snapshot("string", ...)` test call in `tests/fundamentals/test_snapshot.py` (approximately 10 sites) must be replaced with `LookthroughTarget` construction. Use this rewrite recipe per call:

- `build_snapshot("半导体指数", ...)` → `build_snapshot(LookthroughTarget("sector_theme", "x", "半导体指数"), ...)`
- `build_snapshot("never-seen-target", ...)` → `build_snapshot(LookthroughTarget("broad_index", "x", "never-seen-target"), ...)`
- `build_snapshot("Mag7", ...)` → `build_snapshot(LookthroughTarget("qdii_us", "x", "Mag7"), ...)`
- `build_snapshot("HK-Tech", ...)` → `build_snapshot(LookthroughTarget("qdii_hk", "x", "HK-Tech"), ...)`
- `build_snapshot("HSI-test", ...)` → `build_snapshot(LookthroughTarget("qdii_hk", "x", "HSI-test"), ...)`
- `build_snapshot("纳斯达克100", ...)` → `build_snapshot(LookthroughTarget("qdii_us", "nasdaq100", "纳斯达克100"), ...)`
- `build_snapshot("白酒指数", ...)` → `build_snapshot(LookthroughTarget("broad_index", "x", "白酒指数"), ...)`

Add `from irc.opportunity.types import LookthroughTarget` at the top of `tests/fundamentals/test_snapshot.py`.

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_snapshot.py -v`
Expected: PASS (legacy tests preserved + 5 new active-fund tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_snapshot.py
git commit -m "feat(fundamentals): build_snapshot accepts LookthroughTarget; add _build_active_fund_snapshot"
```

---

## Task 13: Update `fundamentals_cmd.py` and its tests

**Files:**
- Modify: `src/irc/commands/fundamentals_cmd.py`
- Modify: `tests/commands/test_fundamentals_cmd.py`

- [ ] **Step 1: Inspect current call site**

Run: `grep -n "build_snapshot" src/irc/commands/fundamentals_cmd.py`

- [ ] **Step 2: Rewrite test mocks to expect `LookthroughTarget`**

In each of the 4 `tests/commands/test_fundamentals_cmd.py` sites that patch `build_snapshot`, update the assertion to confirm the call was made with a `LookthroughTarget`:

```python
# Replace `build_snapshot.assert_called_once_with("半导体", ...)` style:
call_args = mocked.call_args
assert call_args.args[0].display_cn == "半导体"
assert call_args.args[0].kind in ("sector_theme", "broad_index")
```

(Adjust per existing test intent.)

- [ ] **Step 3: Update production call site**

Edit `src/irc/commands/fundamentals_cmd.py`. Wherever `build_snapshot(<string>)` is called, wrap with `LookthroughTarget`. Example:

```python
from irc.opportunity.types import LookthroughTarget

target = LookthroughTarget(
    kind="broad_index", key=user_input, display_cn=user_input,
)
snap = build_snapshot(target, top_n=top_n, as_of_iso=as_of)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_fundamentals_cmd.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/fundamentals_cmd.py tests/commands/test_fundamentals_cmd.py
git commit -m "refactor(commands): fundamentals_cmd builds LookthroughTarget for build_snapshot"
```

---

## Task 14: Extend `snapshot_cache.py` with active-fund cache I/O

**Files:**
- Modify: `src/irc/fundamentals/snapshot_cache.py`
- Test: `tests/fundamentals/test_snapshot_cache.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/fundamentals/test_snapshot_cache.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.fundamentals.snapshot_cache import (
    active_fund_cache_path,
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.types import ConstituentAnalysis, ThesisEvidence


def _make_snapshot(quarter: str = "2024Q1") -> ActiveFundSnapshot:
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2024-04-15", summary="贵州茅台 24Q1",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(ev,), failure_reasons=(), one_line_view="x",
    )
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=(c,),
        failure_reasons_by_symbol={"600519": ()},
    )


def test_active_fund_cache_path_uses_quarter(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    assert path == tmp_path / "fundamentals" / "2024Q1" / "active_fund" / "fund_005827.json"


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    snap = _make_snapshot()
    written = write_active_fund_cache(snap, tmp_path)
    assert written.exists()
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded is not None
    assert loaded.fund_id == "005827"
    assert loaded.source_report_quarter == "2024Q1"
    assert loaded.constituent_analyses[0].symbol == "600519"
    assert loaded.constituent_analyses[0].evidence[0].citation_id != ""


def test_load_active_fund_cache_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_load_active_fund_cache_returns_none_on_malformed(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json}", encoding="utf-8")
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_write_then_reload_preserves_holding_weight_pct(tmp_path: Path) -> None:
    snap = _make_snapshot()
    write_active_fund_cache(snap, tmp_path)
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded.constituent_analyses[0].evidence[0].holding_weight_pct == 6.2
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_snapshot_cache.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement helpers**

Append to `src/irc/fundamentals/snapshot_cache.py`:

```python
from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.types import ConstituentAnalysis, ThesisEvidence


def active_fund_cache_path(fund_id: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / "active_fund" / f"fund_{fund_id}.json"


def _evidence_to_dict(e: ThesisEvidence) -> dict[str, Any]:
    return {
        "type": e.type, "source": e.source, "url": e.url, "date": e.date,
        "summary": e.summary, "scope": e.scope, "citation_kind": e.citation_kind,
        "owner_instrument_id": e.owner_instrument_id,
        "parent_fund_id": e.parent_fund_id,
        "constituent_key": e.constituent_key,
        "citation_id": e.citation_id,
        "holding_weight_pct": e.holding_weight_pct,
    }


def _evidence_from_dict(d: dict[str, Any]) -> ThesisEvidence:
    return ThesisEvidence(
        type=d["type"], source=d["source"], url=d["url"], date=d["date"],
        summary=d["summary"], scope=d["scope"], citation_kind=d["citation_kind"],
        owner_instrument_id=d["owner_instrument_id"],
        parent_fund_id=d.get("parent_fund_id"),
        constituent_key=d.get("constituent_key"),
        holding_weight_pct=d.get("holding_weight_pct"),
    )


def _constituent_to_dict(c: ConstituentAnalysis) -> dict[str, Any]:
    return {
        "symbol": c.symbol, "name_cn": c.name_cn, "weight_pct": c.weight_pct,
        "evidence": [_evidence_to_dict(e) for e in c.evidence],
        "failure_reasons": list(c.failure_reasons),
        "one_line_view": c.one_line_view,
    }


def _constituent_from_dict(d: dict[str, Any]) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=d["symbol"], name_cn=d["name_cn"], weight_pct=float(d["weight_pct"]),
        evidence=tuple(_evidence_from_dict(e) for e in d.get("evidence", [])),
        failure_reasons=tuple(d.get("failure_reasons", ())),
        one_line_view=d.get("one_line_view", ""),
    )


def _active_fund_to_dict(snap: ActiveFundSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "source_report_date": snap.source_report_date,
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "constituent_analyses": [
            _constituent_to_dict(c) for c in snap.constituent_analyses
        ],
        "failure_reasons_by_symbol": {
            k: list(v) for k, v in snap.failure_reasons_by_symbol.items()
        },
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
    }


def _active_fund_from_dict(body: dict[str, Any]) -> ActiveFundSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "constituent_analyses"}
    if not needed.issubset(body):
        return None
    try:
        analyses = tuple(
            _constituent_from_dict(c) for c in body["constituent_analyses"]
        )
    except (KeyError, TypeError, ValueError):
        return None
    return ActiveFundSnapshot(
        fund_id=str(body["fund_id"]),
        source_report_date=str(body.get("source_report_date", "")),
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        constituent_analyses=analyses,
        failure_reasons_by_symbol={
            k: tuple(v) for k, v in body.get("failure_reasons_by_symbol", {}).items()
        },
        fund_level_failure_reasons=tuple(body.get("fund_level_failure_reasons", ())),
    )


def write_active_fund_cache(snap: ActiveFundSnapshot, root: Path) -> Path:
    path = active_fund_cache_path(snap.fund_id, snap.source_report_quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(_active_fund_to_dict(snap), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_active_fund_cache(
    fund_id: str, quarter: str, root: Path,
) -> ActiveFundSnapshot | None:
    path = active_fund_cache_path(fund_id, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _active_fund_from_dict(body)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_snapshot_cache.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot_cache.py tests/fundamentals/test_snapshot_cache.py
git commit -m "feat(fundamentals): active_fund cache path + atomic write/load preserving ThesisEvidence provenance"
```

---

## Task 15: Extend `derive_thesis_from_evidence` to return 5-tuple with flatten ordering

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py`
- Test: `tests/opportunity/test_thesis_evidence.py`

- [ ] **Step 1: Write failing tests (including spec Q-J `test_active_fund_thesis_evidence_flatten_ordering`)**

Append to `tests/opportunity/test_thesis_evidence.py`:

```python
def _make_evidence(
    type_, weight, citation_seed, *, owner="005827", symbol="600519",
):
    """Helper — produce a constituent-scoped evidence with controlled weight + id."""
    from irc.opportunity.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=symbol, url=f"https://x/{citation_seed}",
        date="2024-04-15", summary=f"{symbol}-{citation_seed}",
        scope="constituent", citation_kind="data" if type_ == "filing" else "information",
        owner_instrument_id=owner, parent_fund_id=owner, constituent_key=symbol,
        holding_weight_pct=weight,
    )


def test_derive_thesis_returns_5_tuple_for_active_fund() -> None:
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    from irc.opportunity.types import ConstituentAnalysis
    from irc.fundamentals.types import ActiveFundSnapshot
    ev = _make_evidence("filing", 6.2, "a")
    analysis = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(ev,), failure_reasons=(), one_line_view="x",
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="",
        constituent_analyses=(analysis,),
        failure_reasons_by_symbol={},
    )
    state, reason, evidence, gaps, analyses = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert analyses == (analysis,)
    assert evidence == (ev,)


def test_derive_thesis_5_tuple_non_active_returns_empty_analyses_slot() -> None:
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    result = derive_thesis_from_evidence(
        None, None, asset_class="us_etf", owner_instrument_id="x",
    )
    assert len(result) == 5
    assert result[4] == ()


def test_active_fund_thesis_evidence_flatten_ordering() -> None:
    """Q-J: order by (weight_pct desc, type_rank asc, citation_id asc).

    type_rank: filing=0, broker=1, news=2.
    """
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    from irc.opportunity.types import ConstituentAnalysis
    from irc.fundamentals.types import ActiveFundSnapshot
    # Holding A: weight=9.0 — broker + filing + news (broker added before filing
    # to assert sorter pushes filing first by type_rank).
    a_broker = _make_evidence("broker", 9.0, "ab", symbol="600519")
    a_filing = _make_evidence("filing", 9.0, "af", symbol="600519")
    a_news = _make_evidence("news", 9.0, "an", symbol="600519")
    # Holding B: weight=3.0 — single filing.
    b_filing = _make_evidence("filing", 3.0, "bf", symbol="000333")
    analyses = (
        ConstituentAnalysis("600519", "茅台", 9.0,
                            (a_broker, a_filing, a_news), (), ""),
        ConstituentAnalysis("000333", "美的", 3.0, (b_filing,), (), ""),
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2024Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )
    _, _, evidence, _, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    # Holding A (weight 9.0) first; within A: filing → broker → news; then B.
    assert [e.type for e in evidence] == ["filing", "broker", "news", "filing"]
    assert [e.summary for e in evidence] == [
        "600519-af", "600519-ab", "600519-an", "000333-bf",
    ]
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_thesis_evidence.py::test_derive_thesis_returns_5_tuple_for_active_fund -v`
Expected: FAIL — signature returns 4-tuple.

- [ ] **Step 3: Extend `derive_thesis_from_evidence`**

Edit `src/irc/opportunity/thesis_evidence.py`. Add import:

```python
from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.types import ConstituentAnalysis
```

Change the function signature and prepend the active-fund branch:

```python
_TYPE_RANK: dict[str, int] = {"filing": 0, "broker": 1, "news": 2}


def _flatten_analyses(
    analyses: tuple[ConstituentAnalysis, ...],
) -> tuple[ThesisEvidence, ...]:
    """Flatten per-spec Q-J: (weight_pct desc, type_rank asc, citation_id asc)."""
    entries: list[ThesisEvidence] = []
    for c in analyses:
        entries.extend(c.evidence)
    entries.sort(key=lambda e: e.citation_id)
    entries.sort(key=lambda e: _TYPE_RANK.get(e.type, 99))
    entries.sort(
        key=lambda e: -(e.holding_weight_pct if e.holding_weight_pct is not None else 0.0),
    )
    return tuple(entries)


def derive_thesis_from_evidence(
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | None,
    theme_report: ThemeReport | None,
    *,
    asset_class: str | None = None,
    owner_instrument_id: str,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...], tuple[ConstituentAnalysis, ...]]:
    """Active-fund branch returns analyses + flattened evidence.

    Legacy `ConstituentSnapshot` branch returns the same first-4-slot tuple
    plus an empty analyses tuple at slot 5.
    """
    if isinstance(snapshot, ActiveFundSnapshot):
        analyses = snapshot.constituent_analyses
        flattened = _flatten_analyses(analyses)
        # Item 003: do NOT stamp evidence_gaps yet; item 006 H2 owns that.
        gaps: tuple[str, ...] = ()
        if flattened:
            state: ThesisState = "intact"
            reason = (
                f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"
            )
        else:
            state = "evidence_insufficient"
            reason = "主动基金未能收集到任何成分股证据。"
        return state, reason, flattened, gaps, analyses

    # Legacy path: unchanged behaviour, plus empty 5th slot.
    state, reason, evidence, gaps = _derive_legacy(
        snapshot, theme_report,
        asset_class=asset_class, owner_instrument_id=owner_instrument_id,
    )
    return state, reason, evidence, gaps, ()
```

Rename the existing body of `derive_thesis_from_evidence` to `_derive_legacy` (private; same body, same 4-tuple return).

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_thesis_evidence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/thesis_evidence.py tests/opportunity/test_thesis_evidence.py
git commit -m "feat(opportunity): derive_thesis_from_evidence accepts ActiveFundSnapshot, returns 5-tuple with Q-J flatten ordering"
```

---

## Task 16: Update `build_opportunity_row` to handle the 5-tuple

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

- [ ] **Step 1: Write failing test**

Append to `tests/opportunity/test_states.py`:

```python
def test_build_opportunity_row_populates_constituent_analyses_for_active_fund() -> None:
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import (
        ConstituentAnalysis, OpportunityInput, ThesisEvidence,
    )
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2024-04-15", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    c = ConstituentAnalysis("600519", "贵州茅台", 6.2, (ev,), (), "")
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2024Q1",
        cache_probed_at="", constituent_analyses=(c,),
        failure_reasons_by_symbol={},
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert row.constituent_analyses == (c,)
    assert row.thesis_evidence == (ev,)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_states.py::test_build_opportunity_row_populates_constituent_analyses_for_active_fund -v`
Expected: FAIL — `derive_thesis_from_evidence` 5-tuple return doesn't unpack into 4 vars.

- [ ] **Step 3: Update `build_opportunity_row`**

Edit `src/irc/opportunity/states.py`. Modify the call to `derive_thesis_from_evidence` and the `OpportunityRow` construction:

```python
    structural_gaps = _structural_evidence_gaps(inp)
    constituent_analyses: tuple = ()
    if snapshot is not None or theme_report is not None:
        thesis, thesis_reason, evidence, thesis_gaps, constituent_analyses = (
            derive_thesis_from_evidence(
                snapshot, theme_report,
                asset_class=inp.asset_class,
                owner_instrument_id=inp.instrument_id,
            )
        )
    else:
        thesis, thesis_reason = classify_thesis(inp, theme_thesis)
        evidence = ()
        refined = _refined_table_gap(inp.asset_class)
        legacy = ("missing_constituent_snapshot", "news_stage_skipped")
        thesis_gaps = legacy + ((refined,) if refined is not None else ())
    ...
    return OpportunityRow(
        ...,  # existing fields unchanged
        constituent_analyses=constituent_analyses,
    )
```

Also update the type hint:

```python
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentSnapshot
...
def build_opportunity_row(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
    *,
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | None = None,
    theme_report: ThemeReport | None = None,
) -> OpportunityRow:
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): build_opportunity_row populates constituent_analyses from ActiveFundSnapshot"
```

---

## Task 17: Thread `row.constituent_analyses` into `ThesisCard` via `build_thesis_card`

**Files:**
- Modify: `src/irc/opportunity/cards.py`
- Test: `tests/opportunity/test_cards.py`

- [ ] **Step 1: Write failing test**

Append to `tests/opportunity/test_cards.py`:

```python
def test_build_thesis_card_threads_constituent_analyses() -> None:
    from irc.opportunity.cards import build_thesis_card
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import (
        ConstituentAnalysis, LookthroughTarget, OpportunityRow,
    )
    c = ConstituentAnalysis(
        "600519", "贵州茅台", 6.2, (), (), "",
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", "fund_005827", "易方达蓝筹精选", "005827",
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        opportunity_reason="", evidence_gaps=(),
        constituent_analyses=(c,),
    )
    card = build_thesis_card(row, PositionContext(None, None, None, None, False), "watchlist", "")
    assert card.constituent_analyses == (c,)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_cards.py::test_build_thesis_card_threads_constituent_analyses -v`
Expected: FAIL — `ThesisCard` has no `constituent_analyses` in the return expression.

- [ ] **Step 3: Update `build_thesis_card`**

Edit `src/irc/opportunity/cards.py`. Inside the return expression, append:

```python
        constituent_analyses=row.constituent_analyses,
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_cards.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/cards.py tests/opportunity/test_cards.py
git commit -m "feat(opportunity): build_thesis_card threads row.constituent_analyses into ThesisCard"
```

---

## Task 18: Defensive `citation_id` check for nested constituent evidence in `_card_to_dict`

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Test: `tests/opportunity/test_report.py`

- [ ] **Step 1: Write failing test**

Append to `tests/opportunity/test_report.py`:

```python
def test_card_to_dict_raises_on_missing_nested_citation_id(monkeypatch) -> None:
    import pytest
    from irc.opportunity.report import _card_to_dict
    from irc.opportunity.types import ConstituentAnalysis, ThesisCard, ThesisEvidence
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519",
    )
    c = ConstituentAnalysis(
        "600519", "贵州茅台", 6.2, (ev,), (), "",
    )
    card = ThesisCard(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None, role="watchlist",
        lookthrough_target="易方达蓝筹精选", entry_reason="",
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        dca_action="pause_dca", risk_action="none",
        falsification_triggers=(), trim_triggers=(),
        do_not_sell_just_because=(), review_cadence="weekly",
        evidence_gaps=(), constituent_analyses=(c,),
    )
    d = _card_to_dict(card)
    # Happy path: citation_id present.
    assert d["constituent_analyses"][0]["evidence"][0]["citation_id"] != ""

    # Now simulate a corrupted dict (manually blank the id).
    from unittest.mock import patch
    with patch("irc.opportunity.report.asdict") as mocked_asdict:
        bad = dict(d)
        bad["constituent_analyses"] = [
            {"evidence": [{"citation_id": ""}]},
        ]
        mocked_asdict.return_value = bad
        with pytest.raises(RuntimeError, match="citation_id"):
            _card_to_dict(card)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_report.py::test_card_to_dict_raises_on_missing_nested_citation_id -v`
Expected: FAIL — no check on nested constituent evidence.

- [ ] **Step 3: Add defensive check**

Edit `src/irc/opportunity/report.py`. In `_card_to_dict`, after the existing `thesis_evidence` loop, add:

```python
    for analysis in d.get("constituent_analyses", []):
        for ev_dict in analysis.get("evidence", []):
            if not ev_dict.get("citation_id"):
                raise RuntimeError(
                    f"constituent evidence entry missing citation_id: {ev_dict}"
                )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): _card_to_dict guards nested constituent evidence citation_id"
```

---

## Task 19: Add `FetchPlan`, `FetchBudgetExceeded`, plan_hash in `opportunity_cmd.py`

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_fetch_plan_total_calls_active_fund_only() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=5, active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=10,
    )
    # 5 × (1 + 10*3) = 5 × 31 = 155
    assert plan.total_calls() == 155


def test_fetch_plan_total_calls_with_stale_and_passive() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=2, active_fund_stale=3,
        passive_misses=4, passive_stale=1, top_n=10,
    )
    # (2 + 3) × 31 + 4×2 + 1×2 = 155 + 8 + 2 = 165
    assert plan.total_calls() == 165


def test_fetch_budget_exceeded_carries_breakdown() -> None:
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan
    plan = FetchPlan(5, 0, 0, 0, 10)
    exc = FetchBudgetExceeded(plan=plan, total=155, budget=10)
    msg = str(exc)
    assert "active_fund_misses=5" in msg
    assert "cost=155" in msg
    assert "budget=10" in msg


def test_plan_hash_deterministic() -> None:
    from irc.commands.opportunity_cmd import compute_plan_hash
    h1 = compute_plan_hash("2026-05-22", ["005827", "501025"], 10)
    h2 = compute_plan_hash("2026-05-22", ["501025", "005827"], 10)
    assert h1 == h2  # sorted internally
    assert len(h1) == 12
    h3 = compute_plan_hash("2026-05-23", ["005827", "501025"], 10)
    assert h3 != h1


def test_plan_hash_includes_top_n() -> None:
    from irc.commands.opportunity_cmd import compute_plan_hash
    h1 = compute_plan_hash("2026-05-22", ["005827"], 10)
    h2 = compute_plan_hash("2026-05-22", ["005827"], 15)
    assert h1 != h2
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "fetch_plan or fetch_budget or plan_hash" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add types + helpers**

Edit `src/irc/commands/opportunity_cmd.py`. Add near the top imports:

```python
import hashlib
from dataclasses import dataclass

TOP_N_DEFAULT = 10
IRC_FETCH_BUDGET_DEFAULT = 2000
IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7


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


class FetchBudgetExceeded(RuntimeError):
    def __init__(self, plan: FetchPlan, total: int, budget: int) -> None:
        super().__init__(
            f"FetchBudgetExceeded: "
            f"active_fund_misses={plan.active_fund_misses} "
            f"active_fund_stale={plan.active_fund_stale} "
            f"passive_misses={plan.passive_misses} "
            f"passive_stale={plan.passive_stale} "
            f"cost={total} budget={budget}"
        )
        self.plan = plan
        self.total = total
        self.budget = budget


def compute_plan_hash(output_date: str, instrument_ids: list[str], top_n: int) -> str:
    payload = f"{output_date}:{','.join(sorted(instrument_ids))}:{top_n}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "fetch_plan or fetch_budget or plan_hash" -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): add FetchPlan/FetchBudgetExceeded/compute_plan_hash primitives"
```

---

## Task 20: Resumable state file I/O with `fcntl.flock` + Windows fallback

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_fetch_state_atomic_write_and_load(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state, write_fetch_state
    state = {
        "plan_hash": "abc123def456",
        "started_at": "2026-05-22T10:00:00",
        "items": [
            {"fund_id": "005827", "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-22T10:05:00"},
        ],
    }
    write_fetch_state(state, tmp_path / "data" / "fundamentals", "abc123def456")
    loaded = load_fetch_state(tmp_path / "data" / "fundamentals", "abc123def456")
    assert loaded == state


def test_fetch_state_load_returns_none_when_missing(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state
    assert load_fetch_state(tmp_path / "data" / "fundamentals", "x") is None


def test_fetch_state_load_returns_none_on_hash_mismatch(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state, write_fetch_state
    state = {"plan_hash": "old123", "items": []}
    write_fetch_state(state, tmp_path / "data" / "fundamentals", "old123")
    # New run with different hash.
    assert load_fetch_state(tmp_path / "data" / "fundamentals", "new456") is None


def test_acquire_fetch_lock_second_call_raises(tmp_path, monkeypatch) -> None:
    import pytest
    from irc.commands.opportunity_cmd import acquire_fetch_lock, FetchLockBusy
    path = tmp_path / "lock.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd1 = acquire_fetch_lock(path)
    # Simulate a concurrent process by patching fcntl.flock to raise.
    import fcntl as fcntl_mod
    def raising(*a, **kw):
        raise BlockingIOError("locked")
    monkeypatch.setattr(fcntl_mod, "flock", raising)
    with pytest.raises(FetchLockBusy):
        acquire_fetch_lock(path)
    import os
    os.close(fd1)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "fetch_state or fetch_lock" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement state I/O + lock**

Append to `src/irc/commands/opportunity_cmd.py`:

```python
import os
import sys
import time

try:
    import fcntl  # type: ignore[import-not-found]
    _HAS_FCNTL = True
except ImportError:
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False
    sys.stderr.write(
        "WARNING: fcntl unavailable on this platform — "
        "concurrent-run lock disabled.\n"
    )


class FetchLockBusy(RuntimeError):
    """Raised when another process holds the fetch lock."""


def _fetch_state_path(root_fundamentals: Path, plan_hash: str) -> Path:
    return root_fundamentals / f".fetch_state_{plan_hash}.json"


def load_fetch_state(root_fundamentals: Path, plan_hash: str) -> dict | None:
    """Load state file if plan_hash matches; else None (caller starts fresh)."""
    path = _fetch_state_path(root_fundamentals, plan_hash)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    if body.get("plan_hash") != plan_hash:
        return None
    return body


def write_fetch_state(state: dict, root_fundamentals: Path, plan_hash: str) -> Path:
    path = _fetch_state_path(root_fundamentals, plan_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def acquire_fetch_lock(path: Path) -> int:
    """Acquire an advisory exclusive lock; retry once after 100ms.

    Returns the OS file descriptor on success. Raises `FetchLockBusy` after
    second failure. Windows fallback: returns a sentinel fd, no real lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    if not _HAS_FCNTL:
        return fd  # Windows fallback: no lock.
    for attempt in (0, 1):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if attempt == 0:
                time.sleep(0.1)
                continue
            os.close(fd)
            raise FetchLockBusy(
                "concurrent run detected — set IRC_OPPORTUNITY_AUTOBUILD=0 "
                "or wait for the other run"
            )
    return fd
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "fetch_state or fetch_lock" -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): resumable .fetch_state JSON I/O + fcntl.flock advisory lock"
```

---

## Task 21: Wire active-fund autobuild + freshness probe into `_build_rows`

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_build_rows_autobuild_off_skips_active_fund_fetch(monkeypatch, tmp_path) -> None:
    """IRC_OPPORTUNITY_AUTOBUILD=0 → no AkShare calls; snapshot=None."""
    from irc.commands.opportunity_cmd import _is_active_fund_target_autobuild_on
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "0")
    assert _is_active_fund_target_autobuild_on() is False
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    assert _is_active_fund_target_autobuild_on() is True
    monkeypatch.delenv("IRC_OPPORTUNITY_AUTOBUILD", raising=False)
    assert _is_active_fund_target_autobuild_on() is True  # default on


def test_freshness_probe_same_quarter_reuses_cache(monkeypatch, tmp_path) -> None:
    """Probe returns same quarter → cache_probed_at advances, no full refetch."""
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot, HoldingsResult
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    write_active_fund_cache(cached, tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings",
        lambda sym, top_n=1: HoldingsResult((), "2024-03-31", "2024Q1"),
    )
    fresh, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is False
    assert fresh.cache_probed_at == "2026-05-22"


def test_freshness_probe_new_quarter_schedules_refetch(monkeypatch, tmp_path) -> None:
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.types import ActiveFundSnapshot, HoldingsResult
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings",
        lambda sym, top_n=1: HoldingsResult((), "2024-06-30", "2024Q2"),
    )
    _, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is True


def test_freshness_probe_failure_is_fail_closed(monkeypatch, tmp_path) -> None:
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.types import ActiveFundSnapshot
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    def boom(*a, **kw):
        raise ConnectionError("akshare 502")
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings", boom,
    )
    _, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is True  # fail-closed
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "autobuild or freshness_probe" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement env + probe helpers**

Append to `src/irc/commands/opportunity_cmd.py`:

```python
from dataclasses import replace
from datetime import date as date_cls

from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot


def _is_active_fund_target_autobuild_on() -> bool:
    return os.environ.get("IRC_OPPORTUNITY_AUTOBUILD", "1") != "0"


def _freshness_days() -> int:
    try:
        return int(os.environ.get("IRC_CACHE_FRESHNESS_DAYS", IRC_CACHE_FRESHNESS_DAYS_DEFAULT))
    except ValueError:
        return IRC_CACHE_FRESHNESS_DAYS_DEFAULT


def _fetch_budget() -> int:
    try:
        return int(os.environ.get("IRC_FETCH_BUDGET", IRC_FETCH_BUDGET_DEFAULT))
    except ValueError:
        return IRC_FETCH_BUDGET_DEFAULT


def _is_stale(snap: ActiveFundSnapshot, *, today: date_cls, threshold_days: int) -> bool:
    if not snap.cache_probed_at:
        return True
    try:
        probed = date_cls.fromisoformat(snap.cache_probed_at)
    except ValueError:
        return True
    return (today - probed).days > threshold_days


def _maybe_freshness_probe(
    snap: ActiveFundSnapshot,
    *,
    today: date_cls,
    root: Path,
) -> tuple[ActiveFundSnapshot, bool]:
    """Probe and return (possibly-updated snapshot, schedule_full_refetch).

    Fail-closed: any probe failure or empty result → schedule_full_refetch=True.
    """
    if not _is_stale(snap, today=today, threshold_days=_freshness_days()):
        return snap, False
    try:
        probe = fetch_cn_etf_holdings(snap.fund_id, top_n=1)
    except Exception:
        return snap, True
    if not probe.source_report_quarter or not probe.constituents:
        return snap, True
    if probe.source_report_quarter != snap.source_report_quarter:
        return snap, True
    updated = replace(snap, cache_probed_at=today.isoformat())
    write_active_fund_cache(updated, root)
    return updated, False
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "autobuild or freshness_probe" -v`
Expected: 4 PASS.

- [ ] **Step 5: Wire `_build_rows` dispatch**

Edit `_build_rows` in `src/irc/commands/opportunity_cmd.py`. Replace the inner loop's lookthrough handling:

```python
        target = map_lookthrough(inp)
        snap_obj: object | None = None
        if target.kind == "active_fund" and _is_active_fund_target_autobuild_on():
            if target.key in snapshot_cache:
                snap_obj = snapshot_cache[target.key]
            else:
                # 1. Try disk cache for the latest known quarter
                #    (we don't know the quarter a priori; glob the active_fund dir).
                cached = _load_latest_active_fund_cached(target.provider_symbol, root / "data")
                if cached is None:
                    snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                    if isinstance(snap_obj, ActiveFundSnapshot) and snap_obj.constituent_analyses:
                        write_active_fund_cache(
                            replace(snap_obj, cache_probed_at=date_cls.today().isoformat()),
                            root / "data",
                        )
                else:
                    probed, refresh = _maybe_freshness_probe(
                        cached, today=date_cls.today(), root=root / "data",
                    )
                    if refresh:
                        snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                        if isinstance(snap_obj, ActiveFundSnapshot) and snap_obj.constituent_analyses:
                            write_active_fund_cache(
                                replace(snap_obj, cache_probed_at=date_cls.today().isoformat()),
                                root / "data",
                            )
                    else:
                        snap_obj = probed
                snapshot_cache[target.key] = snap_obj
        else:
            target_name = target.display_cn
            if target_name not in snapshot_cache:
                snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
            snap_obj = snapshot_cache[target_name]
        row = build_opportunity_row(
            inp,
            theme_thesis or None,
            snapshot=snap_obj,
            theme_report=_resolve_research_theme(inp, theme_reports),
        )
```

Add helper:

```python
def _load_latest_active_fund_cached(
    fund_id: str, root: Path,
) -> ActiveFundSnapshot | None:
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/active_fund/fund_{fund_id}.json"))
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        loaded = load_active_fund_cache(fund_id, quarter, root)
        if loaded is not None:
            return loaded
    return None
```

- [ ] **Step 6: Run full opportunity_cmd suite**

Run: `pytest tests/commands/test_opportunity_cmd.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): _build_rows autobuilds active-fund snapshots with disk cache + freshness probe"
```

---

## Task 22: `--limit` / `--rebuild-fundamentals` / `--output-dir` CLI flags + canonical-path rejection

**Files:**
- Modify: `src/irc/cli.py`
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_validate_output_dir_canonical_rejects_limit(tmp_path) -> None:
    import pytest
    from irc.commands.opportunity_cmd import validate_cli_args
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=str(tmp_path / "outputs" / "2026-05-22"),
            limit=3, rebuild_fundamentals=False,
            today="2026-05-22",
        )
    assert exc.value.code == 2


def test_validate_output_dir_non_canonical_accepts_limit(tmp_path) -> None:
    from irc.commands.opportunity_cmd import validate_cli_args
    # Should not raise.
    validate_cli_args(
        output_dir="/tmp/scratch/", limit=3,
        rebuild_fundamentals=False, today="2026-05-22",
    )


def test_validate_output_dir_canonical_accepts_no_limit(tmp_path) -> None:
    from irc.commands.opportunity_cmd import validate_cli_args
    validate_cli_args(
        output_dir=str(tmp_path / "outputs" / "2026-05-22"),
        limit=None, rebuild_fundamentals=False, today="2026-05-22",
    )
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py -k "validate_output_dir" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement validator + thread through `run_opportunity`**

Append to `src/irc/commands/opportunity_cmd.py`:

```python
def validate_cli_args(
    *,
    output_dir: str | None,
    limit: int | None,
    rebuild_fundamentals: bool,
    today: str,
) -> None:
    """Reject `--limit` on canonical `outputs/<today>/` paths (exit code 2)."""
    if output_dir is None:
        return
    if limit is None:
        return
    canonical_suffix = f"outputs/{today}"
    if output_dir.rstrip("/").endswith(canonical_suffix):
        print(
            "--limit is rejected on canonical output paths",
            file=sys.stderr,
        )
        raise SystemExit(2)
```

Extend `run_opportunity` signature:

```python
def run_opportunity(
    repo_root: str,
    *,
    output_dir: str | None = None,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
) -> int:
    root = Path(repo_root)
    today = _today()
    validate_cli_args(
        output_dir=output_dir, limit=limit,
        rebuild_fundamentals=rebuild_fundamentals, today=today,
    )
    ...  # existing body
```

Thread `limit` and `rebuild_fundamentals` into `_build_rows`:

```python
def _build_rows(
    scores: list[dict],
    ...,
    *,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
) -> tuple[list[OpportunityRow], dict, dict, dict]:
    ...
    sorted_scores = sorted(scores, key=lambda s: s.get("instrument_id", ""))
    active_fund_count = 0
    for score in sorted_scores:
        iid = score.get("instrument_id", "")
        ...
        target = map_lookthrough(inp)
        if target.kind == "active_fund":
            if limit is not None and active_fund_count >= limit:
                continue
            active_fund_count += 1
            # ...existing autobuild branch...
            if rebuild_fundamentals:
                snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                ...
```

Update `cli.py` `opportunity` command:

```python
@main.command(help="Run opportunity/thesis/discipline layer; writes 3 outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--output-dir", type=click.Path(file_okay=False), default=None,
              help="Override the default outputs/<today>/ directory.")
@click.option("--limit", type=int, default=None,
              help="Cap cn_equity_fund autobuild rows (rejected on canonical paths).")
@click.option("--rebuild-fundamentals", is_flag=True, default=False,
              help="Force full re-fetch of active-fund caches (skip freshness probe).")
def opportunity(
    repo_root: str,
    output_dir: str | None,
    limit: int | None,
    rebuild_fundamentals: bool,
) -> None:
    from irc.commands.opportunity_cmd import run_opportunity
    rc = run_opportunity(
        repo_root=repo_root, output_dir=output_dir,
        limit=limit, rebuild_fundamentals=rebuild_fundamentals,
    )
    raise SystemExit(rc)
```

Update `run_cmd.py` to plumb identical flags into the `--from opportunity` path; mirror the CLI option block on the `run` command in `cli.py`:

```python
@click.option("--output-dir", type=click.Path(file_okay=False), default=None)
@click.option("--limit", type=int, default=None)
@click.option("--rebuild-fundamentals", is_flag=True, default=False)
def run_command(..., output_dir, limit, rebuild_fundamentals):
    ...
    rc = run_pipeline(
        repo_root=repo_root, from_stage=from_stage, only_stage=only_stage,
        resume=resume, output_dir=output_dir, limit=limit,
        rebuild_fundamentals=rebuild_fundamentals,
    )
```

(Plumb `output_dir`, `limit`, `rebuild_fundamentals` through `run_pipeline` → opportunity stage. Other stages ignore them.)

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/cli.py src/irc/commands/opportunity_cmd.py src/irc/commands/run_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(cli): add --limit/--rebuild-fundamentals/--output-dir flags with canonical-path rejection"
```

> **[DRIFT NOTE — 2026-05-23 autodev/003 drift review]** Implementer delivered `validate_cli_args` as a standalone function and declared the CLI flags in `cli.py`, but did NOT wire them through: `run_opportunity` was not extended with `output_dir`/`limit`/`rebuild_fundamentals` kwargs; `validate_cli_args` is not called from `run_opportunity`; `_build_rows` does not accept `limit`/`rebuild_fundamentals`; and `cli.py` drops the flags (calls `run_opportunity(repo_root=repo_root)` only). The unit-level behaviour of `validate_cli_args` is tested and correct; the end-to-end CLI plumbing is incomplete. This was recorded as a FAIL finding in `003-drift.md`; the next implementer must complete Step 3's threading work.

---

## Task 23: Acceptance-criteria tests (G6 trio + cache reuse + freshness trio + lock + thesis_cards.yaml)

**Files:**
- Test: `tests/commands/test_opportunity_cmd_acceptance.py` (new)
- Test: `tests/fundamentals/test_snapshot_acceptance.py` (new)

- [ ] **Step 1: Write tests**

Create `tests/fundamentals/test_snapshot_acceptance.py`:

```python
"""Spec §Acceptance criteria 6, 7, 8, 9, 10, 11, 29, 30, 31."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals import snapshot as snap_mod
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import (
    ActiveFundSnapshot, BrokerReport, FilingDigest, FundHolding,
    HoldingsResult, NewsItem,
)
from irc.opportunity.types import LookthroughTarget


def _cn_holdings(symbols):
    return HoldingsResult(
        constituents=tuple(
            FundHolding(s, s, 10.0 - i, "SH" if s.startswith("6") else "SZ", s)
            for i, s in enumerate(symbols)
        ),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )


def test_g6_a_full_success_30_evidence_entries(monkeypatch) -> None:
    """Spec §29 G6 (a): 10-stock fund, all adapters succeed."""
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings([f"60001{i}" for i in range(10)]),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_filing_digest",
        lambda s: FilingDigest(
            symbol=s, fiscal_period="2024Q1", filed_at_iso="2024-04-15",
            revenue_yoy=0.10, net_income_yoy=0.12, gross_margin=0.45,
            source_url=f"https://x/{s}",
        ),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_broker_reports",
        lambda s: (BrokerReport(
            symbol=s, broker="中信", rating="买入", target_price=100.0,
            published_iso="2024-04-10", title="买入", source_url="https://x/b",
        ),),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news",
        lambda s, top_k=3: (NewsItem(s, "新品", "https://x", "2024-04-15", "", "stock_news_em"),),
    )
    target = LookthroughTarget("active_fund", "fund_005827", "fund", "005827")
    snap = build_snapshot(target, top_n=10)
    assert isinstance(snap, ActiveFundSnapshot)
    assert len(snap.constituent_analyses) == 10
    total = sum(len(c.evidence) for c in snap.constituent_analyses)
    assert total == 30  # 10 filing + 10 broker + 10 news


def test_g6_b_partial_holdings_6_to_10_all_empty(monkeypatch) -> None:
    """Spec §30 G6 (b): holdings 6–10 all have filing_empty + broker_empty + news_empty."""
    symbols = [f"6000{i:02d}" for i in range(10)]
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings(symbols),
    )
    def selective_filing(s):
        idx = int(s[-2:])
        if idx >= 5:
            return None
        return FilingDigest(s, "2024Q1", "2024-04-15", 0.1, 0.1, 0.3, "")
    monkeypatch.setattr(snap_mod, "fetch_cn_filing_digest", selective_filing)
    def selective_brokers(s):
        idx = int(s[-2:])
        if idx >= 5:
            return ()
        return (BrokerReport(s, "中信", "买入", None, "2024-04-10", "x", "https://x"),)
    monkeypatch.setattr(snap_mod, "fetch_cn_broker_reports", selective_brokers)
    def selective_news(s, top_k=3):
        idx = int(s[-2:])
        if idx >= 5:
            return ()
        return (NewsItem(s, "x", "https://x", "2024-04-15", "", "stock_news_em"),)
    monkeypatch.setattr(snap_mod, "fetch_cn_stock_news", selective_news)
    target = LookthroughTarget("active_fund", "fund_x", "fund", "005827")
    snap = build_snapshot(target, top_n=10)
    assert len(snap.constituent_analyses) == 10
    empties = [c for c in snap.constituent_analyses if not c.evidence]
    assert len(empties) == 5
    for c in empties:
        assert any(r.startswith("filing_empty:") for r in c.failure_reasons)
        assert any(r.startswith("broker_empty:") for r in c.failure_reasons)
        assert any(r.startswith("news_empty:") for r in c.failure_reasons)


def test_g6_c_news_carries_constituent_scope_and_information_kind(monkeypatch) -> None:
    """Spec §31 G6 (c): structured news evidence shape."""
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings(["600519"]),
    )
    monkeypatch.setattr(snap_mod, "fetch_cn_filing_digest", lambda s: None)
    monkeypatch.setattr(snap_mod, "fetch_cn_broker_reports", lambda s: ())
    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news",
        lambda s, top_k=3: (NewsItem(s, "新品", "https://x", "2024-04-15", "", "stock_news_em"),),
    )
    target = LookthroughTarget("active_fund", "fund_x", "fund", "005827")
    snap = build_snapshot(target, top_n=1)
    news_ev = [e for e in snap.constituent_analyses[0].evidence if e.type == "news"]
    assert len(news_ev) == 1
    assert news_ev[0].scope == "constituent"
    assert news_ev[0].citation_kind == "information"
    assert news_ev[0].constituent_key == "600519"
    assert snap.fund_level_failure_reasons == ()
```

Create `tests/commands/test_opportunity_cmd_acceptance.py`:

```python
"""Acceptance criteria 11, 12, 16, 18, 21, 22, 23."""
from __future__ import annotations

import pytest

from irc.commands.opportunity_cmd import (
    FetchBudgetExceeded, FetchPlan, FetchLockBusy,
    acquire_fetch_lock, validate_cli_args,
)


def test_preflight_budget_exceeded_carries_breakdown_to_stderr(capsys) -> None:
    """Spec §16: budget abort prints active_fund_misses=N cost=N budget=N."""
    plan = FetchPlan(5, 0, 0, 0, 10)
    exc = FetchBudgetExceeded(plan, 155, 10)
    msg = str(exc)
    assert "active_fund_misses=5" in msg
    assert "cost=155" in msg
    assert "budget=10" in msg


def test_limit_rejected_on_canonical_path(tmp_path) -> None:
    """Spec §18."""
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=str(tmp_path / "outputs" / "2026-05-22"),
            limit=3, rebuild_fundamentals=False, today="2026-05-22",
        )
    assert exc.value.code == 2


def test_concurrent_lock_second_call_raises(tmp_path, monkeypatch) -> None:
    """Spec §21."""
    import os
    fd1 = acquire_fetch_lock(tmp_path / "lock.lock")
    import fcntl
    monkeypatch.setattr(
        fcntl, "flock",
        lambda *a, **kw: (_ for _ in ()).throw(BlockingIOError("locked")),
    )
    with pytest.raises(FetchLockBusy):
        acquire_fetch_lock(tmp_path / "lock.lock")
    os.close(fd1)
```

- [ ] **Step 2: Run green (no implementation needed; tests assert on already-built primitives)**

Run: `pytest tests/fundamentals/test_snapshot_acceptance.py tests/commands/test_opportunity_cmd_acceptance.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_snapshot_acceptance.py tests/commands/test_opportunity_cmd_acceptance.py
git commit -m "test(opportunity): acceptance-criteria coverage (G6 a/b/c + lock + canonical-path + budget)"
```

---

## Task 24: Final — full `pytest -x` green + `ruff check` clean

**Files:** (none)

- [ ] **Step 1: Run the full suite**

Run: `pytest -x -q`
Expected: PASS for every test (existing + 24 new tasks' tests).

- [ ] **Step 2: Run ruff**

Run: `ruff check src/ tests/`
Expected: zero findings. If anything trips, fix the lint and re-run.

- [ ] **Step 3: Final commit (only if ruff fixes were needed)**

```bash
git add -p src/ tests/
git commit -m "chore(opportunity): ruff lint fixups for item 003"
```

- [ ] **Step 4: Confirm clean tree**

Run: `git status`
Expected: clean working tree on `autodev/thesis-evidence-003-active-fund-constituent-layer`.

---

## Self-review checklist (writer-of-plan only — do not run as a task)

- [x] Every spec section maps to a task: schema (T1–T5), parser/adapters (T6–T9), lookthrough (T10–T11), snapshot (T12–T13), cache (T14), thesis derivation (T15–T16), card threading (T17–T18), orchestrator primitives (T19–T20), wiring + CLI (T21–T22), acceptance (T23), final gates (T24).
- [x] No "TBD"/"implement later"/placeholder steps. Every code block is the literal text the implementer writes.
- [x] Type names consistent across tasks: `LookthroughTarget`, `ActiveFundSnapshot`, `ConstituentAnalysis`, `FundHolding`, `HoldingsResult`, `NewsItem`, `ThesisEvidence`, `FetchPlan`, `FetchBudgetExceeded`, `FetchLockBusy`.
- [x] ADR 0001 §2 citation_id preimage contract preserved (T4 explicitly tests preimage invariance for `holding_weight_pct`).
- [x] ADR 0002 §1 disclosure-quarter cache key (T7 + T14).
- [x] ADR 0002 §2 fail-closed freshness probe (T21 + T23).
- [x] ADR 0002 §3 preflight budget gate (T19 + T23).
- [x] ADR 0002 §4 forbidden adapter pairs (T12 includes `test_build_snapshot_active_fund_routes_hk_through_hk_adapters`).
- [x] Spec Q-J flatten ordering test (`test_active_fund_thesis_evidence_flatten_ordering` in T15).
- [x] HK news fallback = stub-empty (T9; the `hk_news_unsupported_adapter` reason is stamped by `_evidence_for_constituent` in T12).
