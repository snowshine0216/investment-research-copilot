from __future__ import annotations

import pandas as pd

from irc.discovery.metrics import merge_discovery_metrics


def test_merge_discovery_metrics_fills_missing_primary_fields_from_fallback() -> None:
    primary = pd.DataFrame([{
        "instrument_id": "006075",
        "drawdown_3y": float("nan"),
        "tracking_error": 0.004,
        "manager_tenure_years": float("nan"),
    }])
    fallback = pd.DataFrame([{
        "instrument_id": "006075",
        "drawdown_3y": 0.18,
        "tracking_error": 0.0,
        "manager_tenure_years": 5.0,
    }])

    merged = merge_discovery_metrics(primary, fallback)
    row = merged.set_index("instrument_id").loc["006075"]

    assert row["drawdown_3y"] == 0.18
    assert row["tracking_error"] == 0.004
    assert row["manager_tenure_years"] == 5.0
