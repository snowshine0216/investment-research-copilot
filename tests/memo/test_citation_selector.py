from __future__ import annotations

from irc.memo.citation_selector import select_citations
from irc.opportunity.types import ThesisEvidence


def _ev(**over):
    """Helper: minimal-valid ThesisEvidence with overrides."""
    base = dict(
        type="filing", source="s", url="https://u/x", date="2026-04-28",
        summary="x",
        scope="instrument", citation_kind="data",
        owner_instrument_id="510300", parent_fund_id=None, constituent_key=None,
    )
    base.update(over)
    return ThesisEvidence(**base)


def test_select_citations_empty_input_returns_empty_tuple():
    assert select_citations((), cap=3) == ()


def test_select_citations_cap_zero_returns_empty_tuple():
    entries = (_ev(),)
    assert select_citations(entries, cap=0) == ()


def test_select_citations_cap_greater_than_len_returns_all_entries():
    a = _ev(url="https://u/a", citation_kind="data")
    b = _ev(url="https://u/b", citation_kind="information")
    out = select_citations((a, b), cap=10)
    assert set(out) == {a, b}
    assert len(out) == 2


def test_select_citations_deterministic_across_shuffled_inputs():
    """Two input tuples with the same SET of entries (different order) → same output."""
    a = _ev(url="https://u/a", date="2026-04-01", citation_kind="data")
    b = _ev(url="https://u/b", date="2026-04-15", citation_kind="information")
    c = _ev(url="https://u/c", date="2026-05-01", citation_kind="data",
            scope="asset_class_macro")
    d = _ev(url="https://u/d", date="2026-03-10", citation_kind="information",
            scope="constituent", parent_fund_id="005827", constituent_key="600519")
    out_abc = select_citations((a, b, c, d), cap=3)
    out_dcba = select_citations((d, c, b, a), cap=3)
    out_bdac = select_citations((b, d, a, c), cap=3)
    assert out_abc == out_dcba == out_bdac


def test_select_citations_data_and_info_leg_invariant():
    """If inputs contain ≥1 data AND ≥1 information, output contains ≥1 of each.

    Locks the dual-coverage gate invariant: 6 data + 2 info → output includes
    ≥1 info even with cap=3.
    """
    datas = tuple(
        _ev(url=f"https://u/d{i}", citation_kind="data", date=f"2026-04-{10+i:02d}")
        for i in range(6)
    )
    infos = (
        _ev(url="https://u/i0", citation_kind="information", date="2026-04-01"),
        _ev(url="https://u/i1", citation_kind="information", date="2026-04-02"),
    )
    out = select_citations(datas + infos, cap=3)
    kinds = {e.citation_kind for e in out}
    assert "data" in kinds, f"data-leg missing from {out}"
    assert "information" in kinds, f"info-leg missing from {out}"


def test_select_citations_rendering_order_scope_then_date_then_id():
    """Stable rendering order: (scope_rank desc, date desc, citation_id asc).

    Build a fixed input with hand-picked dates so the expected order is
    deterministic.
    """
    # scope=instrument (rank=2), date=2026-05-01, kind=data
    high_recent = _ev(url="https://u/H", date="2026-05-01", citation_kind="data")
    # scope=asset_class_macro (rank=1), date=2026-05-05, kind=information
    low_recent = _ev(url="https://u/L", date="2026-05-05",
                     citation_kind="information", scope="asset_class_macro")
    # scope=instrument (rank=2), date=2026-04-01, kind=information
    high_old = _ev(url="https://u/M", date="2026-04-01", citation_kind="information")
    out = select_citations((low_recent, high_old, high_recent), cap=3)
    # Expected: scope_rank desc first → high_recent and high_old before low_recent.
    # Between high_recent and high_old: date desc → high_recent (May) before high_old (Apr).
    assert out[0] is high_recent
    assert out[1] is high_old
    assert out[2] is low_recent


def test_select_citations_picks_only_one_data_when_no_information_available():
    """If only data entries exist, output contains data only (info-leg empty)."""
    entries = tuple(_ev(url=f"https://u/d{i}", citation_kind="data") for i in range(4))
    out = select_citations(entries, cap=3)
    assert all(e.citation_kind == "data" for e in out)
    assert len(out) == 3
