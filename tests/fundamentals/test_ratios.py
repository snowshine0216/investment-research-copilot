from __future__ import annotations

import dataclasses
import inspect

import pytest

from irc.fundamentals.ratios import KeyRatios, compute_ratios
from irc.fundamentals.types import FilingDigest


def _digest(*, gross_margin=None, roe=None) -> FilingDigest:
    return FilingDigest(
        symbol="600519.SH",
        fiscal_period="2026Q1",
        filed_at_iso="2026-04-30",
        revenue_yoy=0.06,
        net_income_yoy=0.04,
        gross_margin=gross_margin,
        roe=roe,
    )


# ---------- AC1: KeyRatios shape + immutability ----------

def test_key_ratios_has_four_fields_all_default_none() -> None:
    kr = KeyRatios()
    assert kr.roe is None
    assert kr.debt_equity is None
    assert kr.gross_margin is None
    assert kr.fcf_yield is None


def test_key_ratios_is_frozen() -> None:
    kr = KeyRatios()
    with pytest.raises(dataclasses.FrozenInstanceError):
        kr.roe = 0.1  # type: ignore[misc]


# ---------- AC3: gross_margin pass-through ----------

def test_gross_margin_pass_through_finite() -> None:
    kr = compute_ratios(_digest(gross_margin=0.69))
    assert kr.gross_margin == pytest.approx(0.69)


def test_gross_margin_none_stays_none() -> None:
    assert compute_ratios(_digest(gross_margin=None)).gross_margin is None


def test_gross_margin_nan_screened_to_none() -> None:
    assert compute_ratios(_digest(gross_margin=float("nan"))).gross_margin is None


# ---------- AC4: roe pass-through ----------

def test_roe_pass_through_finite() -> None:
    assert compute_ratios(_digest(roe=0.18)).roe == pytest.approx(0.18)


def test_roe_none_stays_none() -> None:
    assert compute_ratios(_digest(roe=None)).roe is None


def test_roe_nan_screened_to_none() -> None:
    assert compute_ratios(_digest(roe=float("nan"))).roe is None


# ---------- AC5: debt_equity / fcf_yield always None today ----------

def test_debt_equity_and_fcf_yield_degrade_to_none_today() -> None:
    # FilingDigest carries no debt/equity/FCF/market-cap line items → always None.
    kr = compute_ratios(_digest(gross_margin=0.69, roe=0.18))
    assert kr.debt_equity is None
    assert kr.fcf_yield is None


# ---------- AC2: determinism ----------

def test_compute_ratios_is_deterministic() -> None:
    d = _digest(gross_margin=0.69, roe=0.18)
    assert compute_ratios(d) == compute_ratios(d)


# ---------- AC2: purity (no I/O imports in the module) ----------

def test_compute_ratios_source_imports_no_io() -> None:
    src = inspect.getsource(compute_ratios)
    for forbidden in ("akshare", "duckdb", "requests", "open(", "llm"):
        assert forbidden not in src
    import irc.fundamentals.ratios as mod
    mod_src = inspect.getsource(mod)
    for forbidden in ("import akshare", "import duckdb", "from irc.llm"):
        assert forbidden not in mod_src


from irc.fundamentals.ratios import ratios_reason_fragment  # noqa: E402


# ---------- AC7 / G4: compact reason fragment, non-None only ----------

def test_fragment_shows_roe_and_gross_margin_compact() -> None:
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    # Compact form fits the [:60] one_line_view cap; caveat present.
    assert frag == "（ROE 18%·毛利69%，口径未核实）"


def test_fragment_omits_none_subfields_never_renders_none() -> None:
    # debt_equity / fcf_yield are None today → omitted (never the string "None").
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    assert "None" not in frag
    assert "负债" not in frag and "FCF" not in frag


def test_fragment_roe_only() -> None:
    assert ratios_reason_fragment(KeyRatios(roe=0.18)) == "（ROE 18%，口径未核实）"


def test_fragment_gross_margin_only() -> None:
    assert ratios_reason_fragment(KeyRatios(gross_margin=0.69)) == "（毛利69%，口径未核实）"


def test_fragment_empty_when_all_none() -> None:
    assert ratios_reason_fragment(KeyRatios()) == ""


def test_fragment_carries_no_ref_marker() -> None:
    import re
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    assert re.search(r"\[ref:[0-9a-f]{16}\]", frag) is None


def test_compute_ratios_no_module_level_side_effects() -> None:
    # Importing the module must not perform I/O or call akshare/duckdb/llm.
    import importlib
    import irc.fundamentals.ratios as mod
    importlib.reload(mod)  # re-import: raises if import does any forbidden effect
    # 1000x repeated calls are byte-stable (determinism under repetition).
    d = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    results = {mod.compute_ratios(d) for _ in range(1000)}
    assert len(results) == 1  # single equal value → frozen dataclass hashes equal


def test_compute_ratios_does_not_mutate_input() -> None:
    import dataclasses
    d = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    snapshot = dataclasses.astuple(d)
    compute_ratios(d)
    assert dataclasses.astuple(d) == snapshot  # input untouched (immutability)


# ---------- FIX A: _finite screens inf (and -inf) as well as NaN ----------

def test_gross_margin_inf_screened_to_none() -> None:
    """_finite must block +inf (e.g. from cost/revenue overflow) → None."""
    assert compute_ratios(_digest(gross_margin=float("inf"))).gross_margin is None


def test_gross_margin_neg_inf_screened_to_none() -> None:
    """_finite must block -inf → None."""
    assert compute_ratios(_digest(gross_margin=float("-inf"))).gross_margin is None


def test_roe_inf_screened_to_none() -> None:
    """_finite must block +inf roe → None."""
    assert compute_ratios(_digest(roe=float("inf"))).roe is None


def test_roe_neg_inf_screened_to_none() -> None:
    """_finite must block -inf roe → None."""
    assert compute_ratios(_digest(roe=float("-inf"))).roe is None


def test_fragment_omits_inf_gross_margin() -> None:
    """inf gross_margin input → compute_ratios screens to None → fragment omits 毛利."""
    # Pass through compute_ratios so _finite runs; KeyRatios.gross_margin becomes None.
    frag = ratios_reason_fragment(compute_ratios(_digest(roe=0.18, gross_margin=float("inf"))))
    assert "毛利" not in frag
    assert "ROE 18%" in frag


def test_fragment_omits_neg_inf_roe() -> None:
    """-inf roe input → compute_ratios screens to None → fragment omits ROE."""
    frag = ratios_reason_fragment(compute_ratios(_digest(roe=float("-inf"), gross_margin=0.69)))
    assert "ROE" not in frag
    assert "毛利69%" in frag


# ---------- FIX B: implausible roe (unit-error guard) degraded to None ----------

def test_roe_within_range_passes_through() -> None:
    """roe=0.18 is within ±1.5 → passed through unchanged."""
    assert compute_ratios(_digest(roe=0.18)).roe == pytest.approx(0.18)


def test_roe_positive_implausible_degraded_to_none() -> None:
    """roe=1.85 (likely percent-scale, i.e. 185%) → degraded to None."""
    assert compute_ratios(_digest(roe=1.85)).roe is None


def test_roe_negative_implausible_degraded_to_none() -> None:
    """roe=-1.6 is outside ±1.5 → degraded to None."""
    assert compute_ratios(_digest(roe=-1.6)).roe is None


def test_roe_boundary_1_5_passes_through() -> None:
    """roe=1.5 is exactly at the boundary → passes through (abs ≤ 1.5)."""
    assert compute_ratios(_digest(roe=1.5)).roe == pytest.approx(1.5)


def test_roe_boundary_neg_1_5_passes_through() -> None:
    """roe=-1.5 is exactly at the boundary → passes through."""
    assert compute_ratios(_digest(roe=-1.5)).roe == pytest.approx(-1.5)
