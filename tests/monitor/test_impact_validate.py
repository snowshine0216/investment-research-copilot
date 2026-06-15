import pytest
from irc.monitor.evidence import make_evidence_item
from irc.monitor.impact_validate import validate_impacts, ImpactValidationError


def _pool(fund="008986"):
    return (make_evidence_item("Reuters", "real yields up", "2026-06-15", "https://r", fund),)


def test_valid_impact_resolves():
    pool = _pool()
    cid = pool[0].citation_id
    rows = [{"key": "gold_drivers", "impact": -0.5, "confidence": 0.8, "citation_ids": [cid]}]
    out = validate_impacts(rows, pool, owner_fund_id="008986")
    assert out[0].impact == -0.5 and out[0].confidence == 0.8


def test_unknown_citation_id_rejected():
    rows = [{"key": "gold_drivers", "impact": 0.1, "confidence": 0.5, "citation_ids": ["dead0000dead0000"]}]
    with pytest.raises(ImpactValidationError, match="unresolved_citation"):
        validate_impacts(rows, _pool(), owner_fund_id="008986")


def test_impact_out_of_range_rejected():
    pool = _pool()
    rows = [{"key": "gold_drivers", "impact": 2.0, "confidence": 0.5, "citation_ids": [pool[0].citation_id]}]
    with pytest.raises(ImpactValidationError, match="schema_invalid"):
        validate_impacts(rows, pool, owner_fund_id="008986")


def test_empty_pool_rejected():
    rows = []
    with pytest.raises(ImpactValidationError, match="empty_pool"):
        validate_impacts(rows, (), owner_fund_id="008986")
