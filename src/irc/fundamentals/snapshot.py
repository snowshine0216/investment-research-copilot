"""Constituent snapshot orchestration + on-disk JSON cache.

`build_snapshot(lookthrough_target)` composes constituents → filings → broker
reports for one theme by dispatching to the right per-market adapter. Per-symbol
failures get recorded in `failure_reasons`, never raised.

The on-disk cache lives at `<root>/fundamentals/<quarter>/<lookthrough_target>.json`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import json
from pathlib import Path
from typing import Any

from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
    fetch_cn_index_constituents,
)
from irc.fundamentals.edgar_client import fetch_us_filing_digest
from irc.fundamentals.hkex_client import fetch_hk_filing_digest
from irc.fundamentals.types import (
    BrokerReport,
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


_TARGET_REGISTRY: dict[str, _TargetSpec] = {
    # CN index baskets (extend as themes onboard).
    "沪深300": _TargetSpec(kind="cn_index", code="000300"),
    "中证500": _TargetSpec(kind="cn_index", code="000905"),
}


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


# ---------- on-disk cache ----------


def cache_path(lookthrough_target: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / f"{lookthrough_target}.json"


def _infer_quarter(as_of_iso: str) -> str:
    """Label a snapshot with the most-recently-reported fiscal quarter.

    Earnings season for Qn ends ~midway through calendar Q(n+1), so the
    snapshot for an as_of date in calendar Qx is tagged Q(x-1)."""
    try:
        ts = date.fromisoformat(as_of_iso)
    except (TypeError, ValueError):
        ts = date.today()
    cal_q = (ts.month - 1) // 3 + 1
    if cal_q == 1:
        return f"{ts.year - 1}Q4"
    return f"{ts.year}Q{cal_q - 1}"


def _snapshot_to_dict(snap: ConstituentSnapshot) -> dict[str, Any]:
    return {
        "lookthrough_target": snap.lookthrough_target,
        "as_of_iso": snap.as_of_iso,
        "constituents": [asdict(c) for c in snap.constituents],
        "filings": [asdict(f) for f in snap.filings],
        "broker_reports": [asdict(r) for r in snap.broker_reports],
        "failure_reasons": list(snap.failure_reasons),
    }


def _snapshot_from_dict(body: dict[str, Any]) -> ConstituentSnapshot | None:
    needed = {"lookthrough_target", "as_of_iso", "constituents", "filings",
              "broker_reports"}
    if not needed.issubset(body):
        return None
    try:
        constituents = tuple(Constituent(**c) for c in body["constituents"])
        filings = tuple(FilingDigest(**f) for f in body["filings"])
        broker_reports = tuple(BrokerReport(**r) for r in body["broker_reports"])
    except TypeError:
        return None
    return ConstituentSnapshot(
        lookthrough_target=str(body["lookthrough_target"]),
        as_of_iso=str(body["as_of_iso"]),
        constituents=constituents,
        filings=filings,
        broker_reports=broker_reports,
        failure_reasons=tuple(body.get("failure_reasons", ())),
    )


def write_snapshot(snapshot: ConstituentSnapshot, root: Path) -> Path:
    quarter = _infer_quarter(snapshot.as_of_iso)
    path = cache_path(snapshot.lookthrough_target, quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_snapshot_to_dict(snapshot), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_cached_snapshot(
    lookthrough_target: str,
    quarter: str,
    root: Path,
) -> ConstituentSnapshot | None:
    path = cache_path(lookthrough_target, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _snapshot_from_dict(body)
