"""Item 002 — pure fundamental valuation anchor over `consensus_upside_pct`.

Spec: docs/2026-05-31-funding-analysis/items/002-spec.md (AC1).
ADR 0009: the input is `None` in production today → signal `None` (no opinion).
"""
from __future__ import annotations

from irc.opportunity.types import OpportunityInput
from irc.opportunity.valuation_fundamental import (
    CHEAP_UPSIDE_THRESHOLD,
    RICH_UPSIDE_THRESHOLD,
    valuation_fundamental_signal,
)


def _equity(**kwargs) -> OpportunityInput:
    base = dict(instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange")
    base.update(kwargs)
    return OpportunityInput(**base)


def test_thresholds_are_ratio_constants() -> None:
    assert CHEAP_UPSIDE_THRESHOLD == 0.20
    assert RICH_UPSIDE_THRESHOLD == -0.10


def test_signal_cheap_at_and_above_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.20)) == "cheap"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.25)) == "cheap"


def test_signal_rich_at_and_below_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.10)) == "rich"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.30)) == "rich"


def test_signal_neutral_between_thresholds() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.05)) == "neutral"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.05)) == "neutral"


def test_signal_none_when_input_none() -> None:
    """Production-today case (ADR 0009): no target price → no opinion."""
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=None)) is None
    assert valuation_fundamental_signal(_equity()) is None
