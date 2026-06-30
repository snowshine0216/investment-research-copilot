from __future__ import annotations
import re
from irc.monitor.render_html import build_citation_index
from irc.monitor.evidence import make_evidence_item
from irc.monitor.render_types import FundView
from irc.monitor.types import NarrativeDoc, SignalRecord


def _view(fid, evs):
    rec = SignalRecord(fid, "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    return FundView(fund_id=fid, name_cn="x", latest_nav=1.0, as_of_date="2026-06-30",
                    nav_series=(), signal=rec, narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=evs, return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


def test_citation_index_numbers_in_appendix_first_seen_order():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    b = make_evidence_item("Bloomberg", "title B", "2026-06-30", "https://b", "001")
    idx = build_citation_index((_view("001", (a, b)),))
    assert idx.number(a.citation_id) == 1
    assert idx.number(b.citation_id) == 2
    assert idx.source(a.citation_id) == "Reuters"
    assert idx.title(a.citation_id) == "title A"


def test_citation_index_dedups_repeated_cid():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    idx = build_citation_index((_view("001", (a,)), _view("002", (a,))))
    assert idx.number(a.citation_id) == 1
    assert len(idx.entries) == 1


def test_citation_index_unknown_cid_returns_none():
    idx = build_citation_index((_view("001", ()),))
    assert idx.number("deadbeefdeadbeef") is None


import re
from irc.monitor.render_html import render_report
from irc.monitor.render_types import Provenance
from irc.monitor.types import Claim


def test_appendix_numbers_align_with_superscripts():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    rec = SignalRecord("001", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("001",
                        price_action_commentary=(Claim("c", "consistent_with", (a.citation_id,)),),
                        signal_rationale_commentary=(), risk_commentary=(), status="ok")
    view = FundView(fund_id="001", name_cn="x", latest_nav=1.0, as_of_date="2026-06-30",
                    nav_series=(), signal=rec, narrative=narr, evidence_pool=(a,),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())
    html = render_report((view,), Provenance("3", "1", "1", ""),
                         prior_signal=None, now="2026-06-30T09:00:00+08:00")
    # appendix li carries a leading "1." and id ev-{cid}
    assert f'<li id="ev-{a.citation_id}">1.' in html
    # the in-text superscript anchor links to the same id with number 1
    assert f'href="#ev-{a.citation_id}" title="Reuters — title A">1</a>' in html
    # no raw [ref:cid] survives anywhere
    assert "[ref:" not in html


def test_no_script_or_remote_refs_in_report():
    html = render_report((), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00")
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "基金概况" not in html
