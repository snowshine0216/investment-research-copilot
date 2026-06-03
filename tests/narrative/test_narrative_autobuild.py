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


from irc.schemas.universe import Instrument  # noqa: E402


def _instr(iid: str, asset_class: str, *, tracked_index=None, theme=None) -> Instrument:
    return Instrument(
        instrument_id=iid, ticker=iid, name_cn=f"fund-{iid}", asset_class=asset_class,
        market="cn_off_exchange", currency="cny",
        tracked_index=tracked_index, theme=theme,
    )


def test_fund_level_eligible_only_for_provider_symbol_kinds(monkeypatch) -> None:
    # us_etf → qdii_us with provider_symbol → eligible
    us = _instr("000U", "us_etf")
    assert NA._fund_level_eligible_target(_shortlist_row("000U", "us_etf"), us, con=object()) \
        is not None
    # cn_equity_fund → active_fund → NOT a fund-level kind → ineligible
    act = _instr("000A", "cn_equity_fund")
    assert NA._fund_level_eligible_target(_shortlist_row("000A", "cn_equity_fund"), act,
                                          con=object()) is None
    # qdii row WITHOUT a tracked_index/theme/provider_symbol → terminal default
    # (broad_index "unknown" carries no provider_symbol) → ineligible
    bare = _instr("000Z", "cn_etf")  # bare cn_etf → terminal default, no provider_symbol
    assert NA._fund_level_eligible_target(_shortlist_row("000Z", "cn_etf"), bare,
                                          con=object()) is None


def test_fund_level_target_resolves_via_instr_no_io() -> None:
    # tracked_index drives the resolution; instr carries the routing keys (RD-3).
    instr = _instr("000B", "cn_etf", tracked_index="csi300")
    target = NA._fund_level_eligible_target(_shortlist_row("000B", "cn_etf"), instr,
                                            con=object())
    assert target is not None
    assert target.provider_symbol == "000B"  # provider_symbol = instrument_id
    assert target.kind in NA._FUND_LEVEL_KINDS or target.kind in (
        "qdii_us", "qdii_hk", "qdii_global",
    )


from irc.fundamentals.types import (  # noqa: E402
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
    ThesisEvidence,
)


def _fund_level_snap(fund_id: str, quarter: str, *, sentinel: bool = False) -> FundLevelSnapshot:
    if sentinel:
        return FundLevelSnapshot(
            fund_id=fund_id, nav_report=None, announcements=(), evidence=(),
            source_report_quarter="",
            cache_probed_at="",
            evidence_gaps=("qdii_information_unavailable",),
        )
    nav_ev = ThesisEvidence(
        type="snapshot", source=fund_id, url="", date="2026-03-15",
        summary="NAV=4.5 @ 2026-03-15", scope="instrument", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=None, constituent_key=None,
    )
    info_ev = ThesisEvidence(
        type="filing", source=fund_id, url="", date="2026-03-20",
        summary="分红公告", scope="instrument", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=None, constituent_key=None,
    )
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=FundNavReport(
            fund_id=fund_id, fund_name=fund_id, latest_nav=4.5,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 4.5),), source_report_quarter=quarter,
        ),
        announcements=(FundAnnouncement(
            fund_id=fund_id, title="x", topic="dividend", date="2026-03-20",
            report_id="AN1"),),
        evidence=(nav_ev, info_ev),
        source_report_quarter=quarter, cache_probed_at="",
    )


def _passive_target(iid: str) -> LookthroughTarget:
    return LookthroughTarget(kind="broad_index", key=iid, display_cn=f"etf-{iid}",
                             provider_symbol=iid)


def test_fund_level_build_one_writes_nav_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000B", "2026Q1"))
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append((snap, root)))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert len(written) == 1
    snap, root = written[0]
    assert snap.cache_probed_at == "2026-06-02"  # replace(), frozen-safe
    assert root == tmp_path


def test_fund_level_build_one_skips_qdii_sentinel(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000Q", "2026Q1",
                                                                sentinel=True))
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000Q"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # qdii_information_unavailable gap → no write


def test_fund_level_build_one_skips_empty_quarter(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _fund_level_snap("000B", "2026Q1"))
    # Override to return snap with empty source_report_quarter
    from dataclasses import replace as dc_replace

    def _empty_quarter_snap(t, *, provider):
        snap = _fund_level_snap("000B", "2026Q1")
        return dc_replace(snap, source_report_quarter="", nav_report=None)

    monkeypatch.setattr(NA, "build_snapshot", _empty_quarter_snap)
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache",
                        lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # empty quarter → no write (path-collapse guard, AC9)


def test_fund_level_build_one_swallows_exception(tmp_path, monkeypatch) -> None:
    def _boom(t, *, provider):
        raise RuntimeError("akshare down")

    monkeypatch.setattr(NA, "build_snapshot", _boom)
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []  # AC10 — degrades, never raises


def test_fund_level_build_one_skips_non_fund_level_snapshot(tmp_path, monkeypatch) -> None:
    # builder returns the wrong type → no write, no crash
    monkeypatch.setattr(NA, "build_snapshot",
                        lambda t, *, provider: _snap("000B", "2026Q1"))  # ActiveFundSnapshot
    written: list = []
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: written.append(snap))
    NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                       data_dir=tmp_path, today_iso="2026-06-02")
    assert written == []


def test_fund_level_build_one_reraises_fetch_budget(tmp_path, monkeypatch) -> None:
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan

    plan = FetchPlan(active_fund_misses=0, active_fund_stale=0, passive_misses=0,
                     passive_stale=0, top_n=10, fund_level_misses=1)

    def _budget_boom(t, *, provider):
        raise FetchBudgetExceeded(plan, 4, 1)

    monkeypatch.setattr(NA, "build_snapshot", _budget_boom)
    monkeypatch.setattr(NA, "write_nav_cache", lambda snap, root: None)
    with pytest.raises(FetchBudgetExceeded):
        NA._build_and_cache_fund_level_one(_passive_target("000B"), provider=object(),
                                           data_dir=tmp_path, today_iso="2026-06-02")


def test_fund_level_missing_excludes_cached_nav(tmp_path, monkeypatch) -> None:
    instr_idx = {
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
        "000C": _instr("000C", "cn_etf", tracked_index="csi300"),
    }
    shortlist = (_shortlist_row("000B", "cn_etf"), _shortlist_row("000C", "cn_etf"))
    # 000B has a cached nav snapshot; 000C does not.
    monkeypatch.setattr(
        NA, "_load_latest_nav_cached",
        lambda fund_id, root: _fund_level_snap("000B", "2026Q1") if fund_id == "000B" else None,
    )
    missing = NA._fund_level_eligible_missing(shortlist, instr_index=instr_idx,
                                              con=object(), data_dir=tmp_path)
    assert tuple(t.provider_symbol for _, t in missing) == ("000C",)


def test_fund_level_missing_excludes_active_and_bare_rows(tmp_path, monkeypatch) -> None:
    instr_idx = {
        "000A": _instr("000A", "cn_equity_fund"),
        "000Z": _instr("000Z", "cn_etf"),  # bare → terminal default, no provider_symbol
    }
    shortlist = (_shortlist_row("000A", "cn_equity_fund"), _shortlist_row("000Z", "cn_etf"))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    missing = NA._fund_level_eligible_missing(shortlist, instr_index=instr_idx,
                                              con=object(), data_dir=tmp_path)
    assert missing == ()  # active → item 001; bare cn_etf → no provider_symbol


def test_passive_autobuild_builds_eligible_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
        "000A": _instr("000A", "cn_equity_fund"),
    }
    shortlist = (_shortlist_row("000B", "cn_etf"), _shortlist_row("000A", "cn_equity_fund"))
    NA.autobuild_fund_level_funds(shortlist, provider=object(), instr_index=instr_idx,
                                  con=object(), data_dir=tmp_path, today_iso="2026-06-02")
    assert built == ["000B"]  # active row never built by the passive path (AC14)


def test_passive_kill_switch_disables_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                  instr_index=instr_idx, con=object(),
                                  data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC8


def test_passive_skips_when_nav_cache_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached",
                        lambda fund_id, root: _fund_level_snap(fund_id, "2026Q1"))
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                  instr_index=instr_idx, con=object(),
                                  data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC3 — cache present → zero builds


def test_shared_budget_guard_raises_before_any_build(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "1")  # per_fund_level = 4 > 1
    built: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: built.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {"000B": _instr("000B", "cn_etf", tracked_index="csi300")}
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_fund_level_funds((_shortlist_row("000B", "cn_etf"),), provider=object(),
                                      instr_index=instr_idx, con=object(),
                                      data_dir=tmp_path, today_iso="2026-06-02")
    assert built == []  # AC11 — raised pre-build


def test_shared_budget_counts_active_and_fund_level_together(tmp_path, monkeypatch) -> None:
    # RD-7a: one shared plan. 1 active (35) + 1 fund_level (4) = 39; budget 38 → raise.
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "38")
    abuilt: list[str] = []
    fbuilt: list[str] = []
    monkeypatch.setattr(NA, "_build_and_cache_one",
                        lambda target, **k: abuilt.append(target.provider_symbol))
    monkeypatch.setattr(NA, "_build_and_cache_fund_level_one",
                        lambda target, **k: fbuilt.append(target.provider_symbol))
    monkeypatch.setattr(NA, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(NA, "_load_latest_nav_cached", lambda fund_id, root: None)
    instr_idx = {
        "000A": _instr("000A", "cn_equity_fund"),
        "000B": _instr("000B", "cn_etf", tracked_index="csi300"),
    }
    shortlist = (_shortlist_row("000A", "cn_equity_fund"), _shortlist_row("000B", "cn_etf"))
    with pytest.raises(NA.FetchBudgetExceeded):
        NA.autobuild_narrative(shortlist, provider=object(), instr_index=instr_idx,
                               con=object(), quarter="2026Q1", data_dir=tmp_path,
                               today_iso="2026-06-02")
    assert abuilt == [] and fbuilt == []  # both sub-paths blocked pre-build


from pathlib import Path as _Path  # noqa: E402

_REPO_ROOT = _Path(__file__).resolve().parents[2]  # tests/narrative/ → repo root


def test_passive_autobuild_no_live_network_marker() -> None:
    """AC13 — module contains no direct AkShare import (fetch goes via build_snapshot)."""
    src = (_REPO_ROOT / "src/irc/commands/narrative_autobuild.py").read_text(encoding="utf-8")
    assert "import akshare" not in src
    assert "akshare" not in src  # no direct akshare reference; fetch is via build_snapshot


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
