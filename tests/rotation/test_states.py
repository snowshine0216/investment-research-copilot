from irc.rotation.states import classify_board


def _series(pctls):
    return tuple((f"2026-06-{i+1:02d}", p) for i, p in enumerate(pctls))


def test_quiet_when_never_above_enter():
    state, dis = classify_board(_series([0.5, 0.6, 0.55, 0.4]))
    assert state == "quiet"


def test_emerging_when_crossed_enter_within_5td():
    # crosses above 0.80 on the last day
    state, dis = classify_board(_series([0.5, 0.6, 0.7, 0.75, 0.85]))
    assert state == "emerging" and dis == 1


def test_hot_when_above_band_more_than_5td():
    state, _ = classify_board(_series([0.85, 0.86, 0.9, 0.88, 0.91, 0.87]))
    assert state == "hot"


def test_no_flap_on_p79_p81_oscillation():
    # oscillates around the band but never exits below 0.70 → stays hot, no flap
    seq = [0.85, 0.86, 0.9, 0.88, 0.91, 0.87, 0.79, 0.81, 0.79, 0.81]
    state, _ = classify_board(_series(seq))
    assert state == "hot"


def test_fading_on_band_exit_within_5td():
    seq = [0.85, 0.9, 0.88, 0.91, 0.87, 0.6]  # fell below 0.70 on last day after hot
    state, dis = classify_board(_series(seq))
    assert state == "fading"


def test_emerging_promotes_to_hot_at_day_6():
    seq = [0.85, 0.86, 0.87, 0.88, 0.89, 0.90]  # 6 consecutive days above enter
    state, _ = classify_board(_series(seq))
    assert state == "hot"


def test_property_total_function_of_slice():
    # any pctl series returns a valid state + non-negative days_in_state
    import itertools
    for combo in itertools.product([0.1, 0.75, 0.85], repeat=4):
        state, dis = classify_board(_series(list(combo)))
        assert state in {"emerging", "hot", "fading", "quiet"}
        assert dis >= 0
