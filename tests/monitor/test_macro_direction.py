from __future__ import annotations
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.macro_direction import direction_class, format_signed, join_macro_impacts


def _imp(key, impact=0.5, confidence=0.7, cids=()):
    return ValidatedImpact(key, impact, confidence, tuple(cids))


# ---- join_macro_impacts ----


def test_join_empty_input_returns_empty():
    assert join_macro_impacts({}) == {}


def test_join_groups_by_exact_theme_key_then_fund():
    a, b = _imp("us_monetary", 0.8), _imp("gold_drivers", -0.4)
    joined = join_macro_impacts({"270023": (a,), "008986": (b,)})
    assert joined == {"us_monetary": {"270023": a}, "gold_drivers": {"008986": b}}


def test_join_is_exact_string_no_normalisation():
    joined = join_macro_impacts({"270023": (_imp("US_Monetary", 0.8),)})
    assert "us_monetary" not in joined and "US_Monetary" in joined


def test_join_duplicate_keys_same_fund_first_wins():
    """RD-1: input tuples preserve LLM emission order — first-wins is the same
    record a trace reader sees first."""
    first, second = _imp("us_monetary", 0.8), _imp("us_monetary", -0.9)
    joined = join_macro_impacts({"270023": (first, second)})
    assert joined["us_monetary"]["270023"] is first


def test_join_fund_without_record_absent_from_theme_map():
    """Absence ≠ zero: the downstream chip must stay uncolored with no number."""
    joined = join_macro_impacts({"270023": (_imp("us_monetary"),), "009225": ()})
    assert "009225" not in joined["us_monetary"]


def test_join_off_config_key_kept_but_never_required():
    """An impact key matching no rendered theme is tolerated: it lands in the
    join output and is simply never looked up by the renderer (trace-only)."""
    joined = join_macro_impacts({"270023": (_imp("weird_llm_key"),)})
    assert "weird_llm_key" in joined


# ---- direction_class ----


def test_direction_class_bands():
    assert direction_class(0.15) == "chip-pos"    # boundary: exactly +0.15 is green
    assert direction_class(-0.15) == "chip-neg"   # boundary: exactly -0.15 is red
    assert direction_class(0.1499) == "chip-flat"
    assert direction_class(-0.1499) == "chip-flat"
    assert direction_class(0.0) == "chip-flat"
    assert direction_class(1.0) == "chip-pos"
    assert direction_class(-1.0) == "chip-neg"


# ---- format_signed ----


def test_format_signed_trim_rules():
    assert format_signed(0.8) == "+0.8"
    assert format_signed(0.85) == "+0.85"
    assert format_signed(1.0) == "+1"
    assert format_signed(-0.15) == "-0.15"
    assert format_signed(0.0) == "+0"


def test_format_signed_negative_zero_normalises():
    assert format_signed(-0.0) == "+0"      # RD-8: never a nonsense "-0" chip


def test_format_signed_tiny_negative_never_renders_minus_zero():
    # -0.001 formats to "-0.00" -> trims to "-0"; the post-trim normalisation
    # extends RD-8 to every value that ROUNDS to zero at 2dp.
    assert format_signed(-0.001) == "+0"
