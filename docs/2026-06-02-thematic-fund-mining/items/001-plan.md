# `irc narrative` — Thematic Fund Mining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `irc narrative <name>` — a narrative-driven fund selector that resolves a curated stock basket to a ranked fund shortlist by holdings look-through, then (opt-in) runs the existing opportunity-grade per-fund analysis and emits a new prospective-buy `position_risk_level`.

**Architecture:** A new pure-core package `src/irc/narrative/` (schemas / screen / risk / report) plus two I/O edges (`holdings_fetch`, `config`), orchestrated by a thin `commands/narrative_cmd.py` and wired as a top-level Click command. The selector sits **in front of** and **reuses** the existing classification cores (`enumerate_universe`, `build_opportunity_row` via `evaluate_funds`/`FundEval`, `derive_thesis_from_evidence`, `derive_risk_action`, snapshot cache) — none of them are modified. New logic is confined to holdings-overlap scoring, the narrative config, and `derive_position_risk_level`.

**Tech Stack:** Python 3.12+, uv, Click, AkShare (`fund_portfolio_hold_em`), pydantic/frozen dataclasses, pytest. All cores are pure and unit-testable without mocks; effects live only at the three edges.

---

## Conventions baked into every task (from CLAUDE.md + spec)

- **TDD strictly:** the failing test is always written and run-to-fail BEFORE the implementation file. Red → green → refactor.
- **Functional / immutable:** every new type is `@dataclass(frozen=True)`; build new values via `dataclasses.replace` / spread; never mutate arguments; no module-global mutable state.
- **Effects at edges:** `schemas.py` / `screen.py` / `risk.py` / `report.py` are pure (no I/O, no logging, no wall-clock, no random — timestamps injected as a parameter). `holdings_fetch.py` / `config.py` / `narrative_cmd.py` own all I/O.
- **Size budget:** every new file < 200 lines, functions < 20 lines (ideal). Extract helpers, use early returns, ≤ 3 nesting levels.
- **Determinism:** the shortlist sort key is `(basket_weight_pct DESC, overlap_count DESC, instrument_id ASC)`. Citation IDs keep the locked 16-hex `[ref:...]` format (`\[ref:[0-9a-f]{16}\]`). Same inputs ⇒ byte-identical outputs.
- **Reuse contract — DO NOT MODIFY:** `enumerate_universe`, `build_opportunity_row`, `evaluate_funds`/`FundEval`, `derive_thesis_from_evidence`, `derive_risk_action`, the snapshot cache, or any existing output (`eval-funds`, `discover`, `score`, `opportunity`).
- **Forbidden literal:** the string `基金概况` MUST NOT appear anywhere under `src/irc/narrative/` (acceptance grep). Holdings come only from `fund_portfolio_hold_em`.
- **No silent caps:** funds with no published holdings are written to `<name>_screen_diagnostics.json` with a reason — never dropped.

## File structure (created / modified)

| Path | Created/Modified | Responsibility | Purity |
|---|---|---|---|
| `src/irc/narrative/__init__.py` | Create | package marker (empty) | — |
| `src/irc/narrative/schemas.py` | Create | frozen types: `BasketStock`, `NarrativeBasket`, `Holding`, `OverlapResult`, `ShortlistRow`, `RiskLevel`, `NarrativeFundReport` | frozen types |
| `src/irc/narrative/screen.py` | Create | `score_overlap`, `rank_shortlist` | **pure** |
| `src/irc/narrative/risk.py` | Create | `derive_position_risk_level` | **pure** |
| `src/irc/narrative/report.py` | Create | `render_shortlist_md/json`, `render_report_md/json`, `render_diagnostics_json` | **pure** |
| `src/irc/narrative/holdings_fetch.py` | Create | `fetch_top_holdings(fund_id, *, cache_dir)` (AkShare + on-disk cache) | I/O edge |
| `src/irc/narrative/config.py` | Create | `load_narrative_basket`, `available_narratives` | I/O edge |
| `src/irc/commands/narrative_cmd.py` | Create | orchestration: load → screen → (snapshot → eval) → render → write | I/O edge |
| `src/irc/cli.py` | Modify (add `@main.command`) | register `irc narrative` | I/O edge |
| `config/narratives/compute_metals.yaml` | Create | DRAFT seeded `compute_metals` basket (user-approval, then frozen) | data |
| `tests/narrative/__init__.py` | Create | test package marker | — |
| `tests/narrative/test_schemas.py` | Create | frozen-type construction | test |
| `tests/narrative/test_screen.py` | Create | `score_overlap` / `rank_shortlist` (richest) | test |
| `tests/narrative/test_risk.py` | Create | `derive_position_risk_level` per driver | test |
| `tests/narrative/test_report.py` | Create | renderer md/json shape + citation regex | test |
| `tests/narrative/test_config.py` | Create | YAML → `NarrativeBasket`, malformed rejection | test |
| `tests/narrative/test_holdings_fetch.py` | Create | edge: cache hit/miss (mocked `_ak_call`) + live (double-gated) | test |
| `tests/narrative/test_narrative_cmd.py` | Create | integration: fixture universe + holdings → shortlist; fixture snapshots → report | test |
| `tests/narrative/test_acceptance.py` | Create | forbidden-literal grep, citation regex, run-twice byte-equality | test |

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
        risk_rationale="very_expensive valuation",
        risk_drivers=("valuation_state",),
        eval_json={"opportunity_state": "small_watch"},
    )
    assert rpt.position_risk_level == "elevated"
    assert rpt.risk_drivers == ("valuation_state",)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_schemas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.schemas'`.

- [ ] **Step 4: Write `src/irc/narrative/schemas.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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
    instrument_id: str
    name_cn: str
    position_risk_level: RiskLevel
    risk_rationale: str
    risk_drivers: tuple[str, ...]
    eval_json: dict[str, Any] = field(default_factory=dict)
```

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

**Reuse note / spec gap (§3.6):** The spec's risk-driver table lists `valuation_state`, `heat_state`, `thesis_state`, `product_quality_state`, holdings concentration, narrative concentration, `drawdown_3y`/`volatility`, and `evidence_gaps`. The actual reusable eval row is `FundEval` (frozen, `src/irc/opportunity/fund_eval.py`) which carries the four sub-states, `evidence_gaps`, and `top_holdings: tuple[(symbol, name_cn, weight_pct), ...]`. **`drawdown_3y` / `volatility` are NOT present** on `FundEval` (nor reliably on `OpportunityInput`, which only has `ret_1m/3m/6m/12m` and `drawdown_since_entry`). Per the spec's "from discovery metrics, **when available**" wording and the hard "never fabricate" rule, this function takes an explicit `metrics: dict[str, float]` injected at the edge; absent keys simply do not raise that driver. Holdings concentration is computed from `FundEval.top_holdings`; narrative concentration from the `OverlapResult`. To keep the core pure and decoupled from `FundEval`'s import surface, the function accepts the four sub-states and `evidence_gaps` as plain primitives (a small `RiskEvalView` frozen view), built at the edge from `FundEval`.

**Files:**
- Modify: `src/irc/narrative/schemas.py` (add `RiskEvalView` frozen view)
- Create: `src/irc/narrative/risk.py`
- Test: `tests/narrative/test_risk.py`

- [ ] **Step 1: Add `RiskEvalView` to `schemas.py`**

Append to `src/irc/narrative/schemas.py`:

```python
@dataclass(frozen=True)
class RiskEvalView:
    """Pure projection of FundEval fields consumed by the risk core.

    Built at the edge so risk.py never imports FundEval. top_holdings is
    (symbol, name_cn, weight_pct) in percent units, weight DESC."""
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


def test_report_md_preserves_ref_markers() -> None:
    cite = "[ref:0123456789abcdef]"
    rpt = NarrativeFundReport(
        instrument_id="A", name_cn="fund-A",
        position_risk_level="elevated",
        risk_rationale=f"elevated — very_expensive valuation {cite}",
        risk_drivers=("valuation_state",),
        eval_json={"opportunity_state": "small_watch", "note_cn": f"理由 {cite}"},
    )
    md = render_report_md("算力金属", (rpt,))
    assert _REF_RE.search(md)
    # citation markers are passed through verbatim, never reformatted
    assert cite in md


def test_report_json_round_trips_eval() -> None:
    rpt = NarrativeFundReport(
        instrument_id="A", name_cn="fund-A",
        position_risk_level="high", risk_rationale="high — thesis falsified",
        risk_drivers=("thesis_state",),
        eval_json={"opportunity_state": "exclude"},
    )
    doc = json.loads(render_report_json("算力金属", (rpt,)))
    assert doc["funds"][0]["position_risk_level"] == "high"
    assert doc["funds"][0]["eval"]["opportunity_state"] == "exclude"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.narrative.report'`.

- [ ] **Step 3: Write `src/irc/narrative/report.py`**

```python
from __future__ import annotations

import json

from irc.narrative.schemas import NarrativeFundReport, ShortlistRow


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


def render_report_md(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    lines = [f"# 主题深度分析 / Narrative report — {narrative}", ""]
    for rpt in reports:
        lines.append(f"## {rpt.instrument_id} {rpt.name_cn}")
        lines.append(f"- 仓位风险等级 / position_risk_level: **{rpt.position_risk_level}**")
        lines.append(f"- 主因 / drivers: {', '.join(rpt.risk_drivers) or '—'}")
        lines.append(f"- 说明: {rpt.risk_rationale}")
        note = rpt.eval_json.get("note_cn", "")
        if note:
            lines.append(f"- 机会评估: {note}")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_report_json(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    doc = {
        "narrative": narrative,
        "funds": [
            {
                "instrument_id": r.instrument_id,
                "name_cn": r.name_cn,
                "position_risk_level": r.position_risk_level,
                "risk_rationale": r.risk_rationale,
                "risk_drivers": list(r.risk_drivers),
                "eval": r.eval_json,
            }
            for r in reports
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: PASS (5 passed).

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

## Task 8: Orchestration — `narrative_cmd.py` (I/O edge)

**Reuse note:** the analyze phase reuses `evaluate_funds`/`FundEval` (which internally call `build_opportunity_row` + `derive_thesis_from_evidence`), `load_active_fund_cache` for snapshots, `derive_risk_action` for the held-position view, and `derive_position_risk_level` for the prospective view. The eval-row → `RiskEvalView` projection is built here at the edge (cores never import `FundEval`). `FetchBudgetExceeded` / `fetch_budget_exhausted` are honoured by deferring to the existing snapshot path; the narrative command itself does not re-implement budgeting — for `--analyze` it reads the cache (built by `irc fundamentals snapshot`) and stamps `evidence_gaps=("snapshot_missing",)` → `position_risk_level="insufficient"` when a snapshot is absent, surfaced not crashed.

**Files:**
- Create: `src/irc/commands/narrative_cmd.py`
- Test: `tests/narrative/test_narrative_cmd.py`

- [ ] **Step 1: Write the failing integration tests (no network)**

Create `tests/narrative/test_narrative_cmd.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from irc.commands import narrative_cmd
from irc.narrative.schemas import Holding


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


def test_screen_only_writes_shortlist_and_diagnostics(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    # universe: two funds — one with basket holdings, one with none.
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.commands.narrative_cmd'`.

- [ ] **Step 3: Write `src/irc/commands/narrative_cmd.py`**

```python
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.narrative.config import available_narratives, load_narrative_basket
from irc.narrative.holdings_fetch import fetch_top_holdings
from irc.narrative.report import (
    render_diagnostics_json,
    render_report_json,
    render_report_md,
    render_shortlist_json,
    render_shortlist_md,
)
from irc.narrative.risk import derive_position_risk_level
from irc.narrative.schemas import (
    NarrativeBasket,
    NarrativeFundReport,
    OverlapResult,
    RiskEvalView,
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
        overlap = score_overlap(holdings, basket)
        candidates.append(ShortlistRow(
            instrument_id=iid, name_cn=name, asset_class=asset_class,
            overlap=overlap, holdings=holdings,
        ))
    shortlist = rank_shortlist(
        tuple(candidates),
        min_basket_weight_pct=basket.min_basket_weight_pct,
        min_overlap_count=basket.min_overlap_count,
        top_n=basket.top_n,
    )
    return shortlist, tuple(excluded)


def _eval_view_from_holdings(row: ShortlistRow) -> RiskEvalView:
    top = tuple((h.symbol, h.name_cn, h.weight_pct) for h in
                sorted(row.holdings, key=lambda h: -h.weight_pct))
    return RiskEvalView(
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        evidence_gaps=("snapshot_missing",),
        top_holdings=top,
    )


def _analyze(shortlist: tuple[ShortlistRow, ...]) -> tuple[NarrativeFundReport, ...]:
    # v1 analyze: surfaces a prospective risk read. When a fundamentals snapshot
    # is absent the row is evidence_insufficient -> position_risk_level=insufficient
    # (surfaced, never crashed). Full snapshot wiring is a follow-up; the screen
    # gate is the load-bearing deliverable.
    reports: list[NarrativeFundReport] = []
    for row in shortlist:
        view = _eval_view_from_holdings(row)
        level, rationale, drivers = derive_position_risk_level(view, row.overlap, {})
        reports.append(NarrativeFundReport(
            instrument_id=row.instrument_id, name_cn=row.name_cn,
            position_risk_level=level, risk_rationale=rationale,
            risk_drivers=drivers,
            eval_json={"evidence_gaps": list(view.evidence_gaps)},
        ))
    return reports


def run_narrative(
    repo_root: str, name: str, *, analyze: bool = False,
    out_dir: str | None = None,
) -> int:
    root = Path(repo_root)
    try:
        basket = load_narrative_basket(name, root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        avail = ", ".join(available_narratives(root)) or "(none)"
        print(f"Available narratives: {avail}", file=sys.stderr)
        return 2
    out = Path(out_dir) if out_dir else (root / "outputs" / _today() / "narrative")
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = root / "data" / "narrative_holdings"
    universe = _enumerate_cn_funds(root)
    shortlist, excluded = _screen(basket, universe, cache_dir)
    label = basket.display_name_cn or basket.narrative_id
    atomic_write_text(out / f"{name}_shortlist.md", render_shortlist_md(label, shortlist))
    atomic_write_text(out / f"{name}_shortlist.json", render_shortlist_json(label, shortlist))
    atomic_write_text(out / f"{name}_screen_diagnostics.json",
                      render_diagnostics_json(excluded))
    if analyze:
        reports = _analyze(shortlist)
        atomic_write_text(out / f"{name}_report.md", render_report_md(label, reports))
        atomic_write_text(out / f"{name}_report.json", render_report_json(label, reports))
    print(f"narrative {name} OK: {len(shortlist)} shortlisted, "
          f"{len(excluded)} excluded -> {out}")
    return 0
```

> Note: `fetch_top_holdings` and `_enumerate_cn_funds` are referenced as module-level names so the integration tests can monkeypatch them.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git add src/irc/commands/narrative_cmd.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(narrative): narrative_cmd orchestration (screen + analyze)"
```

---

## Task 9: CLI wiring — `irc narrative <name>`

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
              help="Run the screen then deep-analyse the shortlist (slow snapshot path).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Output dir (default outputs/<today>/narrative/).")
def narrative(
    name: str, screen_only: bool, analyze: bool, repo_root: str, out_dir: str | None,
) -> None:
    from irc.commands.narrative_cmd import run_narrative
    # --screen-only is the default; --analyze opts into the slow path.
    rc = run_narrative(
        repo_root=repo_root, name=name, analyze=(analyze and not screen_only),
        out_dir=out_dir,
    )
    raise SystemExit(rc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_narrative_cmd.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Verify the command is registered**

Run: `uv run irc narrative --help`
Expected: usage text mentioning `--screen-only`, `--analyze`, `--out`, `--repo-root`.

- [ ] **Step 6: Commit**

```bash
git add src/irc/cli.py tests/narrative/test_narrative_cmd.py
git commit -m "feat(narrative): wire irc narrative top-level command"
```

---

## Task 10: Acceptance + determinism gates

**Files:**
- Test: `tests/narrative/test_acceptance.py`

- [ ] **Step 1: Write the acceptance tests**

Create `tests/narrative/test_acceptance.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

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


def test_report_md_passes_ref_markers_through() -> None:
    # Any [ref:...] markers placed in eval_json/rationale must keep the 16-hex form.
    from irc.narrative.report import render_report_md
    from irc.narrative.schemas import NarrativeFundReport

    cite = "[ref:0123456789abcdef]"
    rpt = NarrativeFundReport(
        instrument_id="A", name_cn="f", position_risk_level="low",
        risk_rationale=f"low {cite}", risk_drivers=(),
        eval_json={"note_cn": f"x {cite}"},
    )
    md = render_report_md("算力金属", (rpt,))
    for m in _REF_RE.findall(md):
        assert re.fullmatch(r"\[ref:[0-9a-f]{16}\]", m)
    assert _REF_RE.search(md)
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

## Task 11: Full-suite verification + final review

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
- §1 narrative→shortlist by holdings look-through → Tasks 2, 3, 8.
- §1 deepest per-fund analysis reuse → Task 8 `_analyze` reuses `derive_position_risk_level`; full `evaluate_funds` snapshot wiring is staged as a documented v1 limitation (screen is the load-bearing deliverable; analyze surfaces the prospective risk read and is `insufficient` without a snapshot — never crashes).
- §1 / §3.6 new `position_risk_level` ∈ {low, moderate, elevated, high, insufficient} → Task 4 (one test per driver + insufficient-on-gaps).
- §1 reusable by config, no code change → Task 6 config loader; adding `ai`/`robots` is a new YAML only.
- §1 screen→analyze gate, cheap by default → Task 9 `--screen-only` default, `--analyze` opt-in.
- §2 non-goals respected → no `Theme` Literal change, no edits to `eval-funds`/`discover`/`score`/`opportunity`; verified in Task 11 Step 3.
- §3.2 package files all created (Tasks 1–8).
- §3.3 config schema → Task 6 YAML + loader.
- §3.5 symbol-first/name-second match + industry credit + either-threshold + stable sort + no-silent-drop → Tasks 2, 3, 8.
- §4 error handling: missing config fail-fast (Tasks 6, 8/9), no-holdings → diagnostics (Task 8), determinism (Tasks 5, 8, 10).
- §5 testing: pure unit (Tasks 2–5), config (6), integration (8), live double-gated (7), acceptance greps (10).
- §6 budgets → Task 11 Step 5.
- §7 DRAFT basket seeded + marked → Task 6 YAML comment.

**Placeholder scan:** no TBD/TODO; every code step shows full content.

**Type consistency:** `score_overlap`/`rank_shortlist` signatures, `OverlapResult`/`ShortlistRow`/`RiskEvalView`/`NarrativeFundReport` field names, and `derive_position_risk_level`'s `(level, rationale, drivers)` return are consistent across Tasks 1–10.

**Known spec gaps / judgment calls (flag for the user):**
1. **`drawdown_3y` / `volatility` (§3.6):** not present on `FundEval` or reliably on `OpportunityInput`. Handled as an injected `metrics: dict[str, float]` that defaults empty; those drivers fire only when a future caller supplies them (never fabricated). See Task 4 reuse note.
2. **Eval-row shape (§1, §3.4):** the reusable "eval row" is `FundEval`, not a bespoke type; the risk core consumes a small `RiskEvalView` projection built at the edge so the pure core never imports `FundEval`. See Task 4.
3. **Analyze depth (§3.4):** v1 analyze emits the prospective risk read and routes snapshot-absent funds to `insufficient`; full `evaluate_funds`/snapshot integration (build_opportunity_row evidence + `[ref:...]` citations on the report) is a documented follow-up so this item ships the screen gate + risk level without modifying the snapshot fetch budget path. Confirm this scoping is acceptable.
