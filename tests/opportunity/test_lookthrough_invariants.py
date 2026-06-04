"""Phase D PR1 — H3 / SAME-3 invariants hold with the look-through flag ON.

Spec §9 requires the invariants to hold "with the flag both off and on". The
flag-OFF case is the dormancy lock (tests/commands/test_opportunity_cmd_lookthrough_dormancy.py).
This file covers the flag-ON case at the level where the valuation axis could
theoretically leak: `build_opportunity_row`.

Spec §7: `valuation_percentile_fundamental[_pb]` are plain numeric inputs (no
`ThesisEvidence`, no `[ref:...]`), so the H3 partition (driven by `evidence_gaps`),
the SAME-3 citation set (driven by `thesis_evidence`), and Policy B / `thesis_state`
ownership are structurally unaffected — exactly as for the index path. This mirrors
the index-path precedent in test_valuation_fundamental_anchor.py
::test_fundamental_block_emits_no_thesis_evidence_or_gap, applied to an active fund
(`cn_equity_fund`, which consumes the same slot via the same `classify_valuation`).
"""
from __future__ import annotations

from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import OpportunityInput


def _active_fund(**kwargs) -> OpportunityInput:
    base = dict(
        instrument_id="AF1", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme=None, tracked_index=None,
    )
    base.update(kwargs)
    return OpportunityInput(**base)


def test_lookthrough_slot_inert_on_every_axis_when_pe_agrees_with_nav() -> None:
    """Realistic active-fund state: the NAV self-percentile is ALWAYS present
    (the momentum proxy Phase D replaces). Flag-OFF derives valuation from NAV;
    flag-ON derives it from the PE percentile. When the PE anchor lands in the
    SAME band as NAV (no divergence), the flag-ON row is byte-identical on every
    axis — valuation_state, evidence_gaps (H3), thesis_evidence (SAME-3),
    advisory_gaps, thesis_state. The look-through slot is genuinely inert here.

    (`missing_valuation_data` fires only when self AND vs_benchmark AND
    fundamental are all None — states._structural_evidence_gaps — so with NAV
    present the slot can never add/remove that gap.)"""
    off_row = build_opportunity_row(
        _active_fund(valuation_percentile_self=0.10, valuation_percentile_fundamental=None),
        theme_thesis={},
    )
    on_row = build_opportunity_row(
        _active_fund(valuation_percentile_self=0.10, valuation_percentile_fundamental=0.05),
        theme_thesis={},
    )
    assert on_row.valuation_state == off_row.valuation_state == "cheap"  # same band
    assert on_row.thesis_evidence == off_row.thesis_evidence  # SAME-3 unaffected
    assert on_row.evidence_gaps == off_row.evidence_gaps      # H3 partition unaffected
    assert on_row.advisory_gaps == off_row.advisory_gaps      # no divergence advisory
    assert on_row.thesis_state == off_row.thesis_state        # Policy B / ownership


def test_lookthrough_divergence_advisory_does_not_touch_h3_same3() -> None:
    """Even when the flag-ON PE percentile DIVERGES from the NAV self percentile
    (the intended divergence advisory fires → advisory_gaps may change),
    evidence_gaps (H3), thesis_evidence (SAME-3) and thesis_state are unchanged."""
    off_row = build_opportunity_row(
        _active_fund(valuation_percentile_self=0.15, valuation_percentile_fundamental=None),
        theme_thesis={},
    )
    on_row = build_opportunity_row(
        _active_fund(valuation_percentile_self=0.15, valuation_percentile_fundamental=0.95),
        theme_thesis={},
    )
    assert on_row.evidence_gaps == off_row.evidence_gaps      # H3 partition stable
    assert on_row.thesis_evidence == off_row.thesis_evidence  # SAME-3 citation set stable
    assert on_row.thesis_state == off_row.thesis_state        # Policy B / ownership stable
