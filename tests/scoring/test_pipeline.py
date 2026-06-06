from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.schemas.scoring import ScoringConfig
from irc.scoring.pipeline import run_scoring


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
def test_pipeline_produces_one_score_per_instrument(mock_macro) -> None:
    mock_macro.return_value = (MagicMock(score=70, raw_refs=("r",), components={}), None)
    watchlist = pd.DataFrame([{
        "instrument_id": "VTI", "name_cn": "VTI", "asset_class": "us_etf",
        "role": "core_us_equity", "cited_refs": "r1", "tracked_index": "S&P 500",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "VTI", "expense_ratio": 0.001,
        "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
        "vol_1y": 0.18, "downside_capture": 0.9,
        "aum_stability_pct": 0.05, "manager_tenure_years": 8,
        "holdings_concentration_top10": 0.25,
    }])
    out, responses = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert "scores" in out
    assert len(out["scores"]) == 1
    assert out["scores"][0]["instrument_id"] == "VTI"
    assert "composite_score" in out["scores"][0]
    assert out["scores"][0]["missing_data"] == []
    assert isinstance(responses, list)


@patch("irc.scoring.pipeline.score_macro_fit")
def test_pipeline_treats_nan_metrics_as_missing(mock_macro) -> None:
    mock_macro.return_value = (MagicMock(score=70, raw_refs=("r",), components={}), None)
    watchlist = pd.DataFrame([{
        "instrument_id": "VTI", "name_cn": "VTI", "asset_class": "us_etf",
        "role": "core_us_equity", "cited_refs": "r1", "tracked_index": "S&P 500",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "VTI", "expense_ratio": float("nan"),
        "premium_discount_pct": float("nan"), "drawdown_3y": float("nan"),
        "vol_1y": float("nan"), "downside_capture": float("nan"),
        "aum_stability_pct": float("nan"), "manager_tenure_years": float("nan"),
        "holdings_concentration_top10": float("nan"),
    }])
    out, _ = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    score = out["scores"][0]
    assert score["data_completeness"] == 0.0
    # us_etf drops aum_stability_pct (universal) and holdings_concentration_top10 (index ETF)
    assert score["missing_data"] == [
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "manager_tenure_years",
    ]
    assert not math.isnan(score["factor_breakdown"]["valuation_cost"]["score"])
    assert not math.isnan(score["factor_breakdown"]["risk"]["score"])
    assert not math.isnan(score["factor_breakdown"]["quality"]["score"])


@patch("irc.scoring.pipeline.score_macro_fit")
def test_pipeline_gold_instrument_completeness_excludes_inapplicable_metrics(mock_macro) -> None:
    """A gold instrument with only the 4 core metrics present should score 1.0 completeness,
    because aum_stability_pct, holdings_concentration_top10, and downside_capture are
    not required for gold."""
    mock_macro.return_value = (MagicMock(score=60, raw_refs=("r",), components={}), None)
    watchlist = pd.DataFrame([{
        "instrument_id": "518880", "name_cn": "黄金ETF", "asset_class": "gold",
        "role": "hedge", "cited_refs": "r1", "tracked_index": "gold_spot",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "518880",
        "expense_ratio": 0.005,
        "premium_discount_pct": 0.0,
        "drawdown_3y": 0.18,
        "vol_1y": 0.25,
        "manager_tenure_years": 7.0,
        # aum_stability_pct, holdings_concentration_top10, downside_capture all absent (NaN)
        "aum_stability_pct": float("nan"),
        "holdings_concentration_top10": float("nan"),
        "downside_capture": float("nan"),
    }])
    out, _ = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    score = out["scores"][0]
    assert score["data_completeness"] == 1.0, (
        f"Expected 1.0 for gold (only core metrics required), got {score['data_completeness']}"
    )
    assert score["missing_data"] == []


@patch("irc.scoring.pipeline.score_macro_fit")
def test_pipeline_empty_watchlist_returns_empty_scores(mock_macro) -> None:
    mock_macro.return_value = (MagicMock(score=50, raw_refs=(), components={}), None)
    watchlist = pd.DataFrame(columns=[
        "instrument_id", "name_cn", "asset_class", "role", "cited_refs", "tracked_index",
    ])
    out, responses = run_scoring(
        watchlist=watchlist, metrics=pd.DataFrame(), news_summaries={},
        regime_summary="neutral", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert out == {"scores": []}
    assert responses == []


@patch("irc.scoring.pipeline.score_macro_fit")
def test_pipeline_instrument_missing_from_metrics_uses_defaults(mock_macro) -> None:
    mock_macro.return_value = (MagicMock(score=50, raw_refs=(), components={}), None)
    watchlist = pd.DataFrame([{
        "instrument_id": "GHOST", "name_cn": "Ghost ETF", "asset_class": "us_etf",
        "role": "core_us_equity", "cited_refs": None, "tracked_index": "S&P 500",
    }])
    out, _ = run_scoring(
        watchlist=watchlist, metrics=pd.DataFrame(), news_summaries={},
        regime_summary="neutral", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert len(out["scores"]) == 1
    assert out["scores"][0]["data_completeness"] == 0.0
    # us_etf drops aum_stability_pct (universal) and holdings_concentration_top10 (index ETF)
    assert out["scores"][0]["missing_data"] == [
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "manager_tenure_years",
    ]


def test_run_scoring_with_non_empty_news_summaries_differentiates_thesis_news():
    """Regression for F4: when news_summaries is non-empty, the thesis_news
    factor must escape the empty-input 50.0 fallback for the matching row.
    Locks the call-site contract at src/irc/scoring/pipeline.py:116-119.
    """
    import pandas as pd

    from irc.config_loader import load_repo_configs
    from irc.scoring.pipeline import run_scoring

    # Two-row watchlist: gold has positive news, cn_bond_fund has none.
    watchlist = pd.DataFrame([
        {
            "instrument_id": "518880",
            "ticker": "518880",
            "name_cn": "黄金ETF",
            "asset_class": "gold",
            "market": "cn_on_exchange",
            "tracked_index": "",
            "cited_refs": "",
            "role": "satellite",
        },
        {
            "instrument_id": "511880",
            "ticker": "511880",
            "name_cn": "国债ETF",
            "asset_class": "cn_bond_fund",
            "market": "cn_on_exchange",
            "tracked_index": "",
            "cited_refs": "",
            "role": "core",
        },
    ])
    metrics = pd.DataFrame([
        {"instrument_id": "518880"},
        {"instrument_id": "511880"},
    ])
    news_summaries = {
        # Hits two _POS terms ("demand", "buy"): momentum +1, base 80.
        "518880": ("Strong demand and central bank buy signals.",),
        # No mapped theme content → fallback path.
        "511880": (),
    }

    # load_repo_configs needs a real repo root for scoring weights; the test
    # repo is the project root itself.
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    bundle = load_repo_configs(repo_root)

    out, _ = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries=news_summaries,
        regime_summary="",
        route=None,  # macro_fit catches None and returns neutral 50
        cfg_scoring=bundle.scoring,
        qdii_premium_resolver=None,
    )
    scores = {row["instrument_id"]: row for row in out["scores"]}

    gold_thesis = scores["518880"]["factor_breakdown"]["thesis_news"]["score"]
    bond_thesis = scores["511880"]["factor_breakdown"]["thesis_news"]["score"]

    # Gold row sees real positive news → must escape the 50.0 fallback.
    assert gold_thesis != 50.0, (
        f"thesis_news for gold should differentiate from 50.0 fallback; got {gold_thesis}"
    )
    # Bond row has empty summaries → preserves the empty-input invariant.
    assert bond_thesis == 50.0, (
        f"thesis_news for cn_bond_fund must preserve 50.0 fallback; got {bond_thesis}"
    )
