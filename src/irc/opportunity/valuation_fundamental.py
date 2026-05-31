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
