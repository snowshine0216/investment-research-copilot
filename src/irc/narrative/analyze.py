from __future__ import annotations

from pathlib import Path

import duckdb

from irc.fundamentals.provider import CnFundamentalsProvider
from irc.fundamentals.snapshot import _FUND_LEVEL_KINDS
from irc.fundamentals.snapshot_cache import load_active_fund_cache, load_latest_nav_cached as _load_latest_nav_cached
from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot
from irc.opportunity.lookthrough import map_lookthrough, QDII_KINDS
from irc.opportunity.types import OpportunityInput
from irc.narrative.risk import derive_position_risk_level
from irc.narrative.schemas import (
    NarrativeFundReport,
    RiskEvalView,
    ShortlistRow,
)
from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.inputs_build import _build_input
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import OpportunityRow
from irc.schemas.universe import Instrument


def error_report(shortlist_row: ShortlistRow, reason: str) -> NarrativeFundReport:
    """Build an 'insufficient' NarrativeFundReport when per-fund analysis fails."""
    return NarrativeFundReport(
        instrument_id=shortlist_row.instrument_id,
        name_cn=shortlist_row.name_cn,
        position_risk_level="insufficient",
        risk_rationale=reason,
        risk_drivers=("evidence_gaps",),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="pause_wait",
        dca_action="do_not_buy",
        risk_action="review_required",
        falsification_triggers=(),
        trim_triggers=(),
        review_cadence="",
        evidence_gaps=(reason,),
        thesis_evidence=(),
    )

_PROSPECTIVE_POSITION = PositionContext(
    portfolio_weight=None, target_band_low=None, target_band_high=None,
    drawdown_since_entry=None, is_holding=False,
)


def _top_holdings_from_row(
    row: OpportunityRow, shortlist_row: ShortlistRow,
) -> tuple[tuple[str, str, float], ...]:
    if row.constituent_analyses:
        ranked = sorted(row.constituent_analyses, key=lambda c: -c.weight_pct)
        return tuple((c.symbol, c.name_cn, c.weight_pct) for c in ranked)
    holds = sorted(shortlist_row.holdings, key=lambda h: -h.weight_pct)
    return tuple((h.symbol, h.name_cn, h.weight_pct) for h in holds)


def _risk_view_from_row(row: OpportunityRow, shortlist_row: ShortlistRow) -> RiskEvalView:
    return RiskEvalView(
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        evidence_gaps=row.evidence_gaps,
        top_holdings=_top_holdings_from_row(row, shortlist_row),
    )


def _report_from_card(
    row: OpportunityRow, shortlist_row: ShortlistRow, *, role: str,
) -> NarrativeFundReport:
    entry_reason = row.opportunity_reason.split("；")[0].split(";")[0]
    card = build_thesis_card(row, _PROSPECTIVE_POSITION, role, entry_reason)
    view = _risk_view_from_row(row, shortlist_row)
    level, rationale, drivers = derive_position_risk_level(view, shortlist_row.overlap, {})
    return NarrativeFundReport(
        instrument_id=card.instrument_id, name_cn=card.name_cn,
        position_risk_level=level, risk_rationale=rationale, risk_drivers=drivers,
        valuation_state=card.valuation_state, heat_state=card.heat_state,
        thesis_state=card.thesis_state, product_quality_state=card.product_quality_state,
        opportunity_state=card.opportunity_state, dca_action=card.dca_action,
        risk_action=card.risk_action,
        falsification_triggers=card.falsification_triggers,
        trim_triggers=card.trim_triggers, review_cadence=card.review_cadence,
        evidence_gaps=card.evidence_gaps, thesis_evidence=card.thesis_evidence,
    )


def _load_snapshot_for_row(
    inp: OpportunityInput, *, quarter: str, data_dir: Path,
) -> ActiveFundSnapshot | FundLevelSnapshot | None:
    """Read-only snapshot loader; dispatches on the resolved lookthrough kind.

    active_fund → load_active_fund_cache(fixed analyze-context quarter).
    fund-level / QDII (w/ provider_symbol) → latest-nav/ FundLevelSnapshot scan.
    Performs NO fetch (AC4).
    """
    target = map_lookthrough(inp)
    if target.kind == "active_fund":
        return load_active_fund_cache(inp.instrument_id, quarter, data_dir)
    if (target.kind in QDII_KINDS or target.kind in _FUND_LEVEL_KINDS) and target.provider_symbol:
        return _load_latest_nav_cached(target.provider_symbol, data_dir)
    return None


def analyze_fund(
    shortlist_row: ShortlistRow,
    *,
    instr: Instrument | None,
    con: duckdb.DuckDBPyConnection,
    provider: CnFundamentalsProvider,
    quarter: str,
    data_dir: Path,
    role: str,
) -> NarrativeFundReport:
    """I/O edge: build the REAL OpportunityRow (cache-only) -> ThesisCard ->
    prospective risk report for one shortlisted fund. Mirrors fund_eval_cmd."""
    iid = shortlist_row.instrument_id
    score_row = {"instrument_id": iid, "asset_class": shortlist_row.asset_class, "role": role}
    inp = _build_input(score_row, instr, None, None, 0.0, set(), con, provider=provider)
    snapshot = _load_snapshot_for_row(inp, quarter=quarter, data_dir=data_dir)
    row = build_opportunity_row(inp, None, snapshot=snapshot, theme_report=None)
    return _report_from_card(row, shortlist_row, role=role)
