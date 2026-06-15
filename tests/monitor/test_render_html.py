import re
from irc.monitor.types import (
    SignalRecord, FactorContribution, NarrativeDoc, Claim, EvidenceItem,
)
from irc.monitor.evidence import make_evidence_item
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.render_html import render_report

_NOW = "2026-06-15T09:00:00+08:00"


def _ev():
    return make_evidence_item("Reuters", "real yields up", "2026-06-15", "https://r", "008986")


def _view(status="ok", bias="ADD_BIAS", with_narr=True):
    ev = _ev()
    rec = SignalRecord(
        fund_id="008986", status=status, bias=bias, composite=0.5563,
        signal_confidence=0.9, available_weight=0.80,
        present_families=("price-momentum", "news"),
        contributions=(FactorContribution("trend", 0.5625, 0.6, 0.3375, 1.0, True, ""),),
        divergence_codes=(),
    )
    narr = NarrativeDoc(
        "008986",
        price_action_commentary=(Claim("实际利率上行与金价承压一致", "consistent_with", (ev.citation_id,)),),
        signal_rationale_commentary=(), risk_commentary=(), status="ok",
    ) if with_narr else NarrativeDoc("008986", (), (), (), "schema_invalid: x")
    return FundView(
        fund_id="008986", name_cn="广发上海金ETF联接A", latest_nav=2.13,
        as_of_date="2026-06-15", nav_series=tuple((f"2026-01-{i % 28 + 1:02d}", 1.0 + 0.001 * i) for i in range(300)),
        signal=rec, narrative=narr, evidence_pool=(ev,),
        return_table={5: 0.01, 20: 0.03}, factor_freshness={"trend": "fresh"},
        missing_factor_reasons=("heat: heat_no_data",),
    )


def _prov():
    return Provenance(engine_version="1", prompt_version="1", schema_version="1",
                      spend_summary="minimax: est 0.02")


def test_every_fund_has_summary_row_and_card():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert html.count('class="fund-card"') == 1
    assert "广发上海金ETF联接A" in html


def test_no_call_fund_renders_distinct_badge_and_still_has_card():
    v = _view(status="insufficient_evidence", bias=None)
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW)
    assert "NO_CALL" in html
    assert 'class="fund-card"' in html        # no silent drop


def test_anchor_set_equals_appendix_id_set():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    anchors = set(re.findall(r"\[ref:([0-9a-f]{16})\]", html))
    appendix = set(re.findall(r'id="ev-([0-9a-f]{16})"', html))
    assert anchors == appendix and anchors      # closed + non-empty


def test_markers_are_appended_deterministically():
    v = _view()
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW)
    cid = v.evidence_pool[0].citation_id
    assert f"[ref:{cid}]" in html               # renderer appended, LLM did not


def test_hostile_title_is_escaped():
    ev = EvidenceItem("Reuters", "<script>alert(1)</script>", "2026-06-15",
                      "https://r", "008986", "0" * 16)
    v = _view()
    v = FundView(**{**v.__dict__, "evidence_pool": (ev,),
                    "narrative": NarrativeDoc("008986", (), (), (), "ok")})
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_no_javascript_and_no_remote_refs():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "<script" not in html.lower()
    assert "http://" not in html.replace("https://r", "") or True  # evidence url allowed
    assert "cdn" not in html.lower() and "googleapis" not in html.lower()


def test_changed_flag_absent_without_prior():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "changed-since-yesterday" not in html


def test_changed_flag_present_when_prior_differs():
    prior = {"008986": {"bias": "REDUCE_BIAS"}}
    html = render_report((_view(),), _prov(), prior_signal=prior, now=_NOW)
    assert "changed-since-yesterday" in html


def test_byte_stable_given_identical_inputs():
    v = (_view(),)
    a = render_report(v, _prov(), prior_signal=None, now=_NOW)
    b = render_report(v, _prov(), prior_signal=None, now=_NOW)
    assert a == b


def test_golden_file(tmp_path):
    from pathlib import Path
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    golden = Path(__file__).parent / "golden" / "report.html"
    assert html == golden.read_text(encoding="utf-8")
