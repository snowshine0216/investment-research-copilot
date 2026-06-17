"""Pure: match LLM impact keys back to snapshot holdings, robust to keying drift.

The monitor_impact LLM sometimes returns a holding key that is not byte-identical
to the snapshot symbol (e.g. "300750.SZ" vs "300750", a whitespace/case variant,
or the company name_cn). Exact-only matching silently dropped every impact, the
constituent factor went N/A, and active-equity funds flapped to
``insufficient_evidence`` run-to-run. See ADR 0017 + CONTEXT.md "Monitor set".
"""
from __future__ import annotations

import re

_EXCHANGE_SUFFIX = re.compile(r"\.(sz|sh|bj|ss)$")


def _norm(s: str) -> str:
    """Casefold + strip whitespace + drop a trailing exchange suffix."""
    return _EXCHANGE_SUFFIX.sub("", s.strip().casefold())


def _numeric_core(s: str) -> str | None:
    """Leading-zero-stripped form, but ONLY for all-digit strings (else None).

    Restricting to all-digit strings keeps the strip "safe": we never mangle a
    name or an alphanumeric ticker, and an all-zeros code collapses to "0".
    """
    return (s.lstrip("0") or "0") if s.isdigit() else None


def match_impact_to_holding(impact_key: str, holdings: tuple) -> str | None:
    """Return the holding.symbol that ``impact_key`` refers to, or None."""
    if not impact_key:
        return None
    key_norm = _norm(impact_key)
    for h in holdings:
        if impact_key == h.symbol or key_norm == _norm(h.symbol):
            return h.symbol
    key_core = _numeric_core(key_norm)
    if key_core is not None:
        for h in holdings:
            if _numeric_core(_norm(h.symbol)) == key_core:
                return h.symbol
    for h in holdings:  # fall back to the company name when the code didn't match
        if key_norm == _norm(h.name_cn):
            return h.symbol
    return None


def select_impacts_by_holding(
    impacts: tuple, holdings: tuple,
) -> tuple[dict, tuple[str, ...]]:
    """Pure: map each impact to at most one holding.symbol, keeping the
    highest-confidence impact per holding (never double-count). Returns
    ``(best_by_symbol, unmatched_keys)``."""
    best: dict = {}
    unmatched: list[str] = []
    for imp in impacts:
        symbol = match_impact_to_holding(imp.key, holdings)
        if symbol is None:
            unmatched.append(imp.key)
            continue
        current = best.get(symbol)
        if current is None or imp.confidence > current.confidence:
            best[symbol] = imp
    return best, tuple(unmatched)
