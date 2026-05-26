"""QDII premium-to-NAV routing helper.

Pure-routing layer that sits between the effectful AkShare adapter
(`src/irc/data/akshare_client.py::fetch_qdii_premium_pct`) and the
scoring pipeline. Decides for each watchlist row whether to invoke
the fetcher, return a synthetic zero (off-exchange feeders that
transact at NAV by construction), or skip the field entirely
(non-QDII rows).

See CONTEXT.md "QDII premium-to-NAV" and ADR 0002 §5 F6.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Final


# Canonical home for the QDII asset-class set. Previously triplicated in
# decision/gates.py, memo/diagnostics.py, allocation/target_weights.py;
# now imported from here (AC21).
_QDII_ASSET_CLASSES: Final[frozenset[str]] = frozenset(
    {"us_etf", "hk_etf", "qdii_global"}
)


def qdii_premium_for_row(
    asset_class: str,
    market: str,
    fetcher: Callable[[str], float | None],
    symbol: str,
) -> float | None:
    """Pure routing helper for QDII premium-to-NAV.

    Returns:
      - ``None`` when ``asset_class`` is not a QDII class (non-QDII rows
        must not stamp the field).
      - ``0.0`` when the row is a QDII off-exchange feeder
        (open-ended LOF/FOF units transact at NAV by construction;
        the secondary-market premium concept does not apply).
      - ``fetcher(symbol)`` otherwise (QDII on-exchange ETFs).

    The fetcher is the only effectful boundary; this function is pure.
    """
    if asset_class not in _QDII_ASSET_CLASSES:
        return None
    if market == "cn_off_exchange":
        return 0.0
    return fetcher(symbol)
