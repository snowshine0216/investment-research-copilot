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
