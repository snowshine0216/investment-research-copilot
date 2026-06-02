from __future__ import annotations

from irc.commands import narrative_autobuild as NA


def test_autobuild_on_default_true(monkeypatch) -> None:
    monkeypatch.delenv("IRC_NARRATIVE_AUTOBUILD", raising=False)
    assert NA._narrative_autobuild_on() is True


def test_autobuild_off_when_env_zero(monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    assert NA._narrative_autobuild_on() is False


from irc.fundamentals.types import LookthroughTarget  # noqa: E402
from irc.narrative.schemas import Holding, OverlapResult, ShortlistRow  # noqa: E402


def _shortlist_row(iid: str, asset_class: str = "cn_equity_fund") -> ShortlistRow:
    ov = OverlapResult(basket_weight_pct=22.0, overlap_count=3,
                       matched_symbols=(), industry_credit_symbols=())
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class=asset_class,
        overlap=ov,
        holdings=(Holding(symbol="601899", name_cn="紫金矿业", weight_pct=38.0),),
    )


def test_eligible_only_for_cn_equity_fund() -> None:
    assert NA._is_eligible(_shortlist_row("000A", "cn_equity_fund")) is True
    assert NA._is_eligible(_shortlist_row("000B", "cn_etf")) is False
    assert NA._is_eligible(_shortlist_row("000C", "qdii_us")) is False


def test_target_for_row_matches_active_fund_shape() -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    assert target == LookthroughTarget(
        kind="active_fund", key="fund_000A", display_cn="fund-000A",
        provider_symbol="000A",
    )
