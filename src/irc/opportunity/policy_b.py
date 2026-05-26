"""Item 006 Slice H2.v2 — Policy B weight-aware quorum evaluator.

Six-rule precedence (1 → 2 → 2.5 → 3 → 4 → 5), locked by ADR 0003 §1+§7.
Each rule short-circuits when it fires. Applies ONLY to `ActiveFundSnapshot`
— passive `FundLevelSnapshot` and legacy `ConstituentSnapshot` never feed
this module. Rule 2.5 (item 001 amendment) accepts fund-level NAV+announcement
evidence in lieu of per-holding filings when foreign weight share ≥ 50 %.

See `docs/adr/0003-failure-mode-policy-b.md` for the full rationale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


# Item 001 (decision-confidence-followup): foreign-heavy threshold for Policy B rule 2.5.
# Hardcoded per ADR 0003 §7 — operators tuning thresholds at runtime would silently
# weaken the audit trail. Future promotion to env var follows IRC_CACHE_FRESHNESS_DAYS.
FOREIGN_HEAVY_THRESHOLD: Final[float] = 0.50
_FOREIGN_EXCHANGES: Final[frozenset[str]] = frozenset({"HK", "US"})


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


def _compute_foreign_listed_share(
    ranked: tuple[ConstituentAnalysis, ...],
) -> float:
    """Weight share of constituents listed on HK or US exchanges.

    Returns a fraction in [0.0, 1.0]. Returns 0.0 on empty input or when
    `sum(weight_pct)` is 0 (defensive guard; rule 1 should have caught this).
    Pure, deterministic. Foreign = `_infer_exchange(symbol) in {"HK", "US"}`.
    `UNKNOWN` and `BJ` are NOT counted as foreign (spec non-goal; conservative
    fail-safe per ADR 0003 §7).
    """
    if not ranked:
        return 0.0
    total = sum(c.weight_pct for c in ranked)
    if total <= 0:
        return 0.0
    foreign = sum(
        c.weight_pct for c in ranked
        if _infer_exchange(c.symbol) in _FOREIGN_EXCHANGES
    )
    return foreign / total


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


def evaluate_policy_b(
    snapshot: ActiveFundSnapshot,
    *,
    top_n: int,
) -> PolicyBVerdict:
    """Apply Policy B v2 — five-rule precedence (1 → 2 → 3 → 4 → 5).

    Pure function. Reads `snapshot.constituent_analyses` +
    `snapshot.fund_level_failure_reasons`. Does NOT touch
    `snapshot.failure_reasons_by_symbol` (item 003 owns that surface).
    Returns a `PolicyBVerdict` whose `gap_codes` is `()` iff publishable.

    See ADR 0003 §1 for the precedence rationale.
    """
    analyses = snapshot.constituent_analyses

    # Rule 1: fund-level holdings fetch failed.
    if not analyses and snapshot.fund_level_failure_reasons:
        return PolicyBVerdict(
            gap_codes=("holdings_fetch_failed",),
            audit_errors=(),
            decision_rule="holdings adapter empty/failed",
            material_symbols=(),
            constituent_coverage=(),
        )

    # Defensive guard (spec edge case): empty AND no failure reason.
    if not analyses and not snapshot.fund_level_failure_reasons:
        return PolicyBVerdict(
            gap_codes=("incomplete_constituent_record",),
            audit_errors=("empty_constituent_analyses_without_failure_reason",),
            decision_rule=f"empty constituent_analyses; 0 of {top_n} holdings",
            material_symbols=(),
            constituent_coverage=(),
        )

    ranked = _rank_by_weight(analyses)

    # Rule 2: missing constituent record (audit error).
    missing = tuple(c for c in ranked if not c.evidence and not c.failure_reasons)
    if missing:
        audit_errors = tuple(
            f"missing_constituent_record:{c.symbol}" for c in missing
        )
        audit_overrides = {
            c.symbol: (f"missing_constituent_record:{c.symbol}",) for c in missing
        }
        return PolicyBVerdict(
            gap_codes=("incomplete_constituent_record",),
            audit_errors=audit_errors,
            decision_rule=f"missing constituent records: {len(missing)} of {top_n}",
            material_symbols=_material_symbols(ranked, top_n),
            constituent_coverage=_build_coverage_entries(
                ranked, top_n, audit_overrides=audit_overrides,
            ),
        )

    # Rule 2.5: foreign-heavy short-circuit (item 001, ADR 0003 §7).
    # Active CN equity funds with ≥ 50 % top-N weight listed on HK or US
    # exchanges (e.g. 006809) cannot satisfy rule 3's per-holding data leg
    # because the CN filings pipeline doesn't reach HK/US tickers. Accept
    # fund-level NAV + announcement evidence as the dual-coverage substitute.
    foreign_share = _compute_foreign_listed_share(ranked)
    if foreign_share >= FOREIGN_HEAVY_THRESHOLD:
        fund_evidence = snapshot.fund_level_evidence
        has_data = any(e.citation_kind == "data" for e in fund_evidence)
        has_info = any(e.citation_kind == "information" for e in fund_evidence)
        share_pct = f"{foreign_share * 100:.0f}%"
        if has_data and has_info:
            return PolicyBVerdict(
                gap_codes=(),
                audit_errors=(),
                decision_rule=(
                    f"foreign-heavy (share={share_pct}); fund-level "
                    f"NAV+announcements accepted"
                ),
                material_symbols=_material_symbols(ranked, top_n),
                constituent_coverage=_build_coverage_entries(ranked, top_n),
            )
        missing_legs: list[str] = []
        if not has_data:
            missing_legs.append("data")
        if not has_info:
            missing_legs.append("information")
        return PolicyBVerdict(
            gap_codes=("foreign_heavy_fund_level_evidence_missing",),
            audit_errors=(),
            decision_rule=(
                f"foreign-heavy (share={share_pct}); fund-level evidence "
                f"missing legs: {missing_legs}"
            ),
            material_symbols=_material_symbols(ranked, top_n),
            constituent_coverage=_build_coverage_entries(ranked, top_n),
        )

    # Rule 3: per-holding data leg required for ALL ranked holdings.
    no_data_leg = tuple(
        c for c in ranked
        if not any(e.citation_kind == "data" for e in c.evidence)
    )
    if no_data_leg:
        symbols = sorted(c.symbol for c in no_data_leg)
        return PolicyBVerdict(
            gap_codes=("incomplete_constituent_data",),
            audit_errors=(),
            decision_rule=(
                f"data leg missing for {len(no_data_leg)} of {top_n} holdings: "
                f"{symbols}"
            ),
            material_symbols=_material_symbols(ranked, top_n),
            constituent_coverage=_build_coverage_entries(ranked, top_n),
        )

    # Rule 4: per-holding info leg required for the material top-half.
    material = _material_set_with_ties(ranked, top_n=top_n)
    info_satisfied = tuple(
        c for c in material
        if any(e.citation_kind == "information" for e in c.evidence)
    )
    if len(info_satisfied) < len(material):
        return PolicyBVerdict(
            gap_codes=("insufficient_info_coverage_top_half",),
            audit_errors=(),
            decision_rule=(
                f"info-leg quorum {len(material)} of {top_n}; "
                f"{len(info_satisfied)} of material top-half satisfied"
            ),
            material_symbols=tuple(c.symbol for c in material),
            constituent_coverage=_build_coverage_entries(ranked, top_n),
        )

    # Rule 5: mixed evidence + failure_reasons (some constituents have only
    # failure_reasons, no evidence at all). In V1 this rule is structurally
    # subordinate to rule 3 (which catches "any holding lacks data leg"); it
    # remains as the leftover diagnostic for future relaxations and for
    # defence-in-depth in item 009.
    only_failure = tuple(c for c in ranked if not c.evidence and c.failure_reasons)
    if only_failure:
        return PolicyBVerdict(
            gap_codes=("incomplete_constituent_coverage",),
            audit_errors=(),
            decision_rule=f"holdings with no evidence: {len(only_failure)} of {top_n}",
            material_symbols=tuple(c.symbol for c in material),
            constituent_coverage=_build_coverage_entries(ranked, top_n),
        )

    # Publishable.
    return PolicyBVerdict(
        gap_codes=(),
        audit_errors=(),
        decision_rule=(
            f"info-leg quorum {len(material)} of {top_n}; "
            f"{len(info_satisfied)} satisfied (publishable)"
        ),
        material_symbols=tuple(c.symbol for c in material),
        constituent_coverage=_build_coverage_entries(ranked, top_n),
    )
