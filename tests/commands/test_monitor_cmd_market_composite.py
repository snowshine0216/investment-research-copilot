from __future__ import annotations
import json
import pandas as pd
from irc.commands import monitor_cmd
from irc.commands.monitor_cmd import _make_view
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc,
)


def _fund():
    return MonitorFund(id="519069", name_cn="x", market="CN",
                       analysis_profile="active_cn_equity", themes=(),
                       constituent_news=False,
                       weights={"trend": .4, "flow": .2, "macro_tilt": .4},
                       bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.0)


def _signal():
    contribs = (
        FactorContribution("trend", .5, .8, .4, 1.0, True, ""),
        FactorContribution("flow", .2, .0, .0, 1.0, True, ""),
        FactorContribution("macro_tilt", .3, 1.0, .3, 1.0, True, ""),
    )
    return SignalRecord("519069", "ok", "ADD_BIAS", 0.7, 1.0, 1.0,
                        ("price-momentum", "capital-flow", "news"), contribs, ())


def test_make_view_populates_market_view():
    fund = _fund()
    view = _make_view(fund, None, _signal(), (), NarrativeDoc("519069", (), (), (), "ok"), ())
    assert view.market_view is not None
    assert view.market_view.eligible_market_factors == 2  # trend + flow (macro excluded)
    assert view.market_view.news_delta != 0.0


def test_build_bias_timeline_dedups_and_bounds(tmp_path):
    led = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    led.parent.mkdir(parents=True)
    rows = [
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-29T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-29T13:00:00+08:00", "manifest_versions": {"engine": "3"}},
        {"run_date": "2026-06-30", "fund_id": "519069", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-30T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
    ]
    led.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    tl = monitor_cmd._build_bias_timeline(tmp_path)
    assert tl.run_dates == ("2026-06-29", "2026-06-30")
    # dedup: latest written_at wins for 2026-06-29 → NEUTRAL
    fund_row = dict(tl.rows)["519069"]
    assert fund_row[0][0] == "NEUTRAL"   # deduped 06-29
    assert fund_row[1][0] == "NEUTRAL"   # 06-30


def test_build_bias_timeline_missing_ledger_empty(tmp_path):
    tl = monitor_cmd._build_bias_timeline(tmp_path)
    assert tl.run_dates == () and tl.rows == ()


def test_make_view_populates_purchase_tag():
    """_make_view with a purchase_table containing the fund → purchase_tag set."""
    fund = _fund()
    table = pd.DataFrame([{"基金代码": "519069", "申购状态": "暂停申购", "日累计限定金额": 1e11}])
    view = _make_view(fund, None, _signal(), (), NarrativeDoc("519069", (), (), (), "ok"), (),
                      purchase_table=table)
    assert view.purchase_tag == "限购"


def test_make_view_purchase_tag_none_when_no_table():
    """_make_view with no purchase_table → purchase_tag is None."""
    fund = _fund()
    view = _make_view(fund, None, _signal(), (), NarrativeDoc("519069", (), (), (), "ok"), ())
    assert view.purchase_tag is None
