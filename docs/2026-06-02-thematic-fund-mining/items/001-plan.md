# `irc narrative` — Thematic Fund Mining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `irc narrative <name>` — a narrative-driven fund selector that resolves a curated stock basket to a ranked fund shortlist by holdings look-through, then (opt-in) runs the existing opportunity-grade per-fund analysis and emits a new prospective-buy `position_risk_level`.

**Architecture:** A new pure-core package `src/irc/narrative/` (schemas / screen / risk / report) plus three I/O edges (`holdings_fetch`, `config`, `analyze`), orchestrated by a thin `commands/narrative_cmd.py` and wired as a top-level Click command. The selector sits **in front of** and **reuses** the existing classification cores — untouched: `enumerate_universe`, `_build_input` → `build_opportunity_row` → `build_thesis_card` (→ `derive_dca_action` + `derive_risk_action`) → `derive_thesis_from_evidence`, plus the snapshot cache. New logic is confined to holdings-overlap scoring, the narrative config, and `derive_position_risk_level`.

**Tech Stack:** Python 3.12+, uv, Click, AkShare (`fund_portfolio_hold_em`), pydantic/frozen dataclasses, pytest. All cores are pure and unit-testable without mocks; effects live only at the three edges.

---

## Conventions baked into every task (from CLAUDE.md + spec)

- **TDD strictly:** the failing test is always written and run-to-fail BEFORE the implementation file. Red → green → refactor.
- **Functional / immutable:** every new type is `@dataclass(frozen=True)`; build new values via `dataclasses.replace` / spread; never mutate arguments; no module-global mutable state.
- **Effects at edges:** `schemas.py` / `screen.py` / `risk.py` / `report.py` are pure (no I/O, no logging, no wall-clock, no random — timestamps injected as a parameter). `holdings_fetch.py` / `config.py` / `analyze.py` / `narrative_cmd.py` own all I/O. (`analyze.py`'s projection helpers `_risk_view_from_row` / `_report_from_card` are themselves pure and unit-tested without DuckDB; only `analyze_fund` touches the cache.)
- **Size budget:** every new file < 200 lines, functions < 20 lines (ideal). Extract helpers, use early returns, ≤ 3 nesting levels.
- **Determinism:** the shortlist sort key is `(basket_weight_pct DESC, overlap_count DESC, instrument_id ASC)`. Citation IDs keep the locked 16-hex `[ref:...]` format (`\[ref:[0-9a-f]{16}\]`). Same inputs ⇒ byte-identical outputs.
- **Reuse contract — DO NOT MODIFY:** `enumerate_universe`, `_build_input`, `build_opportunity_row`, `build_thesis_card`, `derive_dca_action`, `derive_risk_action`, `derive_thesis_from_evidence`, `select_citations`, the snapshot cache (`load_active_fund_cache`), `fund_eval_cmd._instr_by_id`/`_latest_quarter`, or any existing output (`eval-funds`, `discover`, `score`, `opportunity`). The narrative code only IMPORTS and CALLS these.
- **Forbidden literal:** the string `基金概况` MUST NOT appear anywhere under `src/irc/narrative/` (acceptance grep). Holdings come only from `fund_portfolio_hold_em`.
- **No silent caps:** funds with no published holdings are written to `<name>_screen_diagnostics.json` with a reason — never dropped.

## File structure (created / modified)

| Path | Created/Modified | Responsibility | Purity |
|---|---|---|---|
| `src/irc/narrative/__init__.py` | Create | package marker (empty) | — |
| `src/irc/narrative/schemas.py` | Create | frozen types: `BasketStock`, `NarrativeBasket`, `Holding`, `OverlapResult`, `ShortlistRow`, `RiskLevel`, `NarrativeFundReport` | frozen types |
| `src/irc/narrative/screen.py` | Create | `score_overlap`, `rank_shortlist` | **pure** |
| `src/irc/narrative/risk.py` | Create | `derive_position_risk_level` | **pure** |
| `src/irc/narrative/report.py` | Create | `render_shortlist_md/json`, `render_report_md/json` (emits real `[ref:...]` via `select_citations`), `render_diagnostics_json` | **pure** |
| `src/irc/narrative/holdings_fetch.py` | Create | `fetch_top_holdings(fund_id, *, cache_dir)` (AkShare + on-disk cache) | I/O edge |
| `src/irc/narrative/config.py` | Create | `load_narrative_basket`, `available_narratives` | I/O edge |
| `src/irc/narrative/analyze.py` | Create | `analyze_fund` (DuckDB→`_build_input`→`build_opportunity_row`→`build_thesis_card`→`derive_position_risk_level`) + pure projection helpers | I/O edge |
| `src/irc/commands/narrative_cmd.py` | Create | orchestration: load → screen → (open-db → analyze_fund) → render → write | I/O edge |
| `src/irc/cli.py` | Modify (add `@main.command`) | register `irc narrative` | I/O edge |
| `config/narratives/compute_metals.yaml` | Create | DRAFT seeded `compute_metals` basket (user-approval, then frozen) | data |
| `tests/narrative/__init__.py` | Create | test package marker | — |
| `tests/narrative/test_schemas.py` | Create | frozen-type construction | test |
| `tests/narrative/test_screen.py` | Create | `score_overlap` / `rank_shortlist` (richest) | test |
| `tests/narrative/test_risk.py` | Create | `derive_position_risk_level` per driver | test |
| `tests/narrative/test_report.py` | Create | renderer md/json shape + citation regex | test |
| `tests/narrative/test_config.py` | Create | YAML → `NarrativeBasket`, malformed rejection | test |
| `tests/narrative/test_holdings_fetch.py` | Create | edge: cache hit/miss (mocked `_ak_call`) + live (double-gated) | test |
| `tests/narrative/test_analyze.py` | Create | analyze: real `OpportunityRow`→`ThesisCard`→risk projection + monkeypatched DuckDB wiring | test |
| `tests/narrative/test_narrative_cmd.py` | Create | integration: fixture universe → shortlist + diagnostics; `--analyze` renders real citations; missing-db guard; run-twice byte-equality | test |
| `tests/narrative/test_acceptance.py` | Create | forbidden-literal grep, citation regex on a real-evidence report, determinism | test |

---

## Task 1: Package skeleton + frozen schemas

**Files:**
- Create: `src/irc/narrative/__init__.py`
- Create: `src/irc/narrative/schemas.py`
- Create: `tests/narrative/__init__.py`
- Test: `tests/narrative/test_schemas.py`

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p src/irc/narrative tests/narrative config/narratives
: > src/irc/narrative/__init__.py
: > tests/narrative/__init__.py
```

- [ ] **Step 2: Write the failing schema test**

Create `tests/narrative/test_schemas.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from irc.narrative.schemas import (
    BasketStock,
    Holding,
    NarrativeBasket,
    NarrativeFundReport,
    OverlapResult,
    ShortlistRow,
)


def test_basket_stock_is_frozen() -> None:
    s = BasketStock(symbol="601899", name_cn="紫金矿业", metal="copper_gold")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.symbol = "000001"  # type: ignore[misc]


def test_narrative_basket_holds_stocks_and_thresholds() -> None:
    b = NarrativeBasket(
        narrative_id="compute_metals",
        display_name_cn="算力金属",
        display_name_en="Compute-demand metals",
        thesis_cn="AI 数据中心拉动铜铝锡需求",
        basket=(BasketStock(symbol="601899", name_cn="紫金矿业", metal="copper_gold"),),
        industries_sw=("有色金属/工业金属",),
        min_basket_weight_pct=15.0,
        min_overlap_count=2,
        top_n=15,
    )
    assert b.narrative_id == "compute_metals"
    assert b.basket[0].symbol == "601899"
    assert b.min_overlap_count == 2


def test_holding_and_overlap_and_shortlist_construct() -> None:
    h = Holding(symbol="601899", name_cn="紫金矿业", weight_pct=8.0, sw_industry="有色金属/工业金属")
    ov = OverlapResult(
        basket_weight_pct=8.0,
        overlap_count=1,
        matched_symbols=("601899",),
        industry_credit_symbols=(),
    )
    row = ShortlistRow(
        instrument_id="000123",
        name_cn="某有色基金",
        asset_class="cn_equity_fund",
        overlap=ov,
        holdings=(h,),
    )
    assert row.overlap.basket_weight_pct == 8.0
    assert row.holdings[0].weight_pct == 8.0


def test_narrative_fund_report_construct() -> None:
    rpt = NarrativeFundReport(
        instrument_id="000123",
        name_cn="某有色基金",
        position_risk_level="elevated",
        risk_rationale="elevated — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive",
        heat_state="overheated",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="small_watch",
        dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
        thesis_evidence=(),
    )
    assert rpt.position_risk_level == "elevated"
    assert rpt.risk_drivers == ("valuation_state",)
    assert rpt.opportunity_state == "small_watch"
    assert rpt.risk_action == "trim_review"
    assert rpt.thesis_evidence == ()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_schemas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.schemas'`.

- [ ] **Step 4: Write `src/irc/narrative/schemas.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from irc.fundamentals.types import ThesisEvidence
from irc.opportunity.types import (
    DcaAction,
    HeatState,
    OpportunityState,
    ProductQualityState,
    RiskAction,
    ThesisState,
    ValuationState,
)

RiskLevel = Literal["low", "moderate", "elevated", "high", "insufficient"]


@dataclass(frozen=True)
class BasketStock:
    """One stock that DEFINES a narrative."""
    symbol: str
    name_cn: str
    metal: str = ""


@dataclass(frozen=True)
class NarrativeBasket:
    """Curated, frozen reference basket loaded from config/narratives/<id>.yaml."""
    narrative_id: str
    display_name_cn: str
    display_name_en: str
    thesis_cn: str
    basket: tuple[BasketStock, ...]
    industries_sw: tuple[str, ...]
    min_basket_weight_pct: float
    min_overlap_count: int
    top_n: int


@dataclass(frozen=True)
class Holding:
    """One disclosed top-10 holding of a fund (percent units, 0.0–100.0)."""
    symbol: str
    name_cn: str
    weight_pct: float
    sw_industry: str = ""


@dataclass(frozen=True)
class OverlapResult:
    """Result of matching a fund's top-10 against a basket."""
    basket_weight_pct: float
    overlap_count: int
    matched_symbols: tuple[str, ...]
    industry_credit_symbols: tuple[str, ...]


@dataclass(frozen=True)
class ShortlistRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    overlap: OverlapResult
    holdings: tuple[Holding, ...]


@dataclass(frozen=True)
class NarrativeFundReport:
    """Per-fund analyze record. Carries the REAL OpportunityRow/ThesisCard state
    plus the prospective-buy risk level. `thesis_evidence` holds the ACTUAL
    `ThesisEvidence` objects (not a stringified projection) so the renderer can
    reuse `select_citations(thesis_evidence, cap=3)` and emit the locked
    `- [ref:{citation_id}] {type} · {source} · {date}` line."""
    instrument_id: str
    name_cn: str
    position_risk_level: RiskLevel
    risk_rationale: str
    risk_drivers: tuple[str, ...]
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    falsification_triggers: tuple[str, ...]
    trim_triggers: tuple[str, ...]
    review_cadence: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
```

> Note: `thesis_evidence` stays as the real frozen `ThesisEvidence` tuple (NOT a dict projection) — the renderer (Task 5) reuses `select_citations` + the `report.py` line format, which require the objects. `ThesisEvidence` is itself frozen and JSON-serialisable for `render_report_json` via its public fields.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_schemas.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/__init__.py src/irc/narrative/schemas.py \
        tests/narrative/__init__.py tests/narrative/test_schemas.py
git commit -m "feat(narrative): frozen schemas for thematic fund mining"
```

---

## Task 2: `score_overlap` (pure screen core)

**Files:**
- Create: `src/irc/narrative/screen.py`
- Test: `tests/narrative/test_screen.py`

- [ ] **Step 1: Write the failing `score_overlap` tests**

Create `tests/narrative/test_screen.py`:

```python
from __future__ import annotations

from irc.narrative.schemas import BasketStock, Holding, NarrativeBasket
from irc.narrative.screen import score_overlap


def _basket() -> NarrativeBasket:
    return NarrativeBasket(
        narrative_id="compute_metals",
        display_name_cn="算力金属",
        display_name_en="Compute-demand metals",
        thesis_cn="t",
        basket=(
            BasketStock(symbol="601899", name_cn="紫金矿业"),
            BasketStock(symbol="600362", name_cn="江西铜业"),
        ),
        industries_sw=("有色金属/工业金属",),
        min_basket_weight_pct=15.0,
        min_overlap_count=2,
        top_n=15,
    )


def test_symbol_match_sums_weight_and_counts() -> None:
    holdings = (
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0),
        Holding(symbol="600362", name_cn="江西铜业", weight_pct=6.0),
        Holding(symbol="600519", name_cn="贵州茅台", weight_pct=5.0),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.basket_weight_pct == 15.0
    assert ov.overlap_count == 2
    assert ov.matched_symbols == ("600362", "601899")  # sorted ASC


def test_name_match_when_symbol_differs() -> None:
    # symbol mismatch but name_cn matches a basket entry -> credited
    holdings = (Holding(symbol="999999", name_cn="紫金矿业", weight_pct=4.0),)
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.basket_weight_pct == 4.0


def test_industry_credit_for_non_basket_name() -> None:
    holdings = (
        Holding(symbol="000060", name_cn="中金岭南", weight_pct=3.0,
                sw_industry="有色金属/工业金属"),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.industry_credit_symbols == ("000060",)
    assert ov.basket_weight_pct == 3.0


def test_no_double_count_when_basket_and_industry_both_hit() -> None:
    holdings = (
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0,
                sw_industry="有色金属/工业金属"),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.basket_weight_pct == 9.0
    assert ov.industry_credit_symbols == ()  # basket match takes precedence


def test_empty_holdings_zero_overlap() -> None:
    ov = score_overlap((), _basket())
    assert ov.basket_weight_pct == 0.0
    assert ov.overlap_count == 0
    assert ov.matched_symbols == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_screen.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.screen'`.

- [ ] **Step 3: Write the `score_overlap` half of `src/irc/narrative/screen.py`**

```python
from __future__ import annotations

from irc.narrative.schemas import (
    Holding,
    NarrativeBasket,
    OverlapResult,
    ShortlistRow,
)


def _basket_hit(holding: Holding, basket: NarrativeBasket) -> bool:
    symbols = {s.symbol for s in basket.basket}
    names = {s.name_cn for s in basket.basket}
    return holding.symbol in symbols or holding.name_cn in names


def _industry_hit(holding: Holding, basket: NarrativeBasket) -> bool:
    return bool(holding.sw_industry) and holding.sw_industry in basket.industries_sw


def score_overlap(holdings: tuple[Holding, ...], basket: NarrativeBasket) -> OverlapResult:
    """Pure: match a fund's top-10 against the basket (symbol first, name second),
    crediting SW-industry membership for non-basket names. No double-count."""
    matched: list[str] = []
    industry_credit: list[str] = []
    weight = 0.0
    for h in holdings:
        if _basket_hit(h, basket):
            matched.append(h.symbol)
            weight += h.weight_pct
        elif _industry_hit(h, basket):
            industry_credit.append(h.symbol)
            weight += h.weight_pct
    return OverlapResult(
        basket_weight_pct=round(weight, 4),
        overlap_count=len(matched) + len(industry_credit),
        matched_symbols=tuple(sorted(matched)),
        industry_credit_symbols=tuple(sorted(industry_credit)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_screen.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/screen.py tests/narrative/test_screen.py
git commit -m "feat(narrative): score_overlap holdings look-through (pure)"
```

---

## Task 3: `rank_shortlist` (pure screen core)

**Files:**
- Modify: `src/irc/narrative/screen.py` (append `rank_shortlist`)
- Test: `tests/narrative/test_screen.py` (append)

- [ ] **Step 1: Append the failing `rank_shortlist` tests**

Append to `tests/narrative/test_screen.py`:

```python
from irc.narrative.schemas import OverlapResult, ShortlistRow
from irc.narrative.screen import rank_shortlist


def _row(iid: str, weight: float, count: int) -> ShortlistRow:
    ov = OverlapResult(
        basket_weight_pct=weight,
        overlap_count=count,
        matched_symbols=(),
        industry_credit_symbols=(),
    )
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}",
        asset_class="cn_equity_fund", overlap=ov, holdings=(),
    )


def test_keeps_rows_meeting_either_threshold() -> None:
    rows = (
        _row("A", weight=20.0, count=1),  # weight threshold met
        _row("B", weight=5.0, count=2),   # count threshold met
        _row("C", weight=5.0, count=1),   # neither -> dropped
    )
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=15)
    assert tuple(r.instrument_id for r in out) == ("A", "B")


def test_stable_sort_weight_then_count_then_id() -> None:
    rows = (
        _row("Z", weight=30.0, count=2),
        _row("Y", weight=30.0, count=3),  # higher count -> before Z
        _row("X", weight=40.0, count=1),  # higher weight -> first
        _row("W", weight=30.0, count=2),  # tie with Z on weight+count -> id asc
    )
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=15)
    assert tuple(r.instrument_id for r in out) == ("X", "Y", "W", "Z")


def test_top_n_truncation() -> None:
    rows = tuple(_row(f"{i:03d}", weight=20.0, count=2) for i in range(20))
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=5)
    assert len(out) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_screen.py -q`
Expected: FAIL — `ImportError: cannot import name 'rank_shortlist'`.

- [ ] **Step 3: Append `rank_shortlist` to `src/irc/narrative/screen.py`**

```python
def _qualifies(row: ShortlistRow, min_weight: float, min_count: int) -> bool:
    ov = row.overlap
    return ov.basket_weight_pct >= min_weight or ov.overlap_count >= min_count


def _sort_key(row: ShortlistRow) -> tuple[float, int, str]:
    ov = row.overlap
    return (-ov.basket_weight_pct, -ov.overlap_count, row.instrument_id)


def rank_shortlist(
    rows: tuple[ShortlistRow, ...],
    *,
    min_basket_weight_pct: float,
    min_overlap_count: int,
    top_n: int,
) -> tuple[ShortlistRow, ...]:
    """Pure: keep rows meeting EITHER threshold, sort
    (weight DESC, count DESC, id ASC), truncate to top_n."""
    kept = [r for r in rows if _qualifies(r, min_basket_weight_pct, min_overlap_count)]
    ordered = sorted(kept, key=_sort_key)
    return tuple(ordered[:top_n])
```

> Note: the `rank_shortlist` call uses keyword-only args (`*,`); the test calls it with keywords accordingly.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_screen.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/narrative/screen.py tests/narrative/test_screen.py
git add src/irc/narrative/screen.py tests/narrative/test_screen.py
git commit -m "feat(narrative): rank_shortlist threshold + stable sort + top-n (pure)"
```

---

## Task 4: `derive_position_risk_level` (pure risk core)

**Reuse note / spec gap (§3.6):** The spec's risk-driver table lists `valuation_state`, `heat_state`, `thesis_state`, `product_quality_state`, holdings concentration, narrative concentration, `drawdown_3y`/`volatility`, and `evidence_gaps`. The analyze phase (Task 8) builds the REAL `OpportunityRow` (`src/irc/opportunity/types.py:149`), which carries the four sub-states, `evidence_gaps`, and `constituent_analyses` (per-holding `weight_pct`). **`drawdown_3y` / `volatility` are NOT present** on `OpportunityRow`/`OpportunityInput` (which only has `ret_1m/3m/6m/12m` and `drawdown_since_entry`). Per the spec's "from discovery metrics, **when available**" wording and the hard "never fabricate" rule, this function takes an explicit `metrics: dict[str, float]` injected at the edge (Task 8 passes `{}` today); absent keys simply do not raise that driver. Holdings concentration is computed from the row's top holdings (`constituent_analyses`, falling back to the screen `Holding` weights); narrative concentration from the `OverlapResult`. To keep the core PURE and decoupled from the `OpportunityRow` import surface, the function accepts the four sub-states + `evidence_gaps` + top-holdings as a small `RiskEvalView` frozen view, projected at the `analyze.py` edge (Task 8 `_risk_view_from_row`).

**Files:**
- Modify: `src/irc/narrative/schemas.py` (add `RiskEvalView` frozen view)
- Create: `src/irc/narrative/risk.py`
- Test: `tests/narrative/test_risk.py`

- [ ] **Step 1: Add `RiskEvalView` to `schemas.py`**

Append to `src/irc/narrative/schemas.py`:

```python
@dataclass(frozen=True)
class RiskEvalView:
    """Pure projection of OpportunityRow fields consumed by the risk core.

    Built at the analyze edge (Task 8 _risk_view_from_row) so risk.py never
    imports OpportunityRow. top_holdings is (symbol, name_cn, weight_pct) in
    percent units, weight DESC."""
    valuation_state: str
    heat_state: str
    thesis_state: str
    product_quality_state: str
    evidence_gaps: tuple[str, ...]
    top_holdings: tuple[tuple[str, str, float], ...]
```

- [ ] **Step 2: Write the failing risk tests (one per driver row)**

Create `tests/narrative/test_risk.py`:

```python
from __future__ import annotations

from irc.narrative.risk import derive_position_risk_level
from irc.narrative.schemas import OverlapResult, RiskEvalView


def _view(**over: object) -> RiskEvalView:
    base = dict(
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        evidence_gaps=(),
        top_holdings=(("601899", "紫金矿业", 8.0), ("600362", "江西铜业", 6.0)),
    )
    base.update(over)
    return RiskEvalView(**base)  # type: ignore[arg-type]


def _overlap(count: int = 3, weight: float = 30.0) -> OverlapResult:
    return OverlapResult(
        basket_weight_pct=weight, overlap_count=count,
        matched_symbols=(), industry_credit_symbols=(),
    )


def test_clean_row_is_low() -> None:
    level, rationale, drivers = derive_position_risk_level(_view(), _overlap(), {})
    assert level == "low"
    assert drivers == ()


def test_evidence_gaps_force_insufficient() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(evidence_gaps=("holdings_fetch_failed",)), _overlap(), {}
    )
    assert level == "insufficient"
    assert "evidence_gaps" in drivers


def test_valuation_very_expensive_raises() -> None:
    level, rationale, drivers = derive_position_risk_level(
        _view(valuation_state="very_expensive"), _overlap(), {}
    )
    assert level in ("elevated", "high")
    assert "valuation_state" in drivers
    assert "very_expensive" in rationale


def test_heat_overheated_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(heat_state="overheated"), _overlap(), {}
    )
    assert "heat_state" in drivers


def test_thesis_falsified_raises_high() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(thesis_state="falsified"), _overlap(), {}
    )
    assert level == "high"
    assert "thesis_state" in drivers


def test_product_poor_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(product_quality_state="poor"), _overlap(), {}
    )
    assert "product_quality_state" in drivers


def test_holdings_concentration_top1_raises() -> None:
    _l, rationale, drivers = derive_position_risk_level(
        _view(top_holdings=(("601899", "紫金矿业", 38.0),)), _overlap(), {}
    )
    assert "holdings_concentration" in drivers
    assert "38" in rationale


def test_narrative_concentration_thin_slice_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(), _overlap(count=1, weight=20.0), {}
    )
    assert "narrative_concentration" in drivers


def test_drawdown_metric_raises_when_available() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(), _overlap(), {"drawdown_3y": 0.45}
    )
    assert "drawdown_3y" in drivers


def test_multiple_drivers_escalate_to_high() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(valuation_state="very_expensive", heat_state="overheated"),
        _overlap(), {},
    )
    assert level == "high"
    assert {"valuation_state", "heat_state"}.issubset(set(drivers))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_risk.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.risk'`.

- [ ] **Step 4: Write `src/irc/narrative/risk.py`**

```python
from __future__ import annotations

from irc.narrative.schemas import OverlapResult, RiskEvalView, RiskLevel

_TOP1_CONCENTRATION_PCT = 30.0
_TOP3_CONCENTRATION_PCT = 60.0
_DRAWDOWN_3Y_THRESHOLD = 0.30
_VOLATILITY_THRESHOLD = 0.30
_THIN_OVERLAP_COUNT = 1

# Level severity ladder (index = severity).
_LADDER: tuple[RiskLevel, ...] = ("low", "moderate", "elevated", "high")


def _concentration_drivers(view: RiskEvalView) -> tuple[tuple[str, str, int], ...]:
    out: list[tuple[str, str, int]] = []
    holds = view.top_holdings
    if holds and holds[0][2] >= _TOP1_CONCENTRATION_PCT:
        out.append(("holdings_concentration", f"{holds[0][2]:.0f}% in top holding", 2))
    top3 = sum(w for _s, _n, w in holds[:3])
    if top3 >= _TOP3_CONCENTRATION_PCT:
        out.append(("holdings_concentration", f"top-3 weight {top3:.0f}%", 1))
    return tuple(out)


def _state_drivers(view: RiskEvalView, overlap: OverlapResult,
                   metrics: dict[str, float]) -> tuple[tuple[str, str, int], ...]:
    out: list[tuple[str, str, int]] = []
    if view.valuation_state in ("expensive", "very_expensive"):
        out.append(("valuation_state", f"{view.valuation_state} valuation", 2))
    if view.heat_state in ("crowded", "overheated"):
        out.append(("heat_state", f"{view.heat_state} heat", 2))
    if view.thesis_state in ("under_pressure", "falsified"):
        sev = 3 if view.thesis_state == "falsified" else 1
        out.append(("thesis_state", f"thesis {view.thesis_state}", sev))
    if view.product_quality_state in ("weak", "poor"):
        out.append(("product_quality_state", f"{view.product_quality_state} product", 1))
    if overlap.overlap_count <= _THIN_OVERLAP_COUNT:
        out.append(("narrative_concentration", "narrative is a thin slice", 1))
    dd = metrics.get("drawdown_3y")
    if dd is not None and dd >= _DRAWDOWN_3Y_THRESHOLD:
        out.append(("drawdown_3y", f"3y drawdown {dd:.0%}", 1))
    vol = metrics.get("volatility")
    if vol is not None and vol >= _VOLATILITY_THRESHOLD:
        out.append(("volatility", f"volatility {vol:.0%}", 1))
    return tuple(out)


def derive_position_risk_level(
    view: RiskEvalView,
    overlap: OverlapResult,
    metrics: dict[str, float],
) -> tuple[RiskLevel, str, tuple[str, ...]]:
    """Pure: prospective-buy risk level + rationale + dominant drivers.

    evidence_gaps non-empty => 'insufficient' (never fabricate)."""
    if view.evidence_gaps:
        return ("insufficient", "evidence_gaps present — risk cannot be assessed",
                ("evidence_gaps",))
    found = _state_drivers(view, overlap, metrics) + _concentration_drivers(view)
    if not found:
        return ("low", "no elevated risk drivers", ())
    severity = min(len(_LADDER) - 1, sum(w for _d, _why, w in found))
    level = _LADDER[severity]
    drivers = tuple(dict.fromkeys(d for d, _why, _w in found))  # dedup, stable order
    rationale = f"{level} — " + "; ".join(why for _d, why, _w in found)
    return (level, rationale, drivers)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_risk.py -q`
Expected: PASS (10 passed).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check src/irc/narrative/risk.py tests/narrative/test_risk.py src/irc/narrative/schemas.py
git add src/irc/narrative/risk.py src/irc/narrative/schemas.py tests/narrative/test_risk.py
git commit -m "feat(narrative): derive_position_risk_level prospective-buy risk (pure)"
```

---

## Task 5: Renderers (pure report core)

**Files:**
- Create: `src/irc/narrative/report.py`
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing renderer tests**

Create `tests/narrative/test_report.py`:

```python
from __future__ import annotations

import json
import re

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.schemas import (
    NarrativeFundReport,
    OverlapResult,
    ShortlistRow,
)
from irc.narrative.report import (
    render_diagnostics_json,
    render_report_json,
    render_report_md,
    render_shortlist_json,
    render_shortlist_md,
)

_REF_RE = re.compile(r"\[ref:[0-9a-f]{16}\]")


def _row(iid: str) -> ShortlistRow:
    ov = OverlapResult(
        basket_weight_pct=22.5, overlap_count=3,
        matched_symbols=("600362", "601899"), industry_credit_symbols=("000060",),
    )
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}",
        asset_class="cn_equity_fund", overlap=ov, holdings=(),
    )


def _evidence(iid: str) -> ThesisEvidence:
    """A real ThesisEvidence — citation_id is computed in __post_init__ (16 hex)."""
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary="601899 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def _report(iid: str, *, level: str = "elevated",
            evidence: tuple[ThesisEvidence, ...] = ()) -> NarrativeFundReport:
    return NarrativeFundReport(
        instrument_id=iid, name_cn=f"fund-{iid}",
        position_risk_level=level,  # type: ignore[arg-type]
        risk_rationale=f"{level} — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=evidence,
    )


def test_shortlist_md_has_header_and_rows() -> None:
    md = render_shortlist_md("算力金属", (_row("A"), _row("B")))
    assert md.startswith("# ")
    assert "算力金属" in md
    assert "A" in md and "B" in md
    assert md.endswith("\n")


def test_shortlist_json_is_deterministic_and_parses() -> None:
    j1 = render_shortlist_json("算力金属", (_row("A"), _row("B")))
    j2 = render_shortlist_json("算力金属", (_row("A"), _row("B")))
    assert j1 == j2
    doc = json.loads(j1)
    assert doc["narrative"] == "算力金属"
    assert [r["instrument_id"] for r in doc["funds"]] == ["A", "B"]
    assert doc["funds"][0]["basket_weight_pct"] == 22.5


def test_diagnostics_json_lists_excluded_with_reason() -> None:
    j = render_diagnostics_json((("X", "fund-X", "no_published_holdings"),))
    doc = json.loads(j)
    assert doc["excluded"][0]["instrument_id"] == "X"
    assert doc["excluded"][0]["reason"] == "no_published_holdings"


def test_report_md_emits_ref_from_thesis_evidence() -> None:
    ev = _evidence("A")
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    # Citation rendered from the REAL evidence id (16 hex), reusing report.py format.
    assert _REF_RE.search(md)
    assert f"[ref:{ev.citation_id}]" in md
    # the locked line shape: `- [ref:{id}] {type} · {source} · {date}`
    assert f"[ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}" in md


def test_report_md_renders_risk_and_action_fields() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=(_evidence("A"),)),))
    assert "elevated" in md
    assert "small_watch" in md        # opportunity_state
    assert "slow_dca" in md           # dca_action
    assert "trim_review" in md        # risk_action
    assert "weekly_light_monthly_full" in md  # review_cadence


def test_report_md_no_evidence_has_no_ref() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=()),))
    assert not _REF_RE.search(md)  # no citations when evidence is empty


def test_report_json_round_trips_states_and_evidence() -> None:
    ev = _evidence("A")
    doc = json.loads(render_report_json("算力金属", (_report("A", level="high",
                                                            evidence=(ev,)),)))
    fund = doc["funds"][0]
    assert fund["position_risk_level"] == "high"
    assert fund["opportunity_state"] == "small_watch"
    assert fund["risk_action"] == "trim_review"
    assert fund["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert fund["thesis_evidence"][0]["type"] == "filing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.report'`.

- [ ] **Step 3: Write `src/irc/narrative/report.py`**

```python
from __future__ import annotations

import json

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.schemas import NarrativeFundReport, ShortlistRow
from irc.opportunity.citation_selector import select_citations


def render_shortlist_md(narrative: str, rows: tuple[ShortlistRow, ...]) -> str:
    lines = [f"# 主题选基 / Narrative shortlist — {narrative}", ""]
    lines.append(f"## 候选清单（{len(rows)}）")
    lines.append("| 代码 | 名称 | 篮子权重% | 重合数 | 命中 |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        ov = r.overlap
        hits = "、".join(ov.matched_symbols + ov.industry_credit_symbols) or "—"
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {ov.basket_weight_pct:.1f} | "
            f"{ov.overlap_count} | {hits} |"
        )
    return "\n".join(lines) + "\n"


def _shortlist_row_dict(r: ShortlistRow) -> dict:
    ov = r.overlap
    return {
        "instrument_id": r.instrument_id,
        "name_cn": r.name_cn,
        "asset_class": r.asset_class,
        "basket_weight_pct": ov.basket_weight_pct,
        "overlap_count": ov.overlap_count,
        "matched_symbols": list(ov.matched_symbols),
        "industry_credit_symbols": list(ov.industry_credit_symbols),
    }


def render_shortlist_json(narrative: str, rows: tuple[ShortlistRow, ...]) -> str:
    doc = {"narrative": narrative, "funds": [_shortlist_row_dict(r) for r in rows]}
    return json.dumps(doc, ensure_ascii=False, indent=2)


def render_diagnostics_json(excluded: tuple[tuple[str, str, str], ...]) -> str:
    doc = {
        "excluded": [
            {"instrument_id": iid, "name_cn": name, "reason": reason}
            for iid, name, reason in excluded
        ]
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _evidence_bullets(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    """Reuse the locked citation format from opportunity/report.py:210.
    `- [ref:{citation_id}] {type} · {source} · {date}` via select_citations cap=3."""
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}"
        for ev in selected
    ]


def render_report_md(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    lines = [f"# 主题深度分析 / Narrative report — {narrative}", ""]
    for r in reports:
        lines.append(f"## {r.instrument_id} {r.name_cn}")
        lines.append(f"- 仓位风险等级 / position_risk_level: **{r.position_risk_level}**")
        lines.append(f"- 主因 / drivers: {', '.join(r.risk_drivers) or '—'}")
        lines.append(f"- 说明: {r.risk_rationale}")
        lines.append(
            f"- 机会 / dca / 风险: {r.opportunity_state} ｜ {r.dca_action} ｜ {r.risk_action}"
        )
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state}"
        )
        lines.append(f"- 复核节奏 / review_cadence: {r.review_cadence}")
        lines.append(f"- 证伪触发: {', '.join(r.falsification_triggers) or '—'}")
        lines.append(f"- 减仓触发: {', '.join(r.trim_triggers) or '—'}")
        bullets = _evidence_bullets(r.thesis_evidence)
        if bullets:
            lines.append("- 证据 / evidence:")
            lines.extend(bullets)
        lines.append("")
    return "\n".join(lines) + "\n"


def _evidence_dict(ev: ThesisEvidence) -> dict:
    return {
        "citation_id": ev.citation_id,
        "type": ev.type,
        "source": ev.source,
        "date": ev.date,
        "scope": ev.scope,
        "citation_kind": ev.citation_kind,
    }


def _report_dict(r: NarrativeFundReport) -> dict:
    return {
        "instrument_id": r.instrument_id,
        "name_cn": r.name_cn,
        "position_risk_level": r.position_risk_level,
        "risk_rationale": r.risk_rationale,
        "risk_drivers": list(r.risk_drivers),
        "valuation_state": r.valuation_state,
        "heat_state": r.heat_state,
        "thesis_state": r.thesis_state,
        "product_quality_state": r.product_quality_state,
        "opportunity_state": r.opportunity_state,
        "dca_action": r.dca_action,
        "risk_action": r.risk_action,
        "falsification_triggers": list(r.falsification_triggers),
        "trim_triggers": list(r.trim_triggers),
        "review_cadence": r.review_cadence,
        "evidence_gaps": list(r.evidence_gaps),
        "thesis_evidence": [_evidence_dict(ev) for ev in r.thesis_evidence],
    }


def render_report_json(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    doc = {"narrative": narrative, "funds": [_report_dict(r) for r in reports]}
    return json.dumps(doc, ensure_ascii=False, indent=2)
```

> Note: `select_citations` lives at `src/irc/opportunity/citation_selector.py` (the same module `opportunity/report.py:9` imports). The bullet format is byte-identical to `_render_thesis_evidence_bullets` at `opportunity/report.py:196-212`, preserving the SAME-3 selector contract. The renderer stays pure (no I/O); `select_citations` is itself pure.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/narrative/report.py tests/narrative/test_report.py
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(narrative): deterministic md/json renderers (pure)"
```

---

## Task 6: Narrative config loader (I/O edge)

**Files:**
- Create: `src/irc/narrative/config.py`
- Create: `config/narratives/compute_metals.yaml` (DRAFT seed)
- Test: `tests/narrative/test_config.py`

- [ ] **Step 1: Seed the DRAFT `compute_metals.yaml`**

Create `config/narratives/compute_metals.yaml`:

```yaml
# ⚠️ DRAFT — seeded for user approval, then FROZEN (spec §7).
# compute_metals = copper / aluminium / tin industrial metals + PCB-gold names
# whose demand is tied to AI-datacenter buildout. Review the basket before use.
narrative_id: compute_metals
display_name_cn: 算力金属
display_name_en: Compute-demand metals
thesis_cn: AI 数据中心建设拉动铜/铝/锡等工业金属与 PCB 用金需求
basket:
  # — copper / copper-gold / copper-cobalt —
  - { symbol: "601899", name_cn: 紫金矿业, metal: copper_gold }
  - { symbol: "603993", name_cn: 洛阳钼业, metal: copper_cobalt }
  - { symbol: "600362", name_cn: 江西铜业, metal: copper }
  - { symbol: "000630", name_cn: 铜陵有色, metal: copper }
  - { symbol: "600547", name_cn: 山东黄金, metal: gold }
  # — aluminium —
  - { symbol: "601600", name_cn: 中国铝业, metal: aluminium }
  - { symbol: "600219", name_cn: 南山铝业, metal: aluminium }
  - { symbol: "000807", name_cn: 云铝股份, metal: aluminium }
  # — tin —
  - { symbol: "000960", name_cn: 锡业股份, metal: tin }
  # — PCB-gold / electronics-grade metals tied to AI compute —
  - { symbol: "002182", name_cn: 云海金属, metal: magnesium }
  - { symbol: "600961", name_cn: 株冶集团, metal: zinc }
industries_sw:
  - 有色金属/工业金属
  - 有色金属/贵金属
thresholds:
  min_basket_weight_pct: 15.0   # ≥15% of top-10 sits in the basket …
  min_overlap_count: 2          # … OR ≥2 distinct basket names appear
top_n: 15
```

- [ ] **Step 2: Write the failing config tests**

Create `tests/narrative/test_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from irc.narrative.config import available_narratives, load_narrative_basket
from irc.narrative.schemas import NarrativeBasket

REPO = Path(__file__).resolve().parents[2]


def test_load_compute_metals_parses() -> None:
    b = load_narrative_basket("compute_metals", REPO)
    assert isinstance(b, NarrativeBasket)
    assert b.narrative_id == "compute_metals"
    assert b.display_name_cn == "算力金属"
    assert any(s.symbol == "601899" for s in b.basket)
    assert b.min_basket_weight_pct == 15.0
    assert b.min_overlap_count == 2
    assert b.top_n == 15
    assert "有色金属/工业金属" in b.industries_sw


def test_missing_narrative_lists_available(tmp_path: Path) -> None:
    (tmp_path / "config" / "narratives").mkdir(parents=True)
    (tmp_path / "config" / "narratives" / "ai.yaml").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as exc:
        load_narrative_basket("nope", tmp_path)
    assert "ai" in str(exc.value)


def test_malformed_config_rejected(tmp_path: Path) -> None:
    d = tmp_path / "config" / "narratives"
    d.mkdir(parents=True)
    (d / "bad.yaml").write_text("narrative_id: bad\nbasket: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_narrative_basket("bad", tmp_path)


def test_available_narratives_includes_compute_metals() -> None:
    assert "compute_metals" in available_narratives(REPO)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.config'`.

- [ ] **Step 4: Write `src/irc/narrative/config.py`**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from irc.narrative.schemas import BasketStock, NarrativeBasket


def _narratives_dir(repo_root: Path) -> Path:
    return repo_root / "config" / "narratives"


def available_narratives(repo_root: Path) -> tuple[str, ...]:
    d = _narratives_dir(repo_root)
    if not d.exists():
        return ()
    return tuple(sorted(p.stem for p in d.glob("*.yaml")))


def _parse_basket(raw: list) -> tuple[BasketStock, ...]:
    if not isinstance(raw, list):
        raise ValueError("basket must be a list of {symbol, name_cn, metal}")
    return tuple(
        BasketStock(
            symbol=str(item["symbol"]),
            name_cn=str(item["name_cn"]),
            metal=str(item.get("metal", "")),
        )
        for item in raw
    )


def load_narrative_basket(name: str, repo_root: Path) -> NarrativeBasket:
    """I/O edge: read + validate config/narratives/<name>.yaml -> NarrativeBasket.

    Missing config raises FileNotFoundError naming the available narratives."""
    path = _narratives_dir(repo_root) / f"{name}.yaml"
    if not path.exists():
        avail = ", ".join(available_narratives(repo_root)) or "(none)"
        raise FileNotFoundError(
            f"narrative config not found: {path}. Available: {avail}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    thresholds = raw.get("thresholds", {})
    return NarrativeBasket(
        narrative_id=str(raw["narrative_id"]),
        display_name_cn=str(raw.get("display_name_cn", "")),
        display_name_en=str(raw.get("display_name_en", "")),
        thesis_cn=str(raw.get("thesis_cn", "")),
        basket=_parse_basket(raw.get("basket", [])),
        industries_sw=tuple(str(x) for x in raw.get("industries_sw", [])),
        min_basket_weight_pct=float(thresholds.get("min_basket_weight_pct", 15.0)),
        min_overlap_count=int(thresholds.get("min_overlap_count", 2)),
        top_n=int(raw.get("top_n", 15)),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_config.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check src/irc/narrative/config.py tests/narrative/test_config.py
git add src/irc/narrative/config.py config/narratives/compute_metals.yaml tests/narrative/test_config.py
git commit -m "feat(narrative): config loader + DRAFT compute_metals basket"
```

---

## Task 7: `fetch_top_holdings` (I/O edge — AkShare + cache)

**Reuse note:** holdings come from `fund_portfolio_hold_em` via the existing `_ak_call` seam (`src/irc/fundamentals/akshare_fundamentals.py`), reusing the column contract `{股票代码, 股票名称, 占净值比例}` and the `申万一级行业`/`所属行业` column if present for `sw_industry`. The literal `基金概况` is NEVER used. We do not call the heavier `fetch_cn_etf_holdings` (it returns `FundHolding`, not our `Holding`, and carries no SW-industry); the narrative screen needs a thin top-10 + industry fetch with its own on-disk cache (`data/narrative_holdings/<symbol>.json`).

**Files:**
- Create: `src/irc/narrative/holdings_fetch.py`
- Test: `tests/narrative/test_holdings_fetch.py`

- [ ] **Step 1: Write the failing edge tests (mock `_ak_call`) + the live double-gated test**

Create `tests/narrative/test_holdings_fetch.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from irc.narrative.holdings_fetch import fetch_top_holdings
from irc.narrative.schemas import Holding


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "股票代码": ["601899", "600362"],
            "股票名称": ["紫金矿业", "江西铜业"],
            "占净值比例": [9.0, 6.0],
            "季度": ["2026Q1", "2026Q1"],
        }
    )


def test_fetch_parses_top_holdings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "irc.narrative.holdings_fetch._ak_call", lambda *a, **k: _fake_df()
    )
    out = fetch_top_holdings("000123", cache_dir=tmp_path)
    assert out[0] == Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0)
    assert len(out) == 2


def test_cache_hit_skips_network(monkeypatch, tmp_path: Path) -> None:
    calls = {"n": 0}

    def _counting(*a, **k):  # noqa: ANN001
        calls["n"] += 1
        return _fake_df()

    monkeypatch.setattr("irc.narrative.holdings_fetch._ak_call", _counting)
    fetch_top_holdings("000123", cache_dir=tmp_path)
    fetch_top_holdings("000123", cache_dir=tmp_path)
    assert calls["n"] == 1  # second call served from cache


def test_empty_or_failed_returns_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "irc.narrative.holdings_fetch._ak_call",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert fetch_top_holdings("000999", cache_dir=tmp_path) == ()


# ── Live double-gated (CONTEXT.md "Live test gate") ──────────────────────────
_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"


@pytest.mark.live_akshare
@pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare")
def test_fetch_top_holdings_live(tmp_path: Path) -> None:
    # 005827 — active CN equity fund used as the live sanity symbol elsewhere.
    out = fetch_top_holdings("005827", cache_dir=tmp_path)
    assert isinstance(out, tuple)
    if out:
        assert all(isinstance(h, Holding) for h in out)
        assert all(0.0 <= h.weight_pct <= 100.0 for h in out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_holdings_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.holdings_fetch'` (live test skipped).

- [ ] **Step 3: Write `src/irc/narrative/holdings_fetch.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from irc.fundamentals.akshare_fundamentals import _ak_call
from irc.narrative.schemas import Holding

_TOP_N = 10
_NEEDED = {"股票代码", "股票名称", "占净值比例"}
_INDUSTRY_COLS = ("申万一级行业", "所属行业")


def _current_year() -> str:
    return str(datetime.now(timezone.utc).year)


def _industry(row: pd.Series) -> str:
    for col in _INDUSTRY_COLS:
        if col in row.index and pd.notna(row[col]):
            return str(row[col])
    return ""


def _to_holding(row: pd.Series) -> Holding:
    try:
        weight = float(row["占净值比例"])
    except (TypeError, ValueError):
        weight = 0.0
    return Holding(
        symbol=str(row["股票代码"]).strip(),
        name_cn=str(row["股票名称"]).strip(),
        weight_pct=weight,
        sw_industry=_industry(row),
    )


def _parse(df: pd.DataFrame) -> tuple[Holding, ...]:
    if not isinstance(df, pd.DataFrame) or df.empty or not _NEEDED.issubset(df.columns):
        return ()
    ranked = df.sort_values("占净值比例", ascending=False).head(_TOP_N)
    return tuple(_to_holding(row) for _i, row in ranked.iterrows())


def _read_cache(path: Path) -> tuple[Holding, ...] | None:
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return tuple(Holding(**h) for h in body.get("holdings", []))


def _write_cache(path: Path, holdings: tuple[Holding, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"holdings": [h.__dict__ for h in holdings]}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_top_holdings(fund_id: str, *, cache_dir: Path) -> tuple[Holding, ...]:
    """I/O edge: top-10 disclosed holdings for a fund (AkShare, cached). Never raises."""
    cache_path = cache_dir / f"{fund_id}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached
    try:
        df = _ak_call("fund_portfolio_hold_em", symbol=fund_id, date=_current_year())
    except Exception:
        return ()
    holdings = _parse(df)
    _write_cache(cache_path, holdings)
    return holdings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_holdings_fetch.py -q`
Expected: PASS (3 passed, 1 skipped).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/narrative/holdings_fetch.py tests/narrative/test_holdings_fetch.py
git add src/irc/narrative/holdings_fetch.py tests/narrative/test_holdings_fetch.py
git commit -m "feat(narrative): fetch_top_holdings AkShare edge + cache + live gate"
```

---

## Task 8: Real per-fund analyze — `analyze.py` (I/O edge)

**This is the load-bearing analyze revision.** It delivers Goal #2 in full by reusing the existing deepest path — **untouched**: `_build_input` → `build_opportunity_row` → `build_thesis_card` (which itself calls `derive_dca_action` + `derive_risk_action`) → `derive_position_risk_level`. The resulting `NarrativeFundReport` carries the REAL `thesis_evidence` so the renderer emits genuine `[ref:...]` citations.

**Confirmed reuse signatures (file:line):**
- `build_opportunity_row(inp, theme_thesis, *, snapshot=None, theme_report=None) -> OpportunityRow` — `src/irc/opportunity/states.py:522`. Both `snapshot` and `theme_report` are None-able; a missing snapshot yields `evidence_insufficient` sub-states + populated `evidence_gaps` (no hardcoding).
- `PositionContext(portfolio_weight, target_band_low, target_band_high, drawdown_since_entry, is_holding)` — frozen dataclass, `src/irc/opportunity/discipline.py:11-18`. For a PROSPECTIVE (non-held) buy: all four held-position fields `None`, `is_holding=False`.
- `build_thesis_card(row, position, role, entry_reason, review_cadence="weekly_light_monthly_full") -> ThesisCard` — `src/irc/opportunity/cards.py:30`. **It internally calls `derive_dca_action(row)` AND `derive_risk_action(row, position)` (cards.py:39-40)**, so `card.risk_action`/`card.dca_action` are populated — NO separate `derive_risk_action` call needed. It also stamps `falsification_triggers`, `trim_triggers`, `do_not_sell_just_because`, `review_cadence`, and threads `row.thesis_evidence` through verbatim.
- `_build_input(score_row, instr, holding, target_band, portfolio_total_cny, available_venues, con, *, provider) -> OpportunityInput` — `src/irc/opportunity/inputs_build.py:14`.
- `load_active_fund_cache(fund_id, quarter, root) -> ActiveFundSnapshot | None` — `src/irc/fundamentals/snapshot_cache.py:234` (`root` is `repo_root / "data"`).

**Snapshot policy (judgment call — resolves spec §3.4 "ensure snapshot" vs the cache-only architecture):** the analyze phase **READS THE CACHE ONLY**, mirroring `irc opportunity` (CLAUDE.md: "`irc opportunity` reads **cached** evidence; it does not fetch live"). It does NOT trigger the heavy sequential `fundamentals snapshot` job inline (CLAUDE.md: it is a deliberately-separate 5–15 min quarterly job, NOT part of `irc run`). A missing per-fund snapshot → `build_opportunity_row` fallback → `evidence_insufficient` states + `evidence_gaps` → `derive_position_risk_level` → `insufficient` (spec §4, surfaced not crashed). `FetchBudgetExceeded` / `fetch_budget_exhausted` never arise here because no fetch budget is computed — the cache is read, not built. See spec §1 "mirroring `irc opportunity`".

**Files:**
- Create: `src/irc/narrative/analyze.py`
- Test: `tests/narrative/test_analyze.py`

- [ ] **Step 1: Write the failing analyze tests (no network, no DuckDB)**

The pure projection helpers (`_risk_view_from_row`, `_report_from_card`) are unit-testable directly with a hand-built `OpportunityRow` carrying real `thesis_evidence`. The DuckDB→row wiring (`analyze_fund`) is exercised by monkeypatching `build_opportunity_row` / `load_active_fund_cache` / `_build_input`.

Create `tests/narrative/test_analyze.py`:

```python
from __future__ import annotations

from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget, ThesisEvidence
from irc.narrative import analyze as A
from irc.narrative.schemas import Holding, OverlapResult, ShortlistRow
from irc.opportunity.types import OpportunityRow


def _evidence(iid: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary=f"{iid} 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def _row(iid: str, *, valuation="very_expensive", gaps=()) -> OpportunityRow:
    return OpportunityRow(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class="cn_equity_fund",
        theme="metals",
        lookthrough_target=LookthroughTarget(kind="active_fund", key=iid, display_cn=f"fund-{iid}"),
        valuation_state=valuation, heat_state="overheated", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="small_watch",
        opportunity_reason="估值偏高但逻辑完整", evidence_gaps=gaps,
        thesis_evidence=(_evidence(iid),),
        constituent_analyses=(
            ConstituentAnalysis(symbol="601899", name_cn="紫金矿业", weight_pct=38.0,
                                evidence=(), failure_reasons=(), one_line_view="x"),
        ),
    )


def _shortlist_row(iid: str) -> ShortlistRow:
    ov = OverlapResult(basket_weight_pct=22.0, overlap_count=3,
                       matched_symbols=(), industry_credit_symbols=())
    return ShortlistRow(instrument_id=iid, name_cn=f"fund-{iid}",
                        asset_class="cn_equity_fund", overlap=ov,
                        holdings=(Holding(symbol="601899", name_cn="紫金矿业", weight_pct=38.0),))


def test_risk_view_reads_real_row_states() -> None:
    view = A._risk_view_from_row(_row("000A"), _shortlist_row("000A"))
    assert view.valuation_state == "very_expensive"
    assert view.heat_state == "overheated"
    assert view.evidence_gaps == ()
    assert view.top_holdings[0] == ("601899", "紫金矿业", 38.0)  # from constituent_analyses


def test_risk_view_falls_back_to_screen_holdings_when_no_constituents() -> None:
    row = _row("000A")
    row = OpportunityRow(**{**row.__dict__, "constituent_analyses": ()})
    view = A._risk_view_from_row(row, _shortlist_row("000A"))
    assert view.top_holdings[0] == ("601899", "紫金矿业", 38.0)  # from screen Holding


def test_report_from_card_carries_evidence_and_states() -> None:
    rpt = A._report_from_card(_row("000A"), _shortlist_row("000A"),
                              role="satellite_cn_metals")
    assert rpt.position_risk_level in ("elevated", "high")
    assert "valuation_state" in rpt.risk_drivers
    assert rpt.opportunity_state == "small_watch"
    assert rpt.risk_action == "trim_review"  # is_holding=False but expensive+hot fires trim
    assert rpt.thesis_evidence and rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id
    assert rpt.review_cadence == "weekly_light_monthly_full"


def test_report_from_card_missing_snapshot_is_insufficient() -> None:
    row = _row("000A", valuation="evidence_insufficient",
               gaps=("missing_constituent_snapshot",))
    rpt = A._report_from_card(row, _shortlist_row("000A"), role="r")
    assert rpt.position_risk_level == "insufficient"
    assert "evidence_gaps" in rpt.risk_drivers


def test_analyze_fund_wires_cache_and_builder(monkeypatch) -> None:
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: object())
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000A"))
    rpt = A.analyze_fund(
        _shortlist_row("000A"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"),
        role="satellite_cn_metals",
    )
    assert rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id
```

> Verify `ConstituentAnalysis`'s real constructor before running — it is `(symbol, name_cn, weight_pct, evidence, failure_reasons, one_line_view, audit_errors=())` per CONTEXT.md "ConstituentAnalysis". If a field name differs, adjust the test fixture (the production code reads only `.symbol`, `.name_cn`, `.weight_pct`).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_analyze.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.analyze'`.

- [ ] **Step 3: Write `src/irc/narrative/analyze.py`**

```python
from __future__ import annotations

import duckdb

from irc.fundamentals.provider import CnFundamentalsProvider
from irc.fundamentals.snapshot_cache import load_active_fund_cache
from irc.narrative.risk import derive_position_risk_level
from irc.narrative.schemas import (
    NarrativeFundReport,
    RiskEvalView,
    ShortlistRow,
)
from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.inputs_build import _build_input
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import OpportunityRow
from irc.schemas.universe import Instrument

_PROSPECTIVE_POSITION = PositionContext(
    portfolio_weight=None, target_band_low=None, target_band_high=None,
    drawdown_since_entry=None, is_holding=False,
)


def _top_holdings_from_row(row: OpportunityRow,
                           shortlist_row: ShortlistRow) -> tuple[tuple[str, str, float], ...]:
    if row.constituent_analyses:
        ranked = sorted(row.constituent_analyses, key=lambda c: -c.weight_pct)
        return tuple((c.symbol, c.name_cn, c.weight_pct) for c in ranked)
    holds = sorted(shortlist_row.holdings, key=lambda h: -h.weight_pct)
    return tuple((h.symbol, h.name_cn, h.weight_pct) for h in holds)


def _risk_view_from_row(row: OpportunityRow, shortlist_row: ShortlistRow) -> RiskEvalView:
    return RiskEvalView(
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        evidence_gaps=row.evidence_gaps,
        top_holdings=_top_holdings_from_row(row, shortlist_row),
    )


def _report_from_card(row: OpportunityRow, shortlist_row: ShortlistRow,
                      *, role: str) -> NarrativeFundReport:
    entry_reason = row.opportunity_reason.split("；")[0].split(";")[0]
    card = build_thesis_card(row, _PROSPECTIVE_POSITION, role, entry_reason)
    view = _risk_view_from_row(row, shortlist_row)
    level, rationale, drivers = derive_position_risk_level(view, shortlist_row.overlap, {})
    return NarrativeFundReport(
        instrument_id=card.instrument_id, name_cn=card.name_cn,
        position_risk_level=level, risk_rationale=rationale, risk_drivers=drivers,
        valuation_state=card.valuation_state, heat_state=card.heat_state,
        thesis_state=card.thesis_state, product_quality_state=card.product_quality_state,
        opportunity_state=card.opportunity_state, dca_action=card.dca_action,
        risk_action=card.risk_action,
        falsification_triggers=card.falsification_triggers,
        trim_triggers=card.trim_triggers, review_cadence=card.review_cadence,
        evidence_gaps=card.evidence_gaps, thesis_evidence=card.thesis_evidence,
    )


def analyze_fund(
    shortlist_row: ShortlistRow, *, instr: Instrument | None,
    con: duckdb.DuckDBPyConnection, provider: CnFundamentalsProvider,
    quarter: str, data_dir, role: str,
) -> NarrativeFundReport:
    """I/O edge: build the REAL OpportunityRow (cache-only) -> ThesisCard ->
    prospective risk report for one shortlisted fund. Mirrors fund_eval_cmd."""
    iid = shortlist_row.instrument_id
    score_row = {"instrument_id": iid, "asset_class": shortlist_row.asset_class, "role": role}
    inp = _build_input(score_row, instr, None, None, 0.0, set(), con, provider=provider)
    snapshot = load_active_fund_cache(iid, quarter, data_dir)
    row = build_opportunity_row(inp, None, snapshot=snapshot, theme_report=None)
    return _report_from_card(row, shortlist_row, role=role)
```

> Note: `load_active_fund_cache`, `_build_input`, and `build_opportunity_row` are module-level names so `test_analyze.py` can monkeypatch them without touching DuckDB. The file is ~70 lines (< 200). `entry_reason` takes the first `；`/`;`-delimited segment of `opportunity_reason` (a plain-text reason; `[ref:...]` markers do NOT appear there — they live only in `thesis_evidence`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_analyze.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/narrative/analyze.py tests/narrative/test_analyze.py
git add src/irc/narrative/analyze.py tests/narrative/test_analyze.py
git commit -m "feat(narrative): real per-fund analyze (OpportunityRow+ThesisCard+citations)"
```

---

## Task 9: Orchestration — `narrative_cmd.py` (I/O edge)

**Reuse note:** `narrative_cmd` is the thin command edge: load config → screen → (if `--analyze`) open DuckDB read-only + `default_cn_provider()` + build the instrument index (mirroring `fund_eval_cmd._instr_by_id`) → call `analyze.analyze_fund` per shortlisted fund → render → write. It honours the cache-only snapshot policy (Task 8) and the missing-data guard (write the screen first, then error with an actionable message). The screen path is unchanged from the original plan.

**Files:**
- Create: `src/irc/commands/narrative_cmd.py`
- Test: `tests/narrative/test_narrative_cmd.py`

- [ ] **Step 1: Write the failing integration tests (no network / no DuckDB)**

Create `tests/narrative/test_narrative_cmd.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from irc.commands import narrative_cmd
from irc.fundamentals.types import LookthroughTarget, ThesisEvidence
from irc.narrative.schemas import Holding, NarrativeFundReport
from irc.opportunity.types import OpportunityRow


def _wire_repo(tmp_path: Path) -> Path:
    # minimal repo: a narratives config + a tiny cn_funds universe.
    (tmp_path / "config" / "narratives").mkdir(parents=True)
    (tmp_path / "config" / "narratives" / "compute_metals.yaml").write_text(
        "narrative_id: compute_metals\n"
        "display_name_cn: 算力金属\n"
        "display_name_en: Compute-demand metals\n"
        "thesis_cn: t\n"
        "basket:\n"
        "  - { symbol: '601899', name_cn: 紫金矿业 }\n"
        "  - { symbol: '600362', name_cn: 江西铜业 }\n"
        "industries_sw: [有色金属/工业金属]\n"
        "thresholds: { min_basket_weight_pct: 15.0, min_overlap_count: 2 }\n"
        "top_n: 15\n",
        encoding="utf-8",
    )
    return tmp_path


def _evidence(iid: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary=f"{iid} 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def test_screen_only_writes_shortlist_and_diagnostics(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    universe = (
        ("000A", "有色基金", "cn_equity_fund"),
        ("000B", "空仓基金", "cn_equity_fund"),
    )
    monkeypatch.setattr(narrative_cmd, "_enumerate_cn_funds", lambda root: universe)
    holdings_by_id = {
        "000A": (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=12.0),
            Holding(symbol="600362", name_cn="江西铜业", weight_pct=8.0),
        ),
        "000B": (),
    }
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: holdings_by_id[fid],
    )
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=False,
        out_dir=str(out_dir),
    )
    assert rc == 0
    shortlist = json.loads((out_dir / "compute_metals_shortlist.json").read_text())
    assert [r["instrument_id"] for r in shortlist["funds"]] == ["000A"]
    diags = json.loads((out_dir / "compute_metals_screen_diagnostics.json").read_text())
    assert diags["excluded"][0]["instrument_id"] == "000B"
    assert "no_published_holdings" in diags["excluded"][0]["reason"]


def test_unknown_narrative_returns_error(tmp_path: Path) -> None:
    repo = _wire_repo(tmp_path)
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="does_not_exist", analyze=False,
        out_dir=str(repo / "out"),
    )
    assert rc == 2


def test_analyze_renders_real_citations(tmp_path: Path, monkeypatch) -> None:
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
    # make analyze deterministic + DB-free: stub the open-db edge + per-fund analyze.
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    expensive = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金",
        position_risk_level="high", risk_rationale="high — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=(_evidence("000A"),),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund",
                        lambda row, **k: expensive)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 0
    report_md = (out_dir / "compute_metals_report.md").read_text()
    import re
    assert re.search(r"\[ref:[0-9a-f]{16}\]", report_md)
    assert "high" in report_md and "trim_review" in report_md


def test_analyze_missing_db_writes_screen_then_errors(tmp_path: Path, monkeypatch) -> None:
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
    # no data/local.duckdb in the temp repo, no cached quarter
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: None)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 2
    # screen outputs still written before the error
    assert (out_dir / "compute_metals_shortlist.json").exists()
    assert not (out_dir / "compute_metals_report.json").exists()


def test_run_twice_byte_identical(tmp_path: Path, monkeypatch) -> None:
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
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    first = (out_dir / "compute_metals_shortlist.json").read_text()
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    second = (out_dir / "compute_metals_shortlist.json").read_text()
    assert first == second


def test_min_overlap_override_widens_shortlist(tmp_path: Path, monkeypatch) -> None:
    # spec §3.1: --min-overlap lowers the basket-weight bar. Config is
    # min_basket_weight_pct=15 / min_overlap_count=2. A fund with one basket
    # holding at 12% (count=1) misses BOTH config thresholds → dropped by default,
    # but qualifies once --min-overlap=10 overrides the weight bar.
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=12.0),
        ),
    )
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    default_funds = json.loads((out_dir / "compute_metals_shortlist.json").read_text())["funds"]
    assert default_funds == []  # 12% < 15% weight and count 1 < 2 → dropped
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir), min_overlap=10.0)
    widened = json.loads((out_dir / "compute_metals_shortlist.json").read_text())["funds"]
    assert [r["instrument_id"] for r in widened] == ["000A"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.commands.narrative_cmd'`.

- [ ] **Step 3: Write `src/irc/commands/narrative_cmd.py`**

```python
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from irc.commands.fund_eval_cmd import _instr_by_id, _latest_quarter
from irc.config_loader import load_repo_configs
from irc.fundamentals.provider import default_cn_provider
from irc.io_utils import atomic_write_text
from irc.narrative.analyze import analyze_fund
from irc.narrative.config import available_narratives, load_narrative_basket
from irc.narrative.holdings_fetch import fetch_top_holdings
from irc.narrative.report import (
    render_diagnostics_json,
    render_report_json,
    render_report_md,
    render_shortlist_json,
    render_shortlist_md,
)
from irc.narrative.schemas import (
    NarrativeBasket,
    NarrativeFundReport,
    ShortlistRow,
)
from irc.narrative.screen import rank_shortlist, score_overlap


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _enumerate_cn_funds(root: Path) -> tuple[tuple[str, str, str], ...]:
    """(instrument_id, name_cn, asset_class) for the curated CN-fund universe."""
    bundle = load_repo_configs(root)
    uni = getattr(bundle, "universe_cn_funds", None)
    if uni is None:
        return ()
    return tuple((i.instrument_id, i.name_cn, i.asset_class) for i in uni.instruments)


def _screen(basket: NarrativeBasket, universe: tuple[tuple[str, str, str], ...],
            cache_dir: Path) -> tuple[tuple[ShortlistRow, ...], tuple[tuple[str, str, str], ...]]:
    candidates: list[ShortlistRow] = []
    excluded: list[tuple[str, str, str]] = []
    for iid, name, asset_class in universe:
        holdings = fetch_top_holdings(iid, cache_dir=cache_dir)
        if not holdings:
            excluded.append((iid, name, "no_published_holdings"))
            continue
        candidates.append(ShortlistRow(
            instrument_id=iid, name_cn=name, asset_class=asset_class,
            overlap=score_overlap(holdings, basket), holdings=holdings,
        ))
    shortlist = rank_shortlist(
        tuple(candidates), min_basket_weight_pct=basket.min_basket_weight_pct,
        min_overlap_count=basket.min_overlap_count, top_n=basket.top_n,
    )
    return shortlist, tuple(excluded)


def _open_analyze_context(root: Path, db_path: str | None, quarter: str | None):
    """Open DuckDB read-only + resolve provider/quarter/instr-index. Returns
    (con, provider, quarter, instr_index) or None when prerequisites are absent."""
    db = Path(db_path) if db_path else (root / "data" / "local.duckdb")
    resolved_quarter = quarter or _latest_quarter(root)
    if not db.exists() or resolved_quarter is None:
        return None
    try:
        con = duckdb.connect(str(db), read_only=True)
    except Exception:
        return None
    return (con, default_cn_provider(), resolved_quarter, _instr_by_id(root))


def _run_analyze(root: Path, shortlist: tuple[ShortlistRow, ...], *,
                 db_path: str | None, quarter: str | None,
                 role: str) -> tuple[NarrativeFundReport, ...] | None:
    ctx = _open_analyze_context(root, db_path, quarter)
    if ctx is None:
        return None
    con, provider, resolved_quarter, instr_index = ctx
    try:
        return tuple(
            analyze_fund(
                row, instr=instr_index.get(row.instrument_id), con=con,
                provider=provider, quarter=resolved_quarter,
                data_dir=root / "data", role=role,
            )
            for row in shortlist
        )
    finally:
        con.close()


def _write_screen(out: Path, name: str, label: str,
                  shortlist: tuple[ShortlistRow, ...],
                  excluded: tuple[tuple[str, str, str], ...]) -> None:
    atomic_write_text(out / f"{name}_shortlist.md", render_shortlist_md(label, shortlist))
    atomic_write_text(out / f"{name}_shortlist.json", render_shortlist_json(label, shortlist))
    atomic_write_text(out / f"{name}_screen_diagnostics.json",
                      render_diagnostics_json(excluded))


def run_narrative(
    repo_root: str, name: str, *, analyze: bool = False,
    out_dir: str | None = None, quarter: str | None = None,
    db_path: str | None = None, role: str = "satellite_cn_metals",
    min_overlap: float | None = None,
) -> int:
    root = Path(repo_root)
    try:
        basket = load_narrative_basket(name, root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Available narratives: {', '.join(available_narratives(root)) or '(none)'}",
              file=sys.stderr)
        return 2
    # spec §3.1: --min-overlap overrides the config's min_basket_weight_pct (immutably).
    if min_overlap is not None:
        basket = replace(basket, min_basket_weight_pct=min_overlap)
    out = Path(out_dir) if out_dir else (root / "outputs" / _today() / "narrative")
    out.mkdir(parents=True, exist_ok=True)
    label = basket.display_name_cn or basket.narrative_id
    shortlist, excluded = _screen(
        basket, _enumerate_cn_funds(root), root / "data" / "narrative_holdings",
    )
    _write_screen(out, name, label, shortlist, excluded)
    if analyze:
        reports = _run_analyze(root, shortlist, db_path=db_path, quarter=quarter, role=role)
        if reports is None:
            print(
                f"ERROR: --analyze needs data/local.duckdb (run `irc ingest`) and a "
                f"cached snapshot quarter (run `irc fundamentals snapshot`). "
                f"Shortlist written to {out}.", file=sys.stderr,
            )
            return 2
        atomic_write_text(out / f"{name}_report.md", render_report_md(label, reports))
        atomic_write_text(out / f"{name}_report.json", render_report_json(label, reports))
    print(f"narrative {name} OK: {len(shortlist)} shortlisted, "
          f"{len(excluded)} excluded -> {out}")
    return 0
```

> Note: `_enumerate_cn_funds`, `fetch_top_holdings`, `analyze_fund`, and `_open_analyze_context` are module-level names so the integration tests monkeypatch them without touching the network or DuckDB. `_instr_by_id` / `_latest_quarter` are reused verbatim from `fund_eval_cmd` (untouched). File is ~110 lines (< 200).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git add src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(narrative): narrative_cmd orchestration (screen + analyze gate + min-overlap)"
```

---

## Task 10: CLI wiring — `irc narrative <name>`

**Files:**
- Modify: `src/irc/cli.py` (add a top-level `@main.command`, lazy import)
- Test: `tests/narrative/test_narrative_cmd.py` (append a Click invocation smoke test)

- [ ] **Step 1: Append the failing CLI smoke test**

Append to `tests/narrative/test_narrative_cmd.py`:

```python
from click.testing import CliRunner

from irc.cli import main as cli_main


def test_cli_narrative_unknown_exits_2(tmp_path: Path) -> None:
    _wire_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["narrative", "nope", "--repo-root", str(tmp_path), "--out", str(tmp_path / "o")],
    )
    assert result.exit_code == 2


def test_cli_narrative_screen_only(tmp_path: Path, monkeypatch) -> None:
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
    out = repo / "outputs" / "2026-06-02" / "narrative"
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["narrative", "compute_metals", "--repo-root", str(repo),
         "--out", str(out), "--screen-only"],
    )
    assert result.exit_code == 0
    assert (out / "compute_metals_shortlist.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -k cli -q`
Expected: FAIL — Click reports `No such command 'narrative'` (exit code 2 from missing command, but the screen-only test fails on a missing output file / unknown option).

- [ ] **Step 3: Add the command to `src/irc/cli.py`**

Insert after the `eval_funds` command block (after line ~162, before the `allocate` command):

```python
@main.command(help="Mine funds tied to a narrative; screen by holdings, optionally deep-analyse.")
@click.argument("name", required=True)
@click.option("--screen-only", "screen_only", is_flag=True, default=False,
              help="Stop after the light screen (default behaviour when no flag given).")
@click.option("--analyze", "analyze", is_flag=True, default=False,
              help="Run the screen then deep-analyse the shortlist (cache-only snapshot path).")
@click.option("--min-overlap", "min_overlap", type=float, default=None,
              help="Min basket-weight %% to qualify; overrides the config "
                   "thresholds.min_basket_weight_pct when given (spec §3.1).")
@click.option("--quarter", type=str, default=None,
              help="Snapshot quarter for --analyze (default: latest cached on disk).")
@click.option("--db", "db_path", type=click.Path(dir_okay=False), default=None,
              help="DuckDB path for --analyze (default data/local.duckdb).")
@click.option("--role", type=str, default="satellite_cn_metals",
              help="Role label stamped on synthesized analyze rows (display only).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Output dir (default outputs/<today>/narrative/).")
def narrative(
    name: str, screen_only: bool, analyze: bool, min_overlap: float | None,
    quarter: str | None, db_path: str | None, role: str, repo_root: str,
    out_dir: str | None,
) -> None:
    from irc.commands.narrative_cmd import run_narrative
    # --screen-only is the default; --analyze opts into the cache-only deep path.
    rc = run_narrative(
        repo_root=repo_root, name=name, analyze=(analyze and not screen_only),
        out_dir=out_dir, quarter=quarter, db_path=db_path, role=role,
        min_overlap=min_overlap,
    )
    raise SystemExit(rc)
```

> Note: `--min-overlap` (spec §3.1) overrides the config's `min_basket_weight_pct` via `dataclasses.replace` (immutable) before `_screen`; determinism is preserved because the override value is a pure input to `rank_shortlist`, not wall-clock/random state.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Verify the command is registered**

Run: `uv run irc narrative --help`
Expected: usage text mentioning `--screen-only`, `--analyze`, `--quarter`, `--db`, `--role`, `--out`, `--repo-root`.

- [ ] **Step 6: Commit**

```bash
git add src/irc/cli.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(narrative): wire irc narrative top-level command"
```

---

## Task 11: Acceptance + determinism gates

**Files:**
- Test: `tests/narrative/test_acceptance.py`

- [ ] **Step 1: Write the acceptance tests**

Create `tests/narrative/test_acceptance.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.report import render_report_md
from irc.narrative.schemas import NarrativeFundReport

REPO = Path(__file__).resolve().parents[2]
NARRATIVE_SRC = REPO / "src" / "irc" / "narrative"
_REF_RE = re.compile(r"\[ref:[0-9a-f]{16}\]")


def test_forbidden_jijgaikuang_indicator_absent() -> None:
    # CONTEXT.md "Static-profile invariant": 基金概况 forbidden in fetch code.
    for path in NARRATIVE_SRC.rglob("*.py"):
        assert "基金概况" not in path.read_text(encoding="utf-8"), path


def test_holdings_fetch_uses_only_portfolio_endpoint() -> None:
    src = (NARRATIVE_SRC / "holdings_fetch.py").read_text(encoding="utf-8")
    assert "fund_portfolio_hold_em" in src
    assert "基金概况" not in src


def test_rendered_analyze_report_satisfies_citation_regex() -> None:
    # Build a report from a REAL ThesisEvidence (16-hex citation_id computed in
    # __post_init__) — NOT a hand-injected string — and assert the rendered
    # md carries the locked `\[ref:[0-9a-f]{16}\]` marker (spec §5 acceptance).
    ev = ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary="601899 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id="000A", parent_fund_id=None, constituent_key=None,
    )
    rpt = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金",
        position_risk_level="high", risk_rationale="high — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=(), trim_triggers=(),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=(ev,),
    )
    md = render_report_md("算力金属", (rpt,))
    matches = _REF_RE.findall(md)
    assert matches  # at least one citation rendered
    for m in matches:
        assert re.fullmatch(r"\[ref:[0-9a-f]{16}\]", m)
    assert f"[ref:{ev.citation_id}]" in md
```

- [ ] **Step 2: Run the acceptance tests**

Run: `uv run pytest tests/narrative/test_acceptance.py -q`
Expected: PASS (3 passed).

- [ ] **Step 3: Verify run-twice byte-equality at the CLI level (manual)**

Run:
```bash
uv run irc narrative compute_metals --screen-only --out /tmp/narr1 --repo-root . || true
uv run irc narrative compute_metals --screen-only --out /tmp/narr2 --repo-root . || true
diff -r /tmp/narr1 /tmp/narr2 && echo "BYTE-EQUAL"
```
Expected: `BYTE-EQUAL` (the JSON shortlist/diagnostics are deterministic; this runs live AkShare so the holdings cache must be warm — run twice after the first populates `data/narrative_holdings/`). If AkShare is unavailable, the screen yields an empty shortlist + all funds in diagnostics, which is still byte-equal across the two runs.

- [ ] **Step 4: Commit**

```bash
git add tests/narrative/test_acceptance.py
git commit -m "test(narrative): acceptance — forbidden-literal + ref-regex + determinism"
```

---

## Task 12: Full-suite verification + final review

- [ ] **Step 1: Run the whole narrative suite**

Run: `uv run pytest tests/narrative/ -q`
Expected: all pass (live AkShare test skipped without `IRC_RUN_LIVE_AKSHARE=1`).

- [ ] **Step 2: Run lint across the new code**

Run: `uv run ruff check src/irc/narrative src/irc/commands/narrative_cmd.py tests/narrative`
Expected: `All checks passed!`

- [ ] **Step 3: Confirm no existing output / core was modified**

Run: `git diff --stat main -- src/irc/opportunity src/irc/discovery src/irc/fundamentals`
Expected: empty (no changes to reused cores).

- [ ] **Step 4: Run the broader suite to confirm no regression**

Run: `uv run pytest -q`
Expected: no new failures attributable to the narrative package.

- [ ] **Step 5: Verify line budgets**

Run: `wc -l src/irc/narrative/*.py src/irc/commands/narrative_cmd.py`
Expected: every file < 200 lines.

- [ ] **Step 6: Final commit (if any refactor in this task)**

```bash
git add -A
git commit -m "chore(narrative): full-suite verification + budgets" || echo "nothing to commit"
```

---

## Self-Review (run against the spec)

**Spec coverage:**
- §1 narrative→shortlist by holdings look-through → Tasks 2, 3, 9.
- §1 deepest per-fund analysis reuse → **Task 8 (`analyze.py`)** reuses `_build_input` → `build_opportunity_row` → `build_thesis_card` (→ `derive_dca_action` + `derive_risk_action`) → `derive_position_risk_level`, producing `opportunity_state`, `dca_action`, `risk_action`, falsification/trim triggers, review cadence, AND cited `thesis_evidence`. **Goal #2 is FULLY delivered** — faithful reuse, no core modified.
- §1 / §3.6 new `position_risk_level` ∈ {low, moderate, elevated, high, insufficient} → Task 4 (one test per driver + insufficient-on-gaps).
- §1 cited thesis evidence (holdings-level + fund-level) → Task 5 renderer reuses `select_citations` + the `opportunity/report.py:210` `[ref:...]` line format; Task 8 carries the real `thesis_evidence`; Task 11 acceptance asserts the locked `\[ref:[0-9a-f]{16}\]` regex on a real-evidence report.
- §1 reusable by config, no code change → Task 6 config loader; adding `ai`/`robots` is a new YAML only.
- §1 screen→analyze gate, cheap by default → Task 10 `--screen-only` default, `--analyze` opt-in (cache-only, mirroring `irc opportunity`).
- §2 non-goals respected → no `Theme` Literal change, no edits to `eval-funds`/`discover`/`score`/`opportunity`; verified in Task 12 Step 3.
- §3.1 CLI flags → Task 10 (`--screen-only`/`--analyze`/`--min-overlap`/`--quarter`/`--db`/`--role`/`--out`/`--repo-root`); `--min-overlap` overrides the config `min_basket_weight_pct` via `dataclasses.replace`, tested in Task 9 (`test_min_overlap_override_widens_shortlist`).
- §3.2 package files all created (Tasks 1–9) incl. the added `analyze.py` edge.
- §3.3 config schema → Task 6 YAML + loader.
- §3.4 data flow incl. "ensure snapshot" → Task 8 cache-only policy + Task 9 missing-data guard (resolved per CLAUDE.md "`irc opportunity` reads cached evidence").
- §3.5 symbol-first/name-second match + industry credit + either-threshold + stable sort + no-silent-drop → Tasks 2, 3, 9.
- §4 error handling: missing config fail-fast (Tasks 6, 9/10), no-holdings → diagnostics (Task 9), snapshot-fail → `insufficient` (Task 8), missing-db guard (Task 9), determinism (Tasks 5, 9, 11).
- §5 testing: pure unit (Tasks 2–5), config (6), analyze projection (8), integration (9), live double-gated (7), acceptance greps + real-evidence citation regex (11).
- §6 budgets → Task 12 Step 5.
- §7 DRAFT basket seeded + marked → Task 6 YAML comment.

**Placeholder scan:** no TBD/TODO; every code step shows full content.

**Type consistency:** `score_overlap`/`rank_shortlist` signatures, `OverlapResult`/`ShortlistRow`/`RiskEvalView`/`NarrativeFundReport` field names (the expanded `NarrativeFundReport` carries the real card states + `thesis_evidence: tuple[ThesisEvidence, ...]`), `derive_position_risk_level`'s `(level, rationale, drivers)` return, and the confirmed reuse signatures (`build_opportunity_row`, `PositionContext`, `build_thesis_card`) are consistent across Tasks 1–11.

**Known spec gaps / judgment calls (flag for the user):**
1. **`drawdown_3y` / `volatility` (§3.6):** not present on the `OpportunityRow` / `OpportunityInput` surface. Handled as an injected `metrics: dict[str, float]` that defaults empty (`{}` is what Task 8 passes today); those drivers fire only when a future caller supplies them (never fabricated). See Task 4 reuse note.
2. **Snapshot policy (§3.4 "ensure fundamentals snapshot (heavy fetch if missing/stale)") vs cache-only architecture:** RESOLVED as **cache-only** — the analyze phase mirrors `irc opportunity` (CLAUDE.md: reads cached evidence, does NOT fetch live; `fundamentals snapshot` is a deliberately-separate 5–15 min quarterly job). A missing per-fund snapshot → `evidence_insufficient` → `insufficient` (surfaced). If DuckDB or a cached quarter is entirely absent for `--analyze`, the screen outputs are written first, then an actionable error is printed and rc=2 (Task 9). Confirm this is the desired behaviour (the spec's "heavy fetch" phrasing is the one place it diverges from "mirroring `irc opportunity`").
3. **`--min-overlap` CLI override (§3.1):** WIRED per spec — overrides the config `min_basket_weight_pct` immutably via `dataclasses.replace` before `_screen` (Task 9/10). Determinism holds: the override is a pure input to `rank_shortlist`, not wall-clock/random state. Tested by `test_min_overlap_override_widens_shortlist`.
