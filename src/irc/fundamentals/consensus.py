"""Pure consensus-upside metric. No I/O.

`consensus_upside_pct = median(non-None target_price) / latest_close - 1`,
in RATIO units (e.g. 0.12 = +12%), matching the `qdii_premium_pct` convention.
Returns None when no broker report carries a target price, or when
`latest_close` is missing / non-positive. See ADR 0009: this metric is wired
end-to-end but degrades to None today because the only wired broker feed
(EastMoney) drops its 目标价 column upstream — do NOT fabricate a target.
"""
from __future__ import annotations

from statistics import median

from irc.fundamentals.types import BrokerReport


def consensus_upside_pct(
    reports: tuple[BrokerReport, ...],
    latest_close: float | None,
) -> float | None:
    """Return median target / latest_close − 1, or None when undecidable."""
    if latest_close is None or latest_close <= 0:
        return None
    targets = tuple(r.target_price for r in reports if r.target_price is not None)
    if not targets:
        return None
    return median(targets) / latest_close - 1.0
