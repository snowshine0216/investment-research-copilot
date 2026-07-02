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
    monkeypatch.setattr(monitor_cmd, "build_evidence_pool", lambda fund, **k: ())

    class _Imp:
        impacts = ()
        status = "empty_pool"
        cost_entries = ()

    monkeypatch.setattr(monitor_cmd, "gather_impacts",
                        lambda **kw: _Imp())

    out = monitor_cmd._process_fund(_fund(), _Cfg(), tmp_path, object())
    assert len(out) == 3
    view, costs, bundle = out
    assert isinstance(view, FundView)
    assert isinstance(bundle, FundTraceBundle)
    assert bundle.fund_id == "008986"
    assert bundle.constituent_impacts == () and bundle.constituent_pool == ()


def test_eval_trace_schema_version_is_6():
    from irc.monitor.eval.trace import build_eval_trace
    trace = build_eval_trace((), engine_version="3", run_date="2026-07-02")
    assert trace["schema_version"] == "6"


def test_eval_trace_carries_run_level_macro_narrative_field():
    from irc.monitor.eval.trace import build_eval_trace
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    from irc.monitor.types import Claim

    doc = MacroNarrativeDoc(
        blocks=(MacroThemeBlock("us_monetary", (
            Claim("美联储维持利率不变。", "consistent_with", ("abc1234567890def",)),
        )),),
        status="ok",
    )
    trace = build_eval_trace((), engine_version="3", run_date="2026-07-02", macro_narrative=doc)
    assert trace["macro_narrative"]["status"] == "ok"
    assert trace["macro_narrative"]["blocks"][0]["theme"] == "us_monetary"
    assert trace["macro_narrative"]["blocks"][0]["claims"][0]["claim"] == "美联储维持利率不变。"


def test_eval_trace_macro_narrative_absent_defaults_to_none():
    """Additive back-compat: no macro_narrative kwarg passed -> field is still
    present (None), so old readers that .get() it never KeyError, and NEW
    readers see an explicit None rather than a missing key."""
    from irc.monitor.eval.trace import build_eval_trace
    trace = build_eval_trace((), engine_version="3", run_date="2026-07-02")
    assert trace["macro_narrative"] is None


def test_old_trace_without_macro_narrative_field_still_loads():
    """A pre-v3 trace dict (schema_version '5', no macro_narrative key) must
    still be readable via .get() — additive back-compat (spec §2/§5)."""
    old_trace = {"schema_version": "5", "engine_version": "3", "run_date": "2026-06-30",
                 "funds": {}}
    assert old_trace.get("macro_narrative") is None   # never KeyError
