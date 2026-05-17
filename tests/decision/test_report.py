from __future__ import annotations

from irc.decision.report import compose_decision_report, render_decision_markdown


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
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": []}]},
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
        scoring={"scores": [{"instrument_id": "050025", "asset_class": "us_etf", "action": "buy_candidate", "conviction": "med", "data_completeness": 1.0, "missing_data": []}]},
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
