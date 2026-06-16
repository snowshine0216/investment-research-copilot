from __future__ import annotations
from pathlib import Path
from irc.commands import monitor_cmd
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.types import MonitorFund


class _Cfg:
    class history:
        minimum_observations = 2


def _fund(profile="gold"):
    return MonitorFund(id="008986", name_cn="测试", market="CN", analysis_profile=profile,
                       themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def test_process_fund_returns_three_tuple_with_bundle(monkeypatch, tmp_path: Path):
    # Stub all edges so no network/LLM fires; non-lookthrough → constituent legs empty.
    monkeypatch.setattr(monitor_cmd, "nav_series_for", lambda fid: None)
    monkeypatch.setattr(monitor_cmd, "build_evidence_pool", lambda fund, repo_root: ())

    class _Imp:
        impacts = ()
        status = "empty_pool"
        cost_entries = ()

    monkeypatch.setattr(monitor_cmd, "gather_impacts",
                        lambda **kw: _Imp())

    class _Narr:
        from irc.monitor.types import NarrativeDoc as _ND
        doc = _ND("008986", (), (), (), "empty_pool")
        cost_entries = ()

    monkeypatch.setattr(monitor_cmd, "gather_narrative", lambda **kw: _Narr())

    out = monitor_cmd._process_fund(_fund(), _Cfg(), tmp_path, object())
    assert len(out) == 3
    view, costs, bundle = out
    assert isinstance(view, FundView)
    assert isinstance(bundle, FundTraceBundle)
    assert bundle.fund_id == "008986"
    assert bundle.constituent_impacts == () and bundle.constituent_pool == ()
