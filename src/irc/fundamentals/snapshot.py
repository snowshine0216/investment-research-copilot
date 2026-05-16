"""Constituent snapshot orchestration.

`build_snapshot(lookthrough_target)` composes constituents → filings → broker
reports for one theme by dispatching to the right per-market adapter. Per-symbol
failures get recorded in `failure_reasons`, never raised.

On-disk cache helpers live in `snapshot_cache`; this module re-exports them
for backward compatibility so callers can import from either location.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_index_constituents,
    fetch_hk_index_constituents,
)
from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
from irc.fundamentals.edgar_client import (
    fetch_us_filing_digest,           # kept for any external import
    fetch_us_filing_digest_diag,
)
from irc.fundamentals.hkex_client import fetch_hk_filing_digest
from irc.fundamentals.snapshot_cache import (  # noqa: F401 — re-exports
    cache_path,
    infer_quarter as _infer_quarter,
    load_cached_snapshot,
    load_latest_cached_snapshot,
    write_snapshot,
)
from irc.fundamentals.types import (
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
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
    "创业板":    _TargetSpec(kind="cn_index", code="399006"),
    "中证红利":  _TargetSpec(kind="cn_index", code="000922"),
    "红利低波":  _TargetSpec(kind="cn_index", code="930740"),
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


def build_snapshot(
    lookthrough_target: str,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
) -> ConstituentSnapshot:
    """Compose constituent-level evidence for `lookthrough_target`.

    Unknown targets return an empty snapshot with a failure_reason; per-symbol
    fetch failures are recorded the same way. Never raises."""
    spec = _TARGET_REGISTRY.get(lookthrough_target)
    timestamp = as_of_iso or _today_iso()
    if spec is None:
        return ConstituentSnapshot(
            lookthrough_target=lookthrough_target,
            as_of_iso=timestamp,
            constituents=(),
            filings=(),
            broker_reports=(),
            failure_reasons=(f"unknown lookthrough_target: {lookthrough_target}",),
        )
    if spec.kind == "cn_index":
        return _build_cn_snapshot(lookthrough_target, spec, top_n, timestamp)
    if spec.kind == "us_symbols":
        return _build_us_snapshot(lookthrough_target, spec, timestamp)
    if spec.kind == "hk_symbols":
        return _build_hk_snapshot(lookthrough_target, spec, timestamp)
    if spec.kind == "hk_index":
        return _build_hk_index_snapshot(lookthrough_target, spec, top_n, timestamp)
    return ConstituentSnapshot(
        lookthrough_target=lookthrough_target,
        as_of_iso=timestamp,
        constituents=(), filings=(), broker_reports=(),
        failure_reasons=(f"unsupported spec kind: {spec.kind}",),
    )


def _build_cn_snapshot(
    target: str, spec: _TargetSpec, top_n: int, as_of_iso: str,
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
        digest = fetch_cn_filing_digest(c.symbol)
        if digest is None:
            failures.append(f"missing filing digest: {c.symbol}")
        else:
            filings.append(digest)
        reports = fetch_cn_broker_reports(c.symbol)
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

