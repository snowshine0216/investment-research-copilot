"""Item 006 Slice H2.v2 — Policy B weight-aware quorum evaluator.

Five-rule precedence (1 → 2 → 3 → 4 → 5), locked by ADR 0003 §1. Each rule
short-circuits when it fires. Applies ONLY to `ActiveFundSnapshot` — passive
`FundLevelSnapshot` and legacy `ConstituentSnapshot` never feed this module.

See `docs/adr/0003-failure-mode-policy-b.md` for the full rationale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def MATERIAL_HOLDING_QUORUM(top_n: int) -> int:
    """Compute the material-holding quorum for a top-N constituent set.

    Returns `math.ceil(top_n / 2)`. The material top-half is the prefix of the
    weight-sorted constituent list that holds at least this many positions.
    Ties at the cutoff weight EXTEND the material set rather than truncate it
    (see `_material_set_with_ties`).
    """
    if top_n <= 0:
        return 0
    return math.ceil(top_n / 2)


@dataclass(frozen=True)
class ConstituentCoverageEntry:
    """Per-constituent coverage row inside a `RejectionRecord`.

    Ordered by `weight_rank` ascending (rank 1 = highest weight).
    `in_material_top_half` flags whether this constituent is required to
    carry an info leg under Policy B's rule 4.
    """
    symbol: str
    name_cn: str
    weight_pct: float
    weight_rank: int
    in_material_top_half: bool
    exchange: str
    has_data_leg: bool
    has_info_leg: bool
    data_kind_count: int
    information_kind_count: int
    failure_reasons: tuple[str, ...]
    audit_errors: tuple[str, ...]


from irc.fundamentals.types import ConstituentAnalysis


_EXCHANGE_FROM_SYMBOL_PREFIX = {
    "6": "SH",
    "0": "SZ",
    "3": "SZ",
    "4": "BJ",
    "8": "BJ",
}


def _infer_exchange(symbol: str) -> str:
    """Map a constituent symbol to an exchange code.

    Best-effort; mirrors `_parse_exchange_from_ticker` in
    `akshare_fundamentals.py` but takes only the symbol (no DataFrame row).
    Returns "UNKNOWN" when the shape is unrecognised.
    """
    if not symbol:
        return "UNKNOWN"
    code = symbol.strip().upper()
    if code.endswith(".HK"):
        return "HK"
    bare = code.split(".")[0]
    if bare.isdigit():
        if len(bare) in (4, 5):
            return "HK"
        if len(bare) == 6:
            return _EXCHANGE_FROM_SYMBOL_PREFIX.get(bare[0], "UNKNOWN")
    if bare.isalpha():
        return "US"
    return "UNKNOWN"


def _rank_by_weight(
    analyses: tuple[ConstituentAnalysis, ...],
) -> tuple[ConstituentAnalysis, ...]:
    """Sort ConstituentAnalyses by weight_pct DESC, ties broken by symbol ASC.

    Determinism: a second call on the same input returns the same ordering.
    """
    return tuple(sorted(analyses, key=lambda c: (-c.weight_pct, c.symbol)))


def _material_set_with_ties(
    ranked: tuple[ConstituentAnalysis, ...],
    *,
    top_n: int,
) -> tuple[ConstituentAnalysis, ...]:
    """Return the material top-half EXTENDED to include cutoff-weight ties.

    Cutoff = `MATERIAL_HOLDING_QUORUM(top_n)` index (1-based) → 0-based slice
    [:cutoff]. Then extend forward to include any subsequent constituent whose
    weight equals the cutoff weight (the boundary tie rule from §H2.v2).
    """
    if top_n <= 0 or not ranked:
        return ()
    cutoff = MATERIAL_HOLDING_QUORUM(top_n)
    initial = ranked[:cutoff]
    if not initial:
        return ()
    cutoff_weight = initial[-1].weight_pct
    extension = tuple(
        c for c in ranked[cutoff:] if c.weight_pct == cutoff_weight
    )
    return initial + extension


def _build_coverage_entries(
    ranked: tuple[ConstituentAnalysis, ...],
    top_n: int,
    *,
    audit_overrides: dict[str, tuple[str, ...]] | None = None,
) -> tuple[ConstituentCoverageEntry, ...]:
    """Build the per-constituent coverage tuple for a RejectionRecord.

    Entries ordered by `weight_rank` ascending (rank 1 = highest weight).
    `in_material_top_half` set per `_material_set_with_ties`.
    `audit_overrides` injects per-symbol audit_errors (used by rule 2).
    """
    overrides = audit_overrides or {}
    material = _material_set_with_ties(ranked, top_n=top_n)
    material_symbols = {c.symbol for c in material}
    out: list[ConstituentCoverageEntry] = []
    for idx, c in enumerate(ranked, start=1):
        data_kinds = [e for e in c.evidence if e.citation_kind == "data"]
        info_kinds = [e for e in c.evidence if e.citation_kind == "information"]
        out.append(ConstituentCoverageEntry(
            symbol=c.symbol,
            name_cn=c.name_cn,
            weight_pct=c.weight_pct,
            weight_rank=idx,
            in_material_top_half=c.symbol in material_symbols,
            exchange=_infer_exchange(c.symbol),
            has_data_leg=bool(data_kinds),
            has_info_leg=bool(info_kinds),
            data_kind_count=len(data_kinds),
            information_kind_count=len(info_kinds),
            failure_reasons=c.failure_reasons,
            audit_errors=overrides.get(c.symbol, c.audit_errors),
        ))
    return tuple(out)


def _material_symbols(
    ranked: tuple[ConstituentAnalysis, ...],
    top_n: int,
) -> tuple[str, ...]:
    """Symbol list of the material top-half (weight-rank ascending)."""
    return tuple(c.symbol for c in _material_set_with_ties(ranked, top_n=top_n))


@dataclass(frozen=True)
class PolicyBVerdict:
    """Result of `evaluate_policy_b`. `gap_codes==()` iff publishable.

    `audit_errors` carries `f"missing_constituent_record:{symbol}"` entries
    when rule 2 fires (item 003 adapter contract violation).
    `decision_rule` is a template-format-locked string for stable diff output
    (criterion 11). `material_symbols` is the symbol list of the material
    top-half (weight-rank ascending).
    """
    gap_codes: tuple[str, ...]
    audit_errors: tuple[str, ...]
    decision_rule: str
    material_symbols: tuple[str, ...]
    constituent_coverage: tuple[ConstituentCoverageEntry, ...]
