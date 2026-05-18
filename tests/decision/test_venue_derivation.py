from __future__ import annotations

from irc.decision.gates import derive_venue_status, decide_row


def test_derive_returns_direct_when_venues_overlap_and_trade_missing():
    status = derive_venue_status(
        trade=None,
        venue_required=["cmb_fund"],
        available_venues=["cmb_fund", "cmb_gold"],
    )
    assert status == "direct"


def test_derive_returns_blocked_when_no_overlap_and_no_proxy():
    status = derive_venue_status(
        trade=None,
        venue_required=["cn_brokerage"],
        available_venues=["cmb_fund"],
    )
    assert status == "blocked_no_proxy"


def test_derive_returns_proxy_when_no_overlap_but_proxy_exists():
    status = derive_venue_status(
        trade=None,
        venue_required=["cn_brokerage"],
        available_venues=["cmb_fund"],
        proxy_id="000176",
    )
    assert status == "proxy_available"


def test_derive_returns_unknown_when_available_venues_empty():
    status = derive_venue_status(
        trade=None,
        venue_required=["cmb_fund"],
        available_venues=[],
    )
    assert status == "unknown"


def test_derive_returns_unknown_when_venue_required_missing():
    status = derive_venue_status(
        trade=None,
        venue_required=None,
        available_venues=["cmb_fund"],
    )
    assert status == "unknown"


def test_derive_defers_to_trade_when_provided():
    # When a trade exists, the legacy trade-based status wins — derived
    # context is ignored. This preserves today's behavior for the rows
    # that go through allocation.
    trade = {"target": "X", "venue_compatible": True, "proxy_id": None}
    status = derive_venue_status(
        trade=trade,
        venue_required=["cn_brokerage"],  # would say blocked
        available_venues=["cmb_fund"],
    )
    assert status == "direct"


def test_decide_row_threads_venue_context_when_trade_missing():
    score = {
        "instrument_id": "X1", "asset_class": "cn_equity_fund",
        "conviction": "med", "data_completeness": 1.0, "missing_data": [],
        "action": "watch",
    }
    row = decide_row(
        score=score,
        allocation_selected=False,
        target_weight_valid=True,
        trade=None,
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        venue_required=["cmb_fund"],
        available_venues=["cmb_fund", "cmb_gold"],
    )
    assert row["venue_status"] == "direct"
    # Watch row with a derived venue_status doesn't change decision_status;
    # but the venue is now precise.
    assert row["decision_status"] == "watch_only"
