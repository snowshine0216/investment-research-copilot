from __future__ import annotations

from irc.memo.evidence_pool import build_evidence_pool


def test_build_evidence_pool_includes_numeric_facts_per_instrument():
    opportunity_rows = [{
        "instrument_id": "518880",
        "name_cn": "华安黄金ETF",
        "valuation_state": "cheap",
        "heat_state": "normal",
        "thesis_state": "intact",
        "product_quality_state": "strong",
        "opportunity_state": "core_dca",
        "opportunity_reason": "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。",
        "evidence_gaps": [],
    }]
    scoring_rows = [{
        "instrument_id": "518880",
        "composite_score": 51.8,
        "factor_breakdown": {
            "valuation_cost": {"score": 76.0, "components": {"expense_score": 76.0}},
            "risk": {"score": 41.6, "components": {"drawdown": 47.9, "vol": 70.5}},
            "quality": {"score": 75.3, "components": {"tenure": 60.0, "aum_stability": 83.3}},
            "macro_fit": {"score": 35.0, "components": {"llm_score": 35.0}},
            "thesis_news": {"score": 50.0, "components": {}},
        },
    }]
    plan_trades = [{
        "target": "518880",
        "target_weight": 0.564,
        "role": "core_gold_hedge",
        "asset_class": "gold",
    }]
    pool = build_evidence_pool(
        opportunity_rows=opportunity_rows,
        scoring_rows=scoring_rows,
        plan_trades=plan_trades,
        gold_regime={"regime": "range_bound", "zone": "pause", "tilt": "neutral_minus"},
    )
    blob = "\n".join(pool)
    assert "518880" in blob
    assert "华安黄金ETF" in blob
    assert "51.8" in blob          # composite_score
    assert "76" in blob             # valuation_cost
    assert "core_dca" in blob       # opportunity state
    assert "56.4%" in blob          # target_weight
    assert "range_bound" in blob    # gold regime mixed in


def test_build_evidence_pool_gold_regime_first():
    pool = build_evidence_pool(
        opportunity_rows=[],
        scoring_rows=[],
        plan_trades=[],
        gold_regime={"regime": "range_bound", "zone": "pause", "tilt": "neutral_minus"},
    )
    assert len(pool) == 1
    assert "gold" in pool[0].lower()
    assert "range_bound" in pool[0]


def test_build_evidence_pool_dedupes_instruments():
    opportunity_rows = [
        {"instrument_id": "518880", "name_cn": "华安黄金ETF",
         "valuation_state": "cheap", "heat_state": "normal",
         "thesis_state": "intact", "product_quality_state": "strong",
         "opportunity_state": "core_dca", "opportunity_reason": "good", "evidence_gaps": []},
    ]
    plan_trades = [
        {"target": "518880", "target_weight": 0.5, "role": "core", "asset_class": "gold"},
        {"target": "518880", "target_weight": 0.5, "role": "core", "asset_class": "gold"},  # dup
    ]
    pool = build_evidence_pool(
        opportunity_rows=opportunity_rows,
        scoring_rows=[],
        plan_trades=plan_trades,
        gold_regime=None,
    )
    # Only one instrument line despite duplicate trade entry
    instrument_lines = [l for l in pool if "518880" in l]
    assert len(instrument_lines) == 1
