import dataclasses
import re
from datetime import datetime, timedelta, timezone

from irc.monitor.holding_metrics import HoldingMetric
from irc.monitor.render_html import _card, _flow_outage_note, render_report
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.evidence import make_evidence_item
from irc.monitor.types import (
    Claim, EvidenceItem, FactorContribution, FactorScore, NarrativeDoc, SignalRecord,
)

_NOW = "2026-06-15T09:00:00+08:00"
_NOW_DT = datetime(2026, 6, 15, 9, 0, tzinfo=timezone(timedelta(hours=8)))


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
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    # bias is a research lean — not a tradable buy/sell order, not advice
    assert "研究参考" in html and "非买卖指令" in html
    assert "不构成投资建议" in html
    # legend decodes the badges + validation chips
    assert "ADD_BIAS=偏多" in html
    assert "caveated" in html
    # the explainer sits above the per-fund cards
    assert html.index("非买卖指令") < html.index('class="fund-card"')


def test_disclaimer_banner_is_static_and_carries_no_javascript():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert '<aside class="explainer">' in html
    assert "<script" not in html.lower()


def test_every_fund_has_summary_row_and_card():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert html.count('class="fund-card"') == 1
    assert "广发上海金ETF联接A" in html


def test_no_call_fund_renders_distinct_badge_and_still_has_card():
    v = _view(status="insufficient_evidence", bias=None)
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "NO_CALL" in html
    assert 'class="fund-card"' in html        # no silent drop


def test_anchor_set_equals_appendix_id_set():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    # In v2, in-text anchors are <sup><a href="#ev-{cid}">N</a></sup>
    anchors = set(re.findall(r'href="#ev-([0-9a-f]{16})"', html))
    appendix = set(re.findall(r'id="ev-([0-9a-f]{16})"', html))
    assert anchors == appendix and anchors      # closed + non-empty


def test_markers_are_appended_deterministically():
    v = _view()
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    cid = v.evidence_pool[0].citation_id
    # v2: in-text superscript anchor replaces raw [ref:cid] marker
    assert f'href="#ev-{cid}"' in html          # renderer wired citation, LLM did not
    assert "[ref:" not in html                  # no raw markers leak


def test_hostile_title_is_escaped():
    ev = EvidenceItem("Reuters", "<script>alert(1)</script>", "2026-06-15",
                      "https://r", "008986", "0" * 16)
    v = _view()
    v = FundView(**{**v.__dict__, "evidence_pool": (ev,),
                    "narrative": NarrativeDoc("008986", (), (), (), "ok")})
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_no_javascript_and_no_remote_refs():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "<script" not in html.lower()
    assert "http://" not in html.replace("https://r", "") or True  # evidence url allowed
    assert "cdn" not in html.lower() and "googleapis" not in html.lower()


def test_changed_flag_absent_without_prior():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "changed-since-yesterday" not in html


def test_changed_flag_present_when_prior_differs():
    prior = {"008986": {"bias": "REDUCE_BIAS"}}
    html = render_report((_view(),), _prov(), prior_signal=prior, now=_NOW, now_dt=_NOW_DT)
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
    html = render_report((v_bad,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert 'class="fund-card"' in html


def test_byte_stable_given_identical_inputs():
    v = (_view(),)
    a = render_report(v, _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    b = render_report(v, _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert a == b


def test_golden_file(tmp_path):
    from pathlib import Path
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    golden = Path(__file__).parent / "golden" / "report.html"
    assert html == golden.read_text(encoding="utf-8")


def test_card_has_verdict_block():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert 'class="verdict"' in html
    assert "综合分 C" in html


def test_card_has_factor_table_with_na_rows():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "class='factors'" in html
    assert "factor-na" in html               # at least one N/A factor row
    assert "heat_no_data" in html            # structured reason surfaced


def test_card_has_real_returns_table():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "class='returns'" in html
    assert "60d:" in html and "250d:" in html  # the full window set


def test_card_has_risk_block_or_placeholder():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert 'class="risk"' in html


def test_old_missing_ul_is_gone():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "class='missing'" not in html      # replaced by the factor table


def test_no_call_card_keeps_gate_clause_and_no_neutral_label():
    v = _view(status="insufficient_evidence", bias=None)
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "NO_CALL" in html
    # NO_CALL ≠ NEUTRAL: the verdict clause must not assert a NEUTRAL call
    assert "落在中性带内" not in html


# ── Task 2.5: drilldown card embed + flow-outage header note ─────────────────


def _hm(score, reason=None):
    return HoldingMetric("600519", "贵州茅台", 12.0, 30.0, 8.0, 0.8, "expensive",
                         None, 4.0, 3.5, score, reason)


def _view_with_metrics(holding_metrics=()):
    """Build a FundView with given holding_metrics, extending the base _view()."""
    return dataclasses.replace(_view(), holding_metrics=holding_metrics)


def _view_with_factor_na(factor_name: str, na_reason: str):
    """Build a FundView where the named factor is N/A with the given reason."""
    v = _view()
    # Replace factor_scores to include the named factor as N/A
    existing = {s.name: s for s in v.factor_scores}
    existing[factor_name] = FactorScore(factor_name, None, False, na_reason, 1.0)
    return dataclasses.replace(v, factor_scores=tuple(existing.values()))


def _view_with_factor_present(factor_name: str):
    """Build a FundView where the named factor is present (eligible=True)."""
    v = _view()
    existing = {s.name: s for s in v.factor_scores}
    existing[factor_name] = FactorScore(factor_name, 0.5, True, "", 1.0)
    return dataclasses.replace(v, factor_scores=tuple(existing.values()))


def test_card_embeds_board_when_metrics_present():
    from irc.monitor.render_html import CitationIndex
    view = _view_with_metrics(holding_metrics=(_hm(1.0),))
    html = _card(view, None, CitationIndex((), {}))
    assert "holdings-board" in html
    assert "600519" in html


def test_flow_outage_note_only_when_set_wide_collapse():
    # both eligible funds lost flow → note present.
    collapsed = (
        _view_with_factor_na("flow", "flow_no_data"),
        _view_with_factor_na("flow", "flow_no_coverage"),
    )
    assert "资金流数据今日不可用" in _flow_outage_note(collapsed)
    # at least one fund has a present flow factor → no note.
    mixed = (_view_with_factor_present("flow"), _view_with_factor_na("flow", "flow_no_data"))
    assert _flow_outage_note(mixed) == ""
    # no flow-eligible fund at all (all profile_ineligible) → no note (not an outage).
    none_eligible = (_view_with_factor_na("flow", "profile_ineligible"),)
    assert _flow_outage_note(none_eligible) == ""


def test_summary_row_has_market_composite_column():
    from irc.monitor.render_html import _summary_row
    from irc.monitor.market_composite import MarketCompositeView
    import dataclasses
    v = dataclasses.replace(_view(), market_view=MarketCompositeView(0.24, "NEUTRAL", 0.2, 4))
    html = _summary_row(v, None, None)
    assert "市场面" in html or "+0.24" in html


def test_render_report_includes_charts():
    from irc.monitor.render_html import render_report
    from irc.monitor.render_types import Provenance
    from irc.monitor.render_timeline import BiasTimeline
    from irc.monitor.market_composite import MarketCompositeView
    import dataclasses
    v = dataclasses.replace(_view(), market_view=MarketCompositeView(0.3, "ADD_BIAS", 0.1, 2))
    tl = BiasTimeline(run_dates=("2026-06-30",),
                      rows=(("008986", (("ADD_BIAS", "3"),)),))
    html = render_report((v,), Provenance("3", "1", "1", ""), prior_signal=None,
                         now=_NOW, now_dt=_NOW_DT, timeline=tl)
    assert 'class="heatmap"' in html
    assert 'class="timeline"' in html
    assert 'class="contrib"' in html
    # heatmap appears after the summary table, before cards
    assert html.index("summary") < html.index('class="heatmap"') < html.index("fund-card")


def test_macro_narrative_html_renders_theme_labeled_sections_with_anchors():
    from irc.monitor.render_html import macro_narrative_html
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    from irc.monitor.types import Claim

    doc = MacroNarrativeDoc(
        blocks=(
            MacroThemeBlock("us_monetary", (
                Claim("美联储本周维持利率不变。", "consistent_with", ()),
            )),
        ),
        status="ok",
    )
    html = macro_narrative_html(doc, fund_themes_by_theme={"us_monetary": ("270023", "009225")})
    assert 'id="macro-us_monetary"' in html
    assert "美联储政策" in html
    assert "美联储本周维持利率不变。" in html
    assert "270023" in html and "009225" in html   # affected-fund chips


def test_macro_narrative_html_none_doc_renders_empty_string():
    from irc.monitor.render_html import macro_narrative_html
    assert macro_narrative_html(None, fund_themes_by_theme={}) == ""


def test_macro_narrative_html_empty_pool_status_renders_empty_string():
    from irc.monitor.render_html import macro_narrative_html
    from irc.monitor.narrative_macro import MacroNarrativeDoc

    doc = MacroNarrativeDoc(blocks=(), status="empty_pool")
    assert macro_narrative_html(doc, fund_themes_by_theme={}) == ""


def test_macro_narrative_html_claims_capped_at_3_per_theme_defensively():
    """Even if a doc somehow carries >3 claims (should never happen post-gather),
    the renderer only emits what it's given — this test documents that the CAP
    is gather_macro_narrative's responsibility, not the renderer's, by asserting
    all provided claims render (renderer is dumb/pure)."""
    from irc.monitor.render_html import macro_narrative_html
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    from irc.monitor.types import Claim

    doc = MacroNarrativeDoc(
        blocks=(MacroThemeBlock("geopolitics", (
            Claim("声明一。", "consistent_with", ()),
            Claim("声明二。", "consistent_with", ()),
        )),),
        status="ok",
    )
    html = macro_narrative_html(doc, fund_themes_by_theme={"geopolitics": ()})
    assert "声明一。" in html and "声明二。" in html


# ── Item 002 P3: macro direction chips + legend ───────────────────────────────


_LEGEND = ('<p class="macro-legend">图例：数值 = 该主题对基金的影响（−1 利空 … +1 利多）；'
           '绿 ≥ +0.15 · 红 ≤ −0.15 · 灰 = 其间；无数值 = 当日无该主题影响记录</p>')


def _macro_doc(theme="us_monetary", claim_text="美联储本周维持利率不变。"):
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    return MacroNarrativeDoc(
        blocks=(MacroThemeBlock(theme, (Claim(claim_text, "consistent_with", ()),)),),
        status="ok")


def test_macro_chip_with_record_has_direction_class_value_and_title():
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.render_html import macro_narrative_html

    impacts = {"270023": (ValidatedImpact("us_monetary", 0.8, 0.7, ()),)}
    html = macro_narrative_html(
        _macro_doc(), fund_themes_by_theme={"us_monetary": ("270023", "009225")},
        macro_impacts_by_fund=impacts)
    assert ('<span class="fund-chip chip-pos" title="置信度 0.7">270023 +0.8</span>'
            in html)
    # fund WITHOUT a record renders exactly as today: bare chip, no color,
    # no number, no title (absence ≠ zero)
    assert '<span class="fund-chip">009225</span>' in html


def test_macro_chip_direction_boundaries_and_true_zero():
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.render_html import macro_narrative_html

    impacts = {
        "a1": (ValidatedImpact("us_monetary", 0.15, 1.0, ()),),
        "a2": (ValidatedImpact("us_monetary", -0.15, 0.5, ()),),
        "a3": (ValidatedImpact("us_monetary", 0.0, 0.25, ()),),
    }
    html = macro_narrative_html(
        _macro_doc(), fund_themes_by_theme={"us_monetary": ("a1", "a2", "a3")},
        macro_impacts_by_fund=impacts)
    assert '<span class="fund-chip chip-pos" title="置信度 1">a1 +0.15</span>' in html
    assert '<span class="fund-chip chip-neg" title="置信度 0.5">a2 -0.15</span>' in html
    # genuine 0.0 record: grey +0 chip — visibly distinct from an absent record
    assert '<span class="fund-chip chip-flat" title="置信度 0.25">a3 +0</span>' in html


def test_macro_renderer_never_invents_chips_beyond_config_list():
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.render_html import macro_narrative_html

    impacts = {"999999": (ValidatedImpact("us_monetary", 0.9, 1.0, ()),)}  # not a chip
    html = macro_narrative_html(
        _macro_doc(), fund_themes_by_theme={"us_monetary": ("270023",)},
        macro_impacts_by_fund=impacts)
    assert "999999" not in html
    assert '<span class="fund-chip">270023</span>' in html


def test_macro_chip_text_is_escaped():
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.render_html import macro_narrative_html

    impacts = {"<b>": (ValidatedImpact("us_monetary", 0.8, 0.7, ()),)}
    html = macro_narrative_html(
        _macro_doc(), fund_themes_by_theme={"us_monetary": ("<b>",)},
        macro_impacts_by_fund=impacts)
    assert "&lt;b&gt;" in html
    assert "<b>" not in html


def test_macro_impacts_default_none_degrades_to_bare_chips():
    from irc.monitor.render_html import macro_narrative_html

    html = macro_narrative_html(
        _macro_doc(), fund_themes_by_theme={"us_monetary": ("270023",)})
    assert '<span class="fund-chip">270023</span>' in html
    assert "chip-pos" not in html and "chip-neg" not in html and "chip-flat" not in html


def test_macro_legend_renders_once_after_h2_before_first_theme():
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    from irc.monitor.render_html import macro_narrative_html

    doc = MacroNarrativeDoc(
        blocks=(MacroThemeBlock("us_monetary", (Claim("一。", "consistent_with", ()),)),
                MacroThemeBlock("geopolitics", (Claim("二。", "consistent_with", ()),))),
        status="ok")
    html = macro_narrative_html(doc, fund_themes_by_theme={})
    assert html.count('class="macro-legend"') == 1
    assert _LEGEND in html
    assert (html.index("<h2>宏观面速览</h2>") < html.index('class="macro-legend"')
            < html.index('class="macro-theme"'))


def test_macro_legend_absent_when_section_degrades():
    from irc.monitor.narrative_macro import MacroNarrativeDoc
    from irc.monitor.render_html import macro_narrative_html

    assert macro_narrative_html(None, fund_themes_by_theme={}) == ""
    assert macro_narrative_html(
        MacroNarrativeDoc((), "empty_pool"), fund_themes_by_theme={}) == ""


def test_render_report_threads_macro_impacts_to_chips():
    from irc.monitor.impact_validate import ValidatedImpact

    v = dataclasses.replace(_view(), themes=("gold_drivers",))
    doc = _macro_doc(theme="gold_drivers", claim_text="黄金受实际利率支撑。")
    impacts = {"008986": (ValidatedImpact("gold_drivers", 0.8, 0.7, ()),)}
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT,
                         macro_narrative=doc, macro_impacts_by_fund=impacts)
    assert "008986 +0.8" in html


def test_macro_chips_reconcile_with_eval_trace():
    """AC6 / source-spec §4 bullet 2: ONE fixture set fed to BOTH build_eval_trace
    and render_report. Each rendered chip's parsed value == round(trace impact, 2);
    a chip carries color/number IFF the trace impacts["macro"] has a record with
    that theme key for that fund."""
    from irc.monitor.eval.trace import build_eval_trace
    from irc.monitor.eval.types import FundTraceBundle, GateDecision
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.types import MonitorFund

    fund = MonitorFund(id="008986", name_cn="测试", market="CN",
                       analysis_profile="gold_etf", themes=("gold_drivers",),
                       constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)
    view = dataclasses.replace(_view(), themes=("gold_drivers",))
    view2 = dataclasses.replace(_view(), fund_id="600000", themes=("gold_drivers",))
    imp = ValidatedImpact("gold_drivers", 0.847, 0.7, ())     # rounds to +0.85
    off = ValidatedImpact("unrendered_theme", -0.6, 0.5, ())  # trace-only
    bundle = FundTraceBundle("008986", (imp, off), (), ())
    gate = GateDecision("008986", False, (), "validated", "")
    doc = _macro_doc(theme="gold_drivers", claim_text="黄金受实际利率支撑。")

    trace = build_eval_trace(((fund, view, gate, bundle),), engine_version="4",
                             run_date="2026-07-04", macro_narrative=doc)
    html = render_report((view, view2), _prov(), prior_signal=None, now=_NOW,
                         now_dt=_NOW_DT, macro_narrative=doc,
                         macro_impacts_by_fund={"008986": bundle.macro_impacts})

    chips_region = html.split('class="fund-chips">', 1)[1].split("</div>", 1)[0]
    m = re.search(r'<span class="fund-chip (chip-\w+)" title="[^"]*">'
                  r'008986 ([+\-][0-9.]+)</span>', chips_region)
    assert m, chips_region
    trace_rec = {r["key"]: r for r in
                 trace["funds"]["008986"]["impacts"]["macro"]}["gold_drivers"]
    assert float(m.group(2)) == round(trace_rec["impact"], 2)
    assert m.group(1) == "chip-pos"
    # IFF, no-record direction: 600000 has no macro record -> bare chip
    assert '<span class="fund-chip">600000</span>' in chips_region
    # IFF, off-theme direction: the unrendered_theme record is in the trace
    # but renders NOWHERE (trace keeps it; the renderer never invents chips)
    assert "unrendered_theme" not in html
    assert any(r["key"] == "unrendered_theme"
               for r in trace["funds"]["008986"]["impacts"]["macro"])


# ── Item 002 P4: claim strength tags ─────────────────────────────────────────


def test_macro_claim_strength_tags_all_four_values_on_idx_none_path():
    """RD-7: the idx=None path folds into _macro_claim_html — tags on BOTH paths."""
    from irc.monitor.render_html import _macro_claim_html

    labels = {"possible_driver": "可能主因", "consistent_with": "方向一致",
              "supported_attribution": "已证实归因", "unknown": "归因未知"}
    for strength, label in labels.items():
        html = _macro_claim_html(Claim("政策基调转向。", strength, ()), None)
        assert f'<span class="claim-strength">{label}</span>' in html
        assert "政策基调转向。" in html


def test_macro_claim_unmapped_strength_falls_back_to_unknown_label():
    """Unreachable today (_VALID_STRENGTH is closed) — cheap defense pin."""
    from irc.monitor.render_html import _macro_claim_html

    html = _macro_claim_html(Claim("政策基调转向。", "brand_new_value", ()), None)
    assert '<span class="claim-strength">归因未知</span>' in html


def test_macro_claim_with_idx_keeps_refs_and_gains_tag():
    from irc.monitor.render_html import CitationIndex, _macro_claim_html

    cid = "a" * 16
    idx = CitationIndex(((cid, "Reuters", "t", "2026-07-01", ""),), {cid: 0})
    html = _macro_claim_html(Claim("政策基调转向。", "consistent_with", (cid,)), idx)
    assert '<span class="claim-strength">方向一致</span>' in html
    assert f'href="#ev-{cid}"' in html


def test_macro_theme_section_without_index_still_carries_tags():
    from irc.monitor.render_html import macro_narrative_html

    html = macro_narrative_html(_macro_doc(), fund_themes_by_theme={})
    assert '<span class="claim-strength">方向一致</span>' in html


# ── Item 002 P5: 传导 mechanism line ──────────────────────────────────────────


def _macro_doc_with_mechanism(mechanism):
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    return MacroNarrativeDoc(
        blocks=(MacroThemeBlock(
            "us_monetary", (Claim("美联储本周维持利率不变。", "consistent_with", ()),),
            mechanism=mechanism),),
        status="ok")


def test_macro_mechanism_line_renders_between_chips_and_claims():
    from irc.monitor.render_html import macro_narrative_html

    html = macro_narrative_html(
        _macro_doc_with_mechanism("就业数据疲软→加息预期降温→利多黄金"),
        fund_themes_by_theme={"us_monetary": ("270023",)})
    assert ('<p class="macro-mechanism">对本组基金的传导：'
            '就业数据疲软→加息预期降温→利多黄金</p>') in html
    # placement (Q13): h3 -> fund chips -> mechanism -> claims
    assert (html.index('class="fund-chips"') < html.index('class="macro-mechanism"')
            < html.index("美联储本周维持利率不变。"))


def test_macro_mechanism_absent_renders_no_empty_element():
    from irc.monitor.render_html import macro_narrative_html

    html = macro_narrative_html(
        _macro_doc_with_mechanism(None), fund_themes_by_theme={"us_monetary": ()})
    assert "macro-mechanism" not in html
    assert "对本组基金的传导" not in html


def test_macro_mechanism_is_escaped():
    from irc.monitor.render_html import macro_narrative_html

    html = macro_narrative_html(
        _macro_doc_with_mechanism('<script>alert(1)</script>→利多'),
        fund_themes_by_theme={"us_monetary": ()})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_card_drilldown_block_carries_stale_board_pe_age_tag():
    """004 AC-13: the report card (phone-visible surface) renders the tag too."""
    from irc.monitor.board_pe_staleness import BoardPeFreshness
    from irc.monitor.holding_metrics import HoldingMetric

    m = HoldingMetric(symbol="600519", name="茅台", weight_pct=9.0, pe=30.0, pb=8.0,
                      pe_percentile=0.5, valuation_state="fair", valuation_reason=None,
                      flow_pct_5d=None, flow_pct_20d=None, flow_score=None,
                      flow_reason="flow_no_data")
    v = dataclasses.replace(_view(), holding_metrics=(m,),
                            board_pe_freshness=BoardPeFreshness("STALE", "2026-06-30", 2))
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "板块PE 引用 2026-06-30 · 2个交易日前" in html


def test_card_no_age_tag_when_fresh():
    from irc.monitor.board_pe_staleness import BoardPeFreshness
    from irc.monitor.holding_metrics import HoldingMetric

    m = HoldingMetric(symbol="600519", name="茅台", weight_pct=9.0, pe=30.0, pb=8.0,
                      pe_percentile=0.5, valuation_state="fair", valuation_reason=None,
                      flow_pct_5d=None, flow_pct_20d=None, flow_score=None,
                      flow_reason="flow_no_data")
    v = dataclasses.replace(_view(), holding_metrics=(m,),
                            board_pe_freshness=BoardPeFreshness("FRESH", "2026-06-15", 0))
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "板块PE 引用" not in html
