"""Pure key-ratios surface. No I/O, no LLM.

`compute_ratios(financials: FilingDigest) -> KeyRatios` returns a small frozen
record `{roe, debt_equity, gross_margin, fcf_yield}`, all RATIO units
(0.18 = 18%, matching gross_margin / consensus_upside_pct / qdii_premium_pct),
all `float | None`. `roe` and `gross_margin` are pass-throughs of the already-
fetched `FilingDigest` fields (NaN screened to None). `debt_equity` and
`fcf_yield` are ALWAYS None today — their balance-sheet / cash-flow / market-cap
input line items are not yet fetched — and self-activate with zero further wiring
when a richer source lands (wire-but-degrade-to-None, the same contract ADR 0009
records for consensus_upside_pct). Reason-only: never drives a state, gate, or
classifier; carries no citation (see CONTEXT.md `KeyRatios` / `compute_ratios`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from irc.fundamentals.types import FilingDigest


@dataclass(frozen=True)
class KeyRatios:
    roe: float | None = None
    debt_equity: float | None = None
    gross_margin: float | None = None
    fcf_yield: float | None = None


def _finite(value: float | None) -> float | None:
    """Pass-through a finite float; screen None / NaN to None (no fabrication)."""
    if value is None or math.isnan(value):
        return None
    return value


def compute_ratios(financials: FilingDigest) -> KeyRatios:
    """Pure, deterministic. Same FilingDigest in → equal KeyRatios out.

    roe / gross_margin pass through (NaN → None). debt_equity / fcf_yield have no
    input line items on FilingDigest today → None (degrade-to-None, ADR 0009).
    """
    return KeyRatios(
        roe=_finite(financials.roe),
        debt_equity=None,
        gross_margin=_finite(financials.gross_margin),
        fcf_yield=None,
    )
