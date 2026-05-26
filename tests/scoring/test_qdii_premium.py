from __future__ import annotations

import pytest

from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES, qdii_premium_for_row


def test_qdii_asset_classes_is_frozenset_with_three_members() -> None:
    """_QDII_ASSET_CLASSES is the canonical immutable set; consumers import it."""
    assert isinstance(_QDII_ASSET_CLASSES, frozenset)
    assert _QDII_ASSET_CLASSES == frozenset({"us_etf", "hk_etf", "qdii_global"})


class _StubFetcher:
    """Records calls so tests can assert the fetcher is/isn't invoked."""

    def __init__(self, return_value: float | None = 0.0292) -> None:
        self.return_value = return_value
        self.calls: list[str] = []

    def __call__(self, symbol: str) -> float | None:
        self.calls.append(symbol)
        return self.return_value


def test_returns_none_for_non_qdii_asset_class() -> None:
    """Non-QDII rows must not stamp the field — fetcher must not be called."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="cn_equity_fund",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="000001",
    )
    assert out is None
    assert fetcher.calls == []


def test_returns_zero_for_qdii_off_exchange_without_calling_fetcher() -> None:
    """Off-exchange QDII feeders transact at NAV; synthetic 0.0 is correct."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="017641",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_qdii_global_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="qdii_global",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="019547",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_hk_etf_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="161716",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_invokes_fetcher_for_qdii_on_exchange_us_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0292)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="513650",
    )
    assert out == 0.0292
    assert fetcher.calls == ["513650"]


def test_invokes_fetcher_for_qdii_on_exchange_hk_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0079)
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="159691",
    )
    assert out == 0.0079
    assert fetcher.calls == ["159691"]


def test_propagates_none_from_fetcher() -> None:
    """When AkShare returns no row, the resolver propagates None."""
    fetcher = _StubFetcher(return_value=None)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="999999",
    )
    assert out is None
    assert fetcher.calls == ["999999"]


from unittest.mock import MagicMock, patch

import pandas as pd

from irc.schemas.scoring import ScoringConfig


def _scoring_cfg() -> ScoringConfig:
    return ScoringConfig.model_validate({
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60,
            "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_stamps_qdii_premium_pct_when_resolver_provided(
    mock_macro,
) -> None:
    """AC6: run_scoring invokes the resolver per QDII row and stamps the result."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([
        {"instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
         "market": "cn_on_exchange", "role": "core_us_equity",
         "cited_refs": "r1", "tracked_index": ""},
        {"instrument_id": "000001", "name_cn": "华夏成长", "asset_class": "cn_equity_fund",
         "market": "cn_off_exchange", "role": "core_cn_equity",
         "cited_refs": "r2", "tracked_index": ""},
    ])
    metrics = pd.DataFrame([
        {"instrument_id": "513650", "expense_ratio": 0.006,
         "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
         "vol_1y": 0.18, "downside_capture": 0.9,
         "aum_stability_pct": 0.05, "manager_tenure_years": 8,
         "holdings_concentration_top10": 0.25},
        {"instrument_id": "000001", "expense_ratio": 0.015,
         "premium_discount_pct": 0.0, "drawdown_3y": 0.20,
         "vol_1y": 0.20, "downside_capture": 1.0,
         "aum_stability_pct": 0.05, "manager_tenure_years": 5,
         "holdings_concentration_top10": 0.30},
    ])
    resolver_calls: list[tuple[str, str, str]] = []

    def fake_resolver(asset_class: str, market: str, symbol: str) -> float | None:
        resolver_calls.append((asset_class, market, symbol))
        if asset_class == "us_etf":
            return 0.0292
        return None

    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
        qdii_premium_resolver=fake_resolver,
    )
    by_id = {s["instrument_id"]: s for s in out["scores"]}
    assert by_id["513650"]["qdii_premium_pct"] == pytest.approx(0.0292)
    assert "qdii_premium_pct" not in by_id["000001"]
    assert resolver_calls == [("us_etf", "cn_on_exchange", "513650")]


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_omits_qdii_premium_pct_when_no_resolver(mock_macro) -> None:
    """No resolver → no qdii_premium_pct key (back-compat)."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([{
        "instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
        "market": "cn_on_exchange", "role": "core_us_equity",
        "cited_refs": "r1", "tracked_index": "",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "513650", "expense_ratio": 0.006,
        "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
        "vol_1y": 0.18, "downside_capture": 0.9,
        "aum_stability_pct": 0.05, "manager_tenure_years": 8,
        "holdings_concentration_top10": 0.25,
    }])
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert "qdii_premium_pct" not in out["scores"][0]


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_omits_qdii_premium_pct_when_resolver_returns_none(
    mock_macro,
) -> None:
    """Resolver returning None → key absent (existing serialiser convention)."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([{
        "instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
        "market": "cn_on_exchange", "role": "core_us_equity",
        "cited_refs": "r1", "tracked_index": "",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "513650", "expense_ratio": 0.006,
        "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
        "vol_1y": 0.18, "downside_capture": 0.9,
        "aum_stability_pct": 0.05, "manager_tenure_years": 8,
        "holdings_concentration_top10": 0.25,
    }])
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
        qdii_premium_resolver=lambda ac, mk, sym: None,
    )
    assert "qdii_premium_pct" not in out["scores"][0]


def test_qdii_asset_classes_defined_exactly_once_in_src() -> None:
    """AC21: the constant lives in qdii_premium.py only; other modules import."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "grep", "-l", "_QDII_ASSET_CLASSES.*=.*frozenset", "src/"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    matching_files = [
        line for line in result.stdout.strip().splitlines() if line
    ]
    assert matching_files == ["src/irc/scoring/qdii_premium.py"], (
        f"_QDII_ASSET_CLASSES must be defined in exactly one file, found: {matching_files!r}"
    )
