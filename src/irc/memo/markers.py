"""Item 007 D1a — marker grammar.

Single source of truth for the `[ref:{citation_id}]` and `[stock:{symbol}]`
markers emitted by `evidence_pool.py` and `report.py`. Locked by
[ADR 0004 / Q1](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
from __future__ import annotations


REF_MARKER_FMT = "[ref:{citation_id}]"
STOCK_MARKER_FMT = "[stock:{symbol}]"


def format_ref_marker(citation_id: str) -> str:
    """Render `[ref:{citation_id}]`. Raises on empty `citation_id`.

    Item 002 invariant: `citation_id` is always 16 hex chars (computed in
    `ThesisEvidence.__post_init__`). Empty here means a programming error.
    """
    if not citation_id:
        raise ValueError("citation_id must be non-empty")
    return REF_MARKER_FMT.format(citation_id=citation_id)


def format_stock_marker(symbol: str) -> str:
    """Render `[stock:{symbol}]`. Raises on empty `symbol`.

    The symbol passes through verbatim — no transformation (CN 6-digit,
    HK 5-digit, US tickers all carry their native shape).
    """
    if not symbol:
        raise ValueError("symbol must be non-empty")
    return STOCK_MARKER_FMT.format(symbol=symbol)


def format_combined_marker(citation_id: str, symbol: str | None) -> str:
    """Combine `[stock:...] [ref:...]` with single-space separation per Q1.

    Stock marker is OMITTED (not replaced with an empty placeholder) when
    `symbol` is None or empty. The result is always parseable by:
        `^(?:\\[stock:[^\\]]+\\] )?\\[ref:[0-9a-f]{16}\\]`
    """
    ref = format_ref_marker(citation_id)
    if not symbol:
        return ref
    return f"{format_stock_marker(symbol)} {ref}"
