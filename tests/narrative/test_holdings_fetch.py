from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pandas as pd
import pytest

from irc.narrative.holdings_fetch import _parse, _to_holding, fetch_top_holdings
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


# ── Atomic cache write — FIX-1 ───────────────────────────────────────────────


def test_cache_file_is_valid_json_and_round_trips(monkeypatch, tmp_path: Path) -> None:
    """FIX-1: _write_cache must produce a valid JSON file that round-trips
    identically via a second fetch_top_holdings call (confirming atomic write)."""
    monkeypatch.setattr(
        "irc.narrative.holdings_fetch._ak_call", lambda *a, **k: _fake_df()
    )
    first = fetch_top_holdings("000123", cache_dir=tmp_path)
    cache_file = tmp_path / "000123.json"
    assert cache_file.exists(), "cache file must be written after first fetch"
    body = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "holdings" in body, "cache JSON must have 'holdings' key"
    second = fetch_top_holdings("000123", cache_dir=tmp_path)
    assert first == second, "cached round-trip must return identical holdings"


# ── F1: duplicate-symbol dedup in _parse ─────────────────────────────────────


def test_parse_deduplicates_symbol_keeps_highest_weight() -> None:
    """F1: 601899 appearing twice → exactly one Holding for 601899 (highest weight)."""
    df = pd.DataFrame(
        {
            "股票代码": ["601899", "601899", "600362"],
            "股票名称": ["紫金矿业", "紫金矿业", "江西铜业"],
            "占净值比例": [9.0, 5.0, 6.0],  # 601899 dup: 9.0 should win
        }
    )
    result = _parse(df)
    symbols = [h.symbol for h in result]
    assert symbols.count("601899") == 1
    # highest-weight row for 601899 is kept
    zijin = next(h for h in result if h.symbol == "601899")
    assert zijin.weight_pct == 9.0


# ── F2: NaN/inf weight sanitization in _to_holding ───────────────────────────


def test_to_holding_nan_weight_becomes_zero() -> None:
    """F2: NaN in 占净值比例 must not propagate — becomes 0.0."""
    row = pd.Series(
        {"股票代码": "601899", "股票名称": "紫金矿业", "占净值比例": float("nan")}
    )
    h = _to_holding(row)
    assert h.weight_pct == 0.0
    assert not math.isnan(h.weight_pct)


def test_to_holding_inf_weight_becomes_zero() -> None:
    """F2: inf in 占净值比例 must not propagate — becomes 0.0."""
    row = pd.Series(
        {"股票代码": "601899", "股票名称": "紫金矿业", "占净值比例": float("inf")}
    )
    h = _to_holding(row)
    assert h.weight_pct == 0.0


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
