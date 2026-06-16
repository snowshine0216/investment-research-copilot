from __future__ import annotations
from irc.monitor.eval import constants as C


def test_constant_values_pinned():
    assert C.FORWARD_H == 20
    assert C.N_MIN_BLOCKS == 8
    assert C.MIN_CROSS == 4
    assert C.MIN_DEFINED_DAYS == 8
    assert C.MIN_PERM_DATES == 8
    assert C.BOOTSTRAP_B == 2000
    assert C.REVIEW_TRIGGER_K == 4
    assert C.NAV_APPEND_DAYS == 60
    assert C.STALE_EVAL_DAYS == 10


def test_no_retro_grid_floor_literal():
    # The retro grid floor is sourced from config minimum_observations (251),
    # NOT a literal in this module. Guard against re-introducing MIN_TREND_OBS.
    assert not hasattr(C, "MIN_TREND_OBS")
    assert not hasattr(C, "MINIMUM_OBSERVATIONS")
