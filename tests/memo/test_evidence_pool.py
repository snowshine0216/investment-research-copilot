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
    assert "cost_grade=76" in blob  # renamed from valuation_cost to avoid
    # collision with the price-percentile axis carried in 状态=A/B/C/D
    assert "valuation_cost=" not in blob  # display rename — JSON keeps the old key
    assert "risk=42" in blob        # other factors keep their names
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


# ── Item 007 D1a — citation line emission ─────────────────────────────────────

import re


def _evidence(
    *, type_="filing", source="x", url="https://x", date="2024-04-15",
    summary="x", scope="constituent", citation_kind="data",
    owner="005827", parent="005827", constituent_key="600519",
    weight=8.2,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _op_row(
    *, iid="005827", thesis_evidence=(),
    opportunity_state="core_dca",
):
    """Dict-form op row (matches opportunity_report.json shape)."""
    return {
        "instrument_id": iid,
        "name_cn": "易方达蓝筹精选",
        "asset_class": "cn_equity_fund",
        "valuation_state": "fair",
        "heat_state": "normal",
        "thesis_state": "intact",
        "product_quality_state": "strong",
        "opportunity_state": opportunity_state,
        "opportunity_reason": "",
        "thesis_evidence": thesis_evidence,
    }


def test_build_evidence_pool_emits_ref_markers() -> None:
    """AC1 — [ref:...] markers appear with 16-hex citation_id."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence()
    row = _op_row(thesis_evidence=(ev,))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1, "buy_method": "limit"}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert re.search(r"\[ref:[0-9a-f]{16}\]", joined), \
        f"expected [ref:...] in pool, got:\n{joined}"


def test_build_evidence_pool_emits_stock_marker_for_constituent_scope() -> None:
    """AC2 — [stock:600519] appears for scope=constituent entries; not for instrument scope."""
    from irc.memo.evidence_pool import build_evidence_pool
    constituent_ev = _evidence(scope="constituent", constituent_key="600519")
    instrument_ev = _evidence(scope="instrument", constituent_key=None,
                              source="nav", type_="snapshot")
    row = _op_row(thesis_evidence=(constituent_ev, instrument_ev))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert "[stock:600519]" in joined
    # Locked spacing: [stock:...] [ref:...] with exactly one space.
    assert re.search(r"\[stock:600519\] \[ref:[0-9a-f]{16}\]", joined)
    # The instrument-scope entry must NOT carry [stock:...] (no constituent_key).
    instrument_line_re = re.compile(
        r"^(?!\[stock:)\[ref:[0-9a-f]{16}\] snapshot ", re.MULTILINE,
    )
    assert instrument_line_re.search(joined) is not None


def test_build_evidence_pool_rejects_old_literal_ref_format() -> None:
    """AC3 regression — `[ref:filing:600519]` style explicitly rejected."""
    from irc.memo.evidence_pool import build_evidence_pool
    row = _op_row(thesis_evidence=(_evidence(),))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    # No non-hex chars after `[ref:` allowed (the colon-prefixed literal form).
    assert not re.search(r"\[ref:[a-z_]+:", joined)


def test_build_evidence_pool_omits_empty_url_parenthetical() -> None:
    """AC4 — url=="" → no trailing `()` in the rendered line."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence(url="", source="ann", type_="news",
                   summary="[r1] 公告 / dividend")
    row = _op_row(thesis_evidence=(ev,))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    # No trailing `()` empty parenthetical.
    assert not re.search(r"\(\s*\)\s*$", joined, re.MULTILINE)


def test_build_evidence_pool_watchlist_excluded() -> None:
    """AC6 — small_watch rows whose iid is NOT in plan_trades contribute no pool lines."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence()
    row = _op_row(iid="999999", thesis_evidence=(ev,),
                  opportunity_state="small_watch")
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[],  # no trade for 999999
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert "999999" not in joined


def test_build_evidence_pool_renders_top_3_only() -> None:
    """AC1 quantitative — 5 evidence entries → top 3 by select_citations()."""
    from irc.memo.evidence_pool import build_evidence_pool
    # 5 entries with distinct citation_ids (different dates differentiate).
    evs = tuple(
        _evidence(date=f"2024-04-{d:02d}", url=f"https://x/{d}",
                  citation_kind="data" if d % 2 == 0 else "information",
                  scope="constituent",
                  constituent_key=f"60051{d}")
        for d in range(1, 6)
    )
    row = _op_row(thesis_evidence=evs)
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    ref_matches = re.findall(r"\[ref:[0-9a-f]{16}\]", joined)
    # Exactly 3 ref markers from this row.
    assert len(ref_matches) == 3, \
        f"expected 3 [ref:...] markers, got {len(ref_matches)}:\n{joined}"
