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

from irc.fundamentals.akshare_fundamentals import fetch_cn_index_constituents
from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
from irc.fundamentals.edgar_client import fetch_us_filing_digest
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
    # QDII US — top-10 by index weight as of 2026-05-16; update quarterly
    "标普500": _TargetSpec(kind="us_symbols", symbols=(
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "GOOG", "AVGO", "TSLA",
    )),
    "纳斯达克100": _TargetSpec(kind="us_symbols", symbols=(
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "TSLA", "COST",
    )),
}


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
    filings, failures = [], []
    constituents = tuple(
        Constituent(symbol=s, name=s, weight=0.0, market="us") for s in spec.symbols
    )
    for symbol in spec.symbols:
        digest = fetch_us_filing_digest(symbol)
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

