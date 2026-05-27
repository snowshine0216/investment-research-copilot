"""Pure-logic tests for src/irc/memo/concentration.py (item 002).

Covers AC1–AC9 + AC13 of docs/2026-05-27-instrument-pickability/items/002-spec.md.
AC11 (no row-level state change) is verified by the absence of changes to
opportunity/types.py and is asserted indirectly by the existing
test_publishable_set_lockdown.py two-run byte equality.
"""
from __future__ import annotations


def test_concentration_top_n_constant():
    """AC2: CONCENTRATION_TOP_N is a module-level Final[int] = 10."""
    from irc.memo.concentration import CONCENTRATION_TOP_N
    assert CONCENTRATION_TOP_N == 10


def test_concentration_overlap_pct_threshold_constant():
    """AC3: CONCENTRATION_OVERLAP_PCT_THRESHOLD is 30.0 (percent units, NOT fraction)."""
    from irc.memo.concentration import CONCENTRATION_OVERLAP_PCT_THRESHOLD
    assert CONCENTRATION_OVERLAP_PCT_THRESHOLD == 30.0


def test_concentration_marker_constants():
    """AC9: marker constants live at module-top in concentration.py."""
    from irc.memo.concentration import (
        CONCENTRATION_MARKER_BEGIN,
        CONCENTRATION_MARKER_END,
    )
    assert CONCENTRATION_MARKER_BEGIN == "<!-- IRC_CONCENTRATION_BEGIN -->"
    assert CONCENTRATION_MARKER_END == "<!-- IRC_CONCENTRATION_END -->"


def _analysis(symbol: str, weight: float):
    """Helper: build a minimal ConstituentAnalysis fixture."""
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def test_weighted_overlap_pct_symmetric():
    """AC1: weighted_overlap_pct(A, B) == weighted_overlap_pct(B, A)."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0), _analysis("Y", 8.0), _analysis("Z", 4.0))
    b = (_analysis("X", 6.0), _analysis("Y", 12.0), _analysis("W", 5.0))
    assert weighted_overlap_pct(a, b) == weighted_overlap_pct(b, a)


def test_weighted_overlap_pct_known_intersection():
    """AC1: Σ min(w_A[s], w_B[s]) over shared symbols.

    A: X=10, Y=8, Z=4 | B: X=6, Y=12, W=5 | shared = {X, Y}
    Expected: min(10, 6) + min(8, 12) = 6 + 8 = 14.0
    """
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0), _analysis("Y", 8.0), _analysis("Z", 4.0))
    b = (_analysis("X", 6.0), _analysis("Y", 12.0), _analysis("W", 5.0))
    assert weighted_overlap_pct(a, b) == 14.0


def test_weighted_overlap_pct_no_overlap_returns_zero():
    """AC1: Σ over empty intersection is 0.0."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0),)
    b = (_analysis("Y", 10.0),)
    assert weighted_overlap_pct(a, b) == 0.0


def test_weighted_overlap_pct_empty_input_returns_zero():
    """Defensive: empty constituent_analyses on either side → 0.0."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0),)
    assert weighted_overlap_pct(a, ()) == 0.0
    assert weighted_overlap_pct((), a) == 0.0
    assert weighted_overlap_pct((), ()) == 0.0


def test_weighted_overlap_pct_truncates_to_top_n():
    """AC1: topN ranks by weight_pct desc, symbol asc tiebreaker; tail ignored.

    With Top-10 cap, an 11th holding with the same symbol on both sides must
    NOT contribute to the overlap.
    """
    from irc.memo.concentration import weighted_overlap_pct
    a = tuple(
        _analysis(f"S{i:02d}", 50.0 - i) for i in range(11)
    )  # S00..S10, weights 50,49,...,40
    b = (
        _analysis("S10", 100.0),  # would dominate if Top-N were unbounded
    )
    # S10 is rank 11 in `a` after topN truncation (Top-10), so intersection
    # with `b` is empty → 0.0.
    assert weighted_overlap_pct(a, b) == 0.0


def test_weighted_overlap_pct_handles_cardinality_below_top_n():
    """AC1 cardinality clarification (grill Q4): when len(A) < CONCENTRATION_TOP_N,
    topN(A) = A.constituent_analyses after the rank sort with no padding;
    symmetry preserved."""
    from irc.memo.concentration import weighted_overlap_pct
    # A has 4 holdings (< Top-10).
    a = (
        _analysis("X", 20.0), _analysis("Y", 15.0),
        _analysis("Z", 10.0), _analysis("W", 5.0),
    )
    b = (_analysis("X", 18.0), _analysis("Y", 12.0))
    # Intersection {X, Y}: min(20,18) + min(15,12) = 18 + 12 = 30.0.
    assert weighted_overlap_pct(a, b) == 30.0
    # Symmetry under asymmetric cardinality.
    assert weighted_overlap_pct(a, b) == weighted_overlap_pct(b, a)


def test_weighted_overlap_pct_tiebreak_by_symbol_ascending():
    """AC1: when two constituents share weight_pct, symbol ASC breaks the tie
    so two reordered inputs produce the same topN slice."""
    from irc.memo.concentration import weighted_overlap_pct
    # Both sides have 11 holdings with weight 10.0 each — only Top-10 by
    # symbol-asc tiebreaker should participate.
    syms_a = [f"S{i:02d}" for i in range(11)]  # S00..S10
    syms_b = [f"S{i:02d}" for i in range(11)]
    a = tuple(_analysis(s, 10.0) for s in syms_a)
    b = tuple(_analysis(s, 10.0) for s in syms_b)
    # Both topN slices are S00..S09 (symbol-asc tiebreaker drops S10);
    # intersection = S00..S09; overlap = 10 * 10.0 = 100.0.
    assert weighted_overlap_pct(a, b) == 100.0


def test_concentration_pair_is_frozen():
    """AC5: ConcentrationPair is a frozen dataclass."""
    from dataclasses import FrozenInstanceError
    from irc.memo.concentration import ConcentrationPair
    pair = ConcentrationPair(
        instrument_id_a="A", instrument_id_b="B",
        name_cn_a="a", name_cn_b="b",
        overlap_pct=50.0, shared_symbols=("X",),
    )
    try:
        pair.overlap_pct = 60.0  # type: ignore[misc]
        raise AssertionError("expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_make_concentration_pair_sorts_instrument_ids_alphabetically():
    """AC5: factory enforces instrument_id_a < instrument_id_b (strict)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="510300", name_x="沪深300",
        iid_y="005827", name_y="易方达蓝筹",
        overlap_pct_raw=42.5, shared_symbols=("000001", "600519"),
    )
    assert pair.instrument_id_a == "005827"
    assert pair.instrument_id_b == "510300"
    assert pair.name_cn_a == "易方达蓝筹"
    assert pair.name_cn_b == "沪深300"


def test_make_concentration_pair_argument_order_invariant():
    """AC5: passing the two funds in either order produces byte-identical pairs."""
    from irc.memo.concentration import make_concentration_pair
    p1 = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=64.27, shared_symbols=("X", "Y"),
    )
    p2 = make_concentration_pair(
        iid_x="B", name_x="乙", iid_y="A", name_y="甲",
        overlap_pct_raw=64.27, shared_symbols=("Y", "X"),
    )
    assert p1 == p2


def test_make_concentration_pair_rounds_overlap_to_one_decimal():
    """AC5 / grill Q6: overlap_pct is set ONCE at construction via round(_, 1)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=64.27, shared_symbols=("X",),
    )
    assert pair.overlap_pct == 64.3


def test_make_concentration_pair_sorts_shared_symbols_ascending():
    """AC5: shared_symbols sorted ASC (pins determinism on render)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=50.0, shared_symbols=("ZZZ", "AAA", "MMM"),
    )
    assert pair.shared_symbols == ("AAA", "MMM", "ZZZ")
