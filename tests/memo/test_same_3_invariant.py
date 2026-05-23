"""Item 007 ADR 0004 §3 — SAME-3 invariant locked across three surfaces.

For any OpportunityRow, the set of citation_ids rendered in:
  (a) the picks-table 证据 cell (via _build_pick_rows → PickRow.citations)
  (b) the evidence-pool [ref:...] markers (via build_evidence_pool)
  (c) the discipline _render_section nested bullets (via _render_section)
MUST be IDENTICAL. Locked here to prevent silent drift.
"""
from __future__ import annotations

import re

from irc.commands.memo_cmd import _build_pick_rows
from irc.fundamentals.types import ThesisEvidence
from irc.memo.evidence_pool import build_evidence_pool
from irc.memo.citation_selector import select_citations
from irc.opportunity.report import _render_section
from irc.opportunity.types import DisciplineRow


def _ev(d: int, kind: str = "data", scope: str = "constituent") -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source=f"src{d}", url=f"https://x/{d}",
        date=f"2024-04-{d:02d}", summary=f"s{d}", scope=scope,
        citation_kind=kind, owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key=f"60051{d}",
        holding_weight_pct=8.0 - d * 0.1,
    )


def test_same_3_invariant_evidence_pool_and_picks_table() -> None:
    """SAME-3: picks_table.citations and evidence_pool [ref:...] markers
    cite the same 3 citation_ids."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)  # 8 entries
    )

    # Picks-table path: build the dict-form row that _build_pick_rows expects.
    opp_dict = {
        "rows": [{
            "instrument_id": "005827",
            "name_cn": "易方达",
            "asset_class": "cn_equity_fund",
            "opportunity_state": "core_dca",
            "opportunity_reason": "",
            "thesis_evidence": [
                {
                    "type": e.type, "source": e.source, "url": e.url,
                    "date": e.date, "summary": e.summary, "scope": e.scope,
                    "citation_kind": e.citation_kind,
                    "owner_instrument_id": e.owner_instrument_id,
                    "parent_fund_id": e.parent_fund_id,
                    "constituent_key": e.constituent_key,
                    "holding_weight_pct": e.holding_weight_pct,
                }
                for e in evs
            ],
            "evidence_gaps": [],
        }],
    }
    trades = [{"target": "005827", "target_weight": 0.1, "role": ""}]
    scoring = {"scores": []}
    pick_rows, _, _ = _build_pick_rows(trades, opp_dict, scoring)
    picks_cids = {c.citation_id for c in pick_rows[0].citations}

    # Evidence-pool path: pass the dataclass tuple under thesis_evidence.
    op_row_for_pool = {
        "instrument_id": "005827",
        "name_cn": "易方达",
        "asset_class": "cn_equity_fund",
        "opportunity_state": "core_dca",
        "opportunity_reason": "",
        "thesis_evidence": evs,
        "valuation_state": "fair", "heat_state": "normal",
        "thesis_state": "intact", "product_quality_state": "strong",
    }
    pool = build_evidence_pool(
        opportunity_rows=[op_row_for_pool],
        scoring_rows=[], plan_trades=trades, gold_regime=None,
    )
    pool_cids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", "\n".join(pool)))

    assert picks_cids == pool_cids, \
        f"SAME-3 invariant broken between picks-table and evidence-pool:\n" \
        f"  picks: {picks_cids}\n  pool : {pool_cids}"
    assert len(picks_cids) == 3


def test_same_3_invariant_discipline_section_matches_picks_table() -> None:
    """SAME-3: _render_section nested bullets cite the same citation_ids
    as the picks-table."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)
    )

    opp_dict = {
        "rows": [{
            "instrument_id": "005827",
            "name_cn": "易方达",
            "asset_class": "cn_equity_fund",
            "opportunity_state": "core_dca",
            "opportunity_reason": "",
            "thesis_evidence": [
                {
                    "type": e.type, "source": e.source, "url": e.url,
                    "date": e.date, "summary": e.summary, "scope": e.scope,
                    "citation_kind": e.citation_kind,
                    "owner_instrument_id": e.owner_instrument_id,
                    "parent_fund_id": e.parent_fund_id,
                    "constituent_key": e.constituent_key,
                    "holding_weight_pct": e.holding_weight_pct,
                }
                for e in evs
            ],
            "evidence_gaps": [],
        }],
    }
    trades = [{"target": "005827", "target_weight": 0.1, "role": ""}]
    scoring = {"scores": []}
    pick_rows, _, _ = _build_pick_rows(trades, opp_dict, scoring)
    picks_cids = {c.citation_id for c in pick_rows[0].citations}

    discipline_row = DisciplineRow(
        instrument_id="005827", name_cn="易方达",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        thesis_evidence=evs,
    )
    section_md = _render_section("今日可定投", [discipline_row])
    discipline_cids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", section_md))

    assert picks_cids == discipline_cids, \
        f"SAME-3 invariant broken between picks-table and discipline section:\n" \
        f"  picks      : {picks_cids}\n  discipline : {discipline_cids}"
    assert len(picks_cids) == 3


def test_select_citations_shuffle_invariant() -> None:
    """AC25 — select_citations produces the same citation_id set across
    shuffled input orders. Locked at the selector level (ADR 0001 §3);
    this test pins the renderer-side consequence."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)
    )
    cids_a = {e.citation_id for e in select_citations(evs, cap=3)}
    cids_b = {e.citation_id for e in select_citations(tuple(reversed(evs)), cap=3)}
    assert cids_a == cids_b
