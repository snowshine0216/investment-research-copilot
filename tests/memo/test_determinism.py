"""Item 007 AC26 + AC27 — two-run byte equality for memo.md + discipline_report.md.

Locks the determinism contract from MASTER-SPEC AC9.
"""
from __future__ import annotations

import hashlib
import re


def test_evidence_pool_byte_equal_across_runs() -> None:
    """build_evidence_pool produces byte-identical output on two runs over the same input."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.memo.evidence_pool import build_evidence_pool

    def _ev(d: int, kind="data"):
        return ThesisEvidence(
            type="filing", source=f"src{d}", url=f"https://x/{d}",
            date=f"2024-04-{d:02d}", summary=f"s{d}", scope="constituent",
            citation_kind=kind, owner_instrument_id="005827",
            parent_fund_id="005827", constituent_key=f"60051{d}",
            holding_weight_pct=8.0 - d * 0.1,
        )
    evs = tuple(_ev(d, "data" if d % 2 == 0 else "information") for d in range(1, 9))
    row = {
        "instrument_id": "005827", "name_cn": "易方达",
        "asset_class": "cn_equity_fund",
        "opportunity_state": "core_dca",
        "opportunity_reason": "",
        "thesis_evidence": evs,
        "valuation_state": "fair", "heat_state": "normal",
        "thesis_state": "intact", "product_quality_state": "strong",
    }
    trades = [{"target": "005827", "target_weight": 0.1}]

    pool1 = "\n".join(build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[], plan_trades=trades,
        gold_regime=None,
    ))
    pool2 = "\n".join(build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[], plan_trades=trades,
        gold_regime=None,
    ))
    assert hashlib.sha256(pool1.encode("utf-8")).hexdigest() == \
        hashlib.sha256(pool2.encode("utf-8")).hexdigest()


def test_compose_discipline_markdown_byte_equal_across_runs() -> None:
    """compose_discipline_markdown produces byte-identical output on two runs."""
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.report import compose_discipline_markdown
    from irc.opportunity.types import DisciplineRow, OpportunityRow

    ev = ThesisEvidence(
        type="filing", source="x", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(ev,), failure_reasons=(), one_line_view="持有头部白酒",
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(ev,),
        constituent_analyses=(c,),
    )
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        thesis_evidence=(ev,), constituent_analyses=(c,),
    )
    out1 = compose_discipline_markdown(
        rows=(drow,), date="2026-05-23",
        publishable_rows=(row,), pick_order_iids=("005827",),
    )
    out2 = compose_discipline_markdown(
        rows=(drow,), date="2026-05-23",
        publishable_rows=(row,), pick_order_iids=("005827",),
    )
    assert hashlib.sha256(out1.encode("utf-8")).hexdigest() == \
        hashlib.sha256(out2.encode("utf-8")).hexdigest()


def test_appendix_shuffled_evidence_order_byte_equal() -> None:
    """AC25 — select_citations shuffle invariance ⇒ appendix renders byte-equal
    across two input evidence tuples differing only in element order."""
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.report import compose_discipline_markdown
    from irc.opportunity.types import DisciplineRow, OpportunityRow

    def _ev(d, kind):
        return ThesisEvidence(
            type="filing", source=f"src{d}", url=f"https://x/{d}",
            date=f"2024-04-{d:02d}", summary=f"s{d}", scope="constituent",
            citation_kind=kind, owner_instrument_id="005827",
            parent_fund_id="005827", constituent_key="600519",
            holding_weight_pct=8.0,
        )
    evs_forward = tuple(
        _ev(d, "data" if d % 2 == 0 else "information") for d in range(1, 9)
    )
    evs_reverse = tuple(reversed(evs_forward))

    def _compose(evs):
        c = ConstituentAnalysis(
            symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
            evidence=evs, failure_reasons=(), one_line_view="x",
        )
        row = OpportunityRow(
            instrument_id="005827", name_cn="易方达",
            asset_class="cn_equity_fund", theme=None,
            lookthrough_target=LookthroughTarget(
                kind="active_fund", key="005827", display_cn="易方达",
                provider_symbol="",
            ),
            valuation_state="fair", heat_state="normal",
            thesis_state="intact", product_quality_state="strong",
            opportunity_state="core_dca", opportunity_reason="",
            evidence_gaps=(), thesis_evidence=evs,
            constituent_analyses=(c,),
        )
        drow = DisciplineRow(
            instrument_id="005827", name_cn="易方达",
            asset_class="cn_equity_fund", theme=None,
            opportunity_state="core_dca", dca_action="normal_dca",
            risk_action="none", note_cn="",
            thesis_evidence=evs, constituent_analyses=(c,),
        )
        return compose_discipline_markdown(
            rows=(drow,), date="2026-05-23",
            publishable_rows=(row,), pick_order_iids=("005827",),
        )

    assert hashlib.sha256(_compose(evs_forward).encode("utf-8")).hexdigest() == \
        hashlib.sha256(_compose(evs_reverse).encode("utf-8")).hexdigest()
