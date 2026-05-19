from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from irc.config_loader import load_repo_configs
from irc.decision.report import compose_decision_report, render_decision_markdown
from irc.io_utils import atomic_write_text
from irc.memo.auditor import extract_audit_summary
from irc.schemas.universe import UniverseConfig


def _venue_maps_from_bundle(bundle, root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Aggregate venue_required per instrument across every universe yaml,
    plus the account's available_venues. Returns (venue_requirements_by_id,
    available_venues).
    """
    universes: list[UniverseConfig] = [
        bundle.universe_qdii_us,
        bundle.universe_qdii_hk,
        bundle.universe_cn_funds,
        bundle.universe_gold,
    ]
    requirements: dict[str, list[str]] = {}
    for u in universes:
        for instr in u.instruments:
            # The same id should not exist in multiple universes; last-write
            # is fine if a config drift ever introduces a duplicate.
            requirements[instr.instrument_id] = list(instr.venue_required)
    venues: list[str] = []
    for acc in bundle.account.accounts:
        venues.extend(acc.available_venues)
    return requirements, sorted(set(venues))


def _names_from_bundle(bundle) -> dict[str, str]:
    """Aggregate human-readable name_cn per instrument across every universe
    yaml. Used to render decision tables with a readable name column."""
    universes: list[UniverseConfig] = [
        bundle.universe_qdii_us,
        bundle.universe_qdii_hk,
        bundle.universe_cn_funds,
        bundle.universe_gold,
    ]
    names: dict[str, str] = {}
    for u in universes:
        for instr in u.instruments:
            names[instr.instrument_id] = instr.name_cn
    return names


def _load_audit_summary(path: Path) -> dict[str, Any] | None:
    """Read memo_audit.txt if present and return its structured summary.
    Returns None when the file is absent so the decision report renders
    without an audit banner (rather than failing or emitting a misleading
    "未知" banner)."""
    if not path.exists():
        return None
    return extract_audit_summary(path.read_text(encoding="utf-8"))


def _names_from_watchlist_csv(path: Path) -> dict[str, str]:
    """Fallback name map sourced from discovered_watchlist.csv. Used to fill
    rows whose ids aren't in any universe yaml (e.g. discovery added them
    this run but generated universe yaml hadn't propagated yet)."""
    if not path.exists():
        return {}
    import csv
    names: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iid = (row.get("instrument_id") or "").strip()
            name = (row.get("name_cn") or "").strip()
            if iid and name:
                names[iid] = name
    return names


_TZ = timezone(timedelta(hours=8))
_REQUIRED_ARTIFACTS = (
    "scoring.json",
    "proposed_allocation.yaml",
    "trade_plan.yaml",
    "memo_traceability.json",
)


def run_decision(repo_root: str) -> int:
    root = Path(repo_root)
    out_dir = _resolve_output_dir(root)
    missing = [name for name in _REQUIRED_ARTIFACTS if not (out_dir / name).exists()]
    if missing:
        print(f"ERROR: missing decision inputs in {out_dir}: {', '.join(missing)}")
        return 2
    scoring = _read_json(out_dir / "scoring.json")
    allocation = _read_yaml(out_dir / "proposed_allocation.yaml")
    trade_plan = _read_yaml(out_dir / "trade_plan.yaml")
    memo_traceability = _read_json(out_dir / "memo_traceability.json")
    # Load venue context so rows without a trade entry can still report a
    # precise venue_status (direct / blocked_no_proxy) instead of "unknown".
    # Item 008: 85 of 103 rows in 2026-05-18's report had venue=unknown
    # because no trade was generated; for in-universe instruments the
    # status is fully derivable from venue_required ∩ available_venues.
    try:
        bundle = load_repo_configs(root)
        venue_reqs, available_venues = _venue_maps_from_bundle(bundle, root)
        names = _names_from_bundle(bundle)
    except Exception as exc:  # noqa: BLE001 — graceful degrade
        print(f"WARNING: could not load venue context ({exc}); falling back to unknown venue for rows without trades.")
        venue_reqs, available_venues, names = {}, [], {}
    # Universe yamls miss instruments only present in the discovered watchlist
    # for this run. Fall back to that CSV so the markdown never renders naked ids.
    watchlist_names = _names_from_watchlist_csv(out_dir / "discovered_watchlist.csv")
    for iid, name in watchlist_names.items():
        names.setdefault(iid, name)
    proxies = {
        str(row.get("target")): str(row.get("proxy_id"))
        for row in trade_plan.get("trades", [])
        if row.get("proxy_id")
    }
    audit_summary = _load_audit_summary(out_dir / "memo_audit.txt")
    report = compose_decision_report(
        date=out_dir.name,
        scoring=scoring,
        allocation=allocation,
        trade_plan=trade_plan,
        memo_traceability=memo_traceability,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
        venue_requirements_by_id=venue_reqs,
        available_venues=available_venues,
        proxies_by_id=proxies,
        names_by_id=names,
        audit_summary=audit_summary,
    )
    atomic_write_text(out_dir / "decision_report.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "decision_report.md", render_decision_markdown(report))
    print(f"decision {report['overall_status']} -> {out_dir / 'decision_report.md'}")
    return 0


def _resolve_output_dir(root: Path) -> Path:
    today = datetime.now(_TZ).date().isoformat()
    today_dir = root / "outputs" / today
    if today_dir.exists():
        return today_dir
    outputs_dir = root / "outputs"
    candidates = sorted(path for path in outputs_dir.glob("*") if path.is_dir()) if outputs_dir.is_dir() else []
    return candidates[-1] if candidates else today_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
