from __future__ import annotations

from irc.decision.gates import decide_row
from irc.decision.report import (
    _holdings_action_section,
    _summary,
    compose_decision_report,
    render_decision_markdown,
)


def _scoring() -> dict[str, object]:
    return {
        "scores": [
            {
                "instrument_id": "518850",
                "asset_class": "gold",
                "action": "watch",
                "conviction": "low",
                "data_completeness": 0.0,
                "missing_data": ["expense_ratio"],
            },
            {
                "instrument_id": "050025",
                "asset_class": "us_etf",
                "action": "buy_candidate",
                "conviction": "med",
                "data_completeness": 1.0,
                "missing_data": [],
                "qdii_premium_pct": 0.05,
            },
        ]
    }


def test_compose_decision_report_blocks_when_pipeline_halted_and_weights_invalid() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring=_scoring(),
        allocation={
            "selected_instruments": [
                {"instrument_id": "518850", "target_weight": 0.5},
                {"instrument_id": "050025", "target_weight": 0.5},
            ],
            "diagnostics": {"total_weight": 3.0},
        },
        trade_plan={
            "trades": [
                {"target": "518850", "venue_compatible": False, "proxy_id": None},
                {"target": "050025", "venue_compatible": True, "proxy_id": None},
            ]
        },
        memo_traceability={"n_refs_quoted_verbatim": 0},
        pipeline_halted=True,
    )

    assert report["overall_status"] == "blocked"
    assert "pipeline_halted" in report["blocking_reasons"]
    assert "target_weights_invalid" in report["blocking_reasons"]
    assert report["summary"]["actionable_buy_count"] == 0
    assert report["summary"]["blocked_count"] == 2


def test_compose_decision_report_allows_actionable_buy_when_all_gates_clear() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [_scoring()["scores"][1]]},
        allocation={
            "selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}],
            "diagnostics": {"total_weight": 1.0},
        },
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    assert report["overall_status"] == "ok"
    assert report["rows"][0]["decision_status"] == "actionable_buy"


def test_markdown_report_starts_with_clear_verdict() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring=_scoring(),
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 3.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 0},
        pipeline_halted=True,
    )

    markdown = render_decision_markdown(report)

    assert markdown.startswith("# Decision Report 2026-05-11")
    assert "No buy/sell decision is supported today." in markdown
    assert "pipeline_halted" in markdown


def test_compose_decision_report_empty_scores_returns_ok_no_rows() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": []},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    assert report["overall_status"] == "ok"
    assert report["rows"] == []
    assert report["summary"]["actionable_buy_count"] == 0


def test_build_rows_handles_score_with_no_matching_trade() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "UNKNOWN", "asset_class": "gold", "action": "watch", "conviction": "low", "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    assert len(report["rows"]) == 1
    assert report["rows"][0]["venue_status"] == "unknown"


def test_render_decision_markdown_ok_verdict_text() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": [], "qdii_premium_pct": 0.05}]},
        allocation={"selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    markdown = render_decision_markdown(report)

    assert "At least one instrument passed all decision-readiness gates" in markdown


def test_render_decision_markdown_ok_zero_buys_shows_review_row_statuses() -> None:
    """ok overall_status with no actionable_buy rows must not say 'passed' falsely."""
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "watch", "conviction": "low", "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    assert report["overall_status"] == "ok"
    assert report["summary"]["actionable_buy_count"] == 0
    markdown = render_decision_markdown(report)
    assert "Review per-row statuses" in markdown
    assert "At least one instrument passed" not in markdown


def test_compose_decision_report_pipeline_incomplete_when_most_scores_lack_action() -> None:
    scores = [
        {"instrument_id": "A", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "B", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "C", "asset_class": "gold", "action": "watch", "conviction": "low", "data_completeness": 1.0, "missing_data": []},
    ]
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": scores},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    assert report["pipeline_incomplete"] is True
    assert report["overall_status"] == "blocked"
    assert "pipeline_halted" in report["blocking_reasons"]


def test_blocking_section_no_reasons_shows_no_blocking_message() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": [], "qdii_premium_pct": 0.05}]},
        allocation={"selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    markdown = render_decision_markdown(report)

    assert "No system-level blocking reason detected." in markdown
    assert "## Gates Passed" in markdown
    assert "## Why Blocked" not in markdown


# ---------------------------------------------------------------------------
# _scores_missing_action: exactly 50% boundary (gap: report:69, threshold > 0.5)
# ---------------------------------------------------------------------------

def test_pipeline_not_incomplete_at_exactly_50_percent_missing() -> None:
    """Exactly 50% missing action must NOT trigger pipeline_incomplete (threshold is strict > 0.5)."""
    scores = [
        {"instrument_id": "A", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "B", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "C", "asset_class": "gold", "action": "watch", "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "D", "asset_class": "gold", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": []},
    ]
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": scores},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    # 2/4 = 50.0%, which is NOT > 0.5, so pipeline should NOT be flagged as incomplete
    assert report["pipeline_incomplete"] is False
    assert report["overall_status"] == "ok"


def test_pipeline_incomplete_just_above_50_percent_missing() -> None:
    """51%+ missing action triggers pipeline_incomplete."""
    scores = [
        {"instrument_id": "A", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "B", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "C", "asset_class": "gold", "action": None, "conviction": "low", "data_completeness": 1.0, "missing_data": []},
        {"instrument_id": "D", "asset_class": "gold", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": []},
    ]
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": scores},
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1},
        pipeline_halted=False,
    )

    # 3/4 = 75% > 0.5 → incomplete
    assert report["pipeline_incomplete"] is True
    assert "pipeline_halted" in report["blocking_reasons"]


# ---------------------------------------------------------------------------
# Coverage gate: legacy schema, vacuous truth, and narrative_only cases
# ---------------------------------------------------------------------------

def test_coverage_vacuous_truth_when_no_refs_provided() -> None:
    """n_refs_provided=0 (empty evidence pool) must not block via memo_narrative_only."""
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": [], "qdii_premium_pct": 0.05}]},
        allocation={"selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"n_refs_provided": 0, "n_refs_quoted_verbatim": 0, "n_refs": 0},
        pipeline_halted=False,
    )
    assert report["overall_status"] == "ok"
    assert "memo_narrative_only" not in report["blocking_reasons"]


def test_coverage_legacy_schema_does_not_block() -> None:
    """Legacy memo_traceability.json (no n_refs_quoted_verbatim key) must not block decisions."""
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": [], "qdii_premium_pct": 0.05}]},
        allocation={"selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"coverage_ratio": 0.0, "n_refs": 1.0, "n_covered": 0.0},
        pipeline_halted=False,
    )
    assert report["overall_status"] == "ok"
    assert "memo_narrative_only" not in report["blocking_reasons"]


def test_coverage_narrative_only_when_refs_provided_but_none_quoted() -> None:
    """Refs provided but none quoted verbatim → memo_narrative_only → blocked."""
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": [], "qdii_premium_pct": 0.05}]},
        allocation={"selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"n_refs_provided": 3, "n_refs_quoted_verbatim": 0, "n_refs": 3},
        pipeline_halted=False,
    )
    assert "memo_narrative_only" in report["blocking_reasons"]
    assert report["overall_status"] == "blocked"


def _drow(**overrides):
    base = dict(
        instrument_id="510300",
        instrument_name="沪深300ETF",
        asset_class="cn_etf",
        score_action="watch",
        decision_status="review_sell_later",
        portfolio_action="trim_review",
        conviction="med",
        data_completeness=1.0,
        missing_data=[],
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
        blocking_reasons=[],
        reason="",
        next_step="",
        watch_reason=None,
        target_weight=0.05,
        current_weight=0.08,
        weight_delta=0.03,
        is_holding=True,
        role="",
    )
    base.update(overrides)
    return base


def test_summary_counts_sell_actions() -> None:
    rows = [
        _drow(portfolio_action="trim_review"),
        _drow(portfolio_action="exit_review"),
        _drow(portfolio_action="review"),
        _drow(portfolio_action="review"),
        _drow(portfolio_action="no_trade", decision_status="watch_only"),
    ]
    summary = _summary(rows)
    assert summary["trim_count"] == 1
    assert summary["exit_count"] == 1
    assert summary["review_count"] == 2
    assert "sell_count" not in summary
    # Existing keys preserved (additive-only).
    assert "actionable_buy_count" in summary
    assert "watch_count" in summary
    assert "avoid_count" in summary
    assert "blocked_count" in summary


def test_holdings_action_section_renders_held_sell_rows() -> None:
    rows = [_drow(portfolio_action="trim_review")]
    lines = _holdings_action_section(rows)
    text = "\n".join(lines)
    assert "## 持仓行动 / Sell · Trim · Review" in text
    assert "510300" in text
    assert "trim_review" in text
    # Δpp rendered as percentage points: 0.03 -> +3.0
    assert "+3.0" in text


def test_holdings_action_section_empty_state() -> None:
    rows = [_drow(portfolio_action="no_trade", decision_status="watch_only", is_holding=False)]
    lines = _holdings_action_section(rows)
    assert "（无持仓调整建议）" in "\n".join(lines)


def test_holdings_action_section_excludes_non_holdings() -> None:
    # AC7 at the renderer: a non-holding with a stray sell action does not appear.
    rows = [_drow(portfolio_action="trim_review", is_holding=False)]
    lines = _holdings_action_section(rows)
    assert "（无持仓调整建议）" in "\n".join(lines)


def test_markdown_contains_holdings_section_above_blocked() -> None:
    report = {
        "date": "2026-06-10",
        "overall_status": "ok",
        "blocking_reasons": [],
        "summary": _summary([_drow(portfolio_action="trim_review")]),
        "rows": [_drow(portfolio_action="trim_review")],
    }
    md = render_decision_markdown(report)
    assert "## 持仓行动 / Sell · Trim · Review" in md
    holdings_idx = md.index("## 持仓行动")
    blocked_idx = md.index("## Blocked — fixable today")
    assert holdings_idx < blocked_idx


# P0-1: round-trip test — a real decide_row-produced dict preserves is_holding
# and flows into _holdings_action_section (not hand-built dicts).
def test_decide_row_round_trip_is_holding_true() -> None:
    """is_holding=True from decide_row must survive to_dict() and be visible
    in the _holdings_action_section renderer (P0-1 fix)."""
    row = decide_row(
        score={
            "instrument_id": "510300",
            "asset_class": "cn_etf",
            "action": "watch",
            "conviction": "med",
            "data_completeness": 1.0,
            "missing_data": [],
        },
        allocation_selected=False,
        target_weight_valid=True,
        trade=None,
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        risk_action="exit_review",
        is_holding=True,
        portfolio_weight=0.08,
        target_weight=0.05,
        available_venues=["broker_a"],
        venue_required=["broker_a"],
    )
    # is_holding must be in the dict
    assert row["is_holding"] is True
    assert row["portfolio_action"] == "exit_review"
    # The renderer must pick up this row (not empty section)
    lines = _holdings_action_section([row])
    text = "\n".join(lines)
    assert "510300" in text
    assert "exit_review" in text


def test_decide_row_round_trip_is_holding_false_excluded() -> None:
    """is_holding=False must not appear in the holdings-action section."""
    row = decide_row(
        score={
            "instrument_id": "510300",
            "asset_class": "cn_etf",
            "action": "watch",
            "conviction": "med",
            "data_completeness": 1.0,
            "missing_data": [],
        },
        allocation_selected=False,
        target_weight_valid=True,
        trade=None,
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        risk_action="trim_review",
        is_holding=False,
        available_venues=["broker_a"],
        venue_required=["broker_a"],
    )
    assert row["is_holding"] is False
    assert row["portfolio_action"] == "no_trade"
    lines = _holdings_action_section([row])
    assert "（无持仓调整建议）" in "\n".join(lines)
