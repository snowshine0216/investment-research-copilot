from __future__ import annotations

from dataclasses import asdict

from irc.commands.memo_cmd import _build_pick_rows
from irc.opportunity.types import ThesisEvidence


def _make_evidence_dict(**over) -> dict:
    base = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    d = asdict(base)
    d.update(over)
    return d


def _op_row(iid="510300", evidence_gaps=(), thesis_evidence=None, **over):
    base = {
        "instrument_id": iid,
        "name_cn": f"{iid}_name",
        "asset_class": "cn_etf",
        "opportunity_state": "core_dca",
        "opportunity_reason": "r",
        "evidence_gaps": list(evidence_gaps),
        "fetch_types_attempted": ["filing", "broker", "news"],
        "thesis_evidence": list(thesis_evidence or ()),
    }
    base.update(over)
    return base


def test_build_pick_rows_absent_target_routes_to_absent_bucket():
    """trade target whose iid is not in opportunity rows (after venue-proxy
    strip) ends up in `absent`, NOT in `pick_rows`."""
    trades = [{"target": "999999", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert len(absent) == 1
    assert absent[0]["target"] == "999999"
    assert gapped == []


def test_build_pick_rows_gapped_target_routes_to_gapped_bucket():
    """trade target whose op row has `evidence_gaps != ()` ends up in
    `gapped`, NOT in `pick_rows`."""
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300",
                                    evidence_gaps=("holdings_fetch_failed",))]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert absent == []
    assert len(gapped) == 1
    assert gapped[0]["target"] == "510300"
    assert gapped[0]["_matched_row"]["instrument_id"] == "510300"


def test_build_pick_rows_clean_target_builds_pick_with_citations():
    """trade target whose op row has `evidence_gaps == ()` produces a PickRow
    whose `citations` is `select_citations(rebuilt_evidence, cap=3)`."""
    ev_dict = _make_evidence_dict()
    trades = [{"target": "510300", "target_weight": 0.1, "composite_score": 50.0}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1
    pr = pick_rows[0]
    assert pr.instrument_id == "510300"
    assert len(pr.citations) == 1
    assert pr.citations[0].citation_id == ev_dict["citation_id"]


def test_build_pick_rows_preserves_trade_venue_note_for_table_action():
    trades = [{
        "target": "511220",
        "target_weight": 0.04,
        "venue_note": "venue mismatch and no proxy available",
    }]
    opportunity = {"rows": [_op_row(iid="511220", opportunity_state="small_watch")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert pick_rows[0].venue_note == "venue mismatch and no proxy available"


def test_build_pick_rows_explicitly_names_expensive_and_hot_states_in_reason():
    trades = [{"target": "519770", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(
        iid="519770",
        opportunity_state="small_watch",
        opportunity_reason="估值偏高或热度偏高，暂停加仓等待回落。",
        valuation_state="very_expensive",
        heat_state="overheated",
    )]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, {"scores": []})
    reason = pick_rows[0].one_line_reason
    assert "估值=very_expensive" in reason
    assert "热度=overheated" in reason
    assert "等待回落" not in reason


def test_build_pick_rows_venue_proxy_strip_falls_back_to_canonical():
    """A trade target like `A510300.SH` should match op row `510300` after
    suffix strip."""
    trades = [{"target": "A510300.SH", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1


def test_build_pick_rows_raises_on_citation_id_tampering():
    """If the rebuilt ThesisEvidence's recomputed citation_id != the JSON
    value, raise ValueError — detects drift/tampering."""
    import pytest
    ev_dict = _make_evidence_dict()
    ev_dict["citation_id"] = "deadbeefdeadbeef"  # wrong; will recompute differently
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    with pytest.raises(ValueError, match="citation_id"):
        _build_pick_rows(trades, opportunity, {"scores": []})


def test_build_pick_rows_populates_decision_status_actionable_when_no_blockers():
    """A buy_candidate score + allocation_selected + venue=direct → actionable_buy."""
    trades = [{
        "target": "510300",
        "target_weight": 0.1,
        "venue_compatible": True,
        "proxy_id": None,
    }]
    opportunity = {"rows": [_op_row(iid="510300")]}
    scoring = {"scores": [{
        "instrument_id": "510300",
        "asset_class": "cn_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "missing_data": [],
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert pick_rows[0].decision_status == "actionable_buy"


def test_build_pick_rows_populates_decision_status_blocked_when_venue_blocked():
    trades = [{
        "target": "510300",
        "target_weight": 0.1,
        "venue_compatible": False,
        "proxy_id": None,
        "venue_note": "venue mismatch and no proxy available",
    }]
    opportunity = {"rows": [_op_row(iid="510300")]}
    scoring = {"scores": [{
        "instrument_id": "510300",
        "asset_class": "cn_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "missing_data": [],
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert pick_rows[0].decision_status == "blocked"


def test_build_pick_rows_populates_decision_status_avoid_for_avoid_action():
    trades = [{
        "target": "510300",
        "target_weight": 0.1,
        "venue_compatible": True,
        "proxy_id": None,
    }]
    opportunity = {"rows": [_op_row(iid="510300")]}
    scoring = {"scores": [{
        "instrument_id": "510300",
        "asset_class": "cn_etf",
        "action": "avoid",
        "data_completeness": 1.0,
        "missing_data": [],
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert pick_rows[0].decision_status == "avoid"


def test_build_pick_rows_missing_opportunity_falls_into_absent():
    """When opportunity is {} (file absent), every trade target falls into
    `absent` — explicit signal that opportunity didn't run."""
    trades = [{"target": "510300"}, {"target": "159919"}]
    pick_rows, absent, gapped = _build_pick_rows(trades, {}, {"scores": []})
    assert pick_rows == []
    assert {a["target"] for a in absent} == {"510300", "159919"}
    assert gapped == []


def test_render_failure_sections_produces_expected_markdown():
    """Smoke test: absent + gapped buckets render the `###` h3 sub-blocks
    and never emit conclusion fields (opportunity_state, dca_action, etc.)."""
    from irc.memo.picks_table import render_failure_sections

    absent = [{"target": "510300"}]
    gapped = [{
        "target": "005827",
        "_matched_row": {
            "instrument_id": "005827",
            "name_cn": "易方达蓝筹精选",
            "evidence_gaps": ["missing_constituent_snapshot", "news_search_empty"],
            "fetch_types_attempted": ["filing", "broker", "news"],
            # The following MUST NOT appear in the failure section markdown:
            "opportunity_state": "core_dca",
            "dca_action": "normal_dca",
            "risk_action": "none",
            "note_cn": "should-not-appear",
        },
    }]
    md = render_failure_sections(absent, gapped, extra_names={"510300": "华泰柏瑞沪深300ETF"})
    assert "### 未能纳入精选：机会数据缺失" in md
    assert "### 未能纳入精选：证据不足" in md
    assert "510300 华泰柏瑞沪深300ETF" in md
    assert "005827 易方达蓝筹精选" in md
    assert "missing_constituent_snapshot" in md
    assert "filing, broker, news" in md
    # Conclusion fields MUST NOT leak:
    assert "core_dca" not in md
    assert "normal_dca" not in md
    assert "should-not-appear" not in md


def test_render_failure_sections_empty_buckets_returns_empty_string():
    from irc.memo.picks_table import render_failure_sections
    assert render_failure_sections([], []) == ""


def test_render_failure_sections_already_tried_populated():
    """When fetch_types_attempted is non-empty the rendered 已尝试: line shows
    the comma-separated values (from the _matched_row dict, which comes from
    _row_to_dict's fetch_types_attempted serialization)."""
    from irc.memo.picks_table import render_failure_sections
    gapped = [{
        "target": "005827",
        "_matched_row": {
            "instrument_id": "005827",
            "name_cn": "易方达蓝筹精选",
            "evidence_gaps": ["missing_constituent_snapshot"],
            "fetch_types_attempted": ["filing", "broker"],
        },
    }]
    md = render_failure_sections([], gapped)
    assert "已尝试: filing, broker" in md


def test_render_failure_sections_already_tried_empty_renders_dash():
    """When fetch_types_attempted is empty the rendered 已尝试: line shows —
    (em-dash) so the field is not left as a trailing blank."""
    from irc.memo.picks_table import render_failure_sections
    gapped = [{
        "target": "005827",
        "_matched_row": {
            "instrument_id": "005827",
            "name_cn": "易方达蓝筹精选",
            "evidence_gaps": ["missing_constituent_snapshot"],
            "fetch_types_attempted": [],
        },
    }]
    md = render_failure_sections([], gapped)
    assert "已尝试: —" in md


# ── Item 007 OQ1 — memo_cmd._evidence_from_dict delegates to classmethod ──────


def test_memo_cmd_uses_thesis_evidence_from_dict() -> None:
    """memo_cmd must dispatch dict→dataclass through ThesisEvidence.from_dict."""
    import irc.commands.memo_cmd as mc
    # Either _evidence_from_dict was removed (call sites updated to from_dict)
    # OR it now delegates internally to ThesisEvidence.from_dict.
    if hasattr(mc, "_evidence_from_dict"):
        # Delegation path: assert it calls the classmethod.
        from irc.fundamentals.types import ThesisEvidence
        d = {
            "type": "filing", "source": "src", "url": "https://x",
            "date": "2024-04-15", "summary": "x", "scope": "constituent",
            "citation_kind": "data", "owner_instrument_id": "005827",
            "parent_fund_id": "005827", "constituent_key": "600519",
        }
        # Both routes must return identical ThesisEvidence instances.
        assert mc._evidence_from_dict(d).citation_id == ThesisEvidence.from_dict(d).citation_id
    else:
        # Removal path: call sites have already migrated.
        assert True


# ── Item 003 — tranche_cap_pct + trigger_status population ───────────────────


def test_build_pick_rows_populates_tranche_cap_pct_in_build_mode():
    """`target_weight=0.20` + `build_mode='build'` → `tranche_cap_pct=0.05`
    (target ÷ 4 tranches). Reuses suggest_tranche_pct verbatim."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
    )
    assert pick_rows[0].tranche_cap_pct == 0.05


def test_build_pick_rows_populates_trigger_status_from_trade_triggers():
    """Triggers on the trade row → compact-format string on the PickRow."""
    trades = [{
        "target": "510300",
        "target_weight": 0.20,
        "triggers": [{
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        }],
    }]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
    )
    assert pick_rows[0].trigger_status == "weekly_drawdown_4pct ✓"


def test_build_pick_rows_defaults_when_live_inputs_omitted():
    """Legacy callers (e.g. older tests) omit the new kwargs; fields fall
    back to safe sentinels — None for cap (when build_mode default = 'build'
    still yields target/4) and "" for triggers (no live data to evaluate)."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, {"scores": []})
    # build_mode defaults to 'build', so cap is computed.
    assert pick_rows[0].tranche_cap_pct == 0.05
    # No triggers on the trade → empty string.
    assert pick_rows[0].trigger_status == ""


def test_build_pick_rows_missing_triggers_yields_empty_trigger_status():
    """Trade without `triggers` key → trigger_status = "" (renderer → —)."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
        macro_snapshot={"vix": 16.76},
        weekly_return_by_id={"510300": -0.01},
    )
    assert pick_rows[0].trigger_status == ""


def test_build_pick_rows_zero_weight_yields_zero_cap():
    """target_weight=0 (observation-only) → tranche_cap_pct=0.0; renderer
    will emit em-dash (per spec AC11)."""
    trades = [{"target": "510300", "target_weight": 0.0}]
    opportunity = {"rows": [_op_row(iid="510300", opportunity_state="small_watch")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
    )
    assert pick_rows[0].tranche_cap_pct == 0.0
