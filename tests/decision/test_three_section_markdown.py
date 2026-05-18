from __future__ import annotations

from irc.decision.report import compose_decision_report, render_decision_markdown


def _report(scores, allocation_selected, trades, blocking_reasons_per_id=None):
    allocation_rows = [{"instrument_id": iid, "target_weight": 0.5}
                       for iid in allocation_selected]
    return compose_decision_report(
        date="2026-05-18",
        scoring={"scores": scores},
        allocation={"selected_instruments": allocation_rows,
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": trades},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )


def _score(iid, action="watch", completeness=1.0, asset_class="cn_equity_fund"):
    return {"instrument_id": iid, "asset_class": asset_class, "action": action,
            "conviction": "med", "data_completeness": completeness, "missing_data": []}


def test_markdown_has_three_reader_first_sections():
    report = _report(
        scores=[_score("X1", "buy_candidate"), _score("X2", "watch")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    assert "## Actionable buys" in md
    assert "## Blocked — fixable today" in md
    assert "## Watch (no trade)" in md


def test_actionable_buys_section_lists_actionable_rows():
    report = _report(
        scores=[_score("BUY1", "buy_candidate")],
        allocation_selected=["BUY1"],
        trades=[{"target": "BUY1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    # Section header present.
    assert "## Actionable buys" in md
    # The actionable row is in its section.
    section = md.split("## Actionable buys", 1)[1].split("\n## ", 1)[0]
    assert "BUY1" in section


def test_actionable_buys_section_renders_empty_marker_when_no_buys():
    report = _report(
        scores=[_score("WX", "watch")],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    section = md.split("## Actionable buys", 1)[1].split("\n## ", 1)[0]
    assert "（无）" in section


def test_blocked_section_groups_by_first_blocking_reason():
    # Two blocked rows with different reasons:
    # - LOW1 has data_completeness=0.5 -> data_incomplete
    # - V1 has no trade (venue_blocked) plus completeness=1.0
    # Wait: V1 has no trade so venue=blocked_no_proxy iff in-universe.
    # Without venue context, V1's status is unknown -> not venue_blocked.
    # Use LOW1+LOW2 both data_incomplete to test grouping.
    report = _report(
        scores=[
            _score("LOW1", "buy_candidate", completeness=0.5),
            _score("LOW2", "buy_candidate", completeness=0.5),
        ],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    # Split on the level-2 header explicitly (newline before "## ") so that
    # the inner "### Blocked by:" subsection isn't accidentally treated as
    # the next section boundary.
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "Blocked by:" in section
    assert "Data incomplete" in section
    assert "LOW1" in section
    assert "LOW2" in section
    assert "Repair the required financial metrics" in section


def test_watch_section_summary_counts_by_reason():
    report = _report(
        scores=[
            _score("W1", "watch"),
            _score("W2", "watch"),
            _score("W3", "buy_candidate"),  # not selected -> not_selected_by_allocation
        ],
        allocation_selected=[],
        trades=[
            {"target": "W3", "venue_compatible": True, "proxy_id": None},
        ],
    )
    md = render_decision_markdown(report)
    section = md.split("## Watch (no trade)", 1)[1]
    assert "3 个标的暂未触发交易决策" in section
    assert "scored watch: 2" in section
    assert "not selected by allocation: 1" in section


def test_watch_section_collapses_with_details_block():
    report = _report(
        scores=[_score("W1", "watch")],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    section = md.split("## Watch (no trade)", 1)[1]
    assert "<details>" in section
    assert "<summary>" in section
    assert "</details>" in section


def test_json_shape_unchanged_after_markdown_refactor():
    # The JSON report shape is the contract for downstream tools.
    # Markdown restructure must not change it.
    report = _report(
        scores=[_score("X1", "buy_candidate"), _score("X2", "watch")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    assert set(report.keys()) >= {"date", "overall_status", "blocking_reasons",
                                   "summary", "rows", "pipeline_incomplete"}
    assert report["summary"]["actionable_buy_count"] == 1
    assert report["summary"]["watch_count"] == 1
    # rows[0] still carries the full per-row schema (including new watch_reason).
    row = report["rows"][0]
    assert "decision_status" in row
    assert "watch_reason" in row
