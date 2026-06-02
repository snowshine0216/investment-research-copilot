from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from irc.narrative.holdings_fetch import fetch_top_holdings
from irc.narrative.schemas import Holding


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "股票代码": ["601899", "600362"],
            "股票名称": ["紫金矿业", "江西铜业"],
            "占净值比例": [9.0, 6.0],
            "季度": ["2026Q1", "2026Q1"],
        }
    )


def test_fetch_parses_top_holdings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "irc.narrative.holdings_fetch._ak_call", lambda *a, **k: _fake_df()
    )
    out = fetch_top_holdings("000123", cache_dir=tmp_path)
    assert out[0] == Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0)
    assert len(out) == 2


def test_cache_hit_skips_network(monkeypatch, tmp_path: Path) -> None:
    calls = {"n": 0}

    def _counting(*a, **k):  # noqa: ANN001
        calls["n"] += 1
        return _fake_df()

    monkeypatch.setattr("irc.narrative.holdings_fetch._ak_call", _counting)
    fetch_top_holdings("000123", cache_dir=tmp_path)
    fetch_top_holdings("000123", cache_dir=tmp_path)
    assert calls["n"] == 1  # second call served from cache


def test_empty_or_failed_returns_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "irc.narrative.holdings_fetch._ak_call",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert fetch_top_holdings("000999", cache_dir=tmp_path) == ()


# ── Live double-gated (CONTEXT.md "Live test gate") ──────────────────────────
_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"


@pytest.mark.live_akshare
@pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare")
def test_fetch_top_holdings_live(tmp_path: Path) -> None:
    # 005827 — active CN equity fund used as the live sanity symbol elsewhere.
    out = fetch_top_holdings("005827", cache_dir=tmp_path)
    assert isinstance(out, tuple)
    if out:
        assert all(isinstance(h, Holding) for h in out)
        assert all(0.0 <= h.weight_pct <= 100.0 for h in out)
