# Opportunity / Thesis / Discipline Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic opportunity / thesis / discipline sidecar layer that classifies each candidate by valuation + heat + thesis + product-quality state, builds durable thesis cards, derives DCA + risk actions (without auto-selling on drawdown), and emits machine-readable + Chinese human-readable reports — implementing the design in `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md`.

**Architecture:** Pure-function modules under `src/irc/opportunity/` (lookthrough, states, selection, cards, discipline, report) consume scoring + universe + metrics + holdings, return frozen dataclasses. The CLI wrapper `src/irc/commands/opportunity_cmd.py` is the only I/O entry. The layer runs as a sidecar **after** `score` and **before** `memo` / `decision`; it does not change existing allocation behaviour in this first implementation. A new eval stage `evals/opportunity/` enforces thesis completeness, drawdown-not-auto-sell, same-theme limits, hot-chase prevention, valid action enums, and absence of external-worktree paths.

**Tech Stack:** Python 3.12+, `pydantic` (frozen models for config), `dataclasses` (frozen for internal types), `click` (CLI), `pyyaml`, `pandas` (already a project dep), `pytest`. Reuses existing `evals/_shared/{status,report_schema}`, `irc.io_utils.atomic_write_text`, `irc.config_loader.load_repo_configs`.

---

## Required Reading Before Starting

The engineer implementing this plan **must** read these files first — they define the patterns the new code has to follow:

- `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md` — full spec; especially "Opportunity Identification", "Same-Theme Fund Selection", "Sell And Trim Discipline", and "Acceptance Criteria".
- `/Users/snow/.claude/CLAUDE.md` — global FP / TDD / immutability rules. Every pure function in `src/irc/opportunity/` must be deterministic, side-effect free, return new values via spread (`{**state, ...}` for dicts, `dataclasses.replace` for dataclasses). No mutation of inputs. Tests written before implementation.
- `src/irc/scoring/factors/valuation_cost.py` — example of the project's pure-function style (frozen `FactorScore` dataclass, no I/O).
- `src/irc/commands/score_cmd.py` and `src/irc/commands/allocate_cmd.py` — pattern for CLI wrappers (I/O at the edge, `atomic_write_text`, `_today()` helper, falls back to latest output when today's missing).
- `evals/scoring/runner.py` and `evals/scoring/metrics.py` — pattern for eval metric + runner.
- `src/irc/decision/completeness.py` — existing `MIN_BUY_COMPLETENESS` and `is_missing` helper, reused below.

---

## File Structure

**New files under `src/irc/opportunity/`** (each file = one responsibility, < 200 lines):

| File | Responsibility |
| :--- | :--- |
| `__init__.py` | Empty marker. |
| `types.py` | Literal enums (`ValuationState`, `HeatState`, `ThesisState`, `ProductQualityState`, `OpportunityState`, `DcaAction`, `RiskAction`) + frozen dataclasses (`LookthroughTarget`, `OpportunityInput`, `OpportunityRow`, `ThesisCard`, `DisciplineRow`). |
| `lookthrough.py` | `map_lookthrough(instrument, theme_thesis_keys) -> LookthroughTarget`. Maps broad / sector / QDII / bond / gold / active funds to underlying-exposure targets. |
| `states.py` | Four classifiers: `classify_valuation`, `classify_heat`, `classify_thesis`, `classify_product_quality`, plus the composer `compose_opportunity_state`. |
| `selection.py` | Same-index reducer `reduce_same_index`, same-theme reducer `reduce_same_theme`, active-fund demoter `demote_unstable_active`. |
| `cards.py` | `build_thesis_card(row) -> ThesisCard`. |
| `discipline.py` | `derive_dca_action(row) -> DcaAction`, `derive_risk_action(row, drawdown, target_band_state) -> RiskAction`. |
| `report.py` | `compose_opportunity_report(rows)`, `compose_thesis_cards_yaml(cards)`, `compose_discipline_markdown(rows)` — all pure, return strings or dict-trees. |

**New CLI wrapper:** `src/irc/commands/opportunity_cmd.py` — reads scoring/account/universe/metrics, runs pure pipeline, writes outputs.

**New CLI registration:** edit `src/irc/cli.py` to add `irc opportunity` command.

**New evals:** `evals/opportunity/__init__.py`, `evals/opportunity/metrics.py`, `evals/opportunity/runner.py`. Update `src/irc/commands/eval_cmd.py` to register the stage.

**New config (optional):** `config/opportunity/theme_thesis.yaml` — per-theme thesis state for `intact | under_pressure | falsified | evidence_insufficient`. Loader treats missing file as "all themes `evidence_insufficient`".

**New tests:**
- `tests/opportunity/__init__.py`
- `tests/opportunity/test_lookthrough.py`
- `tests/opportunity/test_states.py`
- `tests/opportunity/test_selection.py`
- `tests/opportunity/test_cards.py`
- `tests/opportunity/test_discipline.py`
- `tests/opportunity/test_report.py`
- `tests/commands/test_opportunity_cmd.py`
- `tests/evals/test_opportunity_metrics.py`
- `tests/evals/test_opportunity_runner.py`
- `tests/integration/test_opportunity_pipeline.py`
- `tests/integration/test_decision_without_opportunity.py`

**Modified files:**
- `src/irc/cli.py` — add `opportunity` command registration.
- `src/irc/commands/eval_cmd.py` — register `opportunity` stage.

---

## Working Directory & Branch

This work happens in the worktree at `/Users/snow/.codex/worktrees/6a85/investment-research-copilot`. The branch is currently in detached-HEAD on commit `72a2e8f docs: design opportunity thesis discipline`.

**Before starting:** create a feature branch from current HEAD:

```bash
git checkout -b feat/opportunity-thesis-discipline
```

All commits below land on this branch. The plan does not push or create a PR — that is a follow-up after the user reviews the implementation.

---

## Conventions Used Below

- **Imports**: `from __future__ import annotations` at the top of every new module.
- **Pure function rule**: no `print`, no file I/O, no `datetime.now()` inside `src/irc/opportunity/*` modules. Pass anything time-dependent (e.g. report date) in as an argument.
- **Frozen everything**: dataclasses use `@dataclass(frozen=True)`; pydantic models inherit `FrozenModel` (already in `src/irc/schemas/_types.py`).
- **Test command**: `uv run pytest tests/opportunity/<file> -v` for unit tests; `uv run pytest tests/ -v` for the full suite.
- **Commit style**: follow existing commit message voice — `feat:`, `test:`, `fix:`, `docs:` prefix; body wrapped at 72 chars. One logical change per commit; commit after each task unless noted.

---

## Task 1: Scaffold the opportunity package and shared types

**Files:**
- Create: `src/irc/opportunity/__init__.py`
- Create: `src/irc/opportunity/types.py`
- Create: `tests/opportunity/__init__.py`
- Create: `tests/opportunity/test_types.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_types.py`:

```python
from __future__ import annotations
import pytest
from dataclasses import FrozenInstanceError

from irc.opportunity.types import (
    LookthroughTarget,
    OpportunityInput,
    OpportunityRow,
    ThesisCard,
    DisciplineRow,
    VALUATION_STATES,
    HEAT_STATES,
    THESIS_STATES,
    PRODUCT_QUALITY_STATES,
    OPPORTUNITY_STATES,
    DCA_ACTIONS,
    RISK_ACTIONS,
)


def test_state_enums_match_spec():
    assert VALUATION_STATES == (
        "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
    )
    assert HEAT_STATES == (
        "cold", "normal", "crowded", "overheated", "evidence_insufficient",
    )
    assert THESIS_STATES == (
        "intact", "under_pressure", "falsified", "evidence_insufficient",
    )
    assert PRODUCT_QUALITY_STATES == (
        "strong", "acceptable", "weak", "poor", "evidence_insufficient",
    )
    assert OPPORTUNITY_STATES == ("core_dca", "small_watch", "pause_wait", "exclude")
    assert DCA_ACTIONS == (
        "accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy",
    )
    assert RISK_ACTIONS == ("none", "review_required", "trim_review", "exit_review")


def test_lookthrough_target_is_frozen():
    target = LookthroughTarget(
        kind="broad_index",
        key="csi300",
        display_cn="沪深300",
    )
    with pytest.raises(FrozenInstanceError):
        target.kind = "sector"  # type: ignore[misc]


def test_opportunity_row_required_fields():
    row = OpportunityRow(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        opportunity_reason="底层指数估值合理，热度正常，长期逻辑完好。",
        evidence_gaps=(),
    )
    assert row.opportunity_state == "core_dca"


def test_thesis_card_defaults_immutable_collections():
    card = ThesisCard(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        role="core_cn_equity",
        lookthrough_target="沪深300",
        entry_reason="核心宽基指数底仓。",
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        falsification_triggers=(),
        trim_triggers=(),
        do_not_sell_just_because=("drawdown_since_entry >= 0.20",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
    )
    assert isinstance(card.falsification_triggers, tuple)
    assert isinstance(card.do_not_sell_just_because, tuple)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/opportunity/test_types.py -v
```

Expected: ImportError / ModuleNotFoundError for `irc.opportunity.types`.

- [ ] **Step 3: Create the package marker**

Write `src/irc/opportunity/__init__.py`:

```python
```

(Empty file; Python treats the directory as a package.)

Also write `tests/opportunity/__init__.py`:

```python
```

- [ ] **Step 4: Implement the types module**

Write `src/irc/opportunity/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


VALUATION_STATES: tuple[str, ...] = (
    "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
)
HEAT_STATES: tuple[str, ...] = (
    "cold", "normal", "crowded", "overheated", "evidence_insufficient",
)
THESIS_STATES: tuple[str, ...] = (
    "intact", "under_pressure", "falsified", "evidence_insufficient",
)
PRODUCT_QUALITY_STATES: tuple[str, ...] = (
    "strong", "acceptable", "weak", "poor", "evidence_insufficient",
)
OPPORTUNITY_STATES: tuple[str, ...] = ("core_dca", "small_watch", "pause_wait", "exclude")
DCA_ACTIONS: tuple[str, ...] = (
    "accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy",
)
RISK_ACTIONS: tuple[str, ...] = (
    "none", "review_required", "trim_review", "exit_review",
)


ValuationState = Literal[
    "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
]
HeatState = Literal["cold", "normal", "crowded", "overheated", "evidence_insufficient"]
ThesisState = Literal["intact", "under_pressure", "falsified", "evidence_insufficient"]
ProductQualityState = Literal["strong", "acceptable", "weak", "poor", "evidence_insufficient"]
OpportunityState = Literal["core_dca", "small_watch", "pause_wait", "exclude"]
DcaAction = Literal["accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy"]
RiskAction = Literal["none", "review_required", "trim_review", "exit_review"]


LookthroughKind = Literal[
    "broad_index", "sector_theme", "qdii_us", "qdii_hk", "bond", "gold", "active_fund",
]


@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind
    key: str          # canonical key, e.g. "csi300", "semiconductor", "nasdaq100"
    display_cn: str   # 中文展示名，例如 "沪深300"


@dataclass(frozen=True)
class OpportunityInput:
    """Raw per-instrument metrics consumed by the state classifiers.

    All fields except instrument_id are optional. Missing data drives
    `evidence_insufficient` rather than fabricated states.
    """
    instrument_id: str
    asset_class: str
    market: str
    theme: str | None = None
    tracked_index: str | None = None
    name_cn: str = ""
    role: str = ""
    is_holding: bool = False
    portfolio_weight: float | None = None
    target_band_low: float | None = None
    target_band_high: float | None = None
    drawdown_since_entry: float | None = None
    valuation_percentile_self: float | None = None
    valuation_percentile_vs_benchmark: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None
    premium_discount_pct: float | None = None
    flow_pct_30d: float | None = None
    expense_ratio: float | None = None
    aum_cny: float | None = None
    aum_stability_pct: float | None = None
    tracking_error: float | None = None
    manager_tenure_years: float | None = None
    holdings_concentration_top10: float | None = None
    style_drift_flag: bool | None = None
    venue_compatible: bool = True


@dataclass(frozen=True)
class OpportunityRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    lookthrough_target: LookthroughTarget
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    opportunity_reason: str
    evidence_gaps: tuple[str, ...]


@dataclass(frozen=True)
class ThesisCard:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    role: str
    lookthrough_target: str
    entry_reason: str
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    falsification_triggers: tuple[str, ...]
    trim_triggers: tuple[str, ...]
    do_not_sell_just_because: tuple[str, ...]
    review_cadence: str
    evidence_gaps: tuple[str, ...]


@dataclass(frozen=True)
class DisciplineRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    note_cn: str
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/opportunity/test_types.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/__init__.py src/irc/opportunity/types.py tests/opportunity/__init__.py tests/opportunity/test_types.py
git commit -m "feat(opportunity): scaffold types and state enums"
```

---

## Task 2: Lookthrough mapping

**Files:**
- Create: `src/irc/opportunity/lookthrough.py`
- Create: `tests/opportunity/test_lookthrough.py`

The lookthrough layer maps an instrument to its underlying-exposure target. It uses three sources, in order:

1. Explicit `tracked_index` on `Instrument` (e.g. "csi300", "nasdaq100").
2. `theme` on `Instrument` (e.g. "semiconductor").
3. Asset class + market for fallbacks (bond, gold, active funds).

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_lookthrough.py`:

```python
from __future__ import annotations
import pytest

from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityInput


def _make(**kwargs) -> OpportunityInput:
    base = {
        "instrument_id": "X", "asset_class": "cn_etf", "market": "cn_on_exchange",
    }
    base.update(kwargs)
    return OpportunityInput(**base)


def test_broad_index_etf_maps_to_broad_index_kind():
    target = map_lookthrough(_make(
        instrument_id="510300", asset_class="cn_etf",
        tracked_index="csi300", theme="broad",
    ))
    assert target.kind == "broad_index"
    assert target.key == "csi300"
    assert target.display_cn == "沪深300"


def test_sector_etf_uses_theme_when_tracked_index_unknown():
    target = map_lookthrough(_make(
        instrument_id="512760", asset_class="cn_etf",
        tracked_index=None, theme="semiconductor",
    ))
    assert target.kind == "sector_theme"
    assert target.key == "semiconductor"
    assert target.display_cn == "半导体"


def test_us_qdii_maps_to_qdii_us_kind():
    target = map_lookthrough(_make(
        instrument_id="513100", asset_class="us_etf",
        tracked_index="nasdaq100", theme="tech",
    ))
    assert target.kind == "qdii_us"
    assert target.key == "nasdaq100"
    assert target.display_cn == "纳斯达克100"


def test_hk_qdii_maps_to_qdii_hk_kind():
    target = map_lookthrough(_make(
        instrument_id="513180", asset_class="hk_etf",
        tracked_index="hstech", theme="tech",
    ))
    assert target.kind == "qdii_hk"
    assert target.key == "hstech"
    assert target.display_cn == "恒生科技"


def test_bond_fund_maps_to_bond_kind():
    target = map_lookthrough(_make(
        instrument_id="511010", asset_class="cn_bond_fund",
        tracked_index=None, theme=None,
    ))
    assert target.kind == "bond"
    assert target.key == "cn_bond"


def test_gold_maps_to_gold_kind():
    target = map_lookthrough(_make(
        instrument_id="518880", asset_class="gold",
        tracked_index=None, theme="metals",
    ))
    assert target.kind == "gold"
    assert target.key == "gold"


def test_active_cn_equity_fund_uses_theme_or_active_fund_fallback():
    # theme present -> sector_theme; theme absent -> active_fund
    with_theme = map_lookthrough(_make(
        instrument_id="000001", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme="consumer",
    ))
    assert with_theme.kind == "sector_theme"
    assert with_theme.key == "consumer"

    without_theme = map_lookthrough(_make(
        instrument_id="000002", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme=None,
    ))
    assert without_theme.kind == "active_fund"
    assert without_theme.key == "active_cn_equity"


def test_unknown_index_falls_back_to_kind_with_display_key():
    target = map_lookthrough(_make(
        instrument_id="999999", asset_class="cn_etf",
        tracked_index="some_obscure_index_v2", theme="broad",
    ))
    assert target.kind == "broad_index"
    assert target.key == "some_obscure_index_v2"
    assert target.display_cn  # non-empty fallback
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/opportunity/test_lookthrough.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the lookthrough module**

Write `src/irc/opportunity/lookthrough.py`:

```python
from __future__ import annotations

from irc.opportunity.types import LookthroughTarget, OpportunityInput


_BROAD_INDEX_DISPLAY: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "csi_a500": "中证A500",
    "sse50": "上证50",
    "star50": "科创50",
    "chinext": "创业板",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "红利低波",
}

_SECTOR_THEME_DISPLAY: dict[str, str] = {
    "semiconductor": "半导体",
    "tech": "科技",
    "healthcare": "医药",
    "new_energy": "新能源",
    "consumer": "消费",
    "finance": "金融",
    "defense": "军工",
    "metals": "有色金属",
    "real_estate": "房地产",
    "soe": "国企改革",
    "dividend": "红利",
    "broad": "宽基",
}

_QDII_US_DISPLAY: dict[str, str] = {
    "nasdaq100": "纳斯达克100",
    "sp500": "标普500",
    "dow_jones": "道琼斯",
    "us50": "美国50",
    "us_equity": "美股大盘",
}

_QDII_HK_DISPLAY: dict[str, str] = {
    "hstech": "恒生科技",
    "hsi": "恒生指数",
    "hs_dividend": "港股红利",
    "china_internet": "中概互联",
}

_BROAD_INDEX_KEYS: frozenset[str] = frozenset(_BROAD_INDEX_DISPLAY.keys())
_QDII_US_KEYS: frozenset[str] = frozenset(_QDII_US_DISPLAY.keys())
_QDII_HK_KEYS: frozenset[str] = frozenset(_QDII_HK_DISPLAY.keys())


def _display_for(key: str, table: dict[str, str], fallback: str) -> str:
    return table.get(key, fallback)


def map_lookthrough(inp: OpportunityInput) -> LookthroughTarget:
    """Map an instrument to its underlying-exposure target.

    Order of precedence: tracked_index → theme → asset_class fallback.
    Missing or unknown values fall back deterministically; this function
    never raises on unrecognised input.
    """
    if inp.asset_class == "gold":
        return LookthroughTarget("gold", "gold", "黄金")

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget("bond", "cn_bond", "中国债券")

    tracked = (inp.tracked_index or "").strip().lower() or None
    theme = (inp.theme or "").strip().lower() or None

    if inp.asset_class == "us_etf":
        key = tracked or theme or "us_equity"
        return LookthroughTarget(
            "qdii_us", key, _display_for(key, _QDII_US_DISPLAY, key),
        )

    if inp.asset_class == "hk_etf":
        key = tracked or theme or "hsi"
        return LookthroughTarget(
            "qdii_hk", key, _display_for(key, _QDII_HK_DISPLAY, key),
        )

    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget("broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked])
        if tracked in _QDII_US_KEYS:
            return LookthroughTarget("qdii_us", tracked, _QDII_US_DISPLAY[tracked])
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget("qdii_hk", tracked, _QDII_HK_DISPLAY[tracked])
        # Unknown index: classify as broad_index by default but keep the raw key
        # so downstream code can still group by it. Display falls back to the key itself.
        return LookthroughTarget("broad_index", tracked, tracked)

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget("sector_theme", theme, _SECTOR_THEME_DISPLAY[theme])

    if inp.asset_class == "cn_equity_fund":
        return LookthroughTarget("active_fund", "active_cn_equity", "主动权益")

    return LookthroughTarget("broad_index", "unknown", "未知底层")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/opportunity/test_lookthrough.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough.py
git commit -m "feat(opportunity): pure lookthrough mapping for funds/ETFs"
```

---

## Task 3: Valuation state classifier

**Files:**
- Create: `src/irc/opportunity/states.py`
- Create: `tests/opportunity/test_states.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_states.py`:

```python
from __future__ import annotations
import pytest

from irc.opportunity.states import classify_valuation
from irc.opportunity.types import OpportunityInput


def _make(**kwargs) -> OpportunityInput:
    base = {"instrument_id": "X", "asset_class": "cn_etf", "market": "cn_on_exchange"}
    base.update(kwargs)
    return OpportunityInput(**base)


def test_valuation_evidence_insufficient_when_no_data():
    state, reason = classify_valuation(_make())
    assert state == "evidence_insufficient"
    assert "valuation" in reason.lower() or "估值" in reason


def test_valuation_cheap_when_self_percentile_below_20():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.15))
    assert state == "cheap"


def test_valuation_reasonable_low_when_self_percentile_20_to_40():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.30))
    assert state == "reasonable_low"


def test_valuation_fair_when_self_percentile_40_to_70():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.55))
    assert state == "fair"


def test_valuation_expensive_when_self_percentile_70_to_90():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.80))
    assert state == "expensive"


def test_valuation_very_expensive_when_self_percentile_above_90():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.95))
    assert state == "very_expensive"


def test_valuation_uses_vs_benchmark_when_self_history_missing():
    # No self percentile, but vs-benchmark percentile available.
    state, _ = classify_valuation(_make(
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=0.10,
    ))
    assert state == "cheap"


def test_valuation_never_infers_cheapness_from_drawdown_alone():
    # Big drawdown_since_entry but no valuation evidence -> still insufficient.
    state, _ = classify_valuation(_make(drawdown_since_entry=0.30))
    assert state == "evidence_insufficient"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `classify_valuation`**

Write `src/irc/opportunity/states.py`:

```python
from __future__ import annotations

from irc.opportunity.types import (
    HeatState,
    OpportunityInput,
    OpportunityState,
    ProductQualityState,
    ThesisState,
    ValuationState,
)


def _percentile(inp: OpportunityInput) -> float | None:
    """Prefer self-history percentile; fall back to vs-benchmark."""
    if inp.valuation_percentile_self is not None:
        return inp.valuation_percentile_self
    return inp.valuation_percentile_vs_benchmark


def classify_valuation(inp: OpportunityInput) -> tuple[ValuationState, str]:
    """Classify valuation state. Bands:
      cheap: pct < 0.20
      reasonable_low: 0.20 ≤ pct < 0.40
      fair: 0.40 ≤ pct < 0.70
      expensive: 0.70 ≤ pct < 0.90
      very_expensive: pct ≥ 0.90
    Drawdown alone is NEVER evidence of cheapness.
    """
    pct = _percentile(inp)
    if pct is None:
        return "evidence_insufficient", "估值数据缺失，未能判定。"
    if pct < 0.20:
        return "cheap", f"估值百分位 {pct:.0%} 偏低。"
    if pct < 0.40:
        return "reasonable_low", f"估值百分位 {pct:.0%} 偏低但未极低。"
    if pct < 0.70:
        return "fair", f"估值百分位 {pct:.0%} 中性。"
    if pct < 0.90:
        return "expensive", f"估值百分位 {pct:.0%} 偏高。"
    return "very_expensive", f"估值百分位 {pct:.0%} 极高。"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): classify valuation state from percentiles"
```

---

## Task 4: Heat state classifier

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Modify: `tests/opportunity/test_states.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/opportunity/test_states.py`:

```python
from irc.opportunity.states import classify_heat


def test_heat_insufficient_when_no_data():
    state, _ = classify_heat(_make())
    assert state == "evidence_insufficient"


def test_heat_cold_when_returns_negative_and_no_crowding():
    state, _ = classify_heat(_make(
        ret_3m=-0.05, ret_6m=-0.10, ret_12m=-0.15,
        premium_discount_pct=-0.005,
    ))
    assert state == "cold"


def test_heat_normal_when_mixed_returns():
    state, _ = classify_heat(_make(
        ret_3m=0.02, ret_6m=0.05, ret_12m=0.08,
        premium_discount_pct=0.0,
    ))
    assert state == "normal"


def test_heat_crowded_when_recent_returns_high():
    state, _ = classify_heat(_make(
        ret_1m=0.10, ret_3m=0.25, ret_6m=0.35,
        premium_discount_pct=0.01,
    ))
    assert state == "crowded"


def test_heat_overheated_when_extreme_returns_or_premium():
    state, _ = classify_heat(_make(
        ret_3m=0.40, ret_6m=0.55,
        premium_discount_pct=0.03,
    ))
    assert state == "overheated"


def test_strong_recent_returns_do_not_lower_heat():
    """Recent strong returns should INCREASE heat risk, not decrease it."""
    state, _ = classify_heat(_make(
        ret_1m=0.15, ret_3m=0.30,
        premium_discount_pct=0.025,
    ))
    assert state in ("crowded", "overheated")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/opportunity/test_states.py -v -k "heat"
```

Expected: ImportError for `classify_heat`.

- [ ] **Step 3: Implement `classify_heat`**

Append to `src/irc/opportunity/states.py`:

```python
def _heat_score(inp: OpportunityInput) -> tuple[float, int]:
    """Compute a heat score in [-1, 1] and count of evidence pieces.

    Positive values mean hotter (crowded / overheated). Negative means cold.
    Returns (score, evidence_count). Caller treats evidence_count < 2 as
    insufficient.
    """
    contributions: list[float] = []
    if inp.ret_1m is not None:
        # 0.10 monthly -> +0.5; -0.05 monthly -> -0.25
        contributions.append(max(-1.0, min(1.0, inp.ret_1m * 5.0)))
    if inp.ret_3m is not None:
        # 0.25 quarterly -> +0.625
        contributions.append(max(-1.0, min(1.0, inp.ret_3m * 2.5)))
    if inp.ret_6m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_6m * 1.5)))
    if inp.ret_12m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_12m * 1.0)))
    if inp.premium_discount_pct is not None:
        # 1% premium -> +0.4; -0.5% discount -> -0.2
        contributions.append(max(-1.0, min(1.0, inp.premium_discount_pct * 40.0)))
    if inp.flow_pct_30d is not None:
        contributions.append(max(-1.0, min(1.0, inp.flow_pct_30d * 5.0)))
    if not contributions:
        return 0.0, 0
    return sum(contributions) / len(contributions), len(contributions)


def classify_heat(inp: OpportunityInput) -> tuple[HeatState, str]:
    """Classify trading heat / crowding state.

    Recent strong returns INCREASE heat risk. This is intentional — the
    behavioural goal is to stop the user chasing winners.
    """
    score, n = _heat_score(inp)
    if n < 2:
        return "evidence_insufficient", "热度数据不足，未能判定。"
    if score >= 0.55:
        return "overheated", f"近期涨幅与溢价共同显示极度过热（score={score:.2f}）。"
    if score >= 0.30:
        return "crowded", f"近期涨幅较大，存在追高风险（score={score:.2f}）。"
    if score <= -0.20:
        return "cold", f"近期表现偏弱，市场关注度低（score={score:.2f}）。"
    return "normal", f"热度处于正常区间（score={score:.2f}）。"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: all heat tests pass plus the prior 8 valuation tests.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): classify heat state with anti-chasing bias"
```

---

## Task 5: Thesis state classifier

The thesis state comes from a per-theme thesis table (curated, quarterly-refreshed) plus per-instrument signals (style drift flag, manager change — both optional). The default for any theme with no entry is `evidence_insufficient` — the system must not fabricate thesis confidence.

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Modify: `tests/opportunity/test_states.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/opportunity/test_states.py`:

```python
from irc.opportunity.states import classify_thesis


def test_thesis_insufficient_when_theme_unknown_in_table():
    state, _ = classify_thesis(_make(theme="some_new_theme"), theme_thesis={})
    assert state == "evidence_insufficient"


def test_thesis_uses_table_for_known_theme():
    state, _ = classify_thesis(
        _make(theme="semiconductor"),
        theme_thesis={"semiconductor": "intact"},
    )
    assert state == "intact"


def test_thesis_falsified_when_table_says_falsified():
    state, _ = classify_thesis(
        _make(theme="real_estate"),
        theme_thesis={"real_estate": "falsified"},
    )
    assert state == "falsified"


def test_thesis_degrades_to_under_pressure_on_style_drift():
    state, _ = classify_thesis(
        _make(theme="consumer", style_drift_flag=True),
        theme_thesis={"consumer": "intact"},
    )
    assert state == "under_pressure"


def test_thesis_degrades_to_evidence_insufficient_when_table_is_none():
    """LLM research failure path: theme_thesis=None must NOT crash and must
    NOT promote any state — everything degrades to evidence_insufficient."""
    state, _ = classify_thesis(_make(theme="semiconductor"), theme_thesis=None)
    assert state == "evidence_insufficient"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/opportunity/test_states.py -v -k "thesis"
```

Expected: ImportError for `classify_thesis`.

- [ ] **Step 3: Implement `classify_thesis`**

Append to `src/irc/opportunity/states.py`:

```python
_VALID_THESIS_TABLE_VALUES: frozenset[str] = frozenset(
    {"intact", "under_pressure", "falsified", "evidence_insufficient"}
)


def classify_thesis(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
) -> tuple[ThesisState, str]:
    """Classify long-term thesis state for the instrument's theme.

    `theme_thesis` is keyed by theme. `None` represents an upstream
    research failure — never fabricate `intact` from a missing table.
    `style_drift_flag=True` demotes an otherwise-intact thesis to
    `under_pressure`.
    """
    if theme_thesis is None:
        return "evidence_insufficient", "长期逻辑数据未就绪。"
    theme = inp.theme
    if theme is None:
        return "evidence_insufficient", "标的未标注主题，无法引用长期逻辑表。"
    raw = theme_thesis.get(theme)
    if raw is None or raw not in _VALID_THESIS_TABLE_VALUES:
        return "evidence_insufficient", f"主题 {theme} 在长期逻辑表中无记录。"
    if raw == "intact" and inp.style_drift_flag:
        return "under_pressure", "主题逻辑完好，但产品存在风格漂移迹象。"
    return raw, f"主题 {theme} 逻辑状态：{raw}。"  # type: ignore[return-value]
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: all thesis + heat + valuation tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): classify thesis state with style-drift demotion"
```

---

## Task 6: Product quality state classifier

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Modify: `tests/opportunity/test_states.py` (append)

- [ ] **Step 1: Append failing tests**

```python
from irc.opportunity.states import classify_product_quality


def test_product_quality_strong_for_low_er_high_aum_passive():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.0015, aum_cny=10e9,
        tracking_error=0.001, premium_discount_pct=0.001,
    ))
    assert state == "strong"


def test_product_quality_acceptable_for_midband_passive():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.005, aum_cny=1e9,
        tracking_error=0.005, premium_discount_pct=0.005,
    ))
    assert state == "acceptable"


def test_product_quality_poor_for_high_er_tiny_aum():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.025, aum_cny=5e7,
    ))
    assert state == "poor"


def test_product_quality_insufficient_when_no_data():
    state, _ = classify_product_quality(_make(asset_class="cn_etf"))
    assert state == "evidence_insufficient"


def test_active_fund_demoted_when_manager_tenure_missing():
    """Active funds without tenure/style evidence cannot exceed 'weak'."""
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.012, aum_cny=2e9,
        manager_tenure_years=None,
    ))
    assert state in ("weak", "evidence_insufficient")


def test_active_fund_acceptable_when_tenure_and_aum_present():
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.012, aum_cny=2e9,
        manager_tenure_years=5.5, aum_stability_pct=0.85,
    ))
    assert state in ("acceptable", "strong")
```

- [ ] **Step 2: Run the tests**

Expected: ImportError for `classify_product_quality`.

- [ ] **Step 3: Implement `classify_product_quality`**

Append to `src/irc/opportunity/states.py`:

```python
def _is_active_fund(inp: OpportunityInput) -> bool:
    # Same rule as the ingest fix in commit 324457c: keyed on market,
    # not on asset_class suffix, so passive bond ETFs are not flagged.
    return inp.asset_class == "cn_equity_fund" and inp.market != "cn_on_exchange"


def _passive_quality_score(inp: OpportunityInput) -> tuple[float, int]:
    contributions: list[float] = []
    if inp.expense_ratio is not None:
        # 0.001 -> +1, 0.005 -> +0.6, 0.02 -> 0, 0.03+ -> -1
        contributions.append(max(-1.0, min(1.0, (0.02 - inp.expense_ratio) / 0.02)))
    if inp.aum_cny is not None:
        # >5e9 -> +1, 5e8 -> 0, <1e8 -> -1 (log scale band)
        import math
        log_aum = math.log10(max(inp.aum_cny, 1.0))
        contributions.append(max(-1.0, min(1.0, (log_aum - 8.7) / 1.0)))
    if inp.tracking_error is not None:
        contributions.append(max(-1.0, min(1.0, (0.005 - inp.tracking_error) / 0.005)))
    if inp.premium_discount_pct is not None:
        contributions.append(max(-1.0, min(1.0, (0.01 - abs(inp.premium_discount_pct)) / 0.01)))
    if not contributions:
        return 0.0, 0
    return sum(contributions) / len(contributions), len(contributions)


def classify_product_quality(inp: OpportunityInput) -> tuple[ProductQualityState, str]:
    """Classify product quality. Active funds require manager tenure +
    AUM stability evidence to exceed 'weak'."""
    if _is_active_fund(inp):
        if inp.manager_tenure_years is None or inp.aum_stability_pct is None:
            if inp.manager_tenure_years is None and inp.aum_stability_pct is None:
                return "evidence_insufficient", "主动基金缺少基金经理与AUM稳定性证据。"
            return "weak", "主动基金证据不足，未达可推荐水平。"
        if inp.manager_tenure_years < 2.0:
            return "weak", "基金经理任职年限不足两年。"
        score, n = _passive_quality_score(inp)
        if n < 2:
            return "weak", "主动基金成本/规模证据不足。"
        if score >= 0.5 and inp.manager_tenure_years >= 5.0:
            return "strong", "主动基金长期经理 + 优良成本/规模。"
        if score >= 0.0:
            return "acceptable", "主动基金达到可观察标准。"
        return "weak", "主动基金成本或规模存在明显劣势。"

    score, n = _passive_quality_score(inp)
    if n < 2:
        return "evidence_insufficient", "产品成本/规模数据不足。"
    if score >= 0.55:
        return "strong", "费率低、规模大、跟踪误差小。"
    if score >= 0.10:
        return "acceptable", "产品质量在合理范围内。"
    if score >= -0.30:
        return "weak", "产品质量存在明显短板。"
    return "poor", "产品质量极差，不适合主仓位。"
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: all state tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): classify product quality with active-fund demotion"
```

---

## Task 7: Opportunity state composer + evidence-gap tracking

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Modify: `tests/opportunity/test_states.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/opportunity/test_states.py`:

```python
from irc.opportunity.states import compose_opportunity_state, build_opportunity_row


def test_core_dca_when_cheap_cold_intact_acceptable():
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "core_dca"


def test_core_dca_when_reasonable_low_normal_intact_strong():
    state, _ = compose_opportunity_state(
        valuation="reasonable_low", heat="normal", thesis="intact",
        product_quality="strong",
    )
    assert state == "core_dca"


def test_exclude_when_thesis_falsified():
    """Spec test 3: cheap valuation + falsified thesis -> exclude."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="falsified",
        product_quality="strong",
    )
    assert state == "exclude"


def test_exclude_when_product_quality_poor():
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="poor",
    )
    assert state == "exclude"


def test_pause_wait_when_expensive_or_crowded():
    state, _ = compose_opportunity_state(
        valuation="expensive", heat="crowded", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "pause_wait"


def test_small_watch_when_evidence_insufficient_but_not_excluded():
    state, _ = compose_opportunity_state(
        valuation="reasonable_low", heat="normal",
        thesis="evidence_insufficient", product_quality="acceptable",
    )
    assert state == "small_watch"


def test_build_opportunity_row_records_evidence_gaps():
    """Spec test 9: missing data produces explicit evidence_gaps."""
    inp = _make(theme="semiconductor")
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert "valuation" in row.evidence_gaps
    assert "heat" in row.evidence_gaps
    assert "product_quality" in row.evidence_gaps


def test_build_opportunity_row_no_gaps_when_evidence_present():
    inp = _make(
        theme="broad", tracked_index="csi300", asset_class="cn_etf",
        valuation_percentile_self=0.25,
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    row = build_opportunity_row(inp, theme_thesis={"broad": "intact"})
    assert row.evidence_gaps == ()
```

- [ ] **Step 2: Run the tests**

Expected: ImportError for `compose_opportunity_state`, `build_opportunity_row`.

- [ ] **Step 3: Implement composer + row builder**

Append to `src/irc/opportunity/states.py`:

```python
from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityRow


def compose_opportunity_state(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
) -> tuple[OpportunityState, str]:
    """Compose final opportunity state from four sub-states.

    Conservative defaults: when in doubt, prefer small_watch / pause_wait
    over core_dca. Falsified thesis or poor product => exclude immediately.
    """
    if thesis == "falsified" or product_quality == "poor":
        return "exclude", "长期逻辑被证伪或产品质量过差，禁止建仓。"

    cheap_or_low = valuation in ("cheap", "reasonable_low")
    expensive = valuation in ("expensive", "very_expensive")
    quiet_heat = heat in ("cold", "normal")
    hot_heat = heat in ("crowded", "overheated")
    intact_thesis = thesis == "intact"
    decent_product = product_quality in ("acceptable", "strong")

    if cheap_or_low and quiet_heat and intact_thesis and decent_product:
        return "core_dca", "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。"

    if expensive or hot_heat:
        return "pause_wait", "估值偏高或热度偏高，暂停加仓等待回落。"

    return "small_watch", "证据不完整或信号不一致，列入小仓位观察。"


def _evidence_gaps(inp: OpportunityInput) -> tuple[str, ...]:
    gaps: list[str] = []
    if inp.valuation_percentile_self is None and inp.valuation_percentile_vs_benchmark is None:
        gaps.append("valuation")
    if inp.ret_3m is None and inp.ret_6m is None and inp.premium_discount_pct is None:
        gaps.append("heat")
    if inp.theme is None:
        gaps.append("theme_thesis")
    if inp.expense_ratio is None and inp.aum_cny is None:
        gaps.append("product_quality")
    return tuple(gaps)


def build_opportunity_row(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
) -> OpportunityRow:
    """Compose a full OpportunityRow for a single instrument.

    Pure function: takes all inputs explicitly, returns a frozen row.
    """
    valuation, val_reason = classify_valuation(inp)
    heat, heat_reason = classify_heat(inp)
    thesis, thesis_reason = classify_thesis(inp, theme_thesis)
    product, product_reason = classify_product_quality(inp)
    state, state_reason = compose_opportunity_state(valuation, heat, thesis, product)
    target = map_lookthrough(inp)
    gaps = _evidence_gaps(inp)
    reason = " | ".join([state_reason, val_reason, heat_reason, thesis_reason, product_reason])
    return OpportunityRow(
        instrument_id=inp.instrument_id,
        name_cn=inp.name_cn,
        asset_class=inp.asset_class,
        theme=inp.theme,
        lookthrough_target=target,
        valuation_state=valuation,
        heat_state=heat,
        thesis_state=thesis,
        product_quality_state=product,
        opportunity_state=state,
        opportunity_reason=reason,
        evidence_gaps=gaps,
    )
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_states.py -v
```

Expected: all state tests pass (valuation + heat + thesis + product_quality + compose + build).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): compose opportunity_state and track evidence gaps"
```

---

## Task 8: Same-theme and same-index selection

**Files:**
- Create: `src/irc/opportunity/selection.py`
- Create: `tests/opportunity/test_selection.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_selection.py`:

```python
from __future__ import annotations
import pytest

from irc.opportunity.selection import (
    reduce_same_index,
    reduce_same_theme,
    SelectionQuality,
)
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(
    instrument_id: str, *, lookthrough_key: str = "csi300",
    lookthrough_kind: str = "broad_index", theme: str | None = "broad",
    asset_class: str = "cn_etf",
) -> OpportunityRow:
    return OpportunityRow(
        instrument_id=instrument_id,
        name_cn=f"基金-{instrument_id}",
        asset_class=asset_class,
        theme=theme,
        lookthrough_target=LookthroughTarget(
            lookthrough_kind, lookthrough_key, "display"
        ),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=(),
    )


def _q(expense_ratio: float, aum: float, *, tracking_error: float = 0.002) -> SelectionQuality:
    return SelectionQuality(
        expense_ratio=expense_ratio,
        aum_cny=aum,
        tracking_error=tracking_error,
        premium_discount_abs=0.001,
        history_days=2500,
        data_completeness=0.95,
    )


def test_same_index_keeps_primary_and_backup():
    """Spec test 6: same-index ETF selection keeps one primary and one backup."""
    rows = [
        _row("510300"), _row("510310"),
        _row("159919"), _row("510330"),
    ]
    qualities = {
        "510300": _q(0.0015, 50e9),
        "510310": _q(0.0050, 8e9),
        "159919": _q(0.0050, 30e9),
        "510330": _q(0.0050, 20e9),
    }
    primary, backup, dropped = reduce_same_index(rows, qualities)
    assert primary.instrument_id == "510300"      # lowest ER wins
    assert backup is not None
    assert backup.instrument_id == "159919"        # next: higher AUM among ties
    assert {r.instrument_id for r in dropped} == {"510310", "510330"}


def test_same_index_single_input_returns_no_backup():
    rows = [_row("510300")]
    qualities = {"510300": _q(0.0015, 50e9)}
    primary, backup, dropped = reduce_same_index(rows, qualities)
    assert primary.instrument_id == "510300"
    assert backup is None
    assert dropped == ()


def test_same_theme_different_indexes_keep_up_to_two():
    """Spec test 7: same-theme different-index selection keeps up to two
    representatives when targets differ."""
    rows = [
        _row("510300", lookthrough_key="broad_healthcare", theme="healthcare"),
        _row("159929", lookthrough_key="innovative_drugs", theme="healthcare"),
        _row("159828", lookthrough_key="med_devices", theme="healthcare"),
    ]
    qualities = {
        rid: _q(0.005, 5e9) for rid in ("510300", "159929", "159828")
    }
    kept, dropped = reduce_same_theme(rows, qualities, max_per_theme=2)
    kept_keys = {r.lookthrough_target.key for r in kept}
    assert len(kept) == 2
    assert len(kept_keys) == 2  # two distinct lookthrough keys
    assert len(dropped) == 1


def test_same_theme_collapses_same_index_first():
    """Two ETFs tracking the same index in a theme must collapse to one before
    the per-theme cap applies."""
    rows = [
        _row("510300", lookthrough_key="csi300", theme="broad"),
        _row("510310", lookthrough_key="csi300", theme="broad"),
        _row("159949", lookthrough_key="chinext", theme="broad"),
    ]
    qualities = {
        "510300": _q(0.0015, 50e9),
        "510310": _q(0.0050, 8e9),
        "159949": _q(0.0030, 12e9),
    }
    kept, dropped = reduce_same_theme(rows, qualities, max_per_theme=2)
    kept_ids = {r.instrument_id for r in kept}
    # 510310 must be dropped as a same-index clone of 510300
    assert "510310" not in kept_ids
    assert kept_ids == {"510300", "159949"}
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement selection**

Write `src/irc/opportunity/selection.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from irc.opportunity.types import OpportunityRow


@dataclass(frozen=True)
class SelectionQuality:
    expense_ratio: float | None
    aum_cny: float | None
    tracking_error: float | None
    premium_discount_abs: float | None
    history_days: int | None
    data_completeness: float


def _rank_key(q: SelectionQuality) -> tuple[float, float, float, float, float, float]:
    """Sort key for instrument quality — lower is better.

    Order: ER asc, -AUM asc (i.e. larger AUM first), tracking_error asc,
    premium_discount_abs asc, -history asc, -data_completeness asc.
    """
    return (
        q.expense_ratio if q.expense_ratio is not None else 1.0,
        -(q.aum_cny if q.aum_cny is not None else 0.0),
        q.tracking_error if q.tracking_error is not None else 1.0,
        q.premium_discount_abs if q.premium_discount_abs is not None else 1.0,
        -(q.history_days if q.history_days is not None else 0),
        -q.data_completeness,
    )


def reduce_same_index(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    qualities: dict[str, SelectionQuality],
) -> tuple[OpportunityRow, OpportunityRow | None, tuple[OpportunityRow, ...]]:
    """Pick one primary + at most one backup for instruments sharing
    a lookthrough key. Remaining rows are returned as dropped."""
    if not rows:
        raise ValueError("rows must be non-empty")
    sorted_rows = sorted(
        rows, key=lambda r: _rank_key(qualities[r.instrument_id]),
    )
    primary = sorted_rows[0]
    backup = sorted_rows[1] if len(sorted_rows) >= 2 else None
    dropped = tuple(sorted_rows[2:])
    return primary, backup, dropped


def reduce_same_theme(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    qualities: dict[str, SelectionQuality],
    max_per_theme: int = 2,
) -> tuple[tuple[OpportunityRow, ...], tuple[OpportunityRow, ...]]:
    """Two-stage reduction:
      1. Collapse rows that share a lookthrough key (same index / clone)
         to a single representative — the highest-quality one.
      2. Within a theme, keep at most `max_per_theme` distinct
         lookthrough keys, ranked by best representative quality.

    Returns (kept, dropped).
    """
    if max_per_theme < 1:
        raise ValueError("max_per_theme must be >= 1")
    # Stage 1: group by lookthrough key, keep best.
    by_key: dict[str, list[OpportunityRow]] = {}
    for r in rows:
        by_key.setdefault(r.lookthrough_target.key, []).append(r)
    per_key_best: list[OpportunityRow] = []
    per_key_dropped: list[OpportunityRow] = []
    for key, group in by_key.items():
        ordered = sorted(group, key=lambda r: _rank_key(qualities[r.instrument_id]))
        per_key_best.append(ordered[0])
        per_key_dropped.extend(ordered[1:])
    # Stage 2: cap distinct keys per theme.
    ordered_by_quality = sorted(
        per_key_best, key=lambda r: _rank_key(qualities[r.instrument_id]),
    )
    kept: list[OpportunityRow] = []
    kept_keys: set[str] = set()
    overflow: list[OpportunityRow] = []
    for r in ordered_by_quality:
        if len(kept) < max_per_theme and r.lookthrough_target.key not in kept_keys:
            kept.append(r)
            kept_keys.add(r.lookthrough_target.key)
        else:
            overflow.append(r)
    return tuple(kept), tuple(per_key_dropped + overflow)
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_selection.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/selection.py tests/opportunity/test_selection.py
git commit -m "feat(opportunity): same-index and same-theme reduction"
```

---

## Task 9: Discipline action derivation

**Files:**
- Create: `src/irc/opportunity/discipline.py`
- Create: `tests/opportunity/test_discipline.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_discipline.py`:

```python
from __future__ import annotations
import pytest

from irc.opportunity.discipline import (
    derive_dca_action,
    derive_risk_action,
    PositionContext,
)
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(**overrides) -> OpportunityRow:
    base = dict(
        instrument_id="510300",
        name_cn="X",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def _pos(weight: float, band_high: float, *, drawdown: float = 0.0) -> PositionContext:
    return PositionContext(
        portfolio_weight=weight,
        target_band_low=0.0,
        target_band_high=band_high,
        drawdown_since_entry=drawdown,
        is_holding=True,
    )


def test_accelerate_when_cheap_cold_intact_strong():
    action = derive_dca_action(_row(
        valuation_state="cheap", heat_state="cold",
        thesis_state="intact", product_quality_state="strong",
        opportunity_state="core_dca",
    ))
    assert action == "accelerate_dca"


def test_normal_dca_when_reasonable_low_normal():
    action = derive_dca_action(_row(opportunity_state="core_dca"))
    assert action == "normal_dca"


def test_pause_when_under_pressure_thesis():
    action = derive_dca_action(_row(thesis_state="under_pressure"))
    assert action == "pause_dca"


def test_pause_when_expensive():
    action = derive_dca_action(_row(
        valuation_state="expensive", heat_state="crowded",
        opportunity_state="pause_wait",
    ))
    assert action == "pause_dca"


def test_do_not_buy_when_excluded():
    action = derive_dca_action(_row(
        thesis_state="falsified", opportunity_state="exclude",
    ))
    assert action == "do_not_buy"


def test_drawdown_alone_only_triggers_review_required():
    """Spec test 4: drawdown of 20% does NOT produce sell/exit by itself."""
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30, drawdown=0.22),
    )
    assert action == "review_required"


def test_drawdown_50_still_not_auto_exit():
    """Even a catastrophic drawdown alone must NOT escalate to exit_review
    when thesis remains intact and product is acceptable."""
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30, drawdown=0.50),
    )
    assert action == "review_required"


def test_expensive_crowded_overweight_produces_trim_review():
    """Spec test 5: expensive + crowded + overweight => trim_review."""
    action = derive_risk_action(
        _row(
            valuation_state="expensive", heat_state="crowded",
            opportunity_state="pause_wait",
        ),
        _pos(weight=0.40, band_high=0.30),
    )
    assert action == "trim_review"


def test_falsified_thesis_produces_exit_review():
    action = derive_risk_action(
        _row(thesis_state="falsified", opportunity_state="exclude"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "exit_review"


def test_poor_product_quality_produces_exit_review():
    action = derive_risk_action(
        _row(product_quality_state="poor", opportunity_state="exclude"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "exit_review"


def test_no_risk_action_when_state_normal():
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "none"
```

- [ ] **Step 2: Run the tests**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement discipline**

Write `src/irc/opportunity/discipline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from irc.opportunity.types import DcaAction, OpportunityRow, RiskAction


_DRAWDOWN_REVIEW_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class PositionContext:
    portfolio_weight: float | None
    target_band_low: float | None
    target_band_high: float | None
    drawdown_since_entry: float | None
    is_holding: bool


def derive_dca_action(row: OpportunityRow) -> DcaAction:
    """Map opportunity_state + sub-states to DCA rhythm.

    Rules (from spec, conservative side):
      - exclude => do_not_buy
      - thesis under_pressure or pause_wait => pause_dca
      - cheap + cold + intact + strong => accelerate_dca
      - core_dca otherwise => normal_dca
      - small_watch => slow_dca
    """
    if row.opportunity_state == "exclude":
        return "do_not_buy"
    if row.thesis_state in ("under_pressure", "falsified"):
        return "pause_dca"
    if row.opportunity_state == "pause_wait":
        return "pause_dca"
    if row.opportunity_state == "small_watch":
        return "slow_dca"
    if (
        row.valuation_state == "cheap"
        and row.heat_state == "cold"
        and row.thesis_state == "intact"
        and row.product_quality_state == "strong"
    ):
        return "accelerate_dca"
    return "normal_dca"


def _is_overweight(pos: PositionContext) -> bool:
    if pos.portfolio_weight is None or pos.target_band_high is None:
        return False
    return pos.portfolio_weight > pos.target_band_high


def derive_risk_action(row: OpportunityRow, pos: PositionContext) -> RiskAction:
    """Derive risk action with strict separation between trim and exit.

    - Falsified thesis OR poor product quality => exit_review
    - Trim conditions => trim_review:
      * expensive/very_expensive valuation AND overweight
      * crowded/overheated heat AND overweight
    - Drawdown >= 20% alone => review_required (NEVER auto-sell)
    - Otherwise => none
    """
    if row.thesis_state == "falsified" or row.product_quality_state == "poor":
        return "exit_review"
    overweight = _is_overweight(pos)
    expensive = row.valuation_state in ("expensive", "very_expensive")
    hot = row.heat_state in ("crowded", "overheated")
    if overweight and (expensive or hot):
        return "trim_review"
    drawdown = pos.drawdown_since_entry
    if drawdown is not None and drawdown >= _DRAWDOWN_REVIEW_THRESHOLD:
        return "review_required"
    if row.thesis_state == "under_pressure":
        return "review_required"
    return "none"
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_discipline.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/discipline.py tests/opportunity/test_discipline.py
git commit -m "feat(opportunity): derive DCA + risk actions; drawdown never auto-sells"
```

---

## Task 10: Thesis cards

**Files:**
- Create: `src/irc/opportunity/cards.py`
- Create: `tests/opportunity/test_cards.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_cards.py`:

```python
from __future__ import annotations

from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(**overrides) -> OpportunityRow:
    base = dict(
        instrument_id="512760",
        name_cn="国泰CES半导体芯片行业ETF",
        asset_class="cn_etf",
        theme="semiconductor",
        lookthrough_target=LookthroughTarget("sector_theme", "semiconductor", "半导体"),
        valuation_state="reasonable_low",
        heat_state="crowded",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="pause_wait",
        opportunity_reason="估值合理但热度偏高，暂不追高。",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def _pos(weight: float = 0.05, band_high: float = 0.10) -> PositionContext:
    return PositionContext(
        portfolio_weight=weight,
        target_band_low=0.0,
        target_band_high=band_high,
        drawdown_since_entry=None,
        is_holding=True,
    )


def test_card_includes_required_fields():
    card = build_thesis_card(
        row=_row(),
        position=_pos(),
        role="satellite_cn_semiconductor",
        entry_reason="国产替代与周期复苏逻辑。",
    )
    assert card.instrument_id == "512760"
    assert card.theme == "semiconductor"
    assert card.role == "satellite_cn_semiconductor"
    assert card.review_cadence == "weekly_light_monthly_full"


def test_card_falsification_triggers_include_thesis_and_product():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    assert "theme thesis moves to falsified" in card.falsification_triggers
    assert "product quality moves to poor" in card.falsification_triggers


def test_card_trim_triggers_cover_expensive_crowded_and_overweight():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    joined = " | ".join(card.trim_triggers)
    assert "expensive" in joined
    assert "crowded" in joined or "overheated" in joined
    assert "weight" in joined or "band" in joined


def test_card_records_do_not_sell_just_because_drawdown():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    assert any("0.20" in trigger for trigger in card.do_not_sell_just_because)


def test_card_propagates_evidence_gaps():
    row = _row(evidence_gaps=("valuation", "product_quality"))
    card = build_thesis_card(row=row, position=_pos(), role="x", entry_reason="x")
    assert card.evidence_gaps == ("valuation", "product_quality")


def test_card_dca_and_risk_actions_match_state():
    """Cards built from a pause_wait row should not say accelerate_dca."""
    card = build_thesis_card(
        row=_row(opportunity_state="pause_wait"),
        position=_pos(),
        role="x", entry_reason="x",
    )
    assert card.dca_action in ("pause_dca", "slow_dca")
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement card builder**

Write `src/irc/opportunity/cards.py`:

```python
from __future__ import annotations

from irc.opportunity.discipline import (
    PositionContext,
    derive_dca_action,
    derive_risk_action,
)
from irc.opportunity.types import OpportunityRow, ThesisCard


_FALSIFICATION_TRIGGERS: tuple[str, ...] = (
    "theme thesis moves to falsified",
    "product quality moves to poor",
    "manager change with style drift",
)

_TRIM_TRIGGERS: tuple[str, ...] = (
    "valuation_state in [expensive, very_expensive]",
    "heat_state in [crowded, overheated]",
    "portfolio weight exceeds target band high",
)

_DO_NOT_SELL_JUST_BECAUSE: tuple[str, ...] = (
    "drawdown_since_entry >= 0.20",
    "single-day price drop",
    "short-term volatility spike",
)


def build_thesis_card(
    row: OpportunityRow,
    position: PositionContext,
    role: str,
    entry_reason: str,
    review_cadence: str = "weekly_light_monthly_full",
) -> ThesisCard:
    """Compose a durable ThesisCard. Pure function — derives DCA + risk
    actions from the row + position context."""
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    return ThesisCard(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        role=role,
        lookthrough_target=row.lookthrough_target.display_cn,
        entry_reason=entry_reason,
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        falsification_triggers=_FALSIFICATION_TRIGGERS,
        trim_triggers=_TRIM_TRIGGERS,
        do_not_sell_just_because=_DO_NOT_SELL_JUST_BECAUSE,
        review_cadence=review_cadence,
        evidence_gaps=row.evidence_gaps,
    )
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_cards.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/cards.py tests/opportunity/test_cards.py
git commit -m "feat(opportunity): build durable thesis cards"
```

---

## Task 11: Report composition (JSON + YAML + Markdown)

**Files:**
- Create: `src/irc/opportunity/report.py`
- Create: `tests/opportunity/test_report.py`

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_report.py`:

```python
from __future__ import annotations

from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.report import (
    compose_opportunity_report,
    compose_thesis_cards_yaml,
    compose_discipline_markdown,
)
from irc.opportunity.types import (
    DisciplineRow,
    LookthroughTarget,
    OpportunityRow,
)


def _row(state="core_dca", **overrides) -> OpportunityRow:
    base = dict(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state=state,
        opportunity_reason="核心宽基指数估值合理。",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def test_opportunity_report_summary_counts_states():
    rows = [
        _row(state="core_dca"), _row(state="core_dca", instrument_id="159919"),
        _row(state="pause_wait", instrument_id="512760"),
        _row(state="exclude", instrument_id="000001", thesis_state="falsified"),
    ]
    report = compose_opportunity_report(rows, date="2026-05-14")
    assert report["date"] == "2026-05-14"
    assert report["summary"]["core_dca_count"] == 2
    assert report["summary"]["pause_wait_count"] == 1
    assert report["summary"]["exclude_count"] == 1
    assert report["summary"]["small_watch_count"] == 0
    assert len(report["rows"]) == 4
    sample = report["rows"][0]
    for key in (
        "instrument_id", "name_cn", "asset_class", "theme",
        "lookthrough_target", "valuation_state", "heat_state",
        "thesis_state", "product_quality_state", "opportunity_state",
        "opportunity_reason", "evidence_gaps",
    ):
        assert key in sample


def test_thesis_cards_yaml_includes_required_fields():
    row = _row()
    pos = PositionContext(0.05, 0.0, 0.30, None, True)
    card = build_thesis_card(row, pos, "core_cn_equity", "宽基底仓。")
    payload = compose_thesis_cards_yaml([card])
    assert "instrument_id: '510300'" in payload or 'instrument_id: "510300"' in payload
    assert "do_not_sell_just_because:" in payload
    assert "drawdown_since_entry >= 0.20" in payload


def test_discipline_markdown_has_chinese_action_sections():
    """Spec integration test 3: Markdown starts with Chinese actionable
    sections for DCA, pause, review, trim, and exit."""
    rows = [
        DisciplineRow("510300", "宽基", "cn_etf", "broad", "core_dca",
                      "normal_dca", "none", "可定投"),
        DisciplineRow("512760", "半导体", "cn_etf", "semiconductor", "pause_wait",
                      "pause_dca", "review_required", "暂停加仓"),
        DisciplineRow("000001", "主动", "cn_equity_fund", "consumer", "exclude",
                      "do_not_buy", "exit_review", "退出复核"),
    ]
    md = compose_discipline_markdown(rows, date="2026-05-14")
    assert "## 今日可定投" in md
    assert "## 暂停加仓" in md
    assert "## 风险复核" in md
    assert "## 调仓复核" in md
    assert "## 退出复核" in md
    assert "## 关于回撤的说明" in md
    # The drawdown-not-auto-sell explanation must be present.
    assert "20%" in md


def test_discipline_markdown_empty_categories_render_placeholder():
    md = compose_discipline_markdown([], date="2026-05-14")
    assert "## 今日可定投" in md
    assert "（无）" in md or "(none)" in md
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement report module**

Write `src/irc/opportunity/report.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import yaml

from irc.opportunity.types import (
    DisciplineRow,
    OpportunityRow,
    ThesisCard,
)


def _row_to_dict(row: OpportunityRow) -> dict[str, Any]:
    return {
        "instrument_id": row.instrument_id,
        "name_cn": row.name_cn,
        "asset_class": row.asset_class,
        "theme": row.theme,
        "lookthrough_target": row.lookthrough_target.display_cn,
        "lookthrough_kind": row.lookthrough_target.kind,
        "lookthrough_key": row.lookthrough_target.key,
        "valuation_state": row.valuation_state,
        "heat_state": row.heat_state,
        "thesis_state": row.thesis_state,
        "product_quality_state": row.product_quality_state,
        "opportunity_state": row.opportunity_state,
        "opportunity_reason": row.opportunity_reason,
        "evidence_gaps": list(row.evidence_gaps),
    }


def compose_opportunity_report(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    date: str,
) -> dict[str, Any]:
    summary = {
        "core_dca_count": 0,
        "small_watch_count": 0,
        "pause_wait_count": 0,
        "exclude_count": 0,
    }
    for r in rows:
        summary[f"{r.opportunity_state}_count"] += 1
    return {
        "date": date,
        "summary": summary,
        "rows": [_row_to_dict(r) for r in rows],
    }


def _card_to_dict(card: ThesisCard) -> dict[str, Any]:
    d = asdict(card)
    # Convert tuples to lists for YAML readability.
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps"):
        d[key] = list(d.get(key, []))
    return d


def compose_thesis_cards_yaml(cards: list[ThesisCard] | tuple[ThesisCard, ...]) -> str:
    payload = {"cards": [_card_to_dict(c) for c in cards]}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


_DCA_BUCKET = {
    "accelerate_dca": "今日可定投",
    "normal_dca": "今日可定投",
    "slow_dca": "今日可定投",
    "pause_dca": "暂停加仓",
    "do_not_buy": "暂停加仓",
}

_RISK_BUCKET = {
    "review_required": "风险复核",
    "trim_review": "调仓复核",
    "exit_review": "退出复核",
}


def _bucket_rows(rows: list[DisciplineRow] | tuple[DisciplineRow, ...]) -> dict[str, list[DisciplineRow]]:
    buckets: dict[str, list[DisciplineRow]] = {
        "今日可定投": [],
        "暂停加仓": [],
        "风险复核": [],
        "调仓复核": [],
        "退出复核": [],
    }
    for r in rows:
        if r.risk_action in _RISK_BUCKET:
            buckets[_RISK_BUCKET[r.risk_action]].append(r)
        else:
            buckets[_DCA_BUCKET.get(r.dca_action, "今日可定投")].append(r)
    return buckets


def _render_section(title: str, rows: list[DisciplineRow]) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
    lines.append("")
    return "\n".join(lines)


_DRAWDOWN_NOTE_CN = (
    "## 关于回撤的说明\n\n"
    "持仓回撤达到 20% 或更高时，本系统**不会**自动卖出。\n"
    "回撤只触发风险复核，是否减仓或退出需结合：\n"
    "- 主题长期逻辑是否被证伪；\n"
    "- 产品质量是否变差；\n"
    "- 组合权重是否超出目标区间。\n"
    "短期价格下跌、单日波动不构成卖出理由。\n"
)


def compose_discipline_markdown(
    rows: list[DisciplineRow] | tuple[DisciplineRow, ...],
    date: str,
) -> str:
    buckets = _bucket_rows(rows)
    parts = [
        f"# Discipline Report — {date}\n",
        _render_section("今日可定投", buckets["今日可定投"]),
        _render_section("暂停加仓", buckets["暂停加仓"]),
        _render_section("风险复核", buckets["风险复核"]),
        _render_section("调仓复核", buckets["调仓复核"]),
        _render_section("退出复核", buckets["退出复核"]),
        _DRAWDOWN_NOTE_CN,
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/opportunity/test_report.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): compose JSON/YAML/Markdown reports"
```

---

## Task 12: Theme thesis config loader (optional file)

**Files:**
- Create: `src/irc/opportunity/theme_thesis.py`
- Create: `tests/opportunity/test_theme_thesis.py`
- Create: `src/irc/templates/config/opportunity/theme_thesis.yaml` (template only — for `irc init`)

This is a small loader that reads `config/opportunity/theme_thesis.yaml` if present and returns a `dict[str, str]`. Missing file returns `{}` (everything degrades to `evidence_insufficient`). The template is added to `irc init` later.

- [ ] **Step 1: Write the failing test**

Write `tests/opportunity/test_theme_thesis.py`:

```python
from __future__ import annotations
from pathlib import Path

import pytest

from irc.opportunity.theme_thesis import load_theme_thesis


def test_missing_file_returns_empty_dict(tmp_path: Path):
    out = load_theme_thesis(tmp_path)
    assert out == {}


def test_loads_valid_yaml(tmp_path: Path):
    cfg = tmp_path / "config" / "opportunity"
    cfg.mkdir(parents=True)
    (cfg / "theme_thesis.yaml").write_text(
        "themes:\n"
        "  semiconductor: intact\n"
        "  real_estate: falsified\n"
        "  consumer: under_pressure\n",
        encoding="utf-8",
    )
    out = load_theme_thesis(tmp_path)
    assert out["semiconductor"] == "intact"
    assert out["real_estate"] == "falsified"


def test_rejects_unknown_state_value(tmp_path: Path):
    cfg = tmp_path / "config" / "opportunity"
    cfg.mkdir(parents=True)
    (cfg / "theme_thesis.yaml").write_text(
        "themes:\n  semiconductor: amazing\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_theme_thesis(tmp_path)
```

- [ ] **Step 2: Run the tests**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement loader**

Write `src/irc/opportunity/theme_thesis.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_VALID_VALUES: frozenset[str] = frozenset(
    {"intact", "under_pressure", "falsified", "evidence_insufficient"}
)


def load_theme_thesis(repo_root: Path) -> dict[str, str]:
    """Load `config/opportunity/theme_thesis.yaml`.

    Missing file => empty dict (everything degrades to evidence_insufficient).
    Unknown state values raise ValueError so the user notices typos.
    """
    path = repo_root / "config" / "opportunity" / "theme_thesis.yaml"
    if not path.exists():
        return {}
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    themes = raw.get("themes") or {}
    if not isinstance(themes, dict):
        raise ValueError(
            f"{path}: 'themes' must be a mapping of theme -> state"
        )
    out: dict[str, str] = {}
    for theme, state in themes.items():
        if state not in _VALID_VALUES:
            raise ValueError(
                f"{path}: theme '{theme}' has invalid state '{state}'. "
                f"Valid values: {sorted(_VALID_VALUES)}"
            )
        out[str(theme)] = str(state)
    return out
```

- [ ] **Step 4: Create the template file**

Write `src/irc/templates/config/opportunity/theme_thesis.yaml`:

```yaml
# Theme-level long-term thesis state.
# Refreshed quarterly via deep research (LDR or manual review).
# Valid states: intact | under_pressure | falsified | evidence_insufficient
# Any theme not listed here defaults to evidence_insufficient at runtime.
themes:
  broad: intact
  dividend: intact
  semiconductor: evidence_insufficient
  tech: evidence_insufficient
  healthcare: evidence_insufficient
  new_energy: evidence_insufficient
  consumer: evidence_insufficient
  finance: evidence_insufficient
  defense: evidence_insufficient
  metals: evidence_insufficient
  real_estate: evidence_insufficient
  soe: evidence_insufficient
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/opportunity/test_theme_thesis.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/theme_thesis.py tests/opportunity/test_theme_thesis.py src/irc/templates/config/opportunity/theme_thesis.yaml
git commit -m "feat(opportunity): load theme thesis table; missing file = insufficient"
```

---

## Task 13: CLI command `irc opportunity`

The CLI wrapper is the only piece allowed to do I/O. It reads:
- `outputs/<today>/scoring.json` (or latest)
- `inputs/account.yaml` (current holdings via `bundle.account`)
- `inputs/preferences.yaml` (asset class target bands via `bundle.preferences`)
- universe + metrics via existing helpers
- `config/opportunity/theme_thesis.yaml` (optional)

Writes:
- `outputs/<today>/opportunity_report.json`
- `outputs/<today>/thesis_cards.yaml`
- `outputs/<today>/discipline_report.md`

**Files:**
- Create: `src/irc/commands/opportunity_cmd.py`
- Create: `tests/commands/test_opportunity_cmd.py`
- Modify: `src/irc/cli.py`

- [ ] **Step 1: Write the failing test**

Write `tests/commands/test_opportunity_cmd.py`:

```python
from __future__ import annotations
import json
from pathlib import Path

import pytest
import yaml


def _seed_minimal_repo(tmp_path: Path) -> None:
    """Create the minimum file layout needed by run_opportunity."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()

    # inputs/account.yaml
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund, cn_brokerage]\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )

    # inputs/preferences.yaml — minimal viable
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance:\n  cny: [0.5, 1.0]\n  usd: [0.0, 0.4]\n  hkd: [0.0, 0.3]\n"
        "constraints:\n  allow_short: false\n  allow_leverage: false\n  exclude_themes: []\n"
        "investment_plan:\n  monthly_new_capital_cny: 5000\n"
        "report_language: zh\n",
        encoding="utf-8",
    )

    # config files — copy from the project's templates directory at runtime; the
    # tested command does not need the full bundle for opportunity-only logic.
    repo = Path(__file__).resolve().parents[2]
    src_tpl = repo / "src" / "irc" / "templates"
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((src_tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    # outputs/2026-05-14/scoring.json — a single instrument
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({
            "scores": [{
                "instrument_id": "510300",
                "asset_class": "cn_etf",
                "role": "core_cn_equity",
                "composite_score": 75.0,
                "action": "buy_candidate",
                "data_completeness": 0.85,
                "factor_breakdown": {
                    "valuation_cost": {"score": 80, "raw_refs": []},
                    "risk": {"score": 70, "raw_refs": []},
                    "quality": {"score": 75, "raw_refs": []},
                    "macro_fit": {"score": 65, "raw_refs": []},
                    "thesis_news": {"score": 80, "raw_refs": []},
                },
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_command_writes_three_outputs(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd._today", lambda: "2026-05-14"
    )
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    assert (out / "opportunity_report.json").exists()
    assert (out / "thesis_cards.yaml").exists()
    assert (out / "discipline_report.md").exists()


def test_opportunity_report_json_has_summary_and_rows(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    payload = json.loads((tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text())
    assert payload["date"] == "2026-05-14"
    assert "summary" in payload
    assert isinstance(payload["rows"], list)


def test_opportunity_markdown_starts_with_chinese_sections(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    md = (tmp_path / "outputs" / "2026-05-14" / "discipline_report.md").read_text()
    assert "## 今日可定投" in md
    assert "## 关于回撤的说明" in md


def test_opportunity_does_not_read_external_worktree_path(tmp_path: Path, monkeypatch):
    """Acceptance criterion: never read the external worktree generated universe."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    import irc.commands.opportunity_cmd as opp_mod
    src = Path(opp_mod.__file__).read_text(encoding="utf-8")
    assert "investment-research-copilot.worktrees" not in src


def test_opportunity_works_with_missing_scoring(tmp_path: Path, monkeypatch):
    """Falls back to latest outputs when today's scoring.json missing."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Move scoring under an older date
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
```

Also create `tests/commands/__init__.py` if it does not already exist (check first with `ls tests/commands/`).

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/commands/test_opportunity_cmd.py -v
```

Expected: ModuleNotFoundError for `irc.commands.opportunity_cmd`.

- [ ] **Step 3: Implement the command**

Write `src/irc/commands/opportunity_cmd.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import (
    PositionContext,
    derive_dca_action,
    derive_risk_action,
)
from irc.opportunity.report import (
    compose_discipline_markdown,
    compose_opportunity_report,
    compose_thesis_cards_yaml,
)
from irc.opportunity.selection import SelectionQuality, reduce_same_theme
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.theme_thesis import load_theme_thesis
from irc.opportunity.types import (
    DisciplineRow,
    OpportunityInput,
    OpportunityRow,
)
from irc.schemas.inputs import AccountFile, Holding, PreferencesFile
from irc.schemas.universe import Instrument, UniverseConfig


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _locate_scoring(root: Path, today: str) -> Path | None:
    today_path = root / "outputs" / today / "scoring.json"
    if today_path.exists():
        return today_path
    candidates = sorted((root / "outputs").glob("*/scoring.json"))
    return candidates[-1] if candidates else None


def _load_scores(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return list(raw.get("scores", []))
    if isinstance(raw, list):
        return list(raw)
    return []


def _instrument_index(uni_list: list[UniverseConfig]) -> dict[str, Instrument]:
    index: dict[str, Instrument] = {}
    for u in uni_list:
        for instr in u.instruments:
            index.setdefault(instr.instrument_id, instr)
    return index


def _holdings_index(account: AccountFile) -> dict[str, Holding]:
    idx: dict[str, Holding] = {}
    for acc in account.accounts:
        for h in acc.holdings:
            if h.instrument_id is not None:
                idx[h.instrument_id] = h
    return idx


def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
) -> OpportunityInput:
    asset_class = score_row.get("asset_class") or (instr.asset_class if instr else "unknown")
    market = instr.market if instr else "cn_off_exchange"
    theme = instr.theme if instr else None
    tracked_index = instr.tracked_index if instr else None
    name_cn = instr.name_cn if instr else score_row.get("instrument_id", "")
    weight = None
    if holding is not None and portfolio_total_cny > 0:
        weight = holding.cost_basis_cny / portfolio_total_cny
    return OpportunityInput(
        instrument_id=score_row["instrument_id"],
        asset_class=asset_class,
        market=market,
        theme=theme,
        tracked_index=tracked_index,
        name_cn=name_cn,
        role=score_row.get("role", ""),
        is_holding=holding is not None,
        portfolio_weight=weight,
        target_band_low=target_band[0] if target_band else None,
        target_band_high=target_band[1] if target_band else None,
        drawdown_since_entry=None,
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=None,
        expense_ratio=None,
        aum_cny=None,
        manager_tenure_years=None,
    )


def _selection_quality_from(input_row: OpportunityInput) -> SelectionQuality:
    return SelectionQuality(
        expense_ratio=input_row.expense_ratio,
        aum_cny=input_row.aum_cny,
        tracking_error=input_row.tracking_error,
        premium_discount_abs=(
            abs(input_row.premium_discount_pct)
            if input_row.premium_discount_pct is not None else None
        ),
        history_days=None,
        data_completeness=1.0,
    )


def _discipline_row_from(
    row: OpportunityRow, position: PositionContext,
) -> DisciplineRow:
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    note = row.opportunity_reason.split(" | ")[0] if row.opportunity_reason else ""
    return DisciplineRow(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        note_cn=note,
    )


def run_opportunity(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()

    scoring_path = _locate_scoring(root, today)
    if scoring_path is None:
        print("ERROR: no scoring.json; run `irc score` first.")
        return 2
    scores = _load_scores(scoring_path)

    theme_thesis = load_theme_thesis(root)
    instr_index = _instrument_index([
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    ])
    holdings = _holdings_index(bundle.account)
    portfolio_total_cny = sum(
        h.cost_basis_cny for acc in bundle.account.accounts for h in acc.holdings
    )

    rows: list[OpportunityRow] = []
    positions: dict[str, PositionContext] = {}
    qualities: dict[str, SelectionQuality] = {}
    for score in scores:
        iid = score["instrument_id"]
        instr = instr_index.get(iid)
        holding = holdings.get(iid)
        target_band: tuple[float, float] | None = None
        if instr is not None:
            tgt = bundle.preferences.asset_class_targets.get(instr.asset_class)
            if tgt is not None:
                target_band = (tgt.band[0], tgt.band[1])
        inp = _build_input(score, instr, holding, target_band, portfolio_total_cny)
        row = build_opportunity_row(inp, theme_thesis or None)
        rows.append(row)
        positions[iid] = PositionContext(
            portfolio_weight=inp.portfolio_weight,
            target_band_low=inp.target_band_low,
            target_band_high=inp.target_band_high,
            drawdown_since_entry=inp.drawdown_since_entry,
            is_holding=inp.is_holding,
        )
        qualities[iid] = _selection_quality_from(inp)

    # Same-theme reduction inside each theme bucket.
    by_theme: dict[str, list[OpportunityRow]] = {}
    for r in rows:
        by_theme.setdefault(r.theme or "_unthemed", []).append(r)
    kept_rows: list[OpportunityRow] = []
    dropped_rows: list[OpportunityRow] = []
    for theme, group in by_theme.items():
        if theme == "_unthemed":
            kept_rows.extend(group)
            continue
        kept, dropped = reduce_same_theme(group, qualities, max_per_theme=2)
        kept_rows.extend(kept)
        dropped_rows.extend(dropped)

    # Always include current holdings even if reduction dropped them.
    held_ids = set(holdings.keys())
    for r in dropped_rows:
        if r.instrument_id in held_ids and r not in kept_rows:
            kept_rows.append(r)

    cards = [
        build_thesis_card(
            row=r,
            position=positions[r.instrument_id],
            role=instr_index[r.instrument_id].theme or "watchlist"
            if r.instrument_id in instr_index else "watchlist",
            entry_reason=r.opportunity_reason.split(" | ")[0] if r.opportunity_reason else "",
        )
        for r in kept_rows
        if r.instrument_id in holdings or r.opportunity_state in ("core_dca", "small_watch")
    ]

    discipline_rows = [
        _discipline_row_from(r, positions[r.instrument_id]) for r in kept_rows
    ]

    out_dir = root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    atomic_write_text(
        out_dir / "opportunity_report.json",
        json.dumps(compose_opportunity_report(kept_rows, today), ensure_ascii=False, indent=2),
    )
    atomic_write_text(
        out_dir / "thesis_cards.yaml",
        compose_thesis_cards_yaml(cards),
    )
    atomic_write_text(
        out_dir / "discipline_report.md",
        compose_discipline_markdown(discipline_rows, today),
    )

    print(
        f"opportunity OK: {len(kept_rows)} rows, {len(cards)} cards, "
        f"{len(discipline_rows)} discipline entries -> {out_dir}"
    )
    return 0
```

- [ ] **Step 4: Register CLI command**

Edit `src/irc/cli.py`. After the `@main.command(help="Compose decision-readiness report from today's outputs.")` block ends (around `def decision(repo_root: str) -> None: ...`), insert:

```python
@main.command(help="Run opportunity/thesis/discipline layer; writes 3 outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def opportunity(repo_root: str) -> None:
    from irc.commands.opportunity_cmd import run_opportunity
    rc = run_opportunity(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Run the command tests**

```bash
uv run pytest tests/commands/test_opportunity_cmd.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Smoke-test the CLI**

```bash
uv run irc opportunity --help
```

Expected output contains `Run opportunity/thesis/discipline layer; writes 3 outputs.`.

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py src/irc/cli.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): irc opportunity CLI writes report/cards/discipline"
```

---

## Task 14: Eval metrics

**Files:**
- Create: `evals/opportunity/__init__.py`
- Create: `evals/opportunity/metrics.py`
- Create: `tests/evals/test_opportunity_metrics.py`

The eval reads `outputs/<date>/opportunity_report.json` + `thesis_cards.yaml` + `discipline_report.md` and computes:

1. **`thesis_card_required_field_completeness`** — average fraction of required fields populated across cards.
2. **`opportunity_evidence_gap_visibility`** — 1.0 if every row with any `evidence_insufficient` state lists at least one entry in `evidence_gaps`; else fraction.
3. **`same_theme_distinct_index_limit`** — 1.0 if no theme exceeds 2 distinct lookthrough keys in the report; else fraction.
4. **`drawdown_not_auto_sell`** — checks the discipline markdown for the "## 关于回撤的说明" section AND that no card has `do_not_sell_just_because` missing the 0.20 line.
5. **`hot_chase_prevention`** — 1.0 if every row whose `heat_state in {crowded, overheated}` and `opportunity_state in {core_dca, small_watch}` is absent. (Hot fund chasing = a row that the system put into a buy bucket while heat is overheated.)
6. **`valid_action_enums`** — every `dca_action` and `risk_action` in cards is in the allowed enum.
7. **`no_external_worktree_path`** — the opportunity command's source file does not contain the substring `investment-research-copilot.worktrees`.

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_opportunity_metrics.py`:

```python
from __future__ import annotations

import pytest

from evals.opportunity.metrics import (
    thesis_card_required_field_completeness,
    opportunity_evidence_gap_visibility,
    same_theme_distinct_index_limit,
    drawdown_not_auto_sell,
    hot_chase_prevention,
    valid_action_enums,
    no_external_worktree_path,
)


def _card(**overrides) -> dict:
    base = {
        "instrument_id": "510300",
        "name_cn": "X",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "core",
        "lookthrough_target": "沪深300",
        "entry_reason": "core",
        "valuation_state": "reasonable_low",
        "heat_state": "normal",
        "thesis_state": "intact",
        "product_quality_state": "acceptable",
        "opportunity_state": "core_dca",
        "dca_action": "normal_dca",
        "risk_action": "none",
        "falsification_triggers": ["a"],
        "trim_triggers": ["a"],
        "do_not_sell_just_because": ["drawdown_since_entry >= 0.20"],
        "review_cadence": "weekly_light_monthly_full",
        "evidence_gaps": [],
    }
    base.update(overrides)
    return base


def test_card_completeness_full_when_all_required_present():
    assert thesis_card_required_field_completeness([_card()]) == 1.0


def test_card_completeness_drops_when_field_missing():
    c = _card()
    del c["entry_reason"]
    result = thesis_card_required_field_completeness([c])
    assert 0.0 < result < 1.0


def test_evidence_gap_visibility_full_when_gaps_listed():
    rows = [
        {"valuation_state": "evidence_insufficient", "evidence_gaps": ["valuation"]},
        {"valuation_state": "cheap", "evidence_gaps": []},
    ]
    assert opportunity_evidence_gap_visibility(rows) == 1.0


def test_evidence_gap_visibility_partial_when_gap_hidden():
    rows = [
        {"valuation_state": "evidence_insufficient", "evidence_gaps": []},
        {"valuation_state": "evidence_insufficient", "evidence_gaps": ["valuation"]},
    ]
    assert opportunity_evidence_gap_visibility(rows) == 0.5


def test_same_theme_limit_passes_with_two_distinct_indices():
    rows = [
        {"theme": "healthcare", "lookthrough_key": "broad_healthcare"},
        {"theme": "healthcare", "lookthrough_key": "innovative_drugs"},
    ]
    assert same_theme_distinct_index_limit(rows) == 1.0


def test_same_theme_limit_fails_with_three_distinct_indices():
    rows = [
        {"theme": "healthcare", "lookthrough_key": "a"},
        {"theme": "healthcare", "lookthrough_key": "b"},
        {"theme": "healthcare", "lookthrough_key": "c"},
    ]
    result = same_theme_distinct_index_limit(rows)
    assert result < 1.0


def test_drawdown_not_auto_sell_full_when_section_present_and_cards_have_clause():
    md = "## 关于回撤的说明\n回撤 20% 不构成卖出。"
    cards = [_card()]
    assert drawdown_not_auto_sell(md, cards) == 1.0


def test_drawdown_not_auto_sell_fails_when_section_missing():
    md = "no chinese section"
    cards = [_card()]
    assert drawdown_not_auto_sell(md, cards) < 1.0


def test_drawdown_not_auto_sell_fails_when_card_missing_clause():
    md = "## 关于回撤的说明"
    bad = _card(do_not_sell_just_because=[])
    assert drawdown_not_auto_sell(md, [bad]) < 1.0


def test_hot_chase_prevention_full_when_no_overheated_in_buy_buckets():
    rows = [
        {"heat_state": "normal", "opportunity_state": "core_dca"},
        {"heat_state": "overheated", "opportunity_state": "pause_wait"},
    ]
    assert hot_chase_prevention(rows) == 1.0


def test_hot_chase_prevention_drops_when_overheated_in_core_dca():
    rows = [
        {"heat_state": "overheated", "opportunity_state": "core_dca"},
        {"heat_state": "normal", "opportunity_state": "core_dca"},
    ]
    assert hot_chase_prevention(rows) == 0.5


def test_valid_action_enums_full_when_all_legal():
    assert valid_action_enums([_card()]) == 1.0


def test_valid_action_enums_drops_when_invalid_value():
    bad = _card(dca_action="ramp_up_dca")
    assert valid_action_enums([bad]) < 1.0


def test_no_external_worktree_path_full_when_substring_absent():
    src = "from pathlib import Path\nrun(...)"
    assert no_external_worktree_path(src) == 1.0


def test_no_external_worktree_path_fails_when_substring_present():
    src = "Path('/Users/snow/Documents/Repository/investment-research-copilot.worktrees/x/cn_funds.generated.yaml')"
    assert no_external_worktree_path(src) == 0.0
```

- [ ] **Step 2: Run the tests**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement metrics**

Write `evals/opportunity/__init__.py`:

```python
```

Write `evals/opportunity/metrics.py`:

```python
from __future__ import annotations


_REQUIRED_CARD_FIELDS: tuple[str, ...] = (
    "instrument_id", "name_cn", "asset_class", "theme", "role",
    "lookthrough_target", "entry_reason", "valuation_state", "heat_state",
    "thesis_state", "product_quality_state", "opportunity_state",
    "dca_action", "risk_action", "falsification_triggers", "trim_triggers",
    "do_not_sell_just_because", "review_cadence", "evidence_gaps",
)

_LEGAL_DCA: frozenset[str] = frozenset(
    {"accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy"}
)
_LEGAL_RISK: frozenset[str] = frozenset(
    {"none", "review_required", "trim_review", "exit_review"}
)


def thesis_card_required_field_completeness(cards: list[dict]) -> float:
    if not cards:
        return 1.0
    ratios: list[float] = []
    for c in cards:
        present = sum(1 for k in _REQUIRED_CARD_FIELDS if k in c and c[k] not in (None, "", []))
        ratios.append(present / len(_REQUIRED_CARD_FIELDS))
    return sum(ratios) / len(ratios)


def opportunity_evidence_gap_visibility(rows: list[dict]) -> float:
    insufficient_states = {"evidence_insufficient"}
    relevant: list[dict] = [
        r for r in rows
        if any(
            r.get(field) in insufficient_states
            for field in ("valuation_state", "heat_state", "thesis_state", "product_quality_state")
        )
    ]
    if not relevant:
        return 1.0
    visible = sum(1 for r in relevant if r.get("evidence_gaps"))
    return visible / len(relevant)


def same_theme_distinct_index_limit(rows: list[dict]) -> float:
    """1.0 if every theme has ≤2 distinct lookthrough_key entries.
    Otherwise returns the fraction of themes within the limit."""
    by_theme: dict[str, set[str]] = {}
    for r in rows:
        theme = r.get("theme") or "_unthemed"
        key = r.get("lookthrough_key") or r.get("lookthrough_target") or ""
        by_theme.setdefault(theme, set()).add(key)
    if not by_theme:
        return 1.0
    ok = sum(1 for keys in by_theme.values() if len(keys) <= 2)
    return ok / len(by_theme)


def drawdown_not_auto_sell(markdown: str, cards: list[dict]) -> float:
    """Full score requires BOTH:
       - Markdown contains the 关于回撤的说明 section,
       - Every card lists `drawdown_since_entry >= 0.20` under do_not_sell_just_because.
    """
    parts: list[float] = []
    parts.append(1.0 if "## 关于回撤的说明" in markdown else 0.0)
    if cards:
        ok = sum(
            1 for c in cards
            if any("0.20" in t for t in c.get("do_not_sell_just_because", []))
        )
        parts.append(ok / len(cards))
    else:
        parts.append(1.0)
    return sum(parts) / len(parts)


def hot_chase_prevention(rows: list[dict]) -> float:
    """A row is hot-chasing if heat is crowded/overheated AND opportunity_state
    puts it in a buy bucket (core_dca or small_watch)."""
    if not rows:
        return 1.0
    hot_states = {"crowded", "overheated"}
    buy_buckets = {"core_dca", "small_watch"}
    bad = sum(
        1 for r in rows
        if r.get("heat_state") in hot_states
        and r.get("opportunity_state") in buy_buckets
    )
    return (len(rows) - bad) / len(rows)


def valid_action_enums(cards: list[dict]) -> float:
    if not cards:
        return 1.0
    ok = sum(
        1 for c in cards
        if c.get("dca_action") in _LEGAL_DCA and c.get("risk_action") in _LEGAL_RISK
    )
    return ok / len(cards)


def no_external_worktree_path(source: str) -> float:
    return 0.0 if "investment-research-copilot.worktrees" in source else 1.0
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/evals/test_opportunity_metrics.py -v
```

Expected: 12+ passed.

- [ ] **Step 5: Commit**

```bash
git add evals/opportunity/__init__.py evals/opportunity/metrics.py tests/evals/test_opportunity_metrics.py
git commit -m "feat(evals): opportunity metrics for cards, gaps, hot-chase, drawdown"
```

---

## Task 15: Eval runner + stage registration

**Files:**
- Create: `evals/opportunity/runner.py`
- Create: `tests/evals/test_opportunity_runner.py`
- Modify: `src/irc/commands/eval_cmd.py`

- [ ] **Step 1: Write the failing test**

Write `tests/evals/test_opportunity_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.opportunity.runner import run


def _seed_outputs(tmp_path: Path) -> Path:
    out = tmp_path / "outputs" / "2026-05-14"
    out.mkdir(parents=True)
    (out / "opportunity_report.json").write_text(
        json.dumps({
            "date": "2026-05-14",
            "summary": {"core_dca_count": 1, "small_watch_count": 0,
                        "pause_wait_count": 0, "exclude_count": 0},
            "rows": [{
                "instrument_id": "510300",
                "name_cn": "X",
                "asset_class": "cn_etf",
                "theme": "broad",
                "lookthrough_target": "沪深300",
                "lookthrough_kind": "broad_index",
                "lookthrough_key": "csi300",
                "valuation_state": "reasonable_low",
                "heat_state": "normal",
                "thesis_state": "intact",
                "product_quality_state": "acceptable",
                "opportunity_state": "core_dca",
                "opportunity_reason": "x",
                "evidence_gaps": [],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / "thesis_cards.yaml").write_text(
        yaml.safe_dump({"cards": [{
            "instrument_id": "510300", "name_cn": "X", "asset_class": "cn_etf",
            "theme": "broad", "role": "core", "lookthrough_target": "沪深300",
            "entry_reason": "core",
            "valuation_state": "reasonable_low", "heat_state": "normal",
            "thesis_state": "intact", "product_quality_state": "acceptable",
            "opportunity_state": "core_dca",
            "dca_action": "normal_dca", "risk_action": "none",
            "falsification_triggers": ["a"], "trim_triggers": ["a"],
            "do_not_sell_just_because": ["drawdown_since_entry >= 0.20"],
            "review_cadence": "weekly_light_monthly_full",
            "evidence_gaps": [],
        }]}, allow_unicode=True),
        encoding="utf-8",
    )
    (out / "discipline_report.md").write_text(
        "# Discipline Report — 2026-05-14\n\n"
        "## 今日可定投\n- foo\n\n"
        "## 暂停加仓\n（无）\n\n"
        "## 风险复核\n（无）\n\n"
        "## 调仓复核\n（无）\n\n"
        "## 退出复核\n（无）\n\n"
        "## 关于回撤的说明\n持仓回撤 20% 不构成卖出。\n",
        encoding="utf-8",
    )
    return out


def test_runner_returns_zero_when_no_inputs(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 0
    report = tmp_path / "outputs" / "evals" / "opportunity" / "report.json"
    # The "no inputs" report still writes under today's folder (handled by runner).
    candidates = list((tmp_path / "outputs").glob("*/evals/opportunity/report.json"))
    assert candidates, "runner must always write a report"


def test_runner_writes_report_with_metrics(tmp_path: Path):
    out = _seed_outputs(tmp_path)
    rc = run(tmp_path)
    assert rc in (0, 1)  # PASS or WARN
    report_path = out / "evals" / "opportunity" / "report.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text())
    metric_names = {m["name"] for m in payload["metrics"]}
    expected = {
        "thesis_card_required_field_completeness",
        "opportunity_evidence_gap_visibility",
        "same_theme_distinct_index_limit",
        "drawdown_not_auto_sell",
        "hot_chase_prevention",
        "valid_action_enums",
        "no_external_worktree_path",
    }
    assert expected.issubset(metric_names)


def test_runner_fails_when_external_worktree_path_referenced(tmp_path: Path, monkeypatch):
    """If the opportunity_cmd.py source ever references the external
    worktree path, the eval must FAIL."""
    out = _seed_outputs(tmp_path)
    # Force the runner to see a polluted source file
    monkeypatch.setattr(
        "evals.opportunity.runner._read_opportunity_cmd_source",
        lambda: "x = 'investment-research-copilot.worktrees/foo'",
    )
    rc = run(tmp_path)
    assert rc == 2
    report = json.loads((out / "evals" / "opportunity" / "report.json").read_text())
    assert report["overall"] == "FAIL"
```

- [ ] **Step 2: Run the tests**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement runner**

Write `evals/opportunity/runner.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from evals._shared.report_schema import MetricReport, StageReport, report_to_dict
from evals._shared.status import classify_status, worst_status
from evals.opportunity.metrics import (
    drawdown_not_auto_sell,
    hot_chase_prevention,
    no_external_worktree_path,
    opportunity_evidence_gap_visibility,
    same_theme_distinct_index_limit,
    thesis_card_required_field_completeness,
    valid_action_enums,
)
from irc.io_utils import atomic_write_text


_TZ = timezone(timedelta(hours=8))
_HIGH_TH = {"warn_below": 0.95, "fail_below": 0.80}
_BINARY_TH = {"warn_below": 1.0, "fail_below": 1.0}


def _today() -> str:
    return datetime.now(_TZ).date().isoformat()


def _locate_inputs(root: Path) -> tuple[Path | None, Path | None, Path | None, str]:
    today = _today()
    today_dir = root / "outputs" / today
    target_dir = today_dir if today_dir.exists() else None
    if target_dir is None:
        dated = sorted((root / "outputs").glob("*/opportunity_report.json"))
        if not dated:
            return None, None, None, today
        target_dir = dated[-1].parent
    report = target_dir / "opportunity_report.json"
    cards = target_dir / "thesis_cards.yaml"
    md = target_dir / "discipline_report.md"
    return (
        report if report.exists() else None,
        cards if cards.exists() else None,
        md if md.exists() else None,
        target_dir.name,
    )


def _read_opportunity_cmd_source() -> str:
    from irc.commands import opportunity_cmd as opp_mod
    return Path(opp_mod.__file__).read_text(encoding="utf-8")


def run(repo_root: Path) -> int:
    root = Path(repo_root)
    report_path, cards_path, md_path, date_str = _locate_inputs(root)

    if report_path is None:
        empty = StageReport(
            stage="opportunity", ran_at=datetime.now(_TZ).isoformat(),
            based_on=[], metrics=[], overall="PASS",
        )
        _write(root, empty, date_str)
        print(f"opportunity eval: PASS (no input file)")
        return 0

    rows = json.loads(report_path.read_text(encoding="utf-8")).get("rows", [])
    cards = (
        yaml.safe_load(cards_path.read_text(encoding="utf-8")).get("cards", [])
        if cards_path is not None else []
    )
    md = md_path.read_text(encoding="utf-8") if md_path is not None else ""
    src = _read_opportunity_cmd_source()

    metrics_values = {
        "thesis_card_required_field_completeness": thesis_card_required_field_completeness(cards),
        "opportunity_evidence_gap_visibility": opportunity_evidence_gap_visibility(rows),
        "same_theme_distinct_index_limit": same_theme_distinct_index_limit(rows),
        "drawdown_not_auto_sell": drawdown_not_auto_sell(md, cards),
        "hot_chase_prevention": hot_chase_prevention(rows),
        "valid_action_enums": valid_action_enums(cards),
        "no_external_worktree_path": no_external_worktree_path(src),
    }
    thresholds = {
        "thesis_card_required_field_completeness": _HIGH_TH,
        "opportunity_evidence_gap_visibility": _HIGH_TH,
        "same_theme_distinct_index_limit": _BINARY_TH,
        "drawdown_not_auto_sell": _BINARY_TH,
        "hot_chase_prevention": _BINARY_TH,
        "valid_action_enums": _BINARY_TH,
        "no_external_worktree_path": _BINARY_TH,
    }
    n_obs = {
        "thesis_card_required_field_completeness": len(cards),
        "opportunity_evidence_gap_visibility": len(rows),
        "same_theme_distinct_index_limit": len(rows),
        "drawdown_not_auto_sell": len(cards),
        "hot_chase_prevention": len(rows),
        "valid_action_enums": len(cards),
        "no_external_worktree_path": 1,
    }
    metrics_list = [
        MetricReport(
            name=name, value=value,
            status=classify_status(value, thresholds[name], "higher_is_better"),
            n_observations=n_obs[name], threshold=thresholds[name],
        )
        for name, value in metrics_values.items()
    ]
    overall = worst_status([m.status for m in metrics_list])
    report = StageReport(
        stage="opportunity", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(report_path)] + ([str(cards_path)] if cards_path else [])
        + ([str(md_path)] if md_path else []),
        metrics=metrics_list, overall=overall,
    )
    _write(root, report, date_str)
    print(f"opportunity eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "opportunity"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Register stage**

Edit `src/irc/commands/eval_cmd.py`. Add `"opportunity"` to the `runners` dict and to the `all_stages` tuple:

```python
def _get_runner(stage: str) -> Callable[[Path], int]:
    runners: dict[str, str] = {
        "data":         "evals.data.runner",
        "news":         "evals.news.runner",
        "research":     "evals.research.runner",
        "discovery":    "evals.discovery.runner",
        "scoring":      "evals.scoring.runner",
        "gold_score":   "evals.gold_score.runner",
        "allocation":   "evals.allocation.runner",
        "trade_plan":   "evals.trade_plan.runner",
        "memo":         "evals.memo.runner",
        "queries":      "evals.queries.runner",
        "triggers":     "evals.triggers.runner",
        "architecture": "evals.architecture.runner",
        "opportunity":  "evals.opportunity.runner",
    }
    ...
```

And in `run_eval`:

```python
        for s in ("data", "news", "research", "discovery", "scoring",
                   "gold_score", "allocation", "trade_plan",
                   "memo", "queries", "triggers", "architecture",
                   "opportunity"):
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/evals/test_opportunity_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Smoke test the CLI**

```bash
uv run irc eval opportunity
```

Expected: prints `opportunity eval: PASS (no input file)` and exits 0 in a fresh repo.

- [ ] **Step 7: Commit**

```bash
git add evals/opportunity/runner.py tests/evals/test_opportunity_runner.py src/irc/commands/eval_cmd.py
git commit -m "feat(evals): opportunity eval runner + stage registration"
```

---

## Task 16: Integration test — opportunity pipeline end-to-end

**Files:**
- Create: `tests/integration/test_opportunity_pipeline.py`

- [ ] **Step 1: Write the test**

Write `tests/integration/test_opportunity_pipeline.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from irc.commands.opportunity_cmd import run_opportunity


def _seed(tmp_path: Path) -> None:
    """Seed inputs/, config/, and outputs/scoring.json with realistic data
    that covers core_dca, pause_wait, and exclude buckets."""
    repo_src = Path(__file__).resolve().parents[2]
    tpl = repo_src / "src" / "irc" / "templates"

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()

    # Copy required config templates
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund, cn_brokerage]\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band: {max_drawdown: [0.05, 0.20], horizon: long_core_medium_rotation}\n"
        "universe: {cn_funds: true, cn_etfs: true, hk_etfs: true, us_etfs: true}\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance: {cny: [0.5, 1.0], usd: [0.0, 0.4], hkd: [0.0, 0.3]}\n"
        "constraints: {allow_short: false, allow_leverage: false, exclude_themes: []}\n"
        "investment_plan: {monthly_new_capital_cny: 5000}\n"
        "report_language: zh\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "opportunity" / "theme_thesis.yaml").write_text(
        "themes:\n"
        "  broad: intact\n"
        "  semiconductor: intact\n"
        "  real_estate: falsified\n",
        encoding="utf-8",
    )
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({"scores": [
            {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core",
             "composite_score": 80, "action": "buy_candidate", "data_completeness": 0.9,
             "factor_breakdown": {}},
            {"instrument_id": "512760", "asset_class": "cn_etf", "role": "satellite",
             "composite_score": 60, "action": "watch", "data_completeness": 0.7,
             "factor_breakdown": {}},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_pipeline_produces_three_outputs(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    report = json.loads((out / "opportunity_report.json").read_text())
    assert report["date"] == "2026-05-14"
    assert any(r["instrument_id"] == "510300" for r in report["rows"])
    cards = yaml.safe_load((out / "thesis_cards.yaml").read_text())
    assert isinstance(cards.get("cards"), list)
    md = (out / "discipline_report.md").read_text()
    assert "## 关于回撤的说明" in md


def test_opportunity_pipeline_preserves_holdings_even_when_dropped(tmp_path: Path, monkeypatch):
    """A holding must always appear in the output, even if same-theme
    reduction would have dropped it."""
    _seed(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    rows = json.loads(
        (tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text()
    )["rows"]
    assert any(r["instrument_id"] == "510300" for r in rows)
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/integration/test_opportunity_pipeline.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_opportunity_pipeline.py
git commit -m "test(opportunity): integration test for end-to-end pipeline"
```

---

## Task 17: Integration test — decision command without opportunity outputs

**Files:**
- Create: `tests/integration/test_decision_without_opportunity.py`

This test guards the spec's acceptance criterion that existing `decision` behaviour is unchanged when opportunity outputs are absent.

- [ ] **Step 1: Write the test**

Write `tests/integration/test_decision_without_opportunity.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_decision_command_exit_zero_with_no_opportunity_files(tmp_path: Path, monkeypatch):
    """The decision command must run unchanged when opportunity outputs
    are absent. Existing functionality is preserved as a sidecar layer.
    """
    from irc.commands.decision_cmd import run_decision
    repo_src = Path(__file__).resolve().parents[2]
    tpl = repo_src / "src" / "irc" / "templates"

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n  - broker: cmb\n    currency: cny\n"
        "    available_venues: [cmb_fund]\n"
        "    holdings:\n      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band: {max_drawdown: [0.05, 0.20], horizon: long_core_medium_rotation}\n"
        "universe: {cn_funds: true, cn_etfs: true, hk_etfs: true, us_etfs: true}\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance: {cny: [0.5, 1.0], usd: [0.0, 0.4], hkd: [0.0, 0.3]}\n"
        "constraints: {allow_short: false, allow_leverage: false, exclude_themes: []}\n"
        "investment_plan: {monthly_new_capital_cny: 5000}\n"
        "report_language: zh\n",
        encoding="utf-8",
    )
    # Seed minimal upstream outputs the decision command expects.
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({"scores": []}), encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    rc = run_decision(repo_root=str(tmp_path))
    # rc may be 0 (success) or 2 (missing upstream). It MUST NOT raise.
    assert rc in (0, 2)
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/integration/test_decision_without_opportunity.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_decision_without_opportunity.py
git commit -m "test(opportunity): decision command unchanged when opportunity absent"
```

---

## Task 18: Final full-suite verification

- [ ] **Step 1: Run the entire test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all tests pass; **no regressions** in previously-existing tests under `tests/scoring/`, `tests/allocation/`, `tests/discovery/`, etc.

- [ ] **Step 2: Run all evals**

```bash
uv run irc eval --all --repo-root .
```

Expected: every stage (including the new `opportunity`) reports PASS (or no-input PASS) and the command exits 0. If `opportunity` reports WARN or FAIL, inspect `outputs/<today>/evals/opportunity/report.json` and fix the implementation — do not relax thresholds.

- [ ] **Step 3: Confirm acceptance criteria one-by-one against the spec**

Re-read `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md` § Acceptance Criteria. For each bullet, confirm with a grep / quick run that the implementation satisfies it:

| Criterion | Confirmation |
| :--- | :--- |
| Never uses external worktree path at runtime | `grep -r 'investment-research-copilot.worktrees' src/ evals/` returns no matches in source (only in spec/handoff docs). |
| Opportunity states deterministic from explicit inputs | All `src/irc/opportunity/*` are pure (no `datetime.now`, no I/O); covered by unit tests. |
| Same-theme / same-index reduced before deep research | `selection.reduce_same_theme` runs inside `run_opportunity` before card building. |
| Explains why a hot profitable fund is paused | `derive_dca_action` returns `pause_dca` when `opportunity_state == pause_wait` (covered by `test_pause_when_expensive`). |
| Explains why 20% drawdown is review-only | `discipline.derive_risk_action` returns `review_required`, never `exit_review`, on drawdown alone (covered by `test_drawdown_alone_only_triggers_review_required`, `test_drawdown_50_still_not_auto_exit`). |
| Output distinguishes DCA / pause / review / trim / exit | `compose_discipline_markdown` produces five sections (covered by `test_discipline_markdown_has_chinese_action_sections`). |
| Evidence gaps visible in JSON/YAML and Markdown | `evidence_gaps` field is in `OpportunityRow`, `ThesisCard`, and surfaced in `compose_opportunity_report` / `compose_thesis_cards_yaml`. |
| Active funds remain supplementary | `classify_product_quality` demotes active funds without manager evidence to `weak` or below (covered by `test_active_fund_demoted_when_manager_tenure_missing`). |

- [ ] **Step 4: Final commit (only if anything was tweaked)**

If the verification surfaced any small fixes, commit them:

```bash
git add -A
git commit -m "chore(opportunity): final fixes from acceptance verification"
```

- [ ] **Step 5: Summarize for the user**

Print a final summary to the conversation containing:
- count of new files, test files, eval files
- total test count + pass/fail
- the file paths of the three new output artifacts (`opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md`)
- the eval command to run on a real repo: `uv run irc opportunity && uv run irc eval opportunity`

Do **not** merge to main, do **not** push, do **not** open a PR. Hand back to the user for review.

---

## Notes For The Implementing Engineer

- **Resist scope creep.** This plan implements the spec's "Implementation Plan Scope" section verbatim — pure rules, deterministic discipline. Do not add multi-agent debate, Kronos signals, or full portfolio sell sizing.
- **Preserve detached-HEAD safety.** The worktree opens on a detached HEAD; Task 0 prep is `git checkout -b feat/opportunity-thesis-discipline`. Each task commit lands on that branch, never on `main`.
- **One commit per task.** Frequent commits make rollback trivial if a later task surfaces a design problem in an earlier one.
- **Do not bypass type checking.** This codebase uses pydantic + frozen dataclasses on purpose. If `mypy` or runtime validation complains, fix the type, do not cast.
- **Do not modify allocation behaviour.** The spec is explicit: opportunity runs as a sidecar in this first implementation. Later work will let allocation consume `opportunity_state`; that is a separate plan.
- **README updates are out of scope here.** The spec defers README to after implementation; the user reviews first.
