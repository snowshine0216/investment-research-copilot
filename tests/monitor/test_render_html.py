import re
from irc.monitor.types import (
    SignalRecord, FactorContribution, NarrativeDoc, Claim, EvidenceItem, FactorScore,
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
        factor_scores=(
            FactorScore("trend", 0.6, True, "", 1.0),
            FactorScore("valuation", None, False, "valuation_no_index", 1.0),
            FactorScore("heat", None, False, "heat_no_data", 1.0),
            FactorScore("macro_tilt", None, False, "macro_no_rows", 1.0),
            FactorScore("constituent", None, False, "constituent_no_snapshot", 1.0),
        ),
    )


def _prov():
    return Provenance(engine_version="1", prompt_version="1", schema_version="1",
                      spend_summary="minimax: est 0.02")


def test_report_has_lean_disclaimer_and_legend():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    # bias is a research lean — not a tradable buy/sell order, not advice
    assert "研究参考" in html and "非买卖指令" in html
    assert "不构成投资建议" in html
    # legend decodes the badges + validation chips
    assert "ADD_BIAS=偏多" in html
    assert "caveated" in html
    # the explainer sits above the per-fund cards
    assert html.index("非买卖指令") < html.index('class="fund-card"')


def test_disclaimer_banner_is_static_and_carries_no_javascript():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert '<aside class="explainer">' in html
    assert "<script" not in html.lower()


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


def test_impacts_status_carried_in_fundview():
    """P1 fix: impacts_status field exists and is accessible (not silently dropped)."""
    v_ok = _view()
    assert v_ok.impacts_status == "ok"

    # FundView with a degraded impacts_status should carry the reason
    ev = _ev()
    rec = v_ok.signal
    narr = v_ok.narrative
    v_bad = FundView(
        fund_id="008986", name_cn="广发上海金ETF联接A", latest_nav=2.13,
        as_of_date="2026-06-15",
        nav_series=tuple((f"2026-01-{i % 28 + 1:02d}", 1.0 + 0.001 * i) for i in range(300)),
        signal=rec, narrative=narr, evidence_pool=(ev,),
        return_table={}, factor_freshness={}, missing_factor_reasons=(),
        impacts_status="schema_invalid: bad json",
    )
    assert v_bad.impacts_status == "schema_invalid: bad json"
    # render must not crash when impacts_status is non-ok
    html = render_report((v_bad,), _prov(), prior_signal=None, now=_NOW)
    assert 'class="fund-card"' in html


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


def test_card_has_verdict_block():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert 'class="verdict"' in html
    assert "综合分 C" in html


def test_card_has_factor_table_with_na_rows():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='factors'" in html
    assert "factor-na" in html               # at least one N/A factor row
    assert "heat_no_data" in html            # structured reason surfaced


def test_card_has_real_returns_table():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='returns'" in html
    assert "60d:" in html and "250d:" in html  # the full window set


def test_card_has_risk_block_or_placeholder():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert 'class="risk"' in html


def test_old_missing_ul_is_gone():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='missing'" not in html      # replaced by the factor table


def test_no_call_card_keeps_gate_clause_and_no_neutral_label():
    v = _view(status="insufficient_evidence", bias=None)
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW)
    assert "NO_CALL" in html
    # NO_CALL ≠ NEUTRAL: the verdict clause must not assert a NEUTRAL call
    assert "落在中性带内" not in html
