from __future__ import annotations

import pandas as pd

from irc.discovery.diagnostics import build_discovery_diagnostics
from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


def _row(iid: str, asset_class: str, theme: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid,
        ticker=iid,
        market="cn_off_exchange",
        name_cn=iid,
        asset_class=asset_class,
        currency="cny",
        tracked_index=None,
        theme=theme,
        venue_required=(),
    )


def test_build_discovery_diagnostics_counts_universe_passes_rejections_and_roles() -> None:
    universe = (
        _row("003095", "cn_equity_fund", "healthcare"),
        _row("510300", "cn_etf", "broad"),
    )
    hard = HardFilterResult(
        passed=(universe[0],),
        rejected=(Rejection("510300", ("expense_ratio 0.01 > 0.005",)),),
    )
    quality = HardFilterResult(
        passed=(universe[0],),
        rejected=(),
    )
    bucketed = RoleBucketResult(
        buckets={"satellite_cn_healthcare": (universe[0],), "core_cn_equity": ()},
        relaxed_roles=("satellite_cn_healthcare",),
        failed_roles=("core_cn_equity",),
    )

    out = build_discovery_diagnostics(universe, hard, quality, bucketed)

    assert list(out.columns) == ["stage", "status", "asset_class", "theme", "role", "reason", "count"]
    records = out.to_dict("records")
    assert {
        "stage": "universe",
        "status": "input",
        "asset_class": "cn_equity_fund",
        "theme": "healthcare",
        "role": "",
        "reason": "",
        "count": 1,
    } in records
    assert {
        "stage": "hard_filter",
        "status": "rejected",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reason": "expense_ratio 0.01 > 0.005",
        "count": 1,
    } in records
    assert {
        "stage": "role_bucket",
        "status": "failed",
        "asset_class": "",
        "theme": "",
        "role": "core_cn_equity",
        "reason": "below fail_below",
        "count": 0,
    } in records


def test_empty_discovery_diagnostics_keeps_columns() -> None:
    empty_result = HardFilterResult(passed=(), rejected=())
    bucketed = RoleBucketResult(buckets={}, relaxed_roles=(), failed_roles=())

    out = build_discovery_diagnostics((), empty_result, empty_result, bucketed)

    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["stage", "status", "asset_class", "theme", "role", "reason", "count"]
    assert out.empty
