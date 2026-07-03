"""PURE source-tier classifier for monitor theme-pool evidence (ADR 0022).
Domain-suffix match; unknown domains are tier 3 (kept, badged), never dropped.
Scope: theme (web-search) pool ONLY — constituent-pool evidence is snapshot-
grounded and carries its own 快照 badge (see render_html.py CitationIndex,
Phase 4), never classified here."""
from __future__ import annotations
from dataclasses import dataclass

Tier = int | str   # 1 | 2 | 3 | "blocked"

TIER_LABEL: dict[Tier, str] = {1: "权威", 2: "财经媒体", 3: "未分级", "blocked": "已屏蔽"}


@dataclass(frozen=True)
class SourceTiers:
    blocked: tuple[str, ...]
    tier1: tuple[str, ...]
    tier2: tuple[str, ...]


def _suffix_match(domain: str, suffixes: tuple[str, ...]) -> bool:
    d = domain.lower().strip()
    return any(d == s or d.endswith("." + s) for s in suffixes)


def classify(domain: str, tiers: SourceTiers) -> Tier:
    d = (domain or "").strip()
    if not d:
        return 3
    if _suffix_match(d, tiers.blocked):
        return "blocked"
    if _suffix_match(d, tiers.tier1):
        return 1
    if _suffix_match(d, tiers.tier2):
        return 2
    return 3


def tiers_from_config(raw: dict | None) -> SourceTiers:
    """Missing/malformed `source_tiers:` config -> SourceTiers((), (), ())
    (everything classifies tier 3, fail-open per ADR 0022). Pure: does NOT log;
    the edge caller (monitor_cmd.py) logs the warning when raw is falsy."""
    if not raw or not isinstance(raw, dict):
        return SourceTiers((), (), ())
    return SourceTiers(
        blocked=tuple(raw.get("blocked") or ()),
        tier1=tuple(raw.get("tier1") or ()),
        tier2=tuple(raw.get("tier2") or ()),
    )
