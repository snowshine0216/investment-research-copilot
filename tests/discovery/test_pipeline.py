from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.discovery.universe import UniverseRow
from irc.discovery.pipeline import run_discovery, _refs_for_instrument


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
