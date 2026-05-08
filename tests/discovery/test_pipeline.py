from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.discovery.universe import UniverseRow
from irc.discovery.pipeline import run_discovery


def _row(iid: str, asset_class: str, tracked: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, venue_required=(),
    )


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
