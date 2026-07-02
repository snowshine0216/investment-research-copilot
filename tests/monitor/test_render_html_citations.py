from __future__ import annotations
from datetime import datetime, timedelta, timezone
from irc.monitor.render_html import build_citation_index, render_report
from irc.monitor.evidence import make_evidence_item
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.types import EvidenceItem, NarrativeDoc, SignalRecord, Claim

_NOW_DT = datetime(2026, 6, 30, 9, 0, tzinfo=timezone(timedelta(hours=8)))


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
                         prior_signal=None, now="2026-06-30T09:00:00+08:00", now_dt=_NOW_DT)
    # appendix li carries a leading "1." and id ev-{cid}
    assert f'<li id="ev-{a.citation_id}">1.' in html
    # the in-text superscript anchor links to the same id with number 1; hover title
    # carries source AND date (spec §6, unqualified — parity with _sup_local)
    assert f'href="#ev-{a.citation_id}" title="Reuters — title A · 2026-06-30">1</a>' in html
    # no raw [ref:cid] survives anywhere
    assert "[ref:" not in html


def test_no_script_or_remote_refs_in_report():
    html = render_report((), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00", now_dt=_NOW_DT)
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "基金概况" not in html


def test_citation_index_dedups_by_url_and_date_across_owners():
    """Two EvidenceItems with different cids (different owner_fund_id) but the
    SAME (url, date) collapse to ONE appendix entry (Comp 2 makes this exact
    post-consolidation)."""
    ev_a = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-15",
                        url="https://reuters.com/fed", owner_fund_id="270023",
                        citation_id="a" * 16)
    ev_b = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-15",
                        url="https://reuters.com/fed", owner_fund_id="009225",
                        citation_id="b" * 16)
    view_a = _view("270023", (ev_a,))
    view_b = _view("009225", (ev_b,))

    idx = build_citation_index((view_a, view_b))
    assert idx.number("a" * 16) == idx.number("b" * 16)   # same appendix number
    assert len(idx.entries) == 1


def test_citation_index_no_url_falls_back_to_title_plus_date():
    """No-URL items (e.g. constituent-pool snapshot fallback) dedup on
    (title, date) instead."""
    ev_a = EvidenceItem(source="snapshot:600000", title="X公司 (600000): 概况",
                        date="", url="", owner_fund_id="519069", citation_id="c" * 16)
    ev_b = EvidenceItem(source="snapshot:600000", title="X公司 (600000): 概况",
                        date="", url="", owner_fund_id="260112", citation_id="d" * 16)
    view_a = _view("519069", (ev_a,))
    view_b = _view("260112", (ev_b,))

    idx = build_citation_index((view_a, view_b))
    assert idx.number("c" * 16) == idx.number("d" * 16)
    assert len(idx.entries) == 1


def test_citation_index_different_dates_do_not_dedup():
    ev_a = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-15",
                        url="https://reuters.com/fed", owner_fund_id="270023",
                        citation_id="a" * 16)
    ev_b = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-16",
                        url="https://reuters.com/fed", owner_fund_id="009225",
                        citation_id="b" * 16)
    view_a = _view("270023", (ev_a,))
    view_b = _view("009225", (ev_b,))

    idx = build_citation_index((view_a, view_b))
    assert idx.number("a" * 16) != idx.number("b" * 16)
    assert len(idx.entries) == 2


def test_citation_index_appendix_order_is_first_seen():
    ev_first = EvidenceItem(source="a.com", title="first", date="2026-06-14",
                            url="https://a.com/1", owner_fund_id="270023",
                            citation_id="1" * 16)
    ev_second = EvidenceItem(source="b.com", title="second", date="2026-06-15",
                             url="https://b.com/2", owner_fund_id="270023",
                             citation_id="2" * 16)
    view = _view("270023", (ev_first, ev_second))

    idx = build_citation_index((view,))
    assert idx.number("1" * 16) == 1
    assert idx.number("2" * 16) == 2


def test_appendix_renders_date_and_tier_badge_per_entry():
    from irc.monitor.render_html import _appendix, CitationIndex

    idx = CitationIndex(
        entries=(("a" * 16, "reuters.com", "Fed holds", "2026-06-15", "权威"),),
        cid_to_entry_index={"a" * 16: 0},
    )
    html = _appendix(idx)
    assert "Fed holds" in html
    assert "reuters.com" in html
    assert "2026-06-15" in html
    assert "权威" in html
    assert html.count("<li") == 1


def test_appendix_one_li_per_deduped_entry_not_per_cid():
    ev_a = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-15",
                        url="https://reuters.com/fed", owner_fund_id="270023",
                        citation_id="a" * 16)
    ev_b = EvidenceItem(source="reuters.com", title="Fed holds", date="2026-06-15",
                        url="https://reuters.com/fed", owner_fund_id="009225",
                        citation_id="b" * 16)
    view_a = _view("270023", (ev_a,))
    view_b = _view("009225", (ev_b,))
    idx = build_citation_index((view_a, view_b))
    from irc.monitor.render_html import _appendix
    html = _appendix(idx)
    assert html.count("<li") == 1   # ONE <li>, not two, for the same article


def test_superscript_hover_title_includes_date():
    """spec §6: hover title = source — title · date."""
    from irc.monitor.render_html import _sup_local, CitationIndex

    idx = CitationIndex(
        entries=(("a" * 16, "reuters.com", "Fed holds", "2026-06-15", "权威"),),
        cid_to_entry_index={"a" * 16: 0},
    )
    html = _sup_local("a" * 16, idx)
    assert 'title="reuters.com — Fed holds · 2026-06-15"' in html


def test_build_tier_badges_classifies_theme_pool_items():
    from irc.monitor.render_html import build_tier_badges
    from irc.monitor.source_tiers import SourceTiers

    ev = EvidenceItem(source="reuters.com", title="x", date="2026-06-15",
                      url="https://reuters.com/a", owner_fund_id="270023",
                      citation_id="a" * 16)
    tiers = SourceTiers(blocked=(), tier1=("reuters.com",), tier2=())
    badges = build_tier_badges((ev,), tiers=tiers, constituent_cids=frozenset())
    assert badges["a" * 16] == "权威"


def test_build_tier_badges_constituent_pool_items_get_snapshot_badge():
    from irc.monitor.render_html import build_tier_badges
    from irc.monitor.source_tiers import SourceTiers

    ev = EvidenceItem(source="snapshot:600000", title="x", date="",
                      url="", owner_fund_id="519069", citation_id="c" * 16)
    tiers = SourceTiers(blocked=(), tier1=(), tier2=())
    badges = build_tier_badges((ev,), tiers=tiers, constituent_cids=frozenset({"c" * 16}))
    assert badges["c" * 16] == "快照"


def test_build_tier_badges_unknown_domain_gets_未分级():
    from irc.monitor.render_html import build_tier_badges
    from irc.monitor.source_tiers import SourceTiers

    ev = EvidenceItem(source="some-new-blog.example", title="x", date="2026-06-15",
                      url="https://some-new-blog.example/a", owner_fund_id="270023",
                      citation_id="e" * 16)
    tiers = SourceTiers(blocked=(), tier1=(), tier2=())
    badges = build_tier_badges((ev,), tiers=tiers, constituent_cids=frozenset())
    assert badges["e" * 16] == "未分级"
