"""Pure fundamental valuation anchor over `consensus_upside_pct` (item 002).

`consensus_upside_pct` is the one honestly-obtainable, already-relative
fundamental valuation scalar (price vs analyst target, ratio units). It needs
no peer/history normalisation — unlike absolute pe/pb, which therefore stay
reason-only (spec Open Q3). The anchor AUGMENTS the percentile band, mirroring
the `earnings_yield`/`real_yield_10y` anchor; it never replaces it. `None` in
production today (ADR 0009) → no opinion.

Thresholds are module-level named constants so future tuning is a one-line
change (spec AC1 / Open Q2). +20% is a conventional material-upside-vs-consensus
bar; -10% is asymmetric/tighter so the DCA gate errs slow to call cheap.
"""
from __future__ import annotations

from typing import Literal

from irc.opportunity.types import OpportunityInput

CHEAP_UPSIDE_THRESHOLD: float = 0.20
RICH_UPSIDE_THRESHOLD: float = -0.10

ValuationFundamental = Literal["cheap", "rich", "neutral"]


def valuation_fundamental_signal(
    inp: OpportunityInput,
) -> ValuationFundamental | None:
    """Map `consensus_upside_pct` (ratio) to a fundamental valuation signal.

    cheap   — upside >= CHEAP_UPSIDE_THRESHOLD
    rich    — upside <= RICH_UPSIDE_THRESHOLD
    neutral — present but between the thresholds
    None    — `consensus_upside_pct` is None (production-today; no opinion)
    """
    upside = inp.consensus_upside_pct
    if upside is None:
        return None
    if upside >= CHEAP_UPSIDE_THRESHOLD:
        return "cheap"
    if upside <= RICH_UPSIDE_THRESHOLD:
        return "rich"
    return "neutral"


def _pe_pb_fragment(inp: OpportunityInput) -> str:
    """Optional 'PE x.x / PB x.x' fragment (reason-only; never state, Open Q3)."""
    parts: list[str] = []
    if inp.pe_ttm is not None:
        parts.append(f"PE {inp.pe_ttm}")
    if inp.pb is not None:
        parts.append(f"PB {inp.pb}")
    return f"（指数 {' / '.join(parts)}）" if parts else ""


def _fundamental_reason_phrase(
    signal: ValuationFundamental,
    inp: OpportunityInput,
) -> str:
    """Chinese caveat describing the consensus-upside read (+ optional pe/pb)."""
    upside_pct = f"{inp.consensus_upside_pct:.0%}"
    if signal == "cheap":
        head = f"券商一致目标价隐含上行空间 {upside_pct}，基本面偏便宜。"
    elif signal == "rich":
        head = f"券商一致目标价隐含 {upside_pct} 下行，基本面不便宜。"
    else:
        head = f"券商一致目标价隐含上行空间 {upside_pct}，基本面中性。"
    return head + _pe_pb_fragment(inp)
