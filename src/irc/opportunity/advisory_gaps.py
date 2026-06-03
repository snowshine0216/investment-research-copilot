"""Advisory gap emission for `OpportunityRow.advisory_gaps`.

See ADR 0005 and CONTEXT.md "Failure-mode + audit policy" for the
`advisory_gaps` semantic. First (and currently only) member:
`top_holdings_broker_thin` — fires when an `ActiveFundSnapshot`'s Top-5
holdings have weak broker coverage.

Pure module. No I/O. Imported by `thesis_evidence.py`'s active-fund branch
(via the existing `gaps` return slot) and re-exported by `states.py` for
the 3-way `_partition_gaps` split.
"""
from __future__ import annotations

from typing import Final

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD: Final[int] = 2
TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD: Final[float] = 20.0
_TOP_N: Final[int] = 5

ADVISORY_GAP_CODES: Final[frozenset[str]] = frozenset({
    "top_holdings_broker_thin",
    "valuation_price_fundamental_divergence",
})


def _has_broker_empty(analysis: ConstituentAnalysis) -> bool:
    """True when any failure_reason matches `broker_empty:*`."""
    return any(r.startswith("broker_empty:") for r in analysis.failure_reasons)


def _top_n_by_weight(
    snapshot: ActiveFundSnapshot, n: int = _TOP_N,
) -> tuple[ConstituentAnalysis, ...]:
    """Return the Top-N constituents by weight_pct descending, symbol ASC on tie.

    The secondary `c.symbol` key keeps AC12 (two-run byte equality) stable
    when AkShare returns equal-weight holdings in different orders.
    """
    ranked = sorted(
        snapshot.constituent_analyses,
        key=lambda c: (-c.weight_pct, c.symbol),
    )
    return tuple(ranked[:n])


def count_broker_empty_top5(snapshot: ActiveFundSnapshot) -> int:
    """Number of Top-5 holdings with `broker_empty:*` in failure_reasons."""
    return sum(1 for c in _top_n_by_weight(snapshot) if _has_broker_empty(c))


def weight_broker_empty_top5(snapshot: ActiveFundSnapshot) -> float:
    """Sum of weight_pct over Top-5 holdings with `broker_empty:*` (0–100)."""
    return sum(c.weight_pct for c in _top_n_by_weight(snapshot) if _has_broker_empty(c))


def should_emit_top_holdings_broker_thin(snapshot: ActiveFundSnapshot) -> bool:
    """Disjunctive OR — count >= 2 OR weight_pct sum >= 20.0. Boundary inclusive."""
    return (
        count_broker_empty_top5(snapshot) >= TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD
        or weight_broker_empty_top5(snapshot) >= TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD
    )
