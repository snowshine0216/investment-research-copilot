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


from irc.fundamentals.types import ActiveFundSnapshot  # noqa: E402


def _snap(fund_id: str, quarter: str) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )


def test_build_one_writes_cache_with_probed_at(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, top_n, provider: _snap("000A", "2026Q1"))
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append((snap, root)))
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert len(written) == 1
    snap, root = written[0]
    assert snap.cache_probed_at == "2026-06-02"
    assert root == tmp_path


def test_build_one_skips_write_on_empty_quarter(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, top_n, provider: _snap("000A", ""))
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert written == []  # empty quarter → no write (path-collapse guard)


def test_build_one_swallows_builder_exception(tmp_path, monkeypatch) -> None:
    target = NA._target_for_row(_shortlist_row("000A"))

    def _boom(t, *, top_n, provider):
        raise RuntimeError("akshare down")

    monkeypatch.setattr(NA, "build_snapshot", _boom)
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append(snap))
    # must NOT raise
    NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                            today_iso="2026-06-02")
    assert written == []


import pytest  # noqa: E402


def test_skips_etf_rows_builds_only_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    shortlist = (
        _shortlist_row("000A", "cn_equity_fund"),
        _shortlist_row("000B", "cn_etf"),
    )
    NA.autobuild_active_funds(shortlist, provider=object(), quarter="2026Q1",
                              data_dir=tmp_path, today_iso="2026-06-02")
    assert built == ["000A"]  # cn_etf never built (AC1)


def test_skips_when_resolved_quarter_cache_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    # cache hit for the resolved quarter → zero builds (AC2)
    monkeypatch.setattr(NA, "load_active_fund_cache",
                        lambda iid, q, root: _snap(iid, q))
    NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                              quarter="2026Q1", data_dir=tmp_path,
                              today_iso="2026-06-02")
    assert built == []


def test_kill_switch_disables_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                              quarter="2026Q1", data_dir=tmp_path,
                              today_iso="2026-06-02")
    assert built == []  # AC4


def test_budget_guard_raises_before_any_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "1")  # per_active = 1 + 10*3 + 4 = 35 > 1
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_active_funds((_shortlist_row("000A"),), provider=object(),
                                  quarter="2026Q1", data_dir=tmp_path,
                                  today_iso="2026-06-02")
    assert built == []  # raised BEFORE any build (AC7)


from pathlib import Path as _Path  # noqa: E402

_REPO_ROOT = _Path(__file__).resolve().parents[2]  # tests/narrative/ → repo root


def test_module_has_no_forbidden_indicator() -> None:
    src = (_REPO_ROOT / "src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "基金概况" not in src


def test_module_never_writes_budget_exhausted_sentinel() -> None:
    src = (_REPO_ROOT / "src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "fetch_budget_exhausted" not in src


def test_build_one_reraises_fetch_budget_exceeded(tmp_path, monkeypatch) -> None:
    """P1: FetchBudgetExceeded must propagate out, not degrade."""
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan

    target = NA._target_for_row(_shortlist_row("000A"))
    plan = FetchPlan(active_fund_misses=1, active_fund_stale=0,
                     passive_misses=0, passive_stale=0, top_n=10)

    def _budget_boom(t, *, top_n, provider):
        raise FetchBudgetExceeded(plan, 35, 1)

    monkeypatch.setattr(NA, "build_snapshot", _budget_boom)
    written: list = []
    monkeypatch.setattr(NA, "write_active_fund_cache",
                        lambda snap, root: written.append(snap))
    with pytest.raises(FetchBudgetExceeded):
        NA._build_and_cache_one(target, provider=object(), data_dir=tmp_path,
                                today_iso="2026-06-02")
    assert written == []  # re-raised before any write
