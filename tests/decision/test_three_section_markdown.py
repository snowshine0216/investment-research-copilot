from __future__ import annotations

from irc.decision.report import compose_decision_report, render_decision_markdown


def _report(scores, allocation_selected, trades, blocking_reasons_per_id=None,
            names_by_id=None):
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
        names_by_id=names_by_id,
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


def test_todays_only_action_lists_actionable_buys():
    # 1 actionable_buy with a known name → headline shows it.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{
            "instrument_id": "000139", "asset_class": "cn_bond_fund",
            "action": "buy_candidate", "conviction": "high",
            "data_completeness": 1.0, "missing_data": [],
        }]},
        allocation={"selected_instruments": [
            {"instrument_id": "000139", "target_weight": 0.054}
        ], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "000139", "asset_class": "cn_bond_fund",
             "role": "defensive_cn_bond", "venue_compatible": True,
             "proxy_id": None, "target_weight": 0.054}
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        names_by_id={"000139": "富国国有企业债债券A/B"},
    )
    md = render_decision_markdown(report)
    assert "## 今日唯一行动 / Today's only action" in md
    section = md.split("## 今日唯一行动", 1)[1].split("\n## ", 1)[0]
    assert "000139" in section
    assert "富国国有企业债债券" in section
    assert "defensive_cn_bond" in section
    assert "5" in section  # target weight 5.4%


def test_todays_only_action_empty_when_no_actionable():
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{
            "instrument_id": "X1", "asset_class": "gold",
            "action": "watch", "conviction": "high",
            "data_completeness": 1.0, "missing_data": [],
        }]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    md = render_decision_markdown(report)
    section = md.split("## 今日唯一行动", 1)[1].split("\n## ", 1)[0]
    assert "本周无可执行标的" in section


def test_todays_only_action_appears_before_verdict():
    # The headline must be the FIRST level-2 section so a layperson sees it
    # before anything else.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": []},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    md = render_decision_markdown(report)
    todays = md.find("## 今日唯一行动")
    verdict = md.find("## Verdict")
    assert todays != -1 and verdict != -1
    assert todays < verdict


def test_decision_row_has_target_weight_and_role_fields():
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{
            "instrument_id": "000139", "asset_class": "cn_bond_fund",
            "action": "buy_candidate", "conviction": "high",
            "data_completeness": 1.0, "missing_data": [],
        }]},
        allocation={"selected_instruments": [
            {"instrument_id": "000139", "target_weight": 0.054}
        ], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "000139", "asset_class": "cn_bond_fund",
             "role": "defensive_cn_bond", "venue_compatible": True,
             "proxy_id": None, "target_weight": 0.054}
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    row = report["rows"][0]
    assert row["target_weight"] == 0.054
    assert row["role"] == "defensive_cn_bond"


def test_qdii_premium_unknown_renders_in_blocked_section():
    # A QDII buy_candidate with no qdii_premium_pct → blocked. Rendered
    # markdown must surface the qdii_premium_unknown reason + remediation.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{
            "instrument_id": "017641", "asset_class": "us_etf",
            "action": "buy_candidate", "conviction": "med",
            "data_completeness": 1.0, "missing_data": [],
        }]},
        allocation={"selected_instruments": [
            {"instrument_id": "017641", "target_weight": 0.2}
        ], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "017641", "asset_class": "us_etf",
             "venue_compatible": True, "proxy_id": None,
             "target_weight": 0.2}
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "QDII premium-to-NAV" in section
    assert "Fetch real-time QDII premium" in section


def _audit_report(summary):
    return compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "X1", "asset_class": "gold",
                              "action": "watch", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        audit_summary=summary,
    )


def test_audit_summary_banner_emitted_when_p1_present():
    report = _audit_report({"verdict": "条件通过", "p1_count": 2,
                             "p1_findings": ["| **P1** | foo |"]})
    md = render_decision_markdown(report)
    assert "合规审核未达标" in md
    assert "条件通过" in md
    assert "P1 必改项 2 条" in md


def test_audit_summary_banner_emitted_when_blocked_verdict():
    report = _audit_report({"verdict": "审核未通过", "p1_count": 0,
                             "p1_findings": []})
    md = render_decision_markdown(report)
    assert "合规审核未达标" in md
    assert "审核未通过" in md


def test_audit_summary_banner_suppressed_when_clean_pass():
    report = _audit_report({"verdict": "审核通过", "p1_count": 0,
                             "p1_findings": []})
    md = render_decision_markdown(report)
    assert "合规审核未达标" not in md


def test_audit_summary_banner_suppressed_when_none():
    report = _audit_report(None)
    md = render_decision_markdown(report)
    assert "合规审核未达标" not in md


def test_audit_summary_in_report_dict():
    summary = {"verdict": "条件通过", "p1_count": 2,
               "p1_findings": ["finding 1", "finding 2"]}
    report = _audit_report(summary)
    assert report["audit_summary"] == summary


def _drift_report(cash_target, cash_residual):
    return compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "X1", "asset_class": "gold",
                              "action": "watch", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={
            "target_weights_per_class": {"cash": cash_target, "gold": 0.2},
            "selected_instruments": [],
            "diagnostics": {"total_weight": 1.0, "cash_residual_weight": cash_residual},
        },
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )


def test_execution_drift_banner_emitted_when_above_threshold():
    report = _drift_report(cash_target=0.05, cash_residual=0.15)
    md = render_decision_markdown(report)
    assert "执行漂移提醒" in md
    assert "Execution drift" in md


def test_execution_drift_banner_suppressed_when_below_threshold():
    report = _drift_report(cash_target=0.05, cash_residual=0.07)  # drift 0.02
    md = render_decision_markdown(report)
    assert "执行漂移提醒" not in md


def test_execution_drift_banner_emitted_at_exact_threshold():
    # 5pp exactly should fire — the spec is "≥ 5pp".
    report = _drift_report(cash_target=0.05, cash_residual=0.10)
    md = render_decision_markdown(report)
    assert "执行漂移提醒" in md


def test_execution_drift_field_in_report_dict():
    report = _drift_report(cash_target=0.05, cash_residual=0.15)
    drift = report.get("execution_drift")
    assert drift is not None
    assert drift["drift_pct"] == 0.10
    assert drift["cash_target"] == 0.05
    assert drift["cash_residual"] == 0.15


def test_execution_drift_handles_missing_diagnostics():
    # Allocation lacks target_weights_per_class entirely — should not raise.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "X1", "asset_class": "gold",
                              "action": "watch", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    assert report.get("execution_drift") is None


def test_proxy_coverage_in_report_dict():
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "GOLDETF", "asset_class": "gold",
                              "action": "buy_candidate", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "cmb_paper_gold", "asset_class": "gold",
             "target_weight": 0.2, "proxy_id": "cmb_paper_gold",
             "venue_compatible": False},
            {"target": "017641", "asset_class": "us_etf",
             "target_weight": 0.2, "proxy_id": None,
             "venue_compatible": True},
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
    )
    coverage = report.get("proxy_coverage", {})
    assert "gold" in coverage
    assert any(entry["proxy_id"] == "cmb_paper_gold" for entry in coverage["gold"])
    # us_etf has a direct trade (proxy_id=None) → should NOT be in proxy_coverage.
    assert "us_etf" not in coverage


def test_blocked_section_emits_proxy_coverage_banner():
    # 518880 gold ETF blocked (no venue) but cmb_paper_gold proxy fills gold role.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "518880", "asset_class": "gold",
                              "action": "buy_candidate", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "cmb_paper_gold", "asset_class": "gold",
             "target_weight": 0.2, "proxy_id": "cmb_paper_gold",
             "venue_compatible": False},
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        venue_requirements_by_id={"518880": ["broker_a_share"]},
        available_venues=["cmb"],
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "Role already met" in section
    assert "cmb_paper_gold" in section
    assert "gold" in section


def test_blocked_section_no_banner_when_no_proxy_for_class():
    # Bond ETF blocked by venue, no proxy in cn_bond_fund → no banner.
    report = compose_decision_report(
        date="2026-05-19",
        scoring={"scores": [{"instrument_id": "511520", "asset_class": "cn_bond_fund",
                              "action": "buy_candidate", "conviction": "high",
                              "data_completeness": 1.0, "missing_data": []}]},
        allocation={"selected_instruments": [],
                    "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": []},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        venue_requirements_by_id={"511520": ["broker_a_share"]},
        available_venues=["cmb"],
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "Role already met" not in section


def test_score_action_cell_is_bilingual_in_actionable_section():
    report = _report(
        scores=[_score("X1", "buy_candidate")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    section = md.split("## Actionable buys", 1)[1].split("\n## ", 1)[0]
    assert "buy_candidate / 候选买入" in section


def test_score_action_cell_is_bilingual_in_watch_section():
    report = _report(
        scores=[_score("W1", "watch")],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    section = md.split("## Watch (no trade)", 1)[1]
    assert "watch / 观察" in section


def test_score_action_cell_is_bilingual_in_blocked_section():
    # data_completeness < 0.5 → buy_candidate becomes blocked by data_incomplete.
    report = _report(
        scores=[_score("B1", "buy_candidate", completeness=0.4)],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "buy_candidate / 候选买入" in section


def test_unknown_score_action_falls_back_to_raw_label():
    # Unknown action passes through unchanged (no KeyError, no blank cell).
    report = _report(
        scores=[_score("X1", "weird_new_action")],
        allocation_selected=[],
        trades=[],
    )
    md = render_decision_markdown(report)
    assert "weird_new_action" in md


def test_markdown_has_glossary_section():
    report = _report(
        scores=[_score("X1", "buy_candidate"), _score("X2", "watch")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    assert "## 术语速查 (Glossary)" in md


def test_glossary_contains_required_terms():
    report = _report(
        scores=[_score("X1", "buy_candidate")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    section = md.split("## 术语速查 (Glossary)", 1)[1]
    for term in (
        "buy_candidate",
        "actionable_buy",
        "core_dca",
        "pause_wait",
        "venue_status=direct",
        "venue_status=blocked_no_proxy",
        "venue_status=unknown",
        "data_completeness",
        "watch_reason=scored watch",
        "watch_reason=not_selected_by_allocation",
        "watch_reason=venue_unknown",
    ):
        assert term in section, f"glossary missing term: {term}"


def test_glossary_data_completeness_warning():
    # The trust-check doc's concern A3: "completeness=1.00 reads as
    # 100% confident". The glossary must explicitly disambiguate.
    report = _report(
        scores=[_score("X1", "buy_candidate")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    md = render_decision_markdown(report)
    section = md.split("## 术语速查 (Glossary)", 1)[1]
    assert "不等于" in section
    assert "信心" in section or "胜率" in section


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


def test_rows_carry_instrument_name_when_names_provided():
    report = _report(
        scores=[
            _score("BUY1", "buy_candidate"),
            _score("LOW1", "buy_candidate", completeness=0.5),
            _score("W1", "watch"),
        ],
        allocation_selected=["BUY1"],
        trades=[{"target": "BUY1", "venue_compatible": True, "proxy_id": None}],
        names_by_id={"BUY1": "Acme Buy Fund", "LOW1": "Acme Low Fund", "W1": "Acme Watch Fund"},
    )
    names_by_iid = {r["instrument_id"]: r.get("instrument_name") for r in report["rows"]}
    assert names_by_iid == {
        "BUY1": "Acme Buy Fund",
        "LOW1": "Acme Low Fund",
        "W1": "Acme Watch Fund",
    }


def test_rows_have_none_name_when_names_map_missing():
    report = _report(
        scores=[_score("X1", "buy_candidate")],
        allocation_selected=["X1"],
        trades=[{"target": "X1", "venue_compatible": True, "proxy_id": None}],
    )
    assert report["rows"][0].get("instrument_name") is None


def test_markdown_actionable_section_shows_instrument_name():
    report = _report(
        scores=[_score("BUY1", "buy_candidate")],
        allocation_selected=["BUY1"],
        trades=[{"target": "BUY1", "venue_compatible": True, "proxy_id": None}],
        names_by_id={"BUY1": "Acme Buy Fund"},
    )
    md = render_decision_markdown(report)
    section = md.split("## Actionable buys", 1)[1].split("\n## ", 1)[0]
    assert "Acme Buy Fund" in section
    assert "BUY1" in section


def test_markdown_blocked_section_shows_instrument_name():
    report = _report(
        scores=[_score("LOW1", "buy_candidate", completeness=0.5)],
        allocation_selected=[],
        trades=[],
        names_by_id={"LOW1": "Acme Low Fund"},
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "Acme Low Fund" in section


def test_markdown_watch_section_shows_instrument_name():
    report = _report(
        scores=[_score("W1", "watch")],
        allocation_selected=[],
        trades=[],
        names_by_id={"W1": "Acme Watch Fund"},
    )
    md = render_decision_markdown(report)
    section = md.split("## Watch (no trade)", 1)[1]
    assert "Acme Watch Fund" in section


def test_markdown_renders_without_name_when_unknown():
    report = _report(
        scores=[_score("UNKNOWN", "buy_candidate")],
        allocation_selected=["UNKNOWN"],
        trades=[{"target": "UNKNOWN", "venue_compatible": True, "proxy_id": None}],
        names_by_id={},
    )
    md = render_decision_markdown(report)
    # No "None" leaks into the table when the name is missing.
    assert "| None |" not in md
    assert "UNKNOWN" in md


def test_qdii_premium_too_high_renders_in_blocked_section():
    """AC17: a buy_candidate QDII row with premium > threshold lands in the
    blocked section with the new label + remediation."""
    report = compose_decision_report(
        date="2026-05-26",
        scoring={"scores": [{
            "instrument_id": "513650", "asset_class": "us_etf",
            "action": "buy_candidate", "conviction": "med",
            "data_completeness": 1.0, "missing_data": [],
            "qdii_premium_pct": 0.10,
        }]},
        allocation={"selected_instruments": [
            {"instrument_id": "513650", "target_weight": 0.2}
        ], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "513650", "asset_class": "us_etf",
             "venue_compatible": True, "proxy_id": None,
             "target_weight": 0.2}
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        qdii_max_premium_pct=0.05,
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "QDII premium-to-NAV above threshold" in section
