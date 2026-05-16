from __future__ import annotations

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.rejections import build_discovery_rejections
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


def _row(iid: str, asset_class: str, theme: str | None = None, name: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid,
        ticker=iid,
        market="cn_on_exchange",
        name_cn=name or iid,
        asset_class=asset_class,
        currency="cny",
        tracked_index=None,
        theme=theme,
        venue_required=(),
    )


def test_build_discovery_rejections_hard_filter_rows() -> None:
    universe = (
        _row("159352", "cn_etf", "broad", "A500ETF南方"),
        _row("510300", "cn_etf", "broad", "华泰柏瑞沪深300ETF"),
    )
    hard = HardFilterResult(
        passed=(universe[1],),
        rejected=(Rejection("159352", ("inception 1.6y < 3.0y",)),),
    )
    quality = HardFilterResult(passed=(universe[1],), rejected=())
    bucketed = RoleBucketResult(
        buckets={"core_cn_equity": (universe[1],)},
        relaxed_roles=(),
        failed_roles=(),
    )

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    assert list(out.columns) == [
        "stage", "instrument_id", "ticker", "name_cn",
        "asset_class", "theme", "role", "reasons",
    ]
    records = out.to_dict("records")
    assert {
        "stage": "hard_filter",
        "instrument_id": "159352",
        "ticker": "159352",
        "name_cn": "A500ETF南方",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reasons": "inception 1.6y < 3.0y",
    } in records


def test_build_discovery_rejections_quality_filter_rows() -> None:
    universe = (_row("588000", "cn_etf", "broad", "科创50ETF华夏"),)
    hard = HardFilterResult(passed=universe, rejected=())
    quality = HardFilterResult(
        passed=(),
        rejected=(Rejection("588000", ("drawdown_3y 0.388 > 0.28",)),),
    )
    bucketed = RoleBucketResult(buckets={}, relaxed_roles=(), failed_roles=())

    out = build_discovery_rejections(universe, hard, quality, bucketed)

    records = out.to_dict("records")
    assert {
        "stage": "quality_filter",
        "instrument_id": "588000",
        "ticker": "588000",
        "name_cn": "科创50ETF华夏",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reasons": "drawdown_3y 0.388 > 0.28",
    } in records
