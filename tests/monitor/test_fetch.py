import pandas as pd
from irc.monitor.fetch import nav_series_for, NavFetchResult


def _fake_df():
    return pd.DataFrame({
        "date": ["2026-06-13", "2026-06-15"],
        "nav": [2.10, 2.13],
        "nav_acc": [3.10, 3.13],
    })


def test_nav_series_uses_acc_with_coalesce():
    res = nav_series_for("008986", fetch=lambda code: _fake_df())
    assert isinstance(res, NavFetchResult)
    assert res.as_of_date == "2026-06-15"
    assert res.latest_nav == 2.13
    # acc-NAV series for performance math
    assert res.acc_series[-1] == ("2026-06-15", 3.13)


def test_nav_acc_null_falls_back_to_nav():
    df = pd.DataFrame({"date": ["2026-06-15"], "nav": [2.13], "nav_acc": [None]})
    res = nav_series_for("008986", fetch=lambda code: df)
    assert res.acc_series[-1] == ("2026-06-15", 2.13)  # COALESCE(nav_acc, nav)


def test_fetch_failure_returns_none(monkeypatch):
    def boom(code):
        raise RuntimeError("akshare down")

    res = nav_series_for("008986", fetch=boom)
    assert res is None


def test_empty_dataframe_returns_none():
    res = nav_series_for("000000", fetch=lambda code: pd.DataFrame())
    assert res is None


def test_fund_id_propagated():
    res = nav_series_for("008986", fetch=lambda code: _fake_df())
    assert res is not None
    assert res.fund_id == "008986"


def test_acc_series_sorted_ascending():
    """Rows may arrive unsorted; acc_series must be in date-ascending order."""
    df = pd.DataFrame({
        "date": ["2026-06-15", "2026-06-13"],
        "nav": [2.13, 2.10],
        "nav_acc": [3.13, 3.10],
    })
    res = nav_series_for("008986", fetch=lambda code: df)
    assert res is not None
    dates = [row[0] for row in res.acc_series]
    assert dates == sorted(dates)
