"""Tests for `resolve_trigger_current_value` after relocation to sizing.py.

Pure function: maps a trade_plan trigger dict + live snapshots to a
(value, unit_hint) pair consumed by `format_why_when_line` and
`_format_trigger_status_compact`. No I/O, no caching.
"""
from __future__ import annotations

from irc.decision.sizing import MACRO_FIELD_TO_KEY, resolve_trigger_current_value


def test_macro_field_to_key_maps_known_macro_fields() -> None:
    """The mapping covers the three macro series the trade plan can name."""
    assert MACRO_FIELD_TO_KEY["macro.vix"] == "vix"
    assert MACRO_FIELD_TO_KEY["macro.real_yield_10y_tips"] == "real_yield_10y_tips"
    assert MACRO_FIELD_TO_KEY["macro.dxy"] == "DXY"


def test_resolve_trigger_instrument_weekly_return_returns_pct_unit() -> None:
    """`instrument.weekly_return` short-circuits to weekly_return_by_id[iid]
    with unit 'pct' (caller formats as XX.XX%)."""
    trig = {"data_field": "instrument.weekly_return"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={"vix": 16.76},
        weekly_return_by_id={"510300": -0.0077},
    )
    assert value == -0.0077
    assert unit == "pct"


def test_resolve_trigger_macro_field_returns_raw_unit() -> None:
    """`macro.*` fields map via MACRO_FIELD_TO_KEY to macro_snapshot keys
    with unit 'raw' (caller formats as plain scalar)."""
    trig = {"data_field": "macro.real_yield_10y_tips"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={"real_yield_10y_tips": 2.18},
        weekly_return_by_id={},
    )
    assert value == 2.18
    assert unit == "raw"


def test_resolve_trigger_unknown_field_returns_none_raw() -> None:
    """Unknown data_field → (None, 'raw'). Renderer then falls back to
    a 'missing' marker."""
    trig = {"data_field": "macro.unknown_series"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={},
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"


def test_resolve_trigger_missing_macro_key_returns_none_raw() -> None:
    """A known field whose key is absent from macro_snapshot → (None, 'raw')."""
    trig = {"data_field": "macro.vix"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={},  # vix missing
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"


def test_resolve_trigger_empty_data_field_returns_none_raw() -> None:
    """Defensive: missing data_field key in the trigger dict → (None, 'raw')."""
    value, unit = resolve_trigger_current_value(
        {},
        instrument_id="510300",
        macro_snapshot={},
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"
