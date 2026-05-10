from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.discovery.universe import UniverseRow
from irc.discovery.pipeline import run_discovery, _refs_for_instrument, _index_refs_by_instrument


def _row(iid: str, asset_class: str, tracked: str | None = None, theme: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, theme=theme, venue_required=(),
    )


def test_refs_for_instrument_filters_by_id() -> None:
    pool = (
        "akshare:prices:VTI:2024-05-01",
        "akshare:nav_history:VTI:2024-04-30",
        "akshare:prices:OTHER:2024-05-01",
    )
    out = _refs_for_instrument("VTI", pool)
    assert "akshare:prices:OTHER:2024-05-01" not in out
    assert all(":VTI:" in r for r in out)


def test_refs_for_instrument_caps_at_limit() -> None:
    pool = tuple(f"akshare:prices:VTI:2024-{m:02d}-01" for m in range(1, 13))
    out = _refs_for_instrument("VTI", pool, limit=5)
    assert len(out) == 5


def test_refs_for_instrument_sorts_by_date_desc() -> None:
    pool = (
        "akshare:prices:VTI:2024-01-01",
        "akshare:prices:VTI:2024-12-31",
        "akshare:prices:VTI:2024-06-15",
    )
    out = _refs_for_instrument("VTI", pool)
    assert out[0].endswith("2024-12-31")
    assert out[-1].endswith("2024-01-01")


def test_index_refs_by_instrument_groups_sorts_caps_and_ignores_malformed_refs() -> None:
    pool = (
        "akshare:prices:VTI:2024-01-01",
        "akshare:prices:QQQ:2024-03-01",
        "malformed-ref",
        "akshare:prices:VTI:2024-12-31",
    )

    out = _index_refs_by_instrument(pool, limit=1)

    assert out == {
        "QQQ": ("akshare:prices:QQQ:2024-03-01",),
        "VTI": ("akshare:prices:VTI:2024-12-31",),
    }


@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_passes_only_per_instrument_refs(mock_writer, tmp_path: Path) -> None:
    """write_reason must receive refs filtered to its own candidate's instrument_id."""
    mock_writer.return_value = MagicMock(
        instrument_id="VTI", reason_text="x", cited_refs=("akshare:prices:VTI:2024-05-01",),
        prompt_tokens=10, completion_tokens=5,
    )
    universe = (_row("VTI", "us_etf", "S&P 500"),)
    metadata = pd.DataFrame([{
        "instrument_id": "VTI", "inception_years": 10,
        "aum_cny": 1e9, "expense_ratio": 0.001, "daily_volume_cny": 5e8,
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "VTI", "drawdown_3y": 0.15,
        "tracking_error": 0.001, "manager_tenure_years": 10,
    }])
    pool = (
        "akshare:prices:VTI:2024-05-01",
        "akshare:prices:OTHER:2024-05-01",
        "akshare:nav_history:VTI:2024-04-30",
    )
    run_discovery(
        universe=universe, metadata=metadata, metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None, cfg_discovery=None,
        route=MagicMock(), peer_summary="x", macro_snapshot="x",
        raw_ref_pool=pool,
    )
    mock_writer.assert_called_once()
    ctx = mock_writer.call_args.args[1] if mock_writer.call_args.args else mock_writer.call_args.kwargs["ctx"]
    assert "akshare:prices:OTHER:2024-05-01" not in ctx.raw_refs
    assert all(":VTI:" in r for r in ctx.raw_refs)


@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_returns_dataframe_with_role_and_reason(mock_writer, tmp_path: Path) -> None:
    mock_writer.return_value = MagicMock(
        instrument_id="VTI", reason_text="solid", cited_refs=("ref1",),
        prompt_tokens=10, completion_tokens=5,
    )
    universe = (_row("VTI", "us_etf", "S&P 500"),)
    metadata = pd.DataFrame([{
        "instrument_id": "VTI", "inception_years": 10,
        "aum_cny": 1e9, "expense_ratio": 0.001, "daily_volume_cny": 5e8,
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "VTI", "drawdown_3y": 0.15,
        "tracking_error": 0.001, "manager_tenure_years": 10,
    }])
    out = run_discovery(
        universe=universe,
        metadata=metadata, metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None, cfg_discovery=None,
        route=MagicMock(), peer_summary="x", macro_snapshot="x", raw_ref_pool=("ref1",),
    )
    assert isinstance(out, pd.DataFrame)
    assert {"instrument_id", "role", "reason_text", "cited_refs"} <= set(out.columns)
    assert out.iloc[0]["role"] == "core_us_equity"


@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_respects_excluded_themes_before_reason_generation(mock_writer) -> None:
    universe = (_row("512170", "cn_etf", "中证医疗", theme="healthcare"),)
    metadata = pd.DataFrame([{
        "instrument_id": "512170", "inception_years": 10,
        "aum_cny": 1e9, "expense_ratio": 0.001, "daily_volume_cny": 5e8,
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "512170", "drawdown_3y": 0.15,
        "tracking_error": 0.001, "manager_tenure_years": 10,
    }])

    out = run_discovery(
        universe=universe,
        metadata=metadata,
        metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None,
        cfg_discovery=None,
        route=MagicMock(),
        peer_summary="x",
        macro_snapshot="x",
        raw_ref_pool=("akshare:prices:512170:2026-05-06",),
        excluded_themes=("healthcare",),
    )

    assert out.empty
    mock_writer.assert_not_called()


import time
from unittest.mock import patch
from irc.discovery.pipeline import run_discover_with_reasons


def _slow_reason(*a, **kw):
    time.sleep(0.3)
    return "ok"


@patch("irc.discovery.pipeline.write_reason", side_effect=_slow_reason)
def test_reasons_run_in_parallel(mock_w):
    candidates = [{"role": "r1", "instrument_id": f"I{i}"} for i in range(8)]
    t0 = time.monotonic()
    out = run_discover_with_reasons(candidates=candidates, route=None, max_workers=8)
    elapsed = time.monotonic() - t0
    assert len(out) == 8
    assert elapsed < 0.9  # 8 × 0.3s sequential = 2.4s; parallel ≤ ~0.5s


@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_can_return_diagnostics(mock_writer) -> None:
    from irc.discovery.pipeline import run_discovery_with_diagnostics

    mock_writer.return_value = MagicMock(
        instrument_id="003095",
        reason_text="healthcare active fund",
        cited_refs=(),
        prompt_tokens=10,
        completion_tokens=5,
    )
    universe = (_row("003095", "cn_equity_fund", None, None),)
    metadata = pd.DataFrame([{
        "instrument_id": "003095", "inception_years": 5,
        "aum_cny": 1e9, "expense_ratio": 0.012, "daily_volume_cny": 0,
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "003095", "drawdown_3y": 0.15,
        "tracking_error": None, "manager_tenure_years": 5,
    }])

    result = run_discovery_with_diagnostics(
        universe=universe,
        metadata=metadata,
        metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None,
        cfg_discovery=None,
        route=MagicMock(),
        peer_summary="x",
        macro_snapshot="x",
        raw_ref_pool=(),
    )

    assert result.watchlist["instrument_id"].tolist() == ["003095"]
    assert {"universe", "hard_filter", "quality_filter", "role_bucket"}.issubset(
        set(result.diagnostics["stage"])
    )
