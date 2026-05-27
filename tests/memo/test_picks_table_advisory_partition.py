"""Stable-partition test for §5 picks-table advisory demotion (AC8)."""
from __future__ import annotations

from irc.memo.picks_table import PickRow


def _pick(iid: str, *, advisory: tuple[str, ...] = ()) -> PickRow:
    return PickRow(
        instrument_id=iid, name_cn=iid, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        advisory_gaps=advisory,
    )


def test_pickrow_default_advisory_gaps_is_empty_tuple():
    row = _pick("005827")
    assert row.advisory_gaps == ()


def test_pickrow_accepts_advisory_gaps_keyword():
    row = _pick("005827", advisory=("top_holdings_broker_thin",))
    assert row.advisory_gaps == ("top_holdings_broker_thin",)


def test_stable_partition_demotes_advisory_rows_to_tail():
    """AC8: a stable partition over pick_rows puts non-advisory rows first.

    Trade-plan iteration order is preserved within each partition.
    """
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [
        _pick("A"),  # non-advisory
        _pick("B", advisory=("top_holdings_broker_thin",)),  # advisory
        _pick("C"),  # non-advisory
        _pick("D", advisory=("top_holdings_broker_thin",)),  # advisory
    ]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "C", "B", "D"]


def test_stable_partition_preserves_order_when_no_advisory():
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [_pick("A"), _pick("B"), _pick("C")]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "B", "C"]


def test_stable_partition_preserves_order_when_all_advisory():
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [
        _pick("A", advisory=("top_holdings_broker_thin",)),
        _pick("B", advisory=("top_holdings_broker_thin",)),
    ]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "B"]


def test_stable_partition_does_not_demote_unknown_advisory_codes():
    """AC8: demotion is specific to `top_holdings_broker_thin`.

    Any future advisory code added to `ADVISORY_GAP_CODES` must not silently
    inherit the §5 pick-ordering demotion — that's a separate design decision
    per ADR 0005. This test pins the membership-check semantic against the
    over-broad `not r.advisory_gaps` check.

    Input order is [B-unknown, A-clean, C-broker_thin] specifically so that the
    over-broad check (current bug) produces a different order than the
    membership check (the fix). The over-broad check would demote B and C
    together, yielding [A, B, C]; the correct fix keeps B in its slot,
    yielding [B, A, C].
    """
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [
        _pick("B", advisory=("hypothetical_future_code",)),  # unknown advisory
        _pick("A"),  # non-advisory
        _pick("C", advisory=("top_holdings_broker_thin",)),  # demoting code
    ]
    partitioned = _apply_advisory_partition(rows)
    # B keeps its leading position; only C is demoted to tail.
    assert [r.instrument_id for r in partitioned] == ["B", "A", "C"]
