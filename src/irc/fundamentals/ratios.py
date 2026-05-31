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


def ratios_reason_fragment(ratios: KeyRatios) -> str:
    """Optional compact Chinese ratios fragment (reason-only, mirrors
    valuation_fundamental._pe_pb_fragment). Emits ONLY non-None sub-fields;
    returns "" when all four are None. Percent display, ratio→% for readability.
    Carries the 口径未核实 caveat (filing-evidence-semantics, ADR 0001 §5);
    structurally separate from the locked 财报已披露（口径未核实）summary phrase.
    Never injects a [ref:...] marker. Best-effort within the one_line_view [:60]
    cap (debt_equity / fcf_yield are None today, so today's surface is ≤ ~22 chars).
    """
    parts: list[str] = []
    if ratios.roe is not None:
        parts.append(f"ROE {ratios.roe:.0%}")
    if ratios.gross_margin is not None:
        parts.append(f"毛利{ratios.gross_margin:.0%}")
    # debt_equity / fcf_yield are None today → never appended (omitted, not "None").
    if ratios.debt_equity is not None:
        parts.append(f"负债权益{ratios.debt_equity:.2f}")
    if ratios.fcf_yield is not None:
        parts.append(f"FCF {ratios.fcf_yield:.0%}")
    if not parts:
        return ""
    return f"（{'·'.join(parts)}，口径未核实）"
