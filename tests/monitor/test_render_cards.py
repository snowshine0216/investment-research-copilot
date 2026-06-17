from irc.monitor.types import SignalRecord, NarrativeDoc, Claim
from irc.monitor.render_cards import verdict_block_html, risk_block_html, narrative_sections_html


def _rec(status="ok", bias="ADD_BIAS", c=0.5563, conf=0.9, fams=("price-momentum", "news"),
         aw=0.8, div=()):
    return SignalRecord(
        fund_id="x", status=status, bias=bias, composite=c, signal_confidence=conf,
        available_weight=aw, present_families=fams, contributions=(), divergence_codes=div,
    )


def _narr(sig=(), risk=(), pa=(), status="ok"):
    return NarrativeDoc("x", pa, sig, risk, status)


def test_ok_add_bias_clause_states_band_relationship():
    html = verdict_block_html(_rec(bias="ADD_BIAS", c=0.5563), _narr())
    assert "0.5563" in html
    assert "偏多带" in html and "ADD_BIAS" in html
    assert "偏多倾向" in html              # neutral bias gloss, not a trade verb
    assert "买入阈值" not in html          # no executable buy-order wording


def test_ok_reduce_bias_clause():
    html = verdict_block_html(_rec(bias="REDUCE_BIAS", c=-0.6), _narr())
    assert "偏空带" in html and "REDUCE_BIAS" in html
    assert "偏空倾向" in html
    assert "卖出阈值" not in html


def test_ok_neutral_clause_says_dead_band():
    html = verdict_block_html(_rec(bias="NEUTRAL", c=0.05), _narr())
    assert "中性带" in html and "NEUTRAL" in html


def test_insufficient_evidence_clause_names_gate_and_no_call():
    html = verdict_block_html(_rec(status="insufficient_evidence", bias=None, fams=("news",), aw=0.3), _narr())
    assert "insufficient_evidence" in html and "NO_CALL" in html
    assert "0.30" in html  # available_weight surfaced


def test_low_confidence_clause_names_confidence_and_no_call():
    html = verdict_block_html(_rec(status="low_confidence", bias=None, conf=0.3), _narr())
    assert "low_confidence" in html and "NO_CALL" in html
    assert "0.3" in html  # signal_confidence surfaced


def test_minimax_comment_renders_lead_claim_with_ref():
    narr = _narr(sig=(Claim("动能强劲", "consistent_with", ("a" * 16,)),
                      Claim("第二条不应出现", "consistent_with", ("b" * 16,))))
    html = verdict_block_html(_rec(), narr)
    assert "[ref:" + "a" * 16 + "]" in html
    assert "第二条不应出现" not in html  # capped to lead claim


def test_degraded_narrative_shows_note_not_comment():
    html = verdict_block_html(_rec(), _narr(status="schema_invalid: x"))
    assert "narrative" in html.lower()
    assert "schema_invalid" in html


def test_risk_block_maps_divergence_codes_to_caveats():
    html = risk_block_html(_rec(div=("trend_valuation_conflict",)), _narr())
    assert "趋势与估值背离" in html


def test_risk_block_includes_risk_claims_with_refs():
    narr = _narr(risk=(Claim("回撤风险上升", "consistent_with", ("c" * 16,)),))
    html = risk_block_html(_rec(), narr)
    assert "回撤风险上升" in html and "[ref:" + "c" * 16 + "]" in html


def test_risk_block_empty_renders_muted_placeholder():
    html = risk_block_html(_rec(div=()), _narr())
    assert "无显著风险信号" in html


def test_narrative_sections_only_price_action():
    narr = _narr(pa=(Claim("价格上行", "consistent_with", ()),),
                 sig=(Claim("不应在此", "consistent_with", ()),),
                 risk=(Claim("也不应在此", "consistent_with", ()),))
    html = narrative_sections_html(narr)
    assert "价格上行" in html
    assert "不应在此" not in html  # signal_rationale lives in verdict block
    assert "也不应在此" not in html  # risk lives in risk block
