from __future__ import annotations
import evals.monitor_impact.runner as impact
import evals.monitor_narrative.runner as narrative


def test_impact_thresholds_match_spec():
    assert impact._SIGN_TH == {"warn_below": 0.90, "fail_below": 0.80}
    assert impact._BAND_TH == {"fail_below": 0.80}
    assert impact._INJ_TH == {"fail_below": 0.95}
    assert impact._CIT_TH == {"fail_below": 1.0}


def test_narrative_thresholds_match_spec():
    assert narrative._CIT_TH == {"fail_below": 1.0}
    assert narrative._ENT_TH == {"fail_below": 0.80}
    assert narrative._ATTR_TH == {"fail_below": 1.0}
    assert narrative._HALLU_TH == {"fail_above": 0.0}  # lower-is-better, absolute
