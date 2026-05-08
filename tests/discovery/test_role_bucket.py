from __future__ import annotations

from irc.discovery.universe import UniverseRow
from irc.discovery.role_bucket import (
    ROLE_RULES,
    RoleBucketResult,
    bucket_by_role,
)


def _row(iid: str, asset_class: str, tracked: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, venue_required=(),
    )


def test_bucket_assigns_us_etf_to_core_us_equity() -> None:
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_us_equity" in out.buckets
    assert out.buckets["core_us_equity"][0].instrument_id == "VTI"


def test_bucket_assigns_gold_role() -> None:
    rows = (_row("518880", "gold", None),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_gold_hedge" in out.buckets


def test_bucket_relaxed_flag_when_short() -> None:
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert out.relaxed_roles == ("core_us_equity",)


def test_bucket_fail_below_threshold_marks_failed() -> None:
    rows = ()
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert "core_us_equity" in out.failed_roles
