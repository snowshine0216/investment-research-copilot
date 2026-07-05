from irc.rotation.candidates import rank_candidates
from irc.rotation.types import BoardState, ExposureRow


def _state(code, state):
    return BoardState(board_code=code, board_name=code, state=state, days_in_state=1,
                      composite_pctl=0.85, mom20=1.0, flow5=1.0, turn_delta=0.1,
                      pe_pctl=None, chase_risk=False)


def _exp(fund, code, pct, as_of="2026Q1"):
    return ExposureRow(fund_id=fund, name_cn=fund, board_code=code, exposure_pct=pct,
                       matched_symbols=("600001",), holdings_as_of=as_of)


def test_only_emerging_hot_boards_produce_candidates():
    rows = [_exp("F1", "BK1", 20.0), _exp("F2", "BK2", 30.0)]
    states = [_state("BK1", "emerging"), _state("BK2", "quiet")]
    cands, _ = rank_candidates(rows, states, discovered_watchlist=frozenset(),
                               monitor_set=frozenset(), held=frozenset())
    assert {c.fund_id for c in cands} == {"F1"}  # BK2 is quiet → excluded


def test_threshold_and_annotations():
    rows = [_exp("F1", "BK1", 20.0), _exp("F2", "BK1", 5.0)]  # F2 below 10%
    states = [_state("BK1", "hot")]
    cands, new = rank_candidates(rows, states,
                                 discovered_watchlist=frozenset({"F1"}),
                                 monitor_set=frozenset(), held=frozenset())
    assert [c.fund_id for c in cands] == ["F1"]  # F2 filtered by threshold
    c = cands[0]
    assert c.on_discovered_watchlist is True and c.in_monitor_set is False
    assert c.held is False and c.holdings_as_of == "2026Q1"
    assert new == ()  # F1 is on the discovered watchlist → not new


def test_new_candidates_rollup():
    rows = [_exp("F9", "BK1", 25.0)]
    states = [_state("BK1", "emerging")]
    _, new = rank_candidates(rows, states, discovered_watchlist=frozenset(),
                             monitor_set=frozenset(), held=frozenset())
    assert new == ("F9",)  # on no existing surface
