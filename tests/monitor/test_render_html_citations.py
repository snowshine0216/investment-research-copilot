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
