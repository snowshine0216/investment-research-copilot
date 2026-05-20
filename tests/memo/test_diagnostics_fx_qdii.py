"""FX / QDII premium diagnostic lines (item 014, 2026-05-19)."""
from __future__ import annotations

from irc.memo.diagnostics import compose_fx_qdii_lines


def _alloc(rows: list[dict]) -> dict:
    return {"selected_instruments": rows}


def test_qdii_below_floor_emits_no_lines() -> None:
    alloc = _alloc([
        {"instrument_id": "017641", "asset_class": "us_etf", "target_weight": 0.10},
        {"instrument_id": "G", "asset_class": "gold", "target_weight": 0.20},
    ])
    assert compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45)) == ()


def test_qdii_above_floor_emits_three_lines() -> None:
    """The 2026-05-19 reality: ~25% in us_etf via QDII."""
    alloc = _alloc([
        {"instrument_id": "017641", "asset_class": "us_etf", "target_weight": 0.097},
        {"instrument_id": "050025", "asset_class": "us_etf", "target_weight": 0.056},
        {"instrument_id": "018043", "asset_class": "us_etf", "target_weight": 0.052},
        {"instrument_id": "019172", "asset_class": "us_etf", "target_weight": 0.045},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert len(lines) == 3
    assert "外汇与QDII敞口提醒" in lines[0]
    # 0.097 + 0.056 + 0.052 + 0.045 = 0.25
    assert "25.0%" in lines[0]
    assert "溢价/折价" in lines[1]
    assert "对冲成本" in lines[2]


def test_qdii_within_usd_tolerance_says_so() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert "落在" in lines[0]
    assert "超出" not in lines[0]


def test_qdii_above_usd_tolerance_flags_exceeded() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.50},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert "超出" in lines[0]


def test_qdii_no_tolerance_still_emits_header() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=None)
    assert len(lines) == 3
    assert "外汇与QDII敞口提醒" in lines[0]


def test_hk_etf_counts_toward_qdii() -> None:
    """hk_etf in this codebase is also QDII-feeder."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "hk_etf", "target_weight": 0.15},
        {"instrument_id": "Y", "asset_class": "us_etf", "target_weight": 0.10},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert lines  # 25% combined
    assert "25.0%" in lines[0]


def test_cn_classes_dont_count() -> None:
    alloc = _alloc([
        {"instrument_id": "G", "asset_class": "gold", "target_weight": 0.30},
        {"instrument_id": "B", "asset_class": "cn_bond_fund", "target_weight": 0.30},
    ])
    assert compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45)) == ()


def test_no_alloc_returns_empty() -> None:
    assert compose_fx_qdii_lines(None, usd_tolerance=(0.25, 0.45)) == ()
    assert compose_fx_qdii_lines({}, usd_tolerance=(0.25, 0.45)) == ()


def test_accept_unhedged_within_tolerance_says_policy_allows() -> None:
    """E4 (2026-05-20): when prefs declare fx_hedge.policy='accept_unhedged'
    and QDII weight is within USD tolerance, the hedge line should reflect
    that this is a policy choice, not a missing data feed."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=(0.25, 0.45), fx_hedge_policy="accept_unhedged",
    )
    assert len(lines) == 3
    assert "未配置" not in lines[2]
    assert "政策" in lines[2] or "policy" in lines[2].lower()
    assert "未对冲" in lines[2]


def test_accept_unhedged_above_tolerance_still_flags() -> None:
    """Policy 'accept_unhedged' only excuses exposure within the configured
    tolerance band. If USD weight breaches the upper bound, the hedge line
    must still warn — otherwise the policy becomes a blanket override."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.50},
    ])
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=(0.25, 0.45), fx_hedge_policy="accept_unhedged",
    )
    assert len(lines) == 3
    assert "超出" in lines[0]
    assert "超出容忍带" in lines[2] or "超出" in lines[2]


def test_accept_unhedged_without_tolerance_omits_band_claim() -> None:
    """Pre-PR review P2: when policy='accept_unhedged' and usd_tolerance is None,
    the hedge line must NOT claim "落在容忍带内" (no band exists). Should fall
    back to a band-agnostic policy acknowledgement."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=None, fx_hedge_policy="accept_unhedged",
    )
    assert len(lines) == 3
    assert "容忍带内" not in lines[2]
    assert "政策" in lines[2]
    assert "未对冲" in lines[2]
