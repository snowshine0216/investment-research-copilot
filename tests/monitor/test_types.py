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
