"""_process_fund wires heat restriction inputs from the purchase table (item 003).

Mirrors the constituent-wiring test style: stub every edge except the heat path,
then assert the resulting heat FactorScore. _process_fund must accept the table
as a keyword and default to None (offline / test callers) → heat_no_data.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from irc.commands import monitor_cmd as mc
from irc.monitor.types import MonitorFund


class _MinCfg:
    class history:
        minimum_observations = 2


def _fund(fund_id: str, profile: str = "active_cn_equity") -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="测试", market="cn_off_exchange", analysis_profile=profile,
        themes=(), constituent_news=False, weights={"trend": 1.0},
        bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5,
    )


def _patch_edges(monkeypatch, fund_id: str) -> None:
    """Stub all I/O in _process_fund except the heat path."""
    monkeypatch.setattr(mc, "nav_series_for", lambda fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())

    class _Imp:
        impacts = ()
        status = "empty_pool"
        cost_entries = ()

    monkeypatch.setattr(mc, "gather_impacts", lambda **kw: _Imp())


def _heat_score(view):
    return {s.name: s for s in view.factor_scores}["heat"]


def _table(rows):
    return pd.DataFrame(rows)


def test_process_fund_restricted_fund_gets_crowded_heat(tmp_path: Path, monkeypatch):
    _patch_edges(monkeypatch, "006533")
    table = _table([{"基金代码": "006533", "申购状态": "限大额", "日累计限定金额": 1e5}])
    view, _costs, _bundle = mc._process_fund(
        _fund("006533"), _MinCfg(), tmp_path, object(), purchase_table=table,
    )
    s = _heat_score(view)
    assert s.eligible is True and s.value == -0.5


def test_process_fund_open_fund_gets_calm_heat(tmp_path: Path, monkeypatch):
    _patch_edges(monkeypatch, "000083")
    table = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    view, _costs, _bundle = mc._process_fund(
        _fund("000083"), _MinCfg(), tmp_path, object(), purchase_table=table,
    )
    s = _heat_score(view)
    assert s.eligible is True and s.value == 0.3


def test_process_fund_no_table_defaults_to_heat_no_data(tmp_path: Path, monkeypatch):
    # No purchase_table kwarg → heat_inputs_for yields None → heat_no_data (no break).
    _patch_edges(monkeypatch, "000083")
    view, _costs, _bundle = mc._process_fund(_fund("000083"), _MinCfg(), tmp_path, object())
    s = _heat_score(view)
    assert s.eligible is False and s.reason == "heat_no_data"
