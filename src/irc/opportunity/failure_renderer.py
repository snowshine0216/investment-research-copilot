"""Item 006 Slice H3 + H4 — failure section + V1 systematic exclusion summary.

`render_failure_section` reads only 4 fields off OpportunityRow:
  - instrument_id, name_cn, evidence_gaps, fetch_types_attempted

It NEVER reads conclusion fields (opportunity_state, dca, risk, note_cn,
opportunity_reason, valuation_state, heat_state, thesis_state,
product_quality_state, contributing_dimensions, thesis_evidence,
constituent_analyses). The function signature is the enforcement mechanism —
a future contributor cannot accidentally add such a field because the
locked regex test (criterion 18) greps the rendered output for forbidden
tokens.

`render_v1_systematic_exclusion_summary` computes the once-per-run V1
US-heavy count from `rejections.json` entries. Emitted unconditionally
(N=0 still renders the header line so the section is greppable across runs).
"""
from __future__ import annotations

from collections.abc import Sequence

from irc.opportunity.policy_b import ConstituentCoverageEntry
from irc.opportunity.rejection_log import RejectionRecord
from irc.opportunity.types import OpportunityRow


def render_failure_section(rows: Sequence[OpportunityRow]) -> str:
    """Render one bullet per gapped row.

    Format (locked by criterion 18):
      - **{instrument_id} {name_cn}** ｜ 原因: {gaps_joined} ｜ 已尝试: {fetch_types_joined}
    """
    if not rows:
        return "（无）"
    lines: list[str] = []
    for r in sorted(rows, key=lambda r: (r.asset_class, r.instrument_id)):
        gaps = ", ".join(r.evidence_gaps) or "(none)"
        attempted = ", ".join(r.fetch_types_attempted) or "(none)"
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** ｜ 原因: {gaps} ｜ 已尝试: {attempted}"
        )
    return "\n".join(lines)


def _is_us_heavy(coverage: Sequence[ConstituentCoverageEntry]) -> bool:
    """Strict-majority US in the material top-half."""
    material = [c for c in coverage if c.in_material_top_half]
    if not material:
        return False
    us = sum(1 for c in material if c.exchange == "US")
    return us > len(material) // 2


def render_v1_systematic_exclusion_summary(
    records: Sequence[RejectionRecord],
) -> str:
    """Once-per-run V1 systematic exclusions summary line for discipline_report.md.

    Emitted unconditionally (N=0 still renders the header). Counts funds
    rejected with `insufficient_info_coverage_top_half` whose material
    top-half is strict-majority US.
    """
    us_heavy = [
        r for r in records
        if r.rejection_reason == "insufficient_info_coverage_top_half"
        and _is_us_heavy(r.constituent_coverage)
    ]
    if not us_heavy:
        return (
            "## V1 systematic exclusions: 0 funds excluded due to "
            "US-heavy material holdings"
        )
    names = ", ".join(f"{r.instrument_id} {r.name_cn}" for r in us_heavy)
    return (
        f"## V1 systematic exclusions: {len(us_heavy)} funds excluded due to "
        f"US-heavy material holdings (V2 prerequisite: US information adapter). "
        f"Excluded: {names}"
    )
