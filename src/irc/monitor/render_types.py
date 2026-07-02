from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.types import EvidenceItem, FactorScore, NarrativeDoc, SignalRecord
from irc.monitor.holding_metrics import HoldingMetric
from irc.monitor.market_composite import MarketCompositeView


@dataclass(frozen=True)
class Provenance:
    engine_version: str
    prompt_version: str
    schema_version: str
    spend_summary: str


@dataclass(frozen=True)
class FundView:
    fund_id: str
    name_cn: str
    latest_nav: float
    as_of_date: str
    nav_series: tuple[tuple[str, float], ...]
    signal: SignalRecord
    narrative: NarrativeDoc
    evidence_pool: tuple[EvidenceItem, ...]
    return_table: dict[int, float]
    factor_freshness: dict[str, str]
    missing_factor_reasons: tuple[str, ...]
    factor_scores: tuple[FactorScore, ...] = ()
    impacts_status: str = "ok"   # mirrors impacts.status; surfaced so schema/provider errors aren't silently dropped
    holding_metrics: tuple[HoldingMetric, ...] = ()  # per-stock drill-down (Slice 2+)
    market_view: MarketCompositeView | None = None   # Comp 1: render-derived anchor
    purchase_tag: str | None = None                  # Comp 5: 限购 actionability tag
    themes: tuple[str, ...] = ()   # Comp 3: theme chips -> #macro-<theme> anchors
    provisional_flow_pct: float | None = None   # Comp 6: 盘中提示, render-only, never a factor input
    provisional_flow_as_of: str | None = None   # Comp 6: ACTUAL fetch HH:MM, edge-stamped (spec §8)
