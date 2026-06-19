from __future__ import annotations
from pathlib import Path
from irc.monitor.holding_metrics import build_holding_metrics, HoldingMetric


def test_build_holding_metrics_assembles_from_loaded_inputs():
    # Pure assembly helper — NO I/O. Top holdings + pre-loaded series in → metrics out.
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": (("2026-06-16", 4.0),) * 20}
    metrics = build_holding_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    assert isinstance(metrics[0], HoldingMetric)
    assert metrics[0].flow_score == 1.0
