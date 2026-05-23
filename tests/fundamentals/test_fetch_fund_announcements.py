"""Unit tests for fetch_fund_announcements (mocked _ak_call against item-004 fixtures)."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_fundamentals import fetch_fund_announcements
from irc.fundamentals.types import FundAnnouncement


_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "akshare"


def _load_fixture(name: str) -> pd.DataFrame:
    body = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    rows = body["rows"]
    df = pd.DataFrame(rows)
    # Convert 公告日期 from ISO str (as captured in JSON) back to datetime.date,
    # matching AkShare's live behaviour.
    if "公告日期" in df.columns:
        df["公告日期"] = df["公告日期"].apply(
            lambda s: _dt.date.fromisoformat(s) if isinstance(s, str) and len(s) == 10 else s
        )
    return df


def _mock_3_endpoints_for(fund_id: str):
    """Return a side_effect callable for _ak_call that resolves the 3 endpoints."""
    dividend = _load_fixture(f"fund_announcement_dividend_em_{fund_id}.json")
    report = _load_fixture(f"fund_announcement_report_em_{fund_id}.json")
    personnel = _load_fixture(f"fund_announcement_personnel_em_{fund_id}.json")

    def _side(fn_name, **kw):
        if fn_name == "fund_announcement_dividend_em":
            return dividend
        if fn_name == "fund_announcement_report_em":
            return report
        if fn_name == "fund_announcement_personnel_em":
            return personnel
        raise AssertionError(f"unexpected _ak_call: {fn_name}")
    return _side


def test_fetch_fund_announcements_518880_union_shape() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ) as mocked:
        out = fetch_fund_announcements("518880")
    assert mocked.call_count == 3
    assert isinstance(out, tuple)
    for a in out:
        assert isinstance(a, FundAnnouncement)
        assert a.fund_id == "518880"
        assert a.topic in {"dividend", "report", "personnel"}
        # ISO date shape.
        assert len(a.date) == 10
        assert a.date[4] == "-" and a.date[7] == "-"
        assert a.report_id  # non-empty


def test_fetch_fund_announcements_calls_3_endpoints_in_order() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ) as mocked:
        fetch_fund_announcements("518880")
    fns = [args[0] for args, _kw in mocked.call_args_list]
    assert fns == [
        "fund_announcement_dividend_em",
        "fund_announcement_report_em",
        "fund_announcement_personnel_em",
    ]


def test_fetch_fund_announcements_sorted_by_date_desc_report_id_asc() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("518880"),
    ):
        out = fetch_fund_announcements("518880")
    # Date descending; tie-break by report_id ascending.
    for prev, curr in zip(out, out[1:]):
        if prev.date == curr.date:
            assert prev.report_id <= curr.report_id
        else:
            assert prev.date > curr.date


def test_fetch_fund_announcements_dedup_by_report_id() -> None:
    """If two endpoints return the same 报告ID, the unioned tuple keeps one entry,
    with topic determined by call order (dividend > report > personnel)."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["dup-via-dividend"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": ["DUP1"],
    })
    report = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["dup-via-report"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": ["DUP1"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"],
        "公告标题": ["unique-personnel"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 2)],
        "报告ID": ["UNI1"],
    })

    def _side(fn_name, **kw):
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_report_em": report,
            "fund_announcement_personnel_em": personnel,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    by_id = {a.report_id: a for a in out}
    assert set(by_id.keys()) == {"DUP1", "UNI1"}
    # First-observed endpoint (dividend) wins.
    assert by_id["DUP1"].topic == "dividend"
    assert by_id["DUP1"].title == "dup-via-dividend"


def test_fetch_fund_announcements_endpoint_exception_degrades_to_empty() -> None:
    """Per-endpoint failure does NOT raise; remaining endpoints still queried."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)], "报告ID": ["AN1"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["y"], "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 2)], "报告ID": ["AN2"],
    })

    def _side(fn_name, **kw):
        if fn_name == "fund_announcement_report_em":
            raise ConnectionError("east 502")
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_personnel_em": personnel,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    assert len(out) == 2
    assert {a.report_id for a in out} == {"AN1", "AN2"}


def test_fetch_fund_announcements_all_endpoints_fail_returns_empty() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=RuntimeError("boom"),
    ):
        out = fetch_fund_announcements("518880")
    assert out == ()


def test_fetch_fund_announcements_string_date_passthrough() -> None:
    """If 公告日期 arrives as ISO str, adapter still produces ISO str output."""
    dividend = pd.DataFrame({
        "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
        "公告日期": ["2024-04-15"], "报告ID": ["AN1"],
    })
    empty = pd.DataFrame()

    def _side(fn_name, **kw):
        return {
            "fund_announcement_dividend_em": dividend,
            "fund_announcement_report_em": empty,
            "fund_announcement_personnel_em": empty,
        }[fn_name]

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_side,
    ):
        out = fetch_fund_announcements("518880")
    assert len(out) == 1
    assert out[0].date == "2024-04-15"


def test_fetch_fund_announcements_000001_fixture_shape() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("000001"),
    ):
        out = fetch_fund_announcements("000001")
    assert len(out) > 0
    assert all(a.fund_id == "000001" for a in out)


def test_fetch_fund_announcements_005827_fixture_shape() -> None:
    """Regression: active funds CAN call this adapter (shape-only check)."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_mock_3_endpoints_for("005827"),
    ):
        out = fetch_fund_announcements("005827")
    assert len(out) > 0
    assert all(a.fund_id == "005827" for a in out)
