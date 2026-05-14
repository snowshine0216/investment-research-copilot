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
