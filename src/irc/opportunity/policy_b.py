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
