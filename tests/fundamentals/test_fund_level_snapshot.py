"""Unit tests for fund-level snapshot builders (item 005 F3/F4)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.snapshot import (
    _build_qdii_sentinel_snapshot,
    build_snapshot,
)
from irc.fundamentals.types import (
    FundLevelSnapshot,
    LookthroughTarget,
)


@pytest.mark.parametrize(
    "kind", ["qdii_us", "qdii_hk", "qdii_global"],
)
def test_qdii_sentinel_zero_fetch(kind: str) -> None:
    """No AkShare call should fire for any QDII kind."""
    target = LookthroughTarget(
        kind=kind, key=f"key_{kind}", display_cn="x",
        provider_symbol="ignored",
    )
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        snap = _build_qdii_sentinel_snapshot(target)
    assert mocked.call_count == 0
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.nav_report is None
    assert snap.announcements == ()
    assert snap.evidence == ()
    assert snap.evidence_gaps == ("qdii_information_unavailable",)


def test_qdii_sentinel_fund_id_fallback_to_key() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "qdii_us:sp500"


def test_qdii_sentinel_prefers_provider_symbol_when_present() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="513500",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "513500"


def test_build_snapshot_routes_all_qdii_kinds_to_sentinel() -> None:
    for kind in ("qdii_us", "qdii_hk", "qdii_global"):
        target = LookthroughTarget(kind=kind, key="x", display_cn="x")
        with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
            snap = build_snapshot(target)
        assert isinstance(snap, FundLevelSnapshot)
        assert snap.evidence_gaps == ("qdii_information_unavailable",)
        assert mocked.call_count == 0
