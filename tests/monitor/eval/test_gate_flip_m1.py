from __future__ import annotations
from irc.monitor.eval.gate import GATING_STAGES_M0, GATING_STAGES_M1


def test_gating_stages_m1_is_m0_plus_two_llm_suites():  # AC17
    assert GATING_STAGES_M1 == GATING_STAGES_M0 | {"monitor_impact", "monitor_narrative"}
    assert GATING_STAGES_M0 < GATING_STAGES_M1  # strict superset
