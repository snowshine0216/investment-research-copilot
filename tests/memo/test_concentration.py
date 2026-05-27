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


def _op_row(iid: str, name: str, analyses: tuple = ()):
    """Helper: minimal OpportunityRow with constituent_analyses."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid, display_cn=name, provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
        constituent_analyses=analyses,
    )


def test_compute_concentration_pairs_returns_empty_below_threshold():
    """AC4: when no pair crosses the 30.0% threshold, result is empty tuple."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (
            _analysis("X", 10.0), _analysis("Y", 5.0),
        )),
        _op_row("B", "乙", (
            _analysis("Z", 10.0), _analysis("W", 5.0),
        )),
    )
    assert compute_concentration_pairs(rows) == ()


def test_compute_concentration_pairs_emits_one_pair_above_threshold():
    """AC4: a single qualifying pair is surfaced exactly once."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (
            _analysis("X", 20.0), _analysis("Y", 15.0),
        )),
        _op_row("B", "乙", (
            _analysis("X", 18.0), _analysis("Y", 12.0),
        )),
    )
    # Overlap = min(20,18) + min(15,12) = 18 + 12 = 30.0 → boundary inclusive.
    pairs = compute_concentration_pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].instrument_id_a == "A"
    assert pairs[0].instrument_id_b == "B"
    assert pairs[0].overlap_pct == 30.0
    assert pairs[0].shared_symbols == ("X", "Y")


def test_compute_concentration_pairs_threshold_strict_below_excluded():
    """AC3: pairs strictly below 30.0% are NOT surfaced."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 9.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 11.0))),
    )
    # Overlap = min(20,18) + min(9,11) = 18 + 9 = 27.0 → below threshold.
    assert compute_concentration_pairs(rows) == ()


def test_compute_concentration_pairs_skips_rows_with_empty_constituents():
    """AC6: rows with constituent_analyses=() are silently skipped.

    A passive ETF (FundLevelSnapshot path) has empty constituent_analyses
    and cannot participate in a holdings-level overlap.
    """
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", ()),  # passive — empty constituents
        _op_row("C", "丙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
    )
    pairs = compute_concentration_pairs(rows)
    # Only A↔C is eligible (B is skipped).
    assert len(pairs) == 1
    assert (pairs[0].instrument_id_a, pairs[0].instrument_id_b) == ("A", "C")


def test_compute_concentration_pairs_three_funds_three_qualifying_pairs():
    """AC4: a fully-overlapping 3-fund set produces C(3,2) = 3 pairs."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 14.0))),
        _op_row("C", "丙", (_analysis("X", 17.0), _analysis("Y", 13.0))),
    )
    pairs = compute_concentration_pairs(rows)
    assert len(pairs) == 3
    pair_ids = [(p.instrument_id_a, p.instrument_id_b) for p in pairs]
    # AC4: each unordered pair appears exactly once (never (A,B) AND (B,A)).
    assert pair_ids == sorted(set(pair_ids), key=lambda t: t)


def test_compute_concentration_pairs_render_order_overlap_desc_then_id_asc():
    """AC8: pairs in result sorted by (overlap_pct DESC, id_a ASC, id_b ASC).

    Build three distinct pairs with one high-overlap and two tied-overlap values
    to lock both the primary DESC sort and the alphabetical tiebreaker.

    Fixture design: A↔B share X+Y (overlap=60.0); B↔C share only X (overlap=35.0);
    C↔D share only X (overlap=35.0). A↔C, A↔D do not share enough to qualify
    (A has X=40,Y=20; C has X=35,Z=10 — only X shared → min(40,35)=35 >= 30 ✓,
    but we need them excluded). Use non-overlapping symbols for A↔C/A↔D by
    giving C and D a symbol A does not hold. Refined: A=(X=40,Y=20), B=(X=40,Y=20,Z=5),
    C=(X=35,P=10) where P not in A/B, D=(X=35,Q=10) where Q not in A/B.

    Simplest clean fixture: make A/B overlap at 60 on X+Y; make B/C and C/D overlap
    at 35 on a UNIQUE per-pair symbol so there are exactly 3 pairs:
      A=(X=40,Y=20), B=(X=18,Y=12,M=30) — A↔B: X+Y overlap = min(40,18)+min(20,12)=30; no
    Better: give each pair a dedicated shared symbol with enough weight.
      A=(S=45, T=20), B=(S=35, U=10) — A↔B=35.0; B=(S=35, U=10), C=(S=35, V=10) — B↔C=35.0;
      but then A↔C also overlaps at S=35 → still messy.

    Cleanest approach: use non-overlapping symbol sets so each intended pair is
    the ONLY pair that shares symbols. Give every pair a UNIQUE shared symbol:
      A holds (SHARED_AB=40), B holds (SHARED_AB=38, SHARED_BC=35),
      C holds (SHARED_BC=33, SHARED_CD=32), D holds (SHARED_CD=30).
    A↔B: min(40,38)=38.0 (only SHARED_AB in common).
    B↔C: min(35,33)=33.0 (only SHARED_BC in common).
    C↔D: min(32,30)=30.0 (only SHARED_CD in common; boundary inclusive).
    A↔C, A↔D, B↔D: no symbols in common → 0.0 → excluded.
    """
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("AB", 40.0),)),
        _op_row("B", "乙", (_analysis("AB", 38.0), _analysis("BC", 35.0))),
        _op_row("C", "丙", (_analysis("BC", 33.0), _analysis("CD", 32.0))),
        _op_row("D", "丁", (_analysis("CD", 30.0),)),
    )
    pairs = compute_concentration_pairs(rows)
    # Sorted: 38.0 DESC, then 33.0, then 30.0 — no ties; alphabetical tiebreaker
    # is the same ordering so the primary sort alone determines output.
    ids = [(p.overlap_pct, p.instrument_id_a, p.instrument_id_b) for p in pairs]
    assert ids == [(38.0, "A", "B"), (33.0, "B", "C"), (30.0, "C", "D")]


def test_compute_concentration_pairs_render_order_tiebreak_by_id():
    """AC8 tiebreaker: when overlap_pct ties, sort by id_a ASC then id_b ASC."""
    from irc.memo.concentration import compute_concentration_pairs
    # B↔C and A↔D both overlap at exactly 32.0 (using distinct shared symbols).
    rows = (
        _op_row("A", "甲", (_analysis("AD", 32.0),)),
        _op_row("B", "乙", (_analysis("BC", 32.0),)),
        _op_row("C", "丙", (_analysis("BC", 32.0),)),
        _op_row("D", "丁", (_analysis("AD", 32.0),)),
    )
    pairs = compute_concentration_pairs(rows)
    ids = [(p.overlap_pct, p.instrument_id_a, p.instrument_id_b) for p in pairs]
    # Both pairs tie at 32.0; A↔D comes before B↔C alphabetically by id_a.
    assert ids == [(32.0, "A", "D"), (32.0, "B", "C")]


def test_compute_concentration_pairs_two_argument_orderings_byte_equal():
    """AC5 + AC13: input rows in two orderings produce byte-identical pair tuples."""
    from irc.memo.concentration import compute_concentration_pairs
    a = _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0)))
    b = _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0)))
    assert compute_concentration_pairs((a, b)) == compute_concentration_pairs((b, a))


def _pick(iid: str, name: str):
    """Helper: minimal PickRow."""
    from irc.memo.picks_table import PickRow
    return PickRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
    )


def test_compose_concentration_lines_returns_empty_when_no_pair_qualifies():
    """AC9 empty case: no marker block emitted, no §6 lines at all."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("B", "乙")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 5.0),)),
        "B": _op_row("B", "乙", (_analysis("Y", 5.0),)),
    }
    assert _compose_concentration_lines(pick_rows, op_rows_by_id) == ()


def test_compose_concentration_lines_emits_marker_block_when_pair_qualifies():
    """AC9: marker-wrapped tuple with header + one bullet per pair."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("008382", "融通产业趋势股票"),
                 _pick("008555", "华商龙头优势混合")]
    op_rows_by_id = {
        "008382": _op_row("008382", "融通产业趋势股票", (
            _analysis("300502", 20.0), _analysis("300308", 15.0),
        )),
        "008555": _op_row("008555", "华商龙头优势混合", (
            _analysis("300502", 18.0), _analysis("300308", 14.0),
        )),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    assert lines
    joined = "\n".join(lines)
    assert "<!-- IRC_CONCENTRATION_BEGIN -->" in joined
    assert "<!-- IRC_CONCENTRATION_END -->" in joined
    assert "持仓集中度（Top-10 加权重合 ≥ 30%）" in joined
    assert "008382 融通产业趋势股票" in joined
    assert "008555 华商龙头优势混合" in joined
    assert "加权重合" in joined
    # Body bullet format per AC9.
    assert "↔" in joined
    assert "共同持仓" in joined


def test_compose_concentration_lines_skips_picks_missing_from_op_rows():
    """AC7: pick lookup tolerates missing op rows (e.g. venue proxy that
    doesn't appear in opportunity_report.json) — they cannot contribute."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("missing", "缺失")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 20.0),)),
    }
    assert _compose_concentration_lines(pick_rows, op_rows_by_id) == ()


def test_compose_concentration_lines_caps_shared_symbols_at_5_with_ellipsis():
    """AC9: sym_list capped at 5 symbols with `...` when more than 5 exist."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    # Six shared symbols, each weighted heavily on both sides.
    syms = ["A1", "A2", "A3", "A4", "A5", "A6"]
    analyses_a = tuple(_analysis(s, 6.0) for s in syms)
    analyses_b = tuple(_analysis(s, 6.0) for s in syms)
    pick_rows = [_pick("X", "甲"), _pick("Y", "乙")]
    op_rows_by_id = {
        "X": _op_row("X", "甲", analyses_a),
        "Y": _op_row("Y", "乙", analyses_b),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    joined = "\n".join(lines)
    # First 5 ASC: A1/A2/A3/A4/A5; A6 elided.
    assert "A1/A2/A3/A4/A5..." in joined
    assert "（6 只）" in joined


def test_compose_concentration_lines_renders_at_top_of_six_bullets_format():
    """AC9: body bullet format exactly matches the spec template."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("B", "乙")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (
            _analysis("X", 20.0), _analysis("Y", 15.0),
        )),
        "B": _op_row("B", "乙", (
            _analysis("X", 18.0), _analysis("Y", 12.0),
        )),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    body = [
        ln for ln in lines
        if ln.startswith("- ")
    ]
    assert len(body) == 1
    # Exact format: `- {id_a} {name_a} ↔ {id_b} {name_b}：加权重合 {pct:.1f}%，共同持仓 {syms}（{n} 只）`
    assert body[0] == "- A 甲 ↔ B 乙：加权重合 30.0%，共同持仓 X/Y（2 只）"


def test_concentration_lines_render_through_skeleton_into_section_6():
    """Integration: a non-empty concentration tuple flows through
    `MemoInputs.risk_notes` (prepended) and renders inside §6."""
    from irc.memo.template import MemoInputs, render_skeleton
    inputs = MemoInputs(
        date_str="2026-05-27", gold_regime="—", gold_zone="—", gold_tilt="—",
        allocation_mode="build", macro_summary="—", top_picks=(),
        risk_notes=(
            "<!-- IRC_CONCENTRATION_BEGIN -->",
            "持仓集中度（Top-10 加权重合 ≥ 30%）：...",
            "- A 甲 ↔ B 乙：加权重合 50.0%，共同持仓 X/Y（2 只）",
            "<!-- IRC_CONCENTRATION_END -->",
            "其他风险条目。",
        ),
        tldr_lines=(),
    )
    md = render_skeleton(inputs)
    assert "## 6. 风险提示" in md
    assert "<!-- IRC_CONCENTRATION_BEGIN -->" in md
    assert "<!-- IRC_CONCENTRATION_END -->" in md
    assert "其他风险条目" in md


def test_synthesizer_locks_concentration_block_when_marker_present():
    """AC10: synthesizer.py adds a verbatim-lock instruction for the
    IRC_CONCENTRATION_* marker pair — same pattern as the other 5 markers."""
    from unittest.mock import patch
    from irc.memo.synthesizer import synthesize_memo

    captured_messages: list = []

    def _fake_call_chat(route, messages, **kwargs):
        captured_messages.append(messages)

        class _Resp:
            text = "ok"
            prompt_tokens = 0
            completion_tokens = 0
        return _Resp()

    skeleton = "# memo\n<!-- IRC_CONCENTRATION_BEGIN -->\nbody\n<!-- IRC_CONCENTRATION_END -->\n"
    with patch("irc.memo.synthesizer.call_chat", side_effect=_fake_call_chat):
        synthesize_memo(skeleton, raw_ref_pool=[], route=None)  # type: ignore[arg-type]
    user_msg = next(m for m in captured_messages[0] if m["role"] == "user")["content"]
    assert "IRC_CONCENTRATION_BEGIN/END" in user_msg
    assert "原样保留" in user_msg  # the verbatim-lock keyword used by every other marker


def test_compute_concentration_pairs_does_not_mutate_input_rows():
    """AC11: pure transform — input OpportunityRows are not mutated.

    The frozen dataclass guarantee already enforces this at runtime; this
    test pins the expectation in case a future refactor adds a non-frozen
    wrapper.
    """
    from dataclasses import replace
    from irc.memo.concentration import compute_concentration_pairs
    a = _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0)))
    b = _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0)))
    snapshot_a = replace(a)
    snapshot_b = replace(b)
    _ = compute_concentration_pairs((a, b))
    # Equality on frozen dataclasses → field-wise equality.
    assert a == snapshot_a
    assert b == snapshot_b


def test_compose_concentration_lines_preserves_pick_row_order():
    """AC12: concentration analytic does NOT reorder pick_rows.

    The caller's `pick_rows` list is read-only (iterated in place). After
    the helper returns, pick ordering must be unchanged.
    """
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("B", "乙"), _pick("A", "甲")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        "B": _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
    }
    pre = [r.instrument_id for r in pick_rows]
    _ = _compose_concentration_lines(pick_rows, op_rows_by_id)
    post = [r.instrument_id for r in pick_rows]
    assert pre == post


def test_compute_concentration_pairs_two_run_byte_equality_with_shuffled_inputs():
    """AC13: two calls on the same set with shuffled row order produce
    byte-identical pair tuples (locks the determinism contract that the
    existing test_publishable_set_lockdown.py::test_two_run_byte_equality_memo
    will then exercise via the full pipeline)."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
        _op_row("C", "丙", (_analysis("X", 17.0), _analysis("Y", 13.0))),
        _op_row("D", "丁", ()),
    )
    shuffled = (rows[2], rows[0], rows[3], rows[1])  # deterministic shuffle
    a = compute_concentration_pairs(rows)
    b = compute_concentration_pairs(shuffled)
    assert a == b
    # Also assert repr-equality so any silent identity-vs-equality drift is caught.
    assert repr(a) == repr(b)


# === Review-fix tests (post /ship steps 8+9) =================================
# Adversarial review surfaced 1 P0 (duplicate-symbol undercount), code-reviewer
# surfaced 2 P1 (set-iteration determinism, FP boundary instability) + 1
# missing-coverage (n=5 boundary). RED → GREEN below.


def test_weighted_overlap_pct_dedupes_duplicate_symbol_within_fund():
    """P0 (adversarial): if AkShare returns the same symbol twice in one fund's
    constituent_analyses, the dict comprehension `{c.symbol: c.weight_pct}`
    silently keeps only the LAST entry (which is the lower-weight one after
    DESC sort), understating the overlap. A pair that should be ≥30% silently
    drops below threshold — false negative concentration suppression.

    Fix: dedupe by symbol with SUM-of-weights before topN selection.
    """
    from irc.memo.concentration import weighted_overlap_pct
    # Fund A: X appears twice (15 + 10 → should merge to 25). Y at 5.
    a = (
        _analysis("X", 15.0),
        _analysis("X", 10.0),
        _analysis("Y", 5.0),
    )
    # Fund B: X at 18 (single entry).
    b = (_analysis("X", 18.0),)
    # With dedupe-by-sum, A's X effective weight is 25, overlap = min(25, 18) = 18.
    # Without dedupe (the bug), only the later 10 wins, overlap = min(10, 18) = 10.
    assert weighted_overlap_pct(a, b) == 18.0


def test_weighted_overlap_pct_iterates_shared_symbols_in_deterministic_order():
    """P1 (code-reviewer): set intersection iteration is PYTHONHASHSEED-dependent.
    Float addition is non-commutative in IEEE 754; iteration order matters
    even though empirically deterministic with current data. Pin order
    explicitly with sorted() — also makes the function's determinism provable.
    """
    import inspect
    from irc.memo import concentration
    src = inspect.getsource(concentration.weighted_overlap_pct)
    # Either `sorted(...)` over the intersection, or an explicit pre-sort step.
    assert "sorted(" in src, (
        "weighted_overlap_pct must iterate the shared-symbols set in sorted "
        "order to pin FP summation determinism."
    )


def test_compute_concentration_pairs_threshold_compares_rounded_overlap():
    """P1 (silent-failure-hunter): the threshold check `overlap < THRESHOLD`
    uses the raw float sum BEFORE rounding. With realistic multi-symbol
    summation, a true 30.0%-overlap pair can compute as 29.9999...96 and be
    excluded. The displayed pct (rounded to 1dp inside make_concentration_pair)
    would then be 30.0, but the pair was filtered out — an invisible miss.

    Fix: compare `round(overlap, 1) >= THRESHOLD` so the displayed value and
    the threshold check agree by construction.
    """
    import inspect
    from irc.memo import concentration
    src = inspect.getsource(concentration.compute_concentration_pairs)
    # The threshold check must operate on the rounded value (overlap_pct on
    # the pair, OR an explicit round() before the < / >= comparison).
    assert "round(" in src and "CONCENTRATION_OVERLAP_PCT_THRESHOLD" in src, (
        "compute_concentration_pairs must compare a rounded overlap value "
        "against CONCENTRATION_OVERLAP_PCT_THRESHOLD to avoid FP boundary drop."
    )


def test_compose_concentration_lines_exactly_5_shared_symbols_no_ellipsis():
    """Coverage gap surfaced by code-reviewer: the 5-symbol cap with ellipsis
    is tested at n=6 but not at the boundary n=5 (no cap, no ellipsis).
    """
    from irc.commands.memo_cmd import _compose_concentration_lines
    syms = ["A1", "A2", "A3", "A4", "A5"]  # exactly 5
    analyses_a = tuple(_analysis(s, 7.0) for s in syms)
    analyses_b = tuple(_analysis(s, 7.0) for s in syms)
    pick_rows = [_pick("X", "甲"), _pick("Y", "乙")]
    op_rows_by_id = {
        "X": _op_row("X", "甲", analyses_a),
        "Y": _op_row("Y", "乙", analyses_b),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    joined = "\n".join(lines)
    # All 5 ASC; NO ellipsis, NO "（N 只）" elision suffix beyond the exact count.
    assert "A1/A2/A3/A4/A5" in joined
    assert "A1/A2/A3/A4/A5..." not in joined
    assert "（5 只）" in joined
