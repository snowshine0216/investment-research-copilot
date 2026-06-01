"""TDD tests for snapshot orchestration + JSON cache.

Fetchers are patched at the snapshot module's import site so each test exercises
the orchestration logic with deterministic fake data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.fundamentals import snapshot
from irc.fundamentals.snapshot import (
    build_snapshot,
    cache_path,
    load_cached_snapshot,
    write_snapshot,
)
from irc.fundamentals.types import (
    BrokerReport,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
)
from irc.opportunity.types import LookthroughTarget


# ---------- registry / build_snapshot ----------


@pytest.fixture
def cn_target_registry(monkeypatch):
    """Pin 白酒指数 to a CN index spec for the duration of the test."""
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "白酒指数",
        snapshot._TargetSpec(kind="cn_index", code="399997"),
    )


def test_build_snapshot_cn_index_dispatches_to_akshare(monkeypatch, cn_target_registry):
    constituents = (
        Constituent(symbol="600519.SH", name="贵州茅台", weight=0.40, market="cn"),
        Constituent(symbol="000858.SZ", name="五粮液", weight=0.30, market="cn"),
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-29",
        revenue_yoy=0.06, net_income_yoy=0.05, gross_margin=0.92,
    )
    report = BrokerReport(
        symbol="600519.SH", broker="中信证券", rating="买入", target_price=None,
        published_iso="2026-05-08", title="一季报点评",
    )
    monkeypatch.setattr(
        snapshot, "fetch_cn_index_constituents", lambda code, *, top_n=10: constituents,
    )

    class _FakeProvider:
        def fetch_filing_digest(self, sym):
            return digest if sym == "600519.SH" else None

        def fetch_broker_reports(self, sym, **_):
            return (report,) if sym == "600519.SH" else ()

        def fetch_index_valuation(self, key):
            return None

    snap = build_snapshot(
        LookthroughTarget("broad_index", "x", "白酒指数"),
        top_n=2, as_of_iso="2026-05-15",
        provider=_FakeProvider(),
    )
    assert isinstance(snap, ConstituentSnapshot)
    assert snap.lookthrough_target == "白酒指数"
    assert snap.as_of_iso == "2026-05-15"
    assert snap.constituents == constituents
    # Filing for 600519 returned a digest; 000858 returned None → recorded as failure
    assert snap.filings == (digest,)
    assert any("000858" in reason for reason in snap.failure_reasons)
    assert snap.broker_reports == (report,)


def test_build_snapshot_unknown_target_returns_empty_with_failure_reason() -> None:
    snap = build_snapshot(LookthroughTarget("broad_index", "x", "never-seen-target"), top_n=5, as_of_iso="2026-05-15")
    assert snap.constituents == ()
    assert snap.filings == ()
    assert snap.broker_reports == ()
    assert any("never-seen-target" in r for r in snap.failure_reasons)


def test_build_snapshot_us_symbols_dispatches_to_edgar(monkeypatch):
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "Mag7",
        snapshot._TargetSpec(kind="us_symbols", symbols=("AAPL", "MSFT")),
    )
    aapl_digest = FilingDigest(
        symbol="AAPL", fiscal_period="2026Q2", filed_at_iso="2026-05-02",
        revenue_yoy=0.06, net_income_yoy=0.09, gross_margin=0.45,
    )
    monkeypatch.setattr(
        snapshot, "fetch_us_filing_digest_diag",
        lambda sym: (aapl_digest, None) if sym == "AAPL" else (None, "network"),
    )
    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_us now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "x", "Mag7"), as_of_iso="2026-05-15")
    assert snap.constituents == (
        Constituent(symbol="AAPL", name="AAPL", weight=0.0, market="us"),
        Constituent(symbol="MSFT", name="MSFT", weight=0.0, market="us"),
    )
    assert snap.filings == (aapl_digest,)
    assert any("MSFT" in r for r in snap.failure_reasons)
    assert snap.broker_reports == ()


def test_build_snapshot_hk_symbols_dispatches_to_hkex(monkeypatch):
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "HK-Tech",
        snapshot._TargetSpec(kind="hk_symbols", symbols=("0700.HK",)),
    )
    tencent_digest = FilingDigest(
        symbol="0700.HK", fiscal_period="2026Q1", filed_at_iso="2026-03-31",
        revenue_yoy=0.22, net_income_yoy=0.14, gross_margin=0.57,
    )
    monkeypatch.setattr(
        snapshot, "fetch_hk_filing_digest",
        lambda sym: tencent_digest if sym == "0700.HK" else None,
    )
    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_hk now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "x", "HK-Tech"), as_of_iso="2026-05-15")
    assert snap.filings == (tencent_digest,)
    assert snap.broker_reports == ()


def test_build_snapshot_hk_index_dispatches_to_hk_constituents(monkeypatch):
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "HSI-test",
        snapshot._TargetSpec(kind="hk_index", code="恒生指数"),
    )
    constituents = (
        Constituent(symbol="00700.HK", name="腾讯控股", weight=0.10, market="hk"),
        Constituent(symbol="09988.HK", name="阿里巴巴-W", weight=0.08, market="hk"),
    )
    digest = FilingDigest(
        symbol="00700.HK", fiscal_period="2026Q1", filed_at_iso="2026-03-31",
        revenue_yoy=0.22, net_income_yoy=0.14, gross_margin=0.57,
    )
    monkeypatch.setattr(
        snapshot, "fetch_hk_index_constituents",
        lambda code, *, top_n=10: constituents if code == "恒生指数" else (),
    )
    monkeypatch.setattr(
        snapshot, "fetch_hk_filing_digest",
        lambda sym: digest if sym == "00700.HK" else None,
    )

    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_hk now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "x", "HSI-test"), top_n=2, as_of_iso="2026-05-16")

    assert snap.lookthrough_target == "HSI-test"
    assert snap.constituents == constituents
    assert snap.filings == (digest,)
    assert any("09988.HK" in r for r in snap.failure_reasons)


# ---------- cache_path / round-trip ----------


def test_cache_path_format(tmp_path: Path) -> None:
    path = cache_path("半导体指数", "2026Q1", tmp_path)
    assert path == tmp_path / "fundamentals" / "2026Q1" / "半导体指数.json"


def test_write_snapshot_creates_directory_and_returns_path(tmp_path: Path) -> None:
    snap = ConstituentSnapshot(
        lookthrough_target="白酒指数",
        as_of_iso="2026-05-15",
        constituents=(
            Constituent(symbol="600519.SH", name="贵州茅台", weight=0.07, market="cn"),
        ),
        filings=(),
        broker_reports=(),
    )
    out = write_snapshot(snap, tmp_path)
    assert out.exists()
    assert "白酒指数.json" in str(out)
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["lookthrough_target"] == "白酒指数"
    assert body["constituents"][0]["symbol"] == "600519.SH"


def test_write_then_load_round_trips_all_fields(tmp_path: Path) -> None:
    snap = ConstituentSnapshot(
        lookthrough_target="半导体指数",
        as_of_iso="2026-05-15",
        constituents=(
            Constituent(symbol="688981.SH", name="中芯国际", weight=0.12, market="cn"),
        ),
        filings=(
            FilingDigest(
                symbol="688981.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
                revenue_yoy=0.18, net_income_yoy=-0.05, gross_margin=0.21,
                guidance_text="产能利用率提升", source_url="https://example.com/a",
            ),
        ),
        broker_reports=(
            BrokerReport(
                symbol="688981.SH", broker="中信证券", rating="增持",
                target_price=98.5, published_iso="2026-05-10", title="季报点评",
                source_url="https://example.com/r",
            ),
        ),
        failure_reasons=("edgar 503",),
    )
    write_snapshot(snap, tmp_path)
    loaded = load_cached_snapshot("半导体指数", "2026Q1", tmp_path)
    assert loaded == snap


def test_load_cached_snapshot_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_cached_snapshot("missing", "2026Q1", tmp_path) is None


def test_load_cached_snapshot_returns_none_when_malformed(tmp_path: Path) -> None:
    path = cache_path("bad", "2026Q1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_cached_snapshot("bad", "2026Q1", tmp_path) is None


def test_load_cached_snapshot_returns_none_when_schema_drift(tmp_path: Path) -> None:
    path = cache_path("drift", "2026Q1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    assert load_cached_snapshot("drift", "2026Q1", tmp_path) is None


def test_load_latest_cached_snapshot_picks_newest_quarter(tmp_path: Path) -> None:
    from irc.fundamentals.snapshot import load_latest_cached_snapshot

    old = ConstituentSnapshot("沪深300", "2026-02-01", (), (), (), ())
    new = ConstituentSnapshot("沪深300", "2026-05-15", (), (), (), ())
    write_snapshot(old, tmp_path)
    write_snapshot(new, tmp_path)

    loaded = load_latest_cached_snapshot("沪深300", tmp_path)

    assert loaded is not None
    assert loaded.as_of_iso == "2026-05-15"


def test_load_latest_cached_snapshot_returns_none_when_absent(tmp_path: Path) -> None:
    from irc.fundamentals.snapshot import load_latest_cached_snapshot

    result = load_latest_cached_snapshot("沪深300", tmp_path)
    assert result is None


# ---------- US snapshot per-symbol error tagging ----------


def test_build_us_snapshot_tags_each_failure_with_error_code(monkeypatch) -> None:
    """When every US symbol fails, failure_reasons must (a) tag each per-symbol
    line with the typed error code and (b) emit one summary line when all
    codes agree."""
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "纳斯达克100",
        snapshot._TargetSpec(kind="us_symbols", symbols=tuple(f"SYM{i}" for i in range(10))),
    )
    monkeypatch.setattr(
        snapshot, "fetch_us_filing_digest_diag",
        lambda sym: (None, "missing_email"),
    )
    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_us now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "nasdaq100", "纳斯达克100"), top_n=10, as_of_iso="2026-05-16")
    assert snap.lookthrough_target == "纳斯达克100"
    assert snap.filings == ()
    per_symbol = [r for r in snap.failure_reasons if r.startswith("missing filing digest:")]
    assert len(per_symbol) == 10
    assert all("(missing_email)" in r for r in per_symbol)
    assert any(r == "all US fetches failed: missing_email" for r in snap.failure_reasons)


def test_build_us_snapshot_mixed_failures_omit_summary(monkeypatch) -> None:
    """Per-symbol tagging happens regardless, but the summary line only fires
    when every symbol shares one cause."""
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "纳斯达克100",
        snapshot._TargetSpec(kind="us_symbols", symbols=("AAPL", "MSFT")),
    )
    def fake_fetch(sym: str):
        if sym == "AAPL":
            return None, "http_4xx"
        return None, "missing_email"
    monkeypatch.setattr(snapshot, "fetch_us_filing_digest_diag", fake_fetch)
    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_us now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "nasdaq100", "纳斯达克100"), top_n=10, as_of_iso="2026-05-16")
    assert any("(http_4xx)" in r for r in snap.failure_reasons)
    assert any("(missing_email)" in r for r in snap.failure_reasons)
    assert not any(r.startswith("all US fetches failed:") for r in snap.failure_reasons)


def test_build_us_snapshot_partial_success(monkeypatch) -> None:
    """Successful symbols populate filings; failed ones still record the cause."""
    good = FilingDigest(
        symbol="AAPL", fiscal_period="2026Q2", filed_at_iso="2026-05-02",
        revenue_yoy=0.06, net_income_yoy=0.05, gross_margin=0.45,
    )
    monkeypatch.setitem(
        snapshot._TARGET_REGISTRY,
        "纳斯达克100",
        snapshot._TargetSpec(kind="us_symbols", symbols=("AAPL", "MSFT")),
    )
    def fake_fetch(sym: str):
        if sym == "AAPL":
            return good, None
        return None, "http_4xx"
    monkeypatch.setattr(snapshot, "fetch_us_filing_digest_diag", fake_fetch)
    # Use broad_index kind (no provider_symbol) to route through legacy registry — qdii_us now sentinels (item 005 F4).
    snap = build_snapshot(LookthroughTarget("broad_index", "nasdaq100", "纳斯达克100"), top_n=10, as_of_iso="2026-05-16")
    assert snap.filings == (good,)
    assert any(r == "missing filing digest: MSFT (http_4xx)" for r in snap.failure_reasons)
    assert not any(r.startswith("all US fetches failed:") for r in snap.failure_reasons)


# ── Item 003: active-fund snapshot tests ──────────────────────────────────────

from irc.fundamentals.types import (  # noqa: E402
    ActiveFundSnapshot, FundHolding, HoldingsResult,
)


def _holdings_result_cn(symbols=("600519", "000333")):
    return HoldingsResult(
        constituents=tuple(
            FundHolding(symbol=s, name_cn=s, weight_pct=10.0 - i,
                        exchange="SH" if s.startswith("6") else "SZ",
                        provider_symbol=s)
            for i, s in enumerate(symbols)
        ),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )


def test_build_snapshot_active_fund_dispatch(monkeypatch) -> None:
    """Active-fund target returns ActiveFundSnapshot via _build_active_fund_snapshot."""
    monkeypatch.setattr(
        snapshot, "fetch_cn_etf_holdings", lambda sym, top_n=10: _holdings_result_cn(),
    )
    monkeypatch.setattr(snapshot, "fetch_cn_stock_news", lambda s, top_k=3: ())

    class _NullProvider:
        def fetch_filing_digest(self, s): return None
        def fetch_broker_reports(self, s, **_): return ()
        def fetch_index_valuation(self, k): return None

    target = LookthroughTarget("active_fund", "fund_005827", "易方达蓝筹精选", "005827")
    out = build_snapshot(target, top_n=10, provider=_NullProvider())
    assert isinstance(out, ActiveFundSnapshot)
    assert out.fund_id == "005827"
    assert out.source_report_quarter == "2024Q1"
    assert len(out.constituent_analyses) == 2


def test_build_snapshot_legacy_string_target_still_works(monkeypatch) -> None:
    """build_snapshot still accepts LookthroughTarget for legacy kinds."""
    target = LookthroughTarget("broad_index", "csi300", "never-seen-target")
    snap = build_snapshot(target, top_n=5, as_of_iso="2026-05-15")
    # Unknown legacy display_cn → failure reason path.
    assert snap.lookthrough_target == "never-seen-target"
    assert snap.failure_reasons


def test_build_snapshot_active_fund_empty_holdings_records_fund_level_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        snapshot, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: HoldingsResult((), "", ""),
    )
    target = LookthroughTarget("active_fund", "fund_005827", "易方达蓝筹精选", "005827")
    out = build_snapshot(target, top_n=10)
    assert isinstance(out, ActiveFundSnapshot)
    assert out.constituent_analyses == ()
    assert any(r.startswith("holdings_fetch_failed:005827") for r in out.fund_level_failure_reasons)


def test_build_snapshot_active_fund_routes_hk_through_hk_adapters(monkeypatch) -> None:
    """HK holdings call fetch_hk_filing_digest + fetch_hk_stock_news; NEVER fetch_cn_broker_reports."""
    hk_only = HoldingsResult(
        constituents=(FundHolding("00700", "腾讯", 9.0, "HK", "00700"),),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    monkeypatch.setattr(snapshot, "fetch_cn_etf_holdings", lambda sym, top_n=10: hk_only)
    cn_broker_called = []

    class _TrackingProvider:
        def fetch_filing_digest(self, s): return None

        def fetch_broker_reports(self, s, **_):
            cn_broker_called.append(s)
            return ()

        def fetch_index_valuation(self, k): return None

    monkeypatch.setattr(snapshot, "fetch_hk_filing_digest", lambda s: None)
    monkeypatch.setattr(snapshot, "fetch_hk_stock_news", lambda s, top_k=3: ())
    target = LookthroughTarget("active_fund", "fund_x", "x", "x")
    build_snapshot(target, top_n=1, provider=_TrackingProvider())
    assert cn_broker_called == []  # never called for HK constituents


def test_build_snapshot_active_fund_records_us_unsupported(monkeypatch) -> None:
    us_only = HoldingsResult(
        constituents=(FundHolding("AAPL", "Apple", 9.0, "US", "AAPL"),),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    monkeypatch.setattr(snapshot, "fetch_cn_etf_holdings", lambda sym, top_n=10: us_only)
    target = LookthroughTarget("active_fund", "fund_x", "x", "x")
    out = build_snapshot(target, top_n=1)
    assert isinstance(out, ActiveFundSnapshot)
    assert "us_evidence_unsupported:AAPL" in out.failure_reasons_by_symbol["AAPL"]


def test_build_active_fund_snapshot_populates_fund_level_evidence(monkeypatch):
    """Item 001: _build_active_fund_snapshot must fetch NAV + announcements
    and stamp them on `fund_level_evidence`."""
    from irc.fundamentals import snapshot as _snap_mod
    from irc.fundamentals.types import (
        FundAnnouncement,
        FundHolding,
        FundNavReport,
        HoldingsResult,
        LookthroughTarget,
    )

    fund_id = "006809"

    def _fake_holdings(provider_symbol: str, *, top_n: int) -> HoldingsResult:
        assert provider_symbol == fund_id
        return HoldingsResult(
            constituents=(
                FundHolding(
                    symbol="00700.HK",
                    name_cn="腾讯控股",
                    weight_pct=10.0,
                    exchange="HK",
                    provider_symbol="00700.HK",
                ),
            ),
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
        )

    def _fake_nav(fid: str) -> FundNavReport:
        assert fid == fund_id
        return FundNavReport(
            fund_id=fid,
            fund_name="泰康香港银行指数A",
            latest_nav=1.2345,
            latest_nav_date="2024-04-15",
            nav_history=(("2024-04-15", 1.2345),),
            source_report_quarter="2024Q1",
        )

    def _fake_announcements(fid: str):
        assert fid == fund_id
        return (
            FundAnnouncement(
                fund_id=fid,
                title="季度报告",
                topic="report",
                date="2024-04-10",
                report_id="REP-1",
            ),
        )

    def _fake_evidence_for_constituent(holding, *, fund_id, provider):
        # HK holding hits the no-filings path in real code; emulate empty.
        return (), [f"filing_fetch_failed:{holding.symbol}:KeyError"], None

    monkeypatch.setattr(_snap_mod, "fetch_cn_etf_holdings", _fake_holdings)
    monkeypatch.setattr(_snap_mod, "fetch_fund_nav_report", _fake_nav)
    monkeypatch.setattr(_snap_mod, "fetch_fund_announcements", _fake_announcements)
    monkeypatch.setattr(
        _snap_mod, "_evidence_for_constituent", _fake_evidence_for_constituent
    )

    from irc.fundamentals.provider import AkShareProvider
    target = LookthroughTarget(
        kind="active_fund",
        key=fund_id,
        display_cn="泰康香港银行指数A",
        provider_symbol=fund_id,
    )
    snap = _snap_mod._build_active_fund_snapshot(target, top_n=10, provider=AkShareProvider())

    assert len(snap.fund_level_evidence) == 2
    kinds = sorted(e.citation_kind for e in snap.fund_level_evidence)
    assert kinds == ["data", "information"]
    for e in snap.fund_level_evidence:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == fund_id
        assert e.parent_fund_id is None
        assert e.constituent_key is None


def test_evidence_for_constituent_returns_cn_digest_third(monkeypatch) -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )

    class _DigestProvider:
        def fetch_filing_digest(self, s): return digest
        def fetch_broker_reports(self, s, **_): return ()
        def fetch_index_valuation(self, k): return None

    monkeypatch.setattr(_snap, "fetch_cn_stock_news", lambda s, top_k=3: ())
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    result = _snap._evidence_for_constituent(holding, fund_id="fund_x", provider=_DigestProvider())
    assert len(result) == 3  # (evidence, failures, digest)
    evidence, failures, returned_digest = result
    assert returned_digest is digest


def test_evidence_for_constituent_digest_none_for_non_cn(monkeypatch) -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding
    from irc.fundamentals.provider import AkShareProvider
    monkeypatch.setattr(_snap, "fetch_hk_filing_digest", lambda s: None)
    monkeypatch.setattr(_snap, "fetch_hk_stock_news", lambda s, top_k=3: ())
    monkeypatch.setattr(_snap, "hk_news_adapter_available", lambda: True)
    holding = FundHolding("0700.HK", "腾讯", 10.0, "HK", "00700")
    evidence, failures, digest = _snap._evidence_for_constituent(
        holding, fund_id="f", provider=AkShareProvider()
    )
    assert digest is None  # HK/US digests are out of scope for ratios (spec non-goal)


def test_one_line_view_appends_ratios_fragment_within_cap() -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    view = _snap._one_line_view(holding, (ev,), digest)
    assert "ROE 18%" in view
    assert "毛利69%" in view
    assert "口径未核实" in view
    assert len(view) <= 60  # AC11 hard cap NOT raised


def test_one_line_view_byte_identical_when_digest_none() -> None:
    # AC11: rows where the fragment is empty/None are byte-stable vs the old behaviour.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    # digest=None → no fragment → byte-identical to the pre-004 join+cap output.
    assert _snap._one_line_view(holding, (ev,), None) == ev.summary[:24][:60]


def test_one_line_view_no_digest_arg_defaults_none() -> None:
    # Back-compat: the third arg is defaulted so unrelated call sites are unaffected.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding
    assert _snap._one_line_view(FundHolding("X", "x", 1.0, "SH", "X"), ()) == "证据获取失败"


def test_one_line_view_omits_ratios_fragment_whole_when_it_overflows_60() -> None:
    """FIX C: if appending the ratios fragment would push the join past 60 chars,
    the fragment must be omitted WHOLE (no dangling '（' or separator)."""
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence

    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    # A filing summary + broker summary that together are long enough that
    # appending the ratios fragment would exceed 60 chars.
    long_filing = "600519.SH 2026Q1 财报已披露（口径未核实）——超长内容"
    ev_filing = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary=long_filing,
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    ev_broker = ThesisEvidence(
        type="broker", source="中信证券", url="", date="2026-04-30",
        summary="中信证券 买入: 一季报点评：强劲增长，维持推荐！",
        scope="constituent", citation_kind="information",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    view = _snap._one_line_view(holding, (ev_filing, ev_broker), digest)

    assert len(view) <= 60  # AC11 hard cap still honoured
    # The ratios fragment must be absent WHOLE: no partial 'ROE'/'毛利' from the fragment,
    # and the view must not end with a dangling separator.
    assert not view.endswith(" · ")
    assert "ROE" not in view
    assert "口径未核实）" not in view  # the fragment's closing token must not appear


def test_one_line_view_includes_fragment_when_it_fits() -> None:
    """FIX C: when the join WITH fragment is ≤60 chars, the fragment IS present."""
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence

    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    # Short filing summary → fragment fits.
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    view = _snap._one_line_view(holding, (ev,), digest)
    assert "ROE 18%" in view
    assert "毛利69%" in view
    assert len(view) <= 60


def test_one_line_view_two_run_byte_stable_for_ratio_bearing_row() -> None:
    # AC11: same digest → byte-identical one_line_view across two calls.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    a = _snap._one_line_view(holding, (ev,), digest)
    b = _snap._one_line_view(holding, (ev,), digest)
    assert a == b
    # AC9: the fragment carries no [ref:...] marker.
    import re
    assert re.search(r"\[ref:[0-9a-f]{16}\]", a) is None
