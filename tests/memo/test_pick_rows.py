from __future__ import annotations

from dataclasses import asdict

from irc.commands.memo_cmd import _build_pick_rows
from irc.opportunity.types import ThesisEvidence


def _make_evidence_dict(**over) -> dict:
    base = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    d = asdict(base)
    d.update(over)
    return d


def _op_row(iid="510300", evidence_gaps=(), thesis_evidence=None, **over):
    base = {
        "instrument_id": iid,
        "name_cn": f"{iid}_name",
        "asset_class": "cn_etf",
        "opportunity_state": "core_dca",
        "opportunity_reason": "r",
        "evidence_gaps": list(evidence_gaps),
        "fetch_types_attempted": ["filing", "broker", "news"],
        "thesis_evidence": list(thesis_evidence or ()),
    }
    base.update(over)
    return base


def test_build_pick_rows_absent_target_routes_to_absent_bucket():
    """trade target whose iid is not in opportunity rows (after venue-proxy
    strip) ends up in `absent`, NOT in `pick_rows`."""
    trades = [{"target": "999999", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert len(absent) == 1
    assert absent[0]["target"] == "999999"
    assert gapped == []


def test_build_pick_rows_gapped_target_routes_to_gapped_bucket():
    """trade target whose op row has `evidence_gaps != ()` ends up in
    `gapped`, NOT in `pick_rows`."""
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300",
                                    evidence_gaps=("holdings_fetch_failed",))]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert absent == []
    assert len(gapped) == 1
    assert gapped[0]["target"] == "510300"
    assert gapped[0]["_matched_row"]["instrument_id"] == "510300"


def test_build_pick_rows_clean_target_builds_pick_with_citations():
    """trade target whose op row has `evidence_gaps == ()` produces a PickRow
    whose `citations` is `select_citations(rebuilt_evidence, cap=3)`."""
    ev_dict = _make_evidence_dict()
    trades = [{"target": "510300", "target_weight": 0.1, "composite_score": 50.0}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1
    pr = pick_rows[0]
    assert pr.instrument_id == "510300"
    assert len(pr.citations) == 1
    assert pr.citations[0].citation_id == ev_dict["citation_id"]


def test_build_pick_rows_venue_proxy_strip_falls_back_to_canonical():
    """A trade target like `A510300.SH` should match op row `510300` after
    suffix strip."""
    trades = [{"target": "A510300.SH", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1


def test_build_pick_rows_raises_on_citation_id_tampering():
    """If the rebuilt ThesisEvidence's recomputed citation_id != the JSON
    value, raise ValueError — detects drift/tampering."""
    import pytest
    ev_dict = _make_evidence_dict()
    ev_dict["citation_id"] = "deadbeefdeadbeef"  # wrong; will recompute differently
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    with pytest.raises(ValueError, match="citation_id"):
        _build_pick_rows(trades, opportunity, {"scores": []})


def test_build_pick_rows_missing_opportunity_falls_into_absent():
    """When opportunity is {} (file absent), every trade target falls into
    `absent` — explicit signal that opportunity didn't run."""
    trades = [{"target": "510300"}, {"target": "159919"}]
    pick_rows, absent, gapped = _build_pick_rows(trades, {}, {"scores": []})
    assert pick_rows == []
    assert {a["target"] for a in absent} == {"510300", "159919"}
    assert gapped == []
