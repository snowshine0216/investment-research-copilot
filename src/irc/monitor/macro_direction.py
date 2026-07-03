"""PURE theme->fund direction join + chip formatting for the 宏观面速览
direction chips (report v4 item 002, P3). No I/O, no clock, no LLM.

Direction is DETERMINISTIC from already-validated macro impacts — the LLM
explains, never scores (source spec P5/P9). The ±0.15 color bands are
display-only and unrelated to signal bands. A fund with NO record for a
theme is absent from the join: absence ≠ zero (CONTEXT.md "Mechanism clause
(传导线) / macro direction chips")."""
from __future__ import annotations
from irc.monitor.impact_validate import ValidatedImpact

_POS_BAND = 0.15
_NEG_BAND = -0.15


def join_macro_impacts(
    macro_impacts_by_fund: dict[str, tuple[ValidatedImpact, ...]],
) -> dict[str, dict[str, ValidatedImpact]]:
    """theme -> fund_id -> record, joined on EXACT string equality
    ValidatedImpact.key == theme (the key is unvalidated LLM echo,
    impact_validate.py:37 — best-effort). Duplicate keys for the same fund
    resolve FIRST-wins: input tuples preserve LLM emission order (RD-1)."""
    out: dict[str, dict[str, ValidatedImpact]] = {}
    for fund_id, impacts in macro_impacts_by_fund.items():
        for imp in impacts:
            theme_map = out.setdefault(imp.key, {})
            if fund_id not in theme_map:
                theme_map[fund_id] = imp
    return out


def direction_class(impact: float) -> str:
    """"chip-pos" iff impact >= +0.15, "chip-neg" iff impact <= -0.15,
    else "chip-flat". Display-only bands (spec AC1)."""
    if impact >= _POS_BAND:
        return "chip-pos"
    if impact <= _NEG_BAND:
        return "chip-neg"
    return "chip-flat"


def format_signed(value: float) -> str:
    """Trimmed 2dp signed: +0.80->'+0.8', +0.85->'+0.85', +1.00->'+1',
    0.0->'+0'. value == 0.0 (True for -0.0) short-circuits to '+0' (RD-8);
    the post-trim '-0' guard extends that to values rounding to zero."""
    if value == 0.0:
        return "+0"
    text = f"{value:+.2f}".rstrip("0").rstrip(".")
    return "+0" if text == "-0" else text
