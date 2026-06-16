import dataclasses
import pytest
from irc.monitor.types import (
    EvidenceItem, FactorScore, SignalRecord,
)


def test_evidence_item_has_no_scope_field():
    fields = {f.name for f in dataclasses.fields(EvidenceItem)}
    assert "scope" not in fields                      # ADR 0017
    assert {"source", "title", "date", "url", "owner_fund_id", "citation_id"} <= fields


def test_factor_score_na_carries_reason():
    fs = FactorScore(name="valuation", value=None, eligible=False, reason="valuation_no_anchor")
    assert fs.value is None and fs.reason == "valuation_no_anchor"


def test_signal_record_is_tagged_union_status_plus_bias():
    rec = SignalRecord(
        fund_id="008986", status="insufficient_evidence", bias=None,
        composite=0.0, signal_confidence=0.0, available_weight=0.2,
        present_families=("price-momentum",), contributions=(), divergence_codes=(),
    )
    assert rec.status == "insufficient_evidence"
    assert rec.bias is None                            # null iff status != ok


def test_frozen():
    fs = FactorScore(name="trend", value=0.3, eligible=True, reason="")
    with pytest.raises(dataclasses.FrozenInstanceError):
        fs.value = 0.5


def test_fundview_carries_factor_scores():
    from irc.monitor.render_types import FundView
    from irc.monitor.types import FactorScore, SignalRecord, NarrativeDoc
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("x", (), (), (), "ok")
    fs = (FactorScore("trend", 0.1, True, "", 1.0),)
    v = FundView(
        fund_id="x", name_cn="n", latest_nav=1.0, as_of_date="2026-06-15",
        nav_series=(), signal=rec, narrative=narr, evidence_pool=(),
        return_table={}, factor_freshness={}, missing_factor_reasons=(),
        factor_scores=fs,
    )
    assert v.factor_scores == fs
