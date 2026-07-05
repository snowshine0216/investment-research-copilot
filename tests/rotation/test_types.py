import dataclasses

from irc.rotation.types import (
    BoardDay, BoardState, ExposureRow, RotationCandidate, RotationReport,
)


def test_board_day_is_frozen():
    bd = BoardDay(date="2026-07-06", board_code="BK0475", board_name="半导体",
                  chg_pct=2.31, main_inflow_ratio=1.84, turnover_pct=3.9,
                  board_pe=45.2, source="snapshot")
    bd2 = dataclasses.replace(bd, chg_pct=0.0)
    assert bd2.chg_pct == 0.0 and bd.chg_pct == 2.31


def test_board_day_board_pe_optional():
    bd = BoardDay(date="2026-07-06", board_code="BK0475", board_name="半导体",
                  chg_pct=2.31, main_inflow_ratio=1.84, turnover_pct=3.9,
                  board_pe=None, source="snapshot")
    assert bd.board_pe is None


def test_board_state_defaults_and_frozen():
    bs = BoardState(board_code="BK0475", board_name="半导体", state="emerging",
                    days_in_state=2, composite_pctl=0.83, mom20=1.2, flow5=1.5,
                    turn_delta=0.4, pe_pctl=0.95, chase_risk=True)
    assert bs.state == "emerging" and bs.chase_risk is True
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        bs.state = "hot"  # type: ignore[misc]


def test_report_shape():
    rep = RotationReport(schema_version=1, radar_version=1, data_status="ok",
                         board_states=(), candidates=(), diagnostics={})
    assert rep.schema_version == 1 and rep.radar_version == 1


def test_exposure_row_and_candidate_are_frozen():
    er = ExposureRow(fund_id="000001", name_cn="示例基金", board_code="BK0475",
                     exposure_pct=12.5, matched_symbols=("600000",),
                     holdings_as_of="2026Q1")
    cand = RotationCandidate(fund_id="000001", name_cn="示例基金",
                             board_code="BK0475", board_name="半导体",
                             exposure_pct=12.5, on_discovered_watchlist=True,
                             in_monitor_set=False, held=False,
                             holdings_as_of="2026Q1")
    assert er.board_code == cand.board_code == "BK0475"
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        cand.held = True  # type: ignore[misc]
