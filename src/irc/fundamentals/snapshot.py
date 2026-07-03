"""Constituent snapshot orchestration.

`build_snapshot(target: LookthroughTarget)` composes constituents → filings →
broker reports for one theme by dispatching to the right per-market adapter.
Per-symbol failures get recorded in `failure_reasons`, never raised.

On-disk cache helpers live in `snapshot_cache`; this module re-exports them
for backward compatibility so callers can import from either location.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_etf_holdings,
    fetch_cn_index_constituents,
    fetch_cn_stock_news,
    fetch_fund_announcements,
    fetch_fund_nav_report,
    fetch_hk_index_constituents,
)
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
from irc.fundamentals.edgar_client import (
    fetch_us_filing_digest,  # noqa: F401 — re-exported for callers
    fetch_us_filing_digest_diag,
)
from irc.fundamentals.hkex_client import (
    fetch_hk_filing_digest,
    fetch_hk_stock_news,
    hk_news_adapter_available,
)
from irc.fundamentals.ratios import compute_ratios, ratios_reason_fragment
from irc.fundamentals.snapshot_cache import (  # noqa: F401 — re-exports
    cache_path,
    infer_quarter as _infer_quarter,
    load_cached_snapshot,
    load_latest_cached_snapshot,
    write_snapshot,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    Constituent,
    ConstituentAnalysis,
    ConstituentSnapshot,
    FilingDigest,
    FundHolding,
    FundLevelSnapshot,
    LookthroughTarget,
    ThesisEvidence,
)


@dataclass(frozen=True)
class _TargetSpec:
    """How to resolve a lookthrough_target into per-symbol fetches.

    `kind` is one of: 'cn_index', 'us_symbols', 'hk_symbols'.
    """
    kind: str
    code: str = ""
    symbols: tuple[str, ...] = ()


# Keys MUST equal values produced by
# `irc.opportunity.lookthrough.map_lookthrough(...).display_cn`. The coupling test
# in tests/opportunity/test_lookthrough.py prevents silent drift.
#
# V1 scope: broad CN equity indices only. Sector themes (`半导体`, `医药`, …)
# and QDII targets (`纳斯达克100`, `恒生科技`, …) resolve to `evidence_insufficient`
# thesis_state via the snapshot=None path in opportunity_cmd until their
# corresponding _TargetSpec entries are added.
_TARGET_REGISTRY: dict[str, _TargetSpec] = {
    "沪深300":   _TargetSpec(kind="cn_index", code="000300"),
    "中证500":   _TargetSpec(kind="cn_index", code="000905"),
    "中证1000":  _TargetSpec(kind="cn_index", code="000852"),
    "中证A500":  _TargetSpec(kind="cn_index", code="000510"),  # TODO: verify AkShare code for CSI A500
    "上证50":    _TargetSpec(kind="cn_index", code="000016"),
    "科创50":    _TargetSpec(kind="cn_index", code="000688"),
    "创业板指":  _TargetSpec(kind="cn_index", code="399006"),
    "创业板50":  _TargetSpec(kind="cn_index", code="399673"),  # 创业板50指数
    "中证红利":  _TargetSpec(kind="cn_index", code="000922"),
    "中证红利低波": _TargetSpec(kind="cn_index", code="930740"),
    # Sector indices — verified codes via scripts/verify_sector_index_codes.py (2026-05-16)
    "半导体":   _TargetSpec(kind="cn_index", code="H30184"),
    "医药":     _TargetSpec(kind="cn_index", code="000933"),
    "新能源":   _TargetSpec(kind="cn_index", code="399808"),
    "消费":     _TargetSpec(kind="cn_index", code="000932"),
    "金融":     _TargetSpec(kind="cn_index", code="000934"),
    "军工":     _TargetSpec(kind="cn_index", code="399967"),
    "有色金属": _TargetSpec(kind="cn_index", code="H30202"),
    "房地产":   _TargetSpec(kind="cn_index", code="000952"),
    "国企改革": _TargetSpec(kind="cn_index", code="000861"),
    "科技":     _TargetSpec(kind="cn_index", code="931087"),
    "红利":     _TargetSpec(kind="cn_index", code="000922"),  # 中证红利; maps to dividend theme
    # QDII US — top-10 by index weight as of 2026-05-16; update quarterly.
    # STALENESS_AFTER: 2026-08-16 — after this date, run `irc fundamentals snapshot
    # --target 标普500` and `--target 纳斯达克100` to pick up rebalance changes.
    "标普500": _TargetSpec(kind="us_symbols", symbols=(
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "GOOG", "AVGO", "TSLA",
    )),
    "纳斯达克100": _TargetSpec(kind="us_symbols", symbols=(
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "TSLA", "COST",
    )),
    # US QDII extras — hardcoded top-10 by index weight as of 2026-05-16; update quarterly
    # STALENESS_AFTER: 2026-08-16
    "道琼斯": _TargetSpec(kind="us_symbols", symbols=(
        "UNH", "GS", "MSFT", "HD", "MCD", "CRM", "V", "CAT", "AMGN", "AXP",
    )),
    "美国50": _TargetSpec(kind="us_symbols", symbols=(  # FTSE US 50 (华夏美国50ETF)
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK.B", "AVGO", "JPM",
    )),
    "美股大盘": _TargetSpec(kind="us_symbols", symbols=(  # S&P 500 broad market
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "GOOG", "AVGO", "LLY",
    )),
    # HK QDII indices — hardcoded top-10 by weight (AkShare lacks HK index constituent endpoint)
    # STALENESS_AFTER: 2026-08-16 — refresh quarterly
    "恒生指数": _TargetSpec(kind="hk_symbols", symbols=(
        "00700.HK", "09988.HK", "03690.HK", "01299.HK", "02318.HK",
        "00941.HK", "02388.HK", "01398.HK", "00005.HK", "09999.HK",
    )),
    "恒生科技": _TargetSpec(kind="hk_symbols", symbols=(
        "00700.HK", "09988.HK", "03690.HK", "09618.HK", "09999.HK",
        "09888.HK", "09961.HK", "02015.HK", "09663.HK", "00268.HK",
    )),
    "港股红利": _TargetSpec(kind="hk_symbols", symbols=(
        "00857.HK", "01288.HK", "01088.HK", "02628.HK", "03988.HK",
        "01339.HK", "00386.HK", "00002.HK", "02333.HK", "00881.HK",
    )),
    "中概互联": _TargetSpec(kind="hk_symbols", symbols=(
        "09988.HK", "00700.HK", "09618.HK", "03690.HK", "00241.HK",
        "09961.HK", "09888.HK", "09626.HK", "09999.HK", "09066.HK",
    )),
}

# ISO date after which the hardcoded US index constituent lists should be refreshed.
_US_SYMBOLS_STALE_AFTER = date.fromisoformat("2026-08-16")


def registered_snapshot_targets() -> tuple[str, ...]:
    return tuple(_TARGET_REGISTRY.keys())


def _today_iso() -> str:
    return date.today().isoformat()


def _build_qdii_sentinel_snapshot(target: LookthroughTarget) -> FundLevelSnapshot:
    """In-process sentinel for QDII V1 exclusion. ZERO AkShare calls.

    NOT cached on disk (grill Q5). Item 006's H3 universal-gap invariant
    reads `evidence_gaps=("qdii_information_unavailable",)` and routes the row
    to the discipline failure section. See ADR 0002 §5 F4.
    """
    fund_id = target.provider_symbol or target.key
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        fund_level_failure_reasons=(),
        evidence_gaps=("qdii_information_unavailable",),
    )


_FUND_LEVEL_INFO_CAP = 3


def _build_fund_level_snapshot(target: LookthroughTarget) -> FundLevelSnapshot:
    """Compose NAV (data leg) + announcements (information leg) for non-active
    V1 asset classes (gold, bond, broad_index, sector_theme — when the row IS
    itself a tradeable fund).

    See ADR 0002 §5 (Fund-level engine).
    """
    fund_id = target.provider_symbol
    nav = fetch_fund_nav_report(fund_id)
    anns = fetch_fund_announcements(fund_id)

    evidence: list[ThesisEvidence] = []
    gaps: list[str] = []
    failures: list[str] = []

    # Data leg: ONE evidence record per NAV (re-use existing "snapshot" literal
    # per grill Q4).
    if nav is not None:
        evidence.append(ThesisEvidence(
            type="snapshot",
            source=fund_id,
            url="",
            date=nav.latest_nav_date,
            summary=f"NAV={nav.latest_nav:.4f} @ {nav.latest_nav_date}",
            scope="instrument",
            citation_kind="data",
            owner_instrument_id=fund_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    else:
        gaps.append("fund_nav_unavailable")
        failures.append(f"fund_nav_fetch_failed:{fund_id}")

    # Information leg: up to N announcements (already date-desc / report_id-asc
    # from the adapter; capped at _FUND_LEVEL_INFO_CAP).
    if anns:
        for a in anns[:_FUND_LEVEL_INFO_CAP]:
            evidence.append(ThesisEvidence(
                type="news",
                source=f"fund_announcement_{a.topic}_em",
                url="",
                date=a.date,
                summary=f"[{a.report_id}] {a.title}",
                scope="instrument",
                citation_kind="information",
                owner_instrument_id=fund_id,
                parent_fund_id=None,
                constituent_key=None,
            ))
    else:
        gaps.append("fund_announcements_unavailable")
        failures.append(f"fund_announcements_fetch_failed:{fund_id}")

    quarter = nav.source_report_quarter if nav is not None else ""
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=nav,
        announcements=anns,
        evidence=tuple(evidence),
        source_report_quarter=quarter,
        cache_probed_at=_today_iso(),
        fund_level_failure_reasons=tuple(failures),
        evidence_gaps=tuple(gaps),
    )


_FUND_LEVEL_KINDS: frozenset[str] = frozenset({
    "gold", "bond", "broad_index", "sector_theme",
})


def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
    provider: CnFundamentalsProvider | None = None,
) -> ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot:
    """Compose snapshot for a typed `LookthroughTarget`.

    Dispatch keys off `target.kind` only (ADR 0002 §5):

    | kind                                | Branch                                    |
    |-------------------------------------|-------------------------------------------|
    | active_fund                         | _build_active_fund_snapshot (item 003)    |
    | qdii_us / qdii_hk / qdii_global     | _build_qdii_sentinel_snapshot (F4)        |
    | gold / bond / broad_index /         | _build_fund_level_snapshot (F3)           |
    |  sector_theme — w/ provider_symbol  |                                           |
    | (else / empty provider_symbol)      | _build_legacy_snapshot (display-only)     |
    """
    provider = provider or default_cn_provider()
    timestamp = as_of_iso or _today_iso()
    if target.kind == "active_fund":
        return _build_active_fund_snapshot(target, top_n=top_n, provider=provider)
    if target.kind in ("qdii_us", "qdii_hk", "qdii_global"):
        # Item 016 — QDII funds are CN-registered and DO expose NAV +
        # announcements via the same AkShare endpoints used by gold/bond/
        # broad_index. The legacy sentinel skipped these unconditionally
        # (ADR 0002 §5 F4), which routed every QDII row to the discipline
        # failure section. We now attempt fund-level fetch when the target
        # carries a provider_symbol, falling back to the sentinel only
        # when no fund_id is available (raw-index/global aggregate keys).
        if target.provider_symbol:
            return _build_fund_level_snapshot(target)
        return _build_qdii_sentinel_snapshot(target)
    if target.kind in _FUND_LEVEL_KINDS and target.provider_symbol:
        return _build_fund_level_snapshot(target)
    return _build_legacy_snapshot(
        target.display_cn, top_n=top_n, as_of_iso=timestamp, provider=provider
    )


def _build_legacy_snapshot(
    lookthrough_target: str, *, top_n: int, as_of_iso: str,
    provider: CnFundamentalsProvider,
) -> ConstituentSnapshot:
    """Original `build_snapshot(string)` body, unchanged."""
    spec = _TARGET_REGISTRY.get(lookthrough_target)
    if spec is None:
        return ConstituentSnapshot(
            lookthrough_target=lookthrough_target,
            as_of_iso=as_of_iso,
            constituents=(), filings=(), broker_reports=(),
            failure_reasons=(f"unknown lookthrough_target: {lookthrough_target}",),
        )
    if spec.kind == "cn_index":
        return _build_cn_snapshot(lookthrough_target, spec, top_n, as_of_iso, provider)
    if spec.kind == "us_symbols":
        return _build_us_snapshot(lookthrough_target, spec, as_of_iso)
    if spec.kind == "hk_symbols":
        return _build_hk_snapshot(lookthrough_target, spec, as_of_iso)
    if spec.kind == "hk_index":
        return _build_hk_index_snapshot(lookthrough_target, spec, top_n, as_of_iso)
    return ConstituentSnapshot(
        lookthrough_target=lookthrough_target,
        as_of_iso=as_of_iso,
        constituents=(), filings=(), broker_reports=(),
        failure_reasons=(f"unsupported spec kind: {spec.kind}",),
    )


def _evidence_for_constituent(
    holding: FundHolding,
    *,
    fund_id: str,
    provider: CnFundamentalsProvider,
) -> tuple[tuple[ThesisEvidence, ...], list[str], FilingDigest | None]:
    """Fetch market-routed evidence for one holding.

    Returns (evidence_tuple, failure_reasons_list, cn_filing_digest_or_None).
    The CN digest is threaded out (it is dropped today) so the per-constituent
    ratios fragment can be appended to one_line_view at the call site (item 004).
    HK/US digests are NOT surfaced as ratios (spec non-goal) → digest is None.
    """
    failures: list[str] = []
    evidence: list[ThesisEvidence] = []
    cn_digest: FilingDigest | None = None
    common = dict(
        scope="constituent",
        owner_instrument_id=fund_id,
        parent_fund_id=fund_id,
        constituent_key=holding.symbol,
        holding_weight_pct=holding.weight_pct,
    )
    if holding.exchange in ("SH", "SZ", "BJ"):
        # P1-a: use explicit else on the exception path so _fetch_failed and
        # _empty are mutually exclusive (no double-append).
        _filing_exc = False
        try:
            digest = provider.fetch_filing_digest(holding.symbol)
        except Exception as exc:
            failures.append(f"filing_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            digest = None
            _filing_exc = True
        if not _filing_exc:
            if digest is None:
                failures.append(f"filing_empty:{holding.symbol}")
            else:
                cn_digest = digest
                evidence.append(ThesisEvidence(
                    type="filing", source=digest.symbol,
                    url=digest.source_url, date=digest.filed_at_iso,
                    summary=f"{digest.symbol} {digest.fiscal_period} 财报已披露（口径未核实）",
                    citation_kind="data", **common,
                ))
        _broker_exc = False
        try:
            brokers = provider.fetch_broker_reports(holding.symbol)
        except Exception as exc:
            failures.append(f"broker_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            brokers = ()
            _broker_exc = True
        if not _broker_exc:
            if not brokers:
                failures.append(f"broker_empty:{holding.symbol}")
        for r in brokers[:2]:
            evidence.append(ThesisEvidence(
                type="broker", source=r.broker, url=r.source_url,
                date=r.published_iso, summary=f"{r.broker} {r.rating}: {r.title}".strip(),
                citation_kind="information", **common,
            ))
        # P1-c: fetch_cn_stock_news now re-raises; the except here is the live catch.
        try:
            news = fetch_cn_stock_news(holding.symbol, top_k=3)
        except Exception as exc:
            failures.append(f"news_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            news = ()
        else:
            # P1-a: only append news_empty when no exception fired.
            if not news:
                failures.append(f"news_empty:{holding.symbol}")
        for n in news:
            evidence.append(ThesisEvidence(
                type="news", source=n.source, url=n.url,
                date=n.published_iso, summary=(n.title or n.summary[:120]),
                citation_kind="information", **common,
            ))
    elif holding.exchange == "HK":
        # P1-a: same sentinel pattern for HK filing.
        _hk_filing_exc = False
        try:
            digest = fetch_hk_filing_digest(holding.symbol)
        except Exception as exc:
            failures.append(f"filing_fetch_failed:{holding.symbol}:{type(exc).__name__}")
            digest = None
            _hk_filing_exc = True
        if not _hk_filing_exc:
            if digest is None:
                failures.append(f"filing_empty:{holding.symbol}")
            else:
                evidence.append(ThesisEvidence(
                    type="filing", source=digest.symbol,
                    url=digest.source_url, date=digest.filed_at_iso,
                    summary=f"{digest.symbol} {digest.fiscal_period} 财报已披露（口径未核实）",
                    citation_kind="data", **common,
                ))
        # No HK broker adapter in V1.
        news: tuple = ()
        if not hk_news_adapter_available():
            failures.append(f"hk_news_unsupported_adapter:{holding.symbol}")
        else:
            # P1-c: fetch_hk_stock_news now re-raises; the except here is live.
            try:
                news = fetch_hk_stock_news(holding.symbol, top_k=3)
            except Exception as exc:
                failures.append(f"hk_news_fetch_failed:{holding.symbol}:{type(exc).__name__}")
                news = ()
            else:
                # P1-a: only append hk_news_empty when no exception fired.
                if not news:
                    failures.append(f"hk_news_empty:{holding.symbol}")
        for n in news:
            evidence.append(ThesisEvidence(
                type="news", source=n.source, url=n.url,
                date=n.published_iso, summary=(n.title or n.summary[:120]),
                citation_kind="information", **common,
            ))
    elif holding.exchange == "US":
        failures.append(f"us_evidence_unsupported:{holding.symbol}")
    else:  # UNKNOWN
        failures.append(f"exchange_unknown:{holding.symbol}")
    return tuple(evidence), failures, cn_digest


def _one_line_view(
    holding: FundHolding,
    evidence: tuple[ThesisEvidence, ...],
    cn_digest: FilingDigest | None = None,
) -> str:
    """≤60-char deterministic label. Empty evidence → '证据获取失败'.

    When a CN FilingDigest is supplied (item 004), a compact reason-only ratios
    fragment (ROE / 毛利 today; debt_equity / fcf_yield omitted while None) is
    appended, best-effort within the HARD [:60] cap (NOT raised — AC11). The
    fragment is empty when the digest carries no ROE and no gross_margin, so rows
    without ratios stay byte-identical to the pre-004 output.
    """
    if not evidence:
        return "证据获取失败"
    fragments: list[str] = []
    by_type: dict[str, ThesisEvidence | None] = {"filing": None, "broker": None, "news": None}
    for e in evidence:
        if e.type in by_type and by_type[e.type] is None:
            by_type[e.type] = e
    if by_type["filing"] is not None:
        fragments.append(by_type["filing"].summary[:24])
    if by_type["broker"] is not None:
        fragments.append(by_type["broker"].summary[:18])
    if by_type["news"] is not None:
        fragments.append(by_type["news"].summary[:24])
    if not fragments:
        return "证据获取失败"
    base = " · ".join(fragments)
    if cn_digest is not None:
        ratio_frag = ratios_reason_fragment(compute_ratios(cn_digest))
        if ratio_frag:
            candidate = f"{base} · {ratio_frag}"
            # Append the fragment only if it fits WHOLE within the 60-char cap;
            # a mid-truncated fragment (orphaned '（' or dangling separator) is
            # worse than omitting it entirely (FIX C, item 004).
            if len(candidate) <= 60:
                return candidate
    return base[:60]


def _fetch_active_fund_level_evidence(
    fund_id: str,
) -> tuple[tuple[ThesisEvidence, ...], list[str]]:
    """Fetch fund-level NAV + announcements for an active fund.

    Mirrors the citation shape produced by `_build_fund_level_snapshot`:
    scope="instrument", owner_instrument_id=fund_id, parent_fund_id=None,
    constituent_key=None. Returns (evidence_tuple, failure_reasons_list).
    Item 001 (ADR 0003 §7): Policy B rule 2.5 consumes the data + information
    legs to short-circuit foreign-heavy funds. Per-fund call delta = 4 AkShare
    calls (1 NAV + 3 announcement endpoints, `_FUND_ANN_TOPIC_FNS`); see
    `_fetch_budget` in opportunity_cmd.py (default budget 2000).
    """
    evidence: list[ThesisEvidence] = []
    failures: list[str] = []
    nav = fetch_fund_nav_report(fund_id)
    if nav is not None:
        evidence.append(ThesisEvidence(
            type="snapshot",
            source=fund_id,
            url="",
            date=nav.latest_nav_date,
            summary=f"NAV={nav.latest_nav:.4f} @ {nav.latest_nav_date}",
            scope="instrument",
            citation_kind="data",
            owner_instrument_id=fund_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    else:
        failures.append(f"fund_nav_unavailable:{fund_id}")
    anns = fetch_fund_announcements(fund_id)
    if anns:
        for a in anns[:_FUND_LEVEL_INFO_CAP]:
            evidence.append(ThesisEvidence(
                type="news",
                source=f"fund_announcement_{a.topic}_em",
                url="",
                date=a.date,
                summary=f"[{a.report_id}] {a.title}",
                scope="instrument",
                citation_kind="information",
                owner_instrument_id=fund_id,
                parent_fund_id=None,
                constituent_key=None,
            ))
    else:
        failures.append(f"fund_announcements_unavailable:{fund_id}")
    return tuple(evidence), failures


def _build_active_fund_snapshot(
    target: LookthroughTarget, *, top_n: int, provider: CnFundamentalsProvider,
) -> ActiveFundSnapshot:
    """Fetch holdings then per-constituent evidence per exchange routing.

    Item 001 (ADR 0003 §7): ALWAYS fetches fund-level NAV + announcements so
    Policy B rule 2.5 can short-circuit foreign-heavy funds whose top-N
    holdings are HK/US-listed (and therefore unreachable by the per-holding
    CN filings pipeline).
    """
    fund_id = target.provider_symbol
    holdings = fetch_cn_etf_holdings(target.provider_symbol, top_n=top_n)
    fund_evidence, fund_evidence_failures = _fetch_active_fund_level_evidence(fund_id)
    if not holdings.constituents:
        return ActiveFundSnapshot(
            fund_id=fund_id,
            source_report_date=holdings.source_report_date,
            source_report_quarter=holdings.source_report_quarter,
            cache_probed_at="",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
            fund_level_failure_reasons=(
                f"holdings_fetch_failed:{fund_id}:empty",
            ) + tuple(fund_evidence_failures),
            fund_level_evidence=fund_evidence,
        )
    # P0-5: if quarter parse failed (semi-annual or unparseable text), stamp the
    # fund-level failure reason.  The snapshot is still returned for downstream
    # visibility (item 006 reads fund_level_failure_reasons), but the caller in
    # _build_rows must NOT write the cache when source_report_quarter is empty
    # (to avoid path collapse: data/fundamentals//active_fund/fund_X.json).
    fund_level_failures: list[str] = []
    if not holdings.source_report_quarter:
        fund_level_failures.append(f"holdings_quarter_parse_failed:{fund_id}")
    analyses: list[ConstituentAnalysis] = []
    fail_by_symbol: dict[str, tuple[str, ...]] = {}
    for h in holdings.constituents:
        evidence, failures, _cn_digest = _evidence_for_constituent(
            h, fund_id=fund_id, provider=provider
        )
        if failures:
            fail_by_symbol[h.symbol] = tuple(sorted(failures))
        analyses.append(ConstituentAnalysis(
            symbol=h.symbol,
            name_cn=h.name_cn,
            weight_pct=h.weight_pct,
            evidence=evidence,
            failure_reasons=tuple(sorted(failures)),
            one_line_view=_one_line_view(h, evidence, _cn_digest),
        ))
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date=holdings.source_report_date,
        source_report_quarter=holdings.source_report_quarter,
        cache_probed_at="",
        constituent_analyses=tuple(analyses),
        failure_reasons_by_symbol=fail_by_symbol,
        fund_level_failure_reasons=tuple(fund_level_failures) + tuple(fund_evidence_failures),
        fund_level_evidence=fund_evidence,
    )


def _build_cn_snapshot(
    target: str, spec: _TargetSpec, top_n: int, as_of_iso: str,
    provider: CnFundamentalsProvider,
) -> ConstituentSnapshot:
    constituents = fetch_cn_index_constituents(spec.code, top_n=top_n)
    if not constituents:
        return ConstituentSnapshot(
            lookthrough_target=target, as_of_iso=as_of_iso,
            constituents=(), filings=(), broker_reports=(),
            failure_reasons=(f"cn_index {spec.code} returned no constituents",),
        )
    filings, broker_reports, failures = [], [], []
    for c in constituents:
        digest = provider.fetch_filing_digest(c.symbol)
        if digest is None:
            failures.append(f"missing filing digest: {c.symbol}")
        else:
            filings.append(digest)
        reports = provider.fetch_broker_reports(c.symbol)
        broker_reports.extend(reports)
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=tuple(broker_reports),
        failure_reasons=tuple(failures),
    )


def _build_us_snapshot(
    target: str, spec: _TargetSpec, as_of_iso: str,
) -> ConstituentSnapshot:
    filings: list[FilingDigest] = []
    failures: list[str] = []
    per_symbol_codes: list[str] = []
    constituents = tuple(
        Constituent(symbol=s, name=s, weight=0.0, market="us") for s in spec.symbols
    )
    for symbol in spec.symbols:
        digest, code = fetch_us_filing_digest_diag(symbol)
        if digest is None:
            tag = f" ({code})" if code else ""
            failures.append(f"missing filing digest: {symbol}{tag}")
            if code:
                per_symbol_codes.append(code)
        else:
            filings.append(digest)
    if not filings and per_symbol_codes and len(set(per_symbol_codes)) == 1:
        failures.append(f"all US fetches failed: {per_symbol_codes[0]}")
    if date.today() > _US_SYMBOLS_STALE_AFTER:
        import sys
        print(
            f"WARNING: hardcoded US index constituents for {target!r} are stale "
            f"(stale_after={_US_SYMBOLS_STALE_AFTER}). "
            "Re-run `irc fundamentals snapshot --target <name>` to refresh.",
            file=sys.stderr,
        )
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=(),
        failure_reasons=tuple(failures),
    )


def _build_hk_snapshot(
    target: str, spec: _TargetSpec, as_of_iso: str,
) -> ConstituentSnapshot:
    filings, failures = [], []
    constituents = tuple(
        Constituent(symbol=s, name=s, weight=0.0, market="hk") for s in spec.symbols
    )
    for symbol in spec.symbols:
        digest = fetch_hk_filing_digest(symbol)
        if digest is None:
            failures.append(f"missing filing digest: {symbol}")
        else:
            filings.append(digest)
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=(),
        failure_reasons=tuple(failures),
    )


def _build_hk_index_snapshot(
    target: str, spec: _TargetSpec, top_n: int, as_of_iso: str,
) -> ConstituentSnapshot:
    """Build snapshot for HK index by fetching constituents then per-symbol filings."""
    constituents = fetch_hk_index_constituents(spec.code, top_n=top_n)
    if not constituents:
        return ConstituentSnapshot(
            lookthrough_target=target, as_of_iso=as_of_iso,
            constituents=(), filings=(), broker_reports=(),
            failure_reasons=(f"hk_index {spec.code} returned no constituents",),
        )
    filings, failures = [], []
    for c in constituents:
        digest = fetch_hk_filing_digest(c.symbol)
        if digest is None:
            failures.append(f"missing filing digest: {c.symbol}")
        else:
            filings.append(digest)
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=(),
        failure_reasons=tuple(failures),
    )

