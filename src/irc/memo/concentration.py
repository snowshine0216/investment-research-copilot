"""Holdings overlap / concentration analytic for memo §6 风险提示.

Pure module. Tier-1 import contract: imports from `irc.opportunity.types`
and `irc.fundamentals.types` only — no imports from `irc.memo.*` siblings,
no `irc.commands.*` imports. Mirrors `aliases.py` per CONTEXT.md
"Renderer tier-1 import contract".

Produces `ConcentrationPair` records summarising Top-N weighted-overlap
between every pair of active-fund picks. Memo-only — does NOT mutate
`OpportunityRow`, does NOT touch `evidence_gaps` / `advisory_gaps` /
`thesis_state`, does NOT emit `[ref:...]` markers.

See `docs/2026-05-27-instrument-pickability/items/002-spec.md` AC1–AC15
and CONTEXT.md entries for `IRC_CONCENTRATION_BEGIN/END`,
`weighted_overlap_pct`, `ConcentrationPair`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


# AC2 / spec Q2: Top-10 chosen because the 2026-05-27 CPO cluster extends
# through weight rank 6–8 in several active funds.
CONCENTRATION_TOP_N: Final[int] = 10

# AC3 / spec Q3+Q5: 30.0 percent units (0–100), matches ConstituentAnalysis
# .weight_pct unit per ADR 0002 §4. NOT a fraction. Boundary inclusive (>=)
# mirrors FOREIGN_HEAVY_THRESHOLD precedent.
CONCENTRATION_OVERLAP_PCT_THRESHOLD: Final[float] = 30.0

# AC9 / spec Q9: marker constants live at module-top in concentration.py
# (producing-module pattern, mirrors macro_pillar.py's MACRO_SECTION_MARKER_*).
CONCENTRATION_MARKER_BEGIN: Final[str] = "<!-- IRC_CONCENTRATION_BEGIN -->"
CONCENTRATION_MARKER_END: Final[str] = "<!-- IRC_CONCENTRATION_END -->"

from irc.fundamentals.types import ConstituentAnalysis  # noqa: E402


def _top_n_by_weight(
    analyses: tuple[ConstituentAnalysis, ...],
    n: int = CONCENTRATION_TOP_N,
) -> tuple[ConstituentAnalysis, ...]:
    """Top-N constituents by weight_pct DESC, symbol ASC on tie.

    The secondary `c.symbol` key pins AC1's deterministic topN slice — two
    AkShare DataFrames with equal-weight holdings reordered must produce
    identical topN slices and thus identical pair overlaps.

    When len(analyses) < n, the full list (after sort) is returned with
    no padding (AC1 cardinality clarification / grill Q4).
    """
    ranked = sorted(analyses, key=lambda c: (-c.weight_pct, c.symbol))
    return tuple(ranked[:n])


def weighted_overlap_pct(
    a: tuple[ConstituentAnalysis, ...],
    b: tuple[ConstituentAnalysis, ...],
) -> float:
    """Σ_{s ∈ topN(A) ∩ topN(B)} min(w_A[s], w_B[s]).

    AC1: result in **percent units** (0.0–100.0), NOT a fraction. Symmetric:
    weighted_overlap_pct(A, B) == weighted_overlap_pct(B, A). Empty input
    on either side returns 0.0 (defensive — `OpportunityRow` with no
    constituent_analyses cannot participate per AC6).
    """
    top_a = {c.symbol: c.weight_pct for c in _top_n_by_weight(a)}
    top_b = {c.symbol: c.weight_pct for c in _top_n_by_weight(b)}
    shared = top_a.keys() & top_b.keys()
    return sum(min(top_a[s], top_b[s]) for s in shared)


@dataclass(frozen=True)
class ConcentrationPair:
    """One pairwise Top-N weighted-overlap record between two active-fund picks.

    Class-level invariant `instrument_id_a < instrument_id_b` (strict,
    alphabetical) — the factory `make_concentration_pair` sorts the two
    IDs before assignment so the two argument-orderings of the same fund
    pair produce byte-identical records.

    `overlap_pct` is `round(weighted_overlap_pct, 1)` set ONCE at
    construction (never re-rounded downstream — pins determinism by
    construction per grill Q6). `shared_symbols` sorted ASC.
    """
    instrument_id_a: str
    instrument_id_b: str
    name_cn_a: str
    name_cn_b: str
    overlap_pct: float
    shared_symbols: tuple[str, ...]


def make_concentration_pair(
    *,
    iid_x: str, name_x: str,
    iid_y: str, name_y: str,
    overlap_pct_raw: float,
    shared_symbols: tuple[str, ...],
) -> ConcentrationPair:
    """Factory enforcing AC5 invariants: alphabetic ID ordering, rounded
    overlap_pct (1dp), symbol-ASC sorted shared_symbols.
    """
    if iid_x < iid_y:
        a_id, a_name, b_id, b_name = iid_x, name_x, iid_y, name_y
    else:
        a_id, a_name, b_id, b_name = iid_y, name_y, iid_x, name_x
    return ConcentrationPair(
        instrument_id_a=a_id,
        instrument_id_b=b_id,
        name_cn_a=a_name,
        name_cn_b=b_name,
        overlap_pct=round(overlap_pct_raw, 1),
        shared_symbols=tuple(sorted(shared_symbols)),
    )
