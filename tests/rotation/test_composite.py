from irc.rotation.composite import board_signals, cross_sectional
from irc.rotation.types import BoardDay


def _series(code, chgs, flows=None, turns=None, pes=None):
    n = len(chgs)
    flows = flows if flows is not None else [1.0] * n
    turns = turns if turns is not None else [2.0] * n
    pes = pes if pes is not None else [None] * n
    return tuple(
        BoardDay(date=f"2026-06-{i+1:02d}", board_code=code, board_name=code,
                 chg_pct=chgs[i], main_inflow_ratio=flows[i], turnover_pct=turns[i],
                 board_pe=pes[i], source="snapshot")
        for i in range(n))


def test_boards_below_20td_excluded():
    series = {"BK1": _series("BK1", [1.0] * 10)}  # only 10 days
    assert board_signals(series) == {}


def test_mom20_is_cumulative_chg_minus_cross_board_median():
    # spec §6: mom20 is a 20-TRADING-DAY cumulative window, not the whole series;
    # series carries 25 days of history so boards clear the MIN_TD=20 eligibility
    # gate, but the cumulative sum must be taken over only the trailing 20 days.
    up = _series("BK1", [1.0] * 25)      # last 20 days: +20 cumulative
    flat = _series("BK2", [0.0] * 25)    # last 20 days: 0 cumulative
    sig = board_signals({"BK1": up, "BK2": flat})
    # median cumulative = (20+0)/2 = 10.0; BK1 mom20 = 20-10.0 = 10.0
    assert round(sig["BK1"]["mom20"], 4) == 10.0
    assert round(sig["BK2"]["mom20"], 4) == -10.0


def test_composite_weights_and_ranks():
    hot = _series("BK1", [2.0] * 25, flows=[3.0] * 25, turns=[3.0] * 25)
    cold = _series("BK2", [0.0] * 25, flows=[0.0] * 25, turns=[1.0] * 25)
    comp = cross_sectional(board_signals({"BK1": hot, "BK2": cold}), flow_dark=False)
    assert comp["BK1"] > comp["BK2"]
    assert 0.0 <= comp["BK1"] <= 1.0


def test_flow_dark_renormalizes_and_ignores_flow():
    # BK1 wins on mom+turn even with flow set high on the LOSER — flow must not count
    hot = _series("BK1", [2.0] * 25, flows=[0.0] * 25, turns=[3.0] * 25)
    cold = _series("BK2", [0.0] * 25, flows=[9.0] * 25, turns=[1.0] * 25)
    comp = cross_sectional(board_signals({"BK1": hot, "BK2": cold}), flow_dark=True)
    assert comp["BK1"] > comp["BK2"]  # flow leg dropped for ALL boards


def test_pe_percentiles_ranks_only_boards_with_pe():
    from irc.rotation.composite import pe_percentiles
    pctls = pe_percentiles({"BK1": 80.0, "BK2": 10.0, "BK3": None})
    assert pctls["BK1"] > pctls["BK2"]  # higher PE → higher percentile
    assert "BK3" not in pctls  # PE-less board excluded → pe_pctl None downstream
    assert all(0.0 <= v <= 1.0 for v in pctls.values())


def test_flow_leg_dark_prevents_fabricated_zero_flow():
    """Post-seed window (dark-factor guard, D6): a board whose trailing-5-day flow
    window is all None (backfill rows carry main_inflow_ratio=None) must NOT be
    scored with a fabricated 0.0 flow while another board uses real flow. Even when
    the caller does NOT force flow_dark, flow_leg_dark makes cross_sectional renorm
    globally — so a None flow5 is never laundered into a 0.0 rank."""
    from irc.rotation.composite import flow_leg_dark

    with_flow = _series("BK1", [2.0] * 25, flows=[3.0] * 25, turns=[3.0] * 25)
    no_flow = _series("BK2", [1.0] * 25, flows=[None] * 25, turns=[2.0] * 25)
    sig = board_signals({"BK1": with_flow, "BK2": no_flow})
    assert sig["BK2"]["flow5"] is None            # backfill-only recent flow window
    assert flow_leg_dark(sig) is True             # leg unusable → must drop for all
    # flow_dark=False must still renorm (never use the flow leg) → identical to forced:
    assert cross_sectional(sig, flow_dark=False) == cross_sectional(sig, flow_dark=True)


def test_flow_leg_kept_when_all_boards_have_flow5():
    """Complement: when EVERY board has a real flow5, flow_leg_dark is False and the
    flow leg is used (composite differs from the renormalized flow-dark result)."""
    from irc.rotation.composite import flow_leg_dark

    a = _series("BK1", [2.0] * 25, flows=[3.0] * 25, turns=[3.0] * 25)
    b = _series("BK2", [0.0] * 25, flows=[0.0] * 25, turns=[1.0] * 25)
    sig = board_signals({"BK1": a, "BK2": b})
    assert flow_leg_dark(sig) is False
    assert cross_sectional(sig, flow_dark=False) != cross_sectional(sig, flow_dark=True)


def test_mom20_uniform_across_backfill_and_snapshot_source():
    """mom20 must not special-case row `source` — backfill rows derive chg_pct
    from close/prev_close, snapshot rows use EM field f3, but both represent the
    same daily close-to-close % change and must sum identically into mom20."""
    mixed = tuple(
        BoardDay(date=f"2026-06-{i+1:02d}", board_code="BK1", board_name="BK1",
                 chg_pct=1.0, main_inflow_ratio=1.0, turnover_pct=2.0,
                 board_pe=None, source="backfill" if i < 15 else "snapshot")
        for i in range(25))
    all_snapshot = _series("BK2", [1.0] * 25)
    sig = board_signals({"BK1": mixed, "BK2": all_snapshot})
    # same chg_pct sequence regardless of source split -> identical mom20
    assert sig["BK1"]["mom20"] == sig["BK2"]["mom20"]
