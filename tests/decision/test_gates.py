from __future__ import annotations

from irc.decision.gates import decide_row, target_weights_are_valid, venue_status_for_trade


def _score(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "instrument_id": "518850",
        "asset_class": "gold",
        "action": "buy_candidate",
        "conviction": "med",
        "data_completeness": 1.0,
        "missing_data": [],
    }
    return {**row, **overrides}


def test_target_weights_are_valid_requires_total_near_one() -> None:
    assert target_weights_are_valid({"diagnostics": {"total_weight": 1.0}})
    assert not target_weights_are_valid({"diagnostics": {"total_weight": 3.0}})


def test_target_weights_are_valid_accepts_cash_residual() -> None:
    """When classes lack a scored candidate (e.g., cash, hk_etf), the
    unallocated portion is reported as cash_residual_weight; invested + cash
    must cover the portfolio."""
    assert target_weights_are_valid(
        {"diagnostics": {"total_weight": 0.85, "cash_residual_weight": 0.15}}
    )
    assert target_weights_are_valid(
        {"diagnostics": {"total_weight": 0.0, "cash_residual_weight": 1.0}}
    )
    assert not target_weights_are_valid(
        {"diagnostics": {"total_weight": 0.85, "cash_residual_weight": 0.05}}
    )


def test_pipeline_halt_blocks_everything() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["portfolio_action"] == "no_trade"
    assert "pipeline_halted" in decision["blocking_reasons"]


def test_low_data_completeness_blocks_buy() -> None:
    decision = decide_row(
        score=_score(data_completeness=0.0, missing_data=["expense_ratio"]),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert "data_incomplete" in decision["blocking_reasons"]


def test_excluded_from_opportunity_report_blocks_actionable_buy() -> None:
    """When a row was filtered out of `opportunity_report.json` (e.g. Policy B
    rejected it as `incomplete_constituent_data` for foreign-listed holdings)
    the decision row must not claim `actionable_buy`. The downgrade keeps
    decision_report.md consistent with memo.md §5's "未能纳入精选：机会数据缺失"
    section."""
    decision = decide_row(
        score=_score(instrument_id="006809"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        excluded_from_opportunity=True,
    )
    assert decision["decision_status"] == "blocked"
    assert "opportunity_excluded" in decision["blocking_reasons"]


def test_included_in_opportunity_report_allows_actionable_buy() -> None:
    """Sanity-check the default path: row is included → no opportunity_excluded
    reason → status stays at the score+venue-derived verdict."""
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        excluded_from_opportunity=False,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "opportunity_excluded" not in decision["blocking_reasons"]


def test_compute_blocking_reasons_emits_qdii_premium_too_high() -> None:
    """AC8: when the qdii_premium_too_high flag is True, the code lands in reasons."""
    from irc.decision.gates import compute_blocking_reasons

    reasons = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="direct",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
        qdii_premium_too_high=True,
    )
    assert reasons == ["qdii_premium_too_high"]


def test_compute_blocking_reasons_qdii_premium_too_high_default_is_false() -> None:
    """Existing call sites stay working (default False)."""
    from irc.decision.gates import compute_blocking_reasons

    reasons = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="direct",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
    )
    assert reasons == []


def test_qdii_buy_with_premium_above_threshold_blocks() -> None:
    """AC15: QDII buy_candidate with premium > qdii_max_premium_pct → blocked."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.10),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "blocked"
    assert "qdii_premium_too_high" in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_buy_with_premium_at_threshold_admits_boundary() -> None:
    """AC15: premium == threshold passes (strict-greater comparison)."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.05),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_buy_with_healthy_premium_passes() -> None:
    """AC15: small positive premium below threshold admits; no QDII code fires."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.01),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_off_exchange_synthetic_zero_passes() -> None:
    """qdii_premium_pct=0.0 (off-exchange synthetic) clears both QDII codes."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.0),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_premium_unknown_unchanged_when_premium_is_none() -> None:
    """Regression: the existing qdii_premium_unknown branch still fires."""
    decision = decide_row(
        score=_score(asset_class="us_etf"),  # no qdii_premium_pct
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "blocked"
    assert "qdii_premium_unknown" in decision["blocking_reasons"]
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]


def test_non_qdii_premium_above_threshold_is_ignored() -> None:
    """Non-QDII rows with arbitrary qdii_premium_pct must not trigger either code."""
    decision = decide_row(
        score=_score(asset_class="cn_equity_fund", qdii_premium_pct=0.99),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_watch_action_with_high_premium_does_not_block() -> None:
    """Only BUY actions trigger the QDII premium gate."""
    decision = decide_row(
        score=_score(asset_class="us_etf", action="watch", qdii_premium_pct=0.10),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]


def test_avoid_action_stays_avoid_even_when_selected() -> None:
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "avoid"
    assert decision["portfolio_action"] == "no_trade"


def test_incompatible_venue_without_proxy_blocks_execution() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": False, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["venue_status"] == "blocked_no_proxy"


def test_complete_healthy_buy_candidate_can_be_actionable() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "actionable_buy"
    assert decision["portfolio_action"] == "no_trade"


def test_zero_memo_traceability_marks_evidence_narrative_only() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=0.0,
    )

    assert decision["memo_evidence_status"] == "narrative_only"
    assert "memo_narrative_only" in decision["blocking_reasons"]
    assert decision["decision_status"] == "blocked"


def test_target_weights_valid_falls_back_to_sum_selected_when_total_absent() -> None:
    allocation = {
        "selected_instruments": [
            {"instrument_id": "A", "target_weight": 0.6},
            {"instrument_id": "B", "target_weight": 0.4},
        ]
    }
    assert target_weights_are_valid(allocation)


def test_venue_status_none_trade_returns_unknown() -> None:
    assert venue_status_for_trade(None) == "unknown"


def test_venue_status_proxy_available_when_proxy_id_present() -> None:
    assert venue_status_for_trade({"venue_compatible": False, "proxy_id": "PROXY"}) == "proxy_available"


def test_target_weights_invalid_blocks_via_decide_row() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=False,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "target_weights_invalid" in decision["blocking_reasons"]
    assert decision["decision_status"] == "blocked"


def test_score_avoid_appears_in_blocking_reasons() -> None:
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "score_avoid" in decision["blocking_reasons"]


def test_watch_only_when_buy_candidate_not_selected() -> None:
    decision = decide_row(
        score=_score(action="buy_candidate"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "watch_only"


def test_watch_only_when_action_is_watch() -> None:
    decision = decide_row(
        score=_score(action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "watch_only"


def test_strong_buy_candidate_action_results_in_actionable_buy() -> None:
    decision = decide_row(
        score=_score(action="strong_buy_candidate"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "actionable_buy"


def test_next_step_for_target_weights_invalid() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=False,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "Fix allocation normalization" in decision["next_step"]


def test_next_step_watch_only_fallback() -> None:
    decision = decide_row(
        score=_score(action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "watchlist" in decision["next_step"]


def test_avoid_with_pipeline_halted_reports_both_reasons_and_status_is_avoid() -> None:
    # design: score_action wins → "avoid"; blocking_reasons still records both gates
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "avoid"
    assert "pipeline_halted" in decision["blocking_reasons"]
    assert "score_avoid" in decision["blocking_reasons"]


# ---------------------------------------------------------------------------
# _next_step: remaining text branches not yet asserted
# ---------------------------------------------------------------------------

def test_next_step_actionable_buy_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "Review manually" in decision["next_step"]


def test_next_step_pipeline_halted_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )
    assert "Fix the halted stage" in decision["next_step"]


def test_next_step_data_incomplete_text() -> None:
    decision = decide_row(
        score=_score(data_completeness=0.0),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "Repair required financial metrics" in decision["next_step"]


def test_next_step_venue_blocked_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": False, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "Add a compatible account venue" in decision["next_step"]


def test_next_step_memo_narrative_only_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=0.0,
    )
    assert "memo traceability" in decision["next_step"]


def test_qdii_buy_without_premium_blocks() -> None:
    """QDII row marked as buy_candidate but with no qdii_premium_pct should
    be downgraded from actionable to blocked — the trust-check identified
    this as the highest single-trade-loss risk."""
    decision = decide_row(
        score=_score(asset_class="us_etf"),  # no qdii_premium_pct
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert decision["decision_status"] == "blocked"
    assert "qdii_premium_unknown" in decision["blocking_reasons"]


def test_qdii_buy_with_premium_passes_qdii_gate() -> None:
    """Once premium data flows in, the gate releases and the row can be
    actionable_buy (subject to other gates)."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.05),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]
    assert decision["decision_status"] == "actionable_buy"


def test_non_qdii_buy_without_premium_passes() -> None:
    """A-share / bond rows must not be gated by QDII-specific premium data."""
    decision = decide_row(
        score=_score(asset_class="cn_equity_fund"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_watch_without_premium_not_blocked_by_gate() -> None:
    """Only buy-side actions trigger the QDII premium gate — a watch row
    with no premium data is still watch_only, not blocked."""
    decision = decide_row(
        score=_score(asset_class="us_etf", action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_hk_etf_also_gated() -> None:
    """hk_etf is also a QDII class — same gate applies."""
    decision = decide_row(
        score=_score(asset_class="hk_etf"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "qdii_premium_unknown" in decision["blocking_reasons"]


def test_compute_decision_status_pure_golden() -> None:
    """Pure function: (score_action, blocking_reasons, allocation_selected) → DecisionStatus.

    Promoted from `_decision_status` so memo can call it without depending on
    decision_report.json.
    """
    from irc.decision.gates import compute_decision_status

    # avoid wins over anything
    assert compute_decision_status("avoid", [], True) == "avoid"
    assert compute_decision_status("strong_avoid", ["venue_blocked"], False) == "avoid"

    # any blocking reason → blocked (unless avoid already won)
    assert compute_decision_status("buy_candidate", ["venue_blocked"], True) == "blocked"
    assert compute_decision_status("watch", ["pipeline_halted"], False) == "blocked"

    # buy + allocated + no blocking → actionable_buy
    assert compute_decision_status("buy_candidate", [], True) == "actionable_buy"
    assert compute_decision_status("strong_buy_candidate", [], True) == "actionable_buy"

    # buy but not allocated → watch_only
    assert compute_decision_status("buy_candidate", [], False) == "watch_only"

    # plain watch with no blocking → watch_only
    assert compute_decision_status("watch", [], True) == "watch_only"
    assert compute_decision_status("watch", [], False) == "watch_only"


def test_compute_blocking_reasons_pure_smoke() -> None:
    """compute_blocking_reasons is the promoted, public form of _blocking_reasons.

    Smoke test — full coverage already in earlier tests via decide_row.
    """
    from irc.decision.gates import compute_blocking_reasons

    reasons = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="blocked_no_proxy",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
    )
    assert reasons == ["venue_blocked"]
    assert compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="direct",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
    ) == []
