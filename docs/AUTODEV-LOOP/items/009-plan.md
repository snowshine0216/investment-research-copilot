# Item 009 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/009-spec.md`. Base: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-009-fundamentals-backfill`.

## Diagnosis (which 2-3 metrics are systematically missing)

Read `src/irc/scoring/metrics_loader.py:39-57`:

1. **`aum_stability_pct`** — hardcoded `math.nan` at line 54 with the comment _"aum_stability_pct requires a multi-period AUM history we do not yet ingest"_. UNIVERSALLY MISSING for every instrument, every asset_class.
2. **`holdings_concentration_top10`** — computed from `fund_holdings` table at `_latest_holdings_concentration` (lines 127-144). For instruments without holdings data (gold ETFs, broad-index ETFs, bond funds without per-issuer reporting), it returns NaN. Systematically missing for non-active-equity asset classes.
3. **`downside_capture`** — at line 53, falls back to risk dict from `derive_risk_metrics`. For asset classes whose price-vs-benchmark relationship doesn't translate (bonds, gold), even the computed value is semantically wrong even when present.

The completeness distribution in `outputs/2026-05-17/decision_report.md` (`0.57 = 4/7` and `0.71 = 5/7`) maps cleanly to:
- 4/7 = missing aum_stability + holdings_concentration + downside_capture (gold/bond instruments)
- 5/7 = missing aum_stability + holdings_concentration (ETFs / passive index funds)

## Goal

Make `completeness_ratio` asset-class-aware so structurally-inapplicable metrics aren't counted against an instrument. Specifically:

- **Drop `aum_stability_pct` from required for ALL asset classes** until the ingest pipeline writes a multi-period AUM history. (Don't fake the metric; honestly drop it from the requirement.)
- **Drop `holdings_concentration_top10` from required for** `cn_etf`, `us_etf`, `hk_etf`, `cn_bond_fund`, `gold`. (Index ETFs don't choose holdings; bond/gold have no equity-style top-10.)
- **Drop `downside_capture` from required for** `cn_bond_fund`, `gold`. (Different reference market.)
- **Keep `expense_ratio`, `drawdown_3y`, `vol_1y`, `manager_tenure_years`** as required for all classes (price-derivable or already-ingested).

The constant `REQUIRED_METRIC_FIELDS` itself is preserved — it's still the SUPERSET of all candidates. The per-asset-class subset is the new addition.

## Files

| File | Change |
|---|---|
| `src/irc/decision/completeness.py` | New `REQUIRED_METRICS_BY_ASSET_CLASS` mapping + `required_for_asset_class()` + asset_class kwarg on `missing_required_fields` / `completeness_ratio` |
| `src/irc/scoring/pipeline.py:88-92` | Pass `r.asset_class` through to the new helpers |
| `tests/decision/test_completeness.py` (extend) | Asset-class-aware regression tests |
| `tests/scoring/` | Verify scoring still computes correct completeness for sample classes |

---

## Task 1: Asset-class-aware required metrics in `completeness.py`

### Step 1.1: Write failing tests

- [ ] Add to `tests/decision/test_completeness.py`:

```python
from irc.decision.completeness import (
    REQUIRED_METRIC_FIELDS,
    REQUIRED_METRICS_BY_ASSET_CLASS,
    completeness_ratio,
    missing_required_fields,
    required_for_asset_class,
)


def _all_metrics_present() -> dict:
    return {f: 1.0 for f in REQUIRED_METRIC_FIELDS}


def test_required_for_asset_class_drops_aum_stability_universally():
    for cls in ("cn_etf", "cn_equity_fund", "cn_bond_fund", "gold", "us_etf", "hk_etf"):
        assert "aum_stability_pct" not in required_for_asset_class(cls)


def test_required_for_cn_etf_drops_holdings_concentration():
    req = required_for_asset_class("cn_etf")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" in req  # ETFs DO have equity downside capture
    assert "manager_tenure_years" in req


def test_required_for_cn_bond_fund_drops_both_holdings_and_downside():
    req = required_for_asset_class("cn_bond_fund")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" not in req


def test_required_for_gold_drops_holdings_and_downside():
    req = required_for_asset_class("gold")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" not in req


def test_required_for_active_equity_fund_keeps_holdings_concentration():
    req = required_for_asset_class("cn_equity_fund")
    assert "holdings_concentration_top10" in req  # active funds DO report top-10


def test_required_for_unknown_asset_class_falls_back_to_default():
    """Unrecognized asset_class should not silently drop everything — it falls
    back to the full set minus aum_stability_pct."""
    req = required_for_asset_class("unknown_class_xyz")
    assert "expense_ratio" in req
    assert "holdings_concentration_top10" in req
    assert "aum_stability_pct" not in req


def test_completeness_ratio_uses_asset_class_when_provided():
    """A gold instrument missing only holdings_concentration_top10 + downside_capture
    should score 1.0, not 5/7, because those aren't required for gold."""
    row = {
        "expense_ratio": 0.005, "drawdown_3y": 0.18, "vol_1y": 0.25,
        "manager_tenure_years": 7.0,
        # aum_stability_pct, holdings_concentration_top10, downside_capture all missing
    }
    assert completeness_ratio(row, asset_class="gold") == 1.0


def test_completeness_ratio_falls_back_to_full_required_when_no_asset_class():
    """Back-compat: omitting asset_class uses the full REQUIRED_METRIC_FIELDS."""
    row = {f: 1.0 for f in REQUIRED_METRIC_FIELDS}
    assert completeness_ratio(row) == 1.0


def test_missing_required_fields_uses_asset_class_when_provided():
    row = {"expense_ratio": 0.005}
    missing = missing_required_fields(row, asset_class="gold")
    # Gold requires expense_ratio, drawdown_3y, vol_1y, manager_tenure_years
    assert "drawdown_3y" in missing
    assert "vol_1y" in missing
    assert "manager_tenure_years" in missing
    assert "holdings_concentration_top10" not in missing  # not required for gold
    assert "downside_capture" not in missing
    assert "aum_stability_pct" not in missing
```

### Step 1.2: Run tests, expect failure
- [ ] Run: `uv run pytest tests/decision/test_completeness.py -k "required_for_asset_class or uses_asset_class or falls_back_to_full" -v`
- [ ] Expected: most FAIL — `REQUIRED_METRICS_BY_ASSET_CLASS` / `required_for_asset_class` don't exist; `completeness_ratio` doesn't accept `asset_class`.

### Step 1.3: Implement asset-class-aware required sets
- [ ] Replace `src/irc/decision/completeness.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


REQUIRED_METRIC_FIELDS: tuple[str, ...] = (
    "expense_ratio",
    "drawdown_3y",
    "vol_1y",
    "downside_capture",
    "aum_stability_pct",
    "manager_tenure_years",
    "holdings_concentration_top10",
)

MIN_BUY_COMPLETENESS: float = 0.80

# Per-asset-class required metric subsets. Universally dropped:
#   - aum_stability_pct (we do not yet ingest a multi-period AUM history —
#     see metrics_loader.py:54). Keeping it as "required" would bias completeness
#     down across every instrument; honest drop until the data lands.
# Asset-class-specific drops:
#   - holdings_concentration_top10: dropped for index ETFs (the benchmark
#     dictates concentration, not the fund) and for bond/gold (no equity-style
#     top-10). Kept for active equity funds.
#   - downside_capture: dropped for bonds and gold (different reference market;
#     the computed value is not semantically meaningful).
_FULL_MINUS_AUM_STABILITY: tuple[str, ...] = tuple(
    f for f in REQUIRED_METRIC_FIELDS if f != "aum_stability_pct"
)

REQUIRED_METRICS_BY_ASSET_CLASS: Mapping[str, tuple[str, ...]] = {
    "cn_equity_fund": _FULL_MINUS_AUM_STABILITY,
    "cn_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "us_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "hk_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "cn_bond_fund": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY
        if f not in ("holdings_concentration_top10", "downside_capture")
    ),
    "gold": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY
        if f not in ("holdings_concentration_top10", "downside_capture")
    ),
}


def required_for_asset_class(asset_class: str | None) -> tuple[str, ...]:
    """Return the required-metric set for the given asset_class.

    Unrecognized or `None` asset_class falls back to the full required set
    minus `aum_stability_pct` (the universal drop).
    """
    if asset_class is None:
        return _FULL_MINUS_AUM_STABILITY
    return REQUIRED_METRICS_BY_ASSET_CLASS.get(asset_class, _FULL_MINUS_AUM_STABILITY)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def missing_required_fields(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
) -> tuple[str, ...]:
    """Return the names of required fields that are missing on `row`.

    Precedence: explicit `required` > `asset_class`-derived set > full required.
    """
    if required is None:
        required = (
            required_for_asset_class(asset_class)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    if row is None:
        return tuple(required)
    return tuple(field for field in required if is_missing(row.get(field)))


def completeness_ratio(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
) -> float:
    """Fraction of required fields present on `row`. 1.0 when nothing is required."""
    if required is None:
        required = (
            required_for_asset_class(asset_class)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    if not required:
        return 1.0
    missing = missing_required_fields(row, required)
    return (len(required) - len(missing)) / len(required)


def summarize_completeness(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    if not rows:
        return {"overall_avg": 1.0, "by_asset_class": {}}
    values = [float(row.get("data_completeness", 0.0)) for row in rows]
    by_class_values: dict[str, list[float]] = {}
    for row in rows:
        asset_class = str(row.get("asset_class", "unknown"))
        by_class_values.setdefault(asset_class, []).append(
            float(row.get("data_completeness", 0.0))
        )
    by_asset_class = {
        asset_class: sum(class_values) / len(class_values)
        for asset_class, class_values in by_class_values.items()
    }
    return {"overall_avg": sum(values) / len(values), "by_asset_class": by_asset_class}
```

### Step 1.4: Run tests, verify pass
- [ ] Run: `uv run pytest tests/decision/test_completeness.py -v`
- [ ] Expected: new tests PASS, existing tests still PASS (default behavior unchanged when no asset_class given).

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/decision/completeness.py tests/decision/test_completeness.py
git commit -m "feat(decision): asset-class-aware required-metrics + drop aum_stability_pct"
```

---

## Task 2: Wire asset_class through `scoring/pipeline.py`

### Step 2.1: Inspect the scoring row type
- [ ] Read `src/irc/scoring/pipeline.py` around lines 88-92 and find the type of `r` (likely a dataclass with `asset_class`). If `r.asset_class` exists, proceed. If not, STOP — that's a deeper refactor than the plan covers.

### Step 2.2: Write the failing test
- [ ] Find the existing scoring pipeline test (likely `tests/scoring/test_pipeline.py` or `tests/commands/test_score_cmd.py`). Add a test that:
  - Builds a gold-instrument scoring input with `aum_stability_pct`, `holdings_concentration_top10`, `downside_capture` all NaN
  - Runs the scoring pipeline
  - Asserts the resulting `data_completeness` is 1.0 (because gold doesn't require those three)
  - Without the wiring change, this test fails with `data_completeness ≈ 0.57`.

### Step 2.3: Wire asset_class through
- [ ] In `src/irc/scoring/pipeline.py:91-92`, change:

```python
        completeness = _completeness(m, _REQUIRED)
        missing_data = list(missing_required_fields(m, _REQUIRED))
```

to:

```python
        asset_class = getattr(r, "asset_class", None)
        completeness = completeness_ratio(m, asset_class=asset_class)
        missing_data = list(missing_required_fields(m, asset_class=asset_class))
```

(And update the local `_completeness` helper or import `completeness_ratio` from `irc.decision.completeness` — pick whichever is more consistent with the existing code.)

### Step 2.4: Run tests
- [ ] Run: `uv run pytest tests/scoring/ tests/commands/test_score_cmd.py tests/decision/ -v`
- [ ] Expected: new test PASSes; existing tests still PASS. Any test that asserted on a specific low completeness for an instrument should be updated to reflect the new asset-class-aware value.

### Step 2.5: Commit
- [ ] Run:

```bash
git add src/irc/scoring/pipeline.py tests/
git commit -m "feat(scoring): use asset-class-aware completeness in scoring pipeline"
```

---

## Task 3: Full-suite verification

### Step 3.1: Run all tests
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS.

### Step 3.2: Ruff
- [ ] Run: `uv run ruff check src/irc/decision/ src/irc/scoring/ tests/decision/ tests/scoring/`
- [ ] Expected: no new findings.
