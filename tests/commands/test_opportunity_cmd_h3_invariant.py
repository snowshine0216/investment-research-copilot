"""Item 006 Slice H3 — universal gapped-row invariant integration tests.

Tests cover acceptance criteria 17, 20, 21, 22, 27.
"""
from __future__ import annotations

import json

import pytest
import yaml


def _row(
    instrument_id,
    name_cn="x",
    asset_class="cn_equity_fund",
    evidence_gaps=(),
    fetch_types_attempted=(),
    opportunity_state="exclude",
    opportunity_reason="",
):
    """Build a minimal OpportunityRow.

    Item 009 fix: publishable rows (evidence_gaps==()) carry dual-leg thesis
    evidence so the citation gate does not route them to gapped. Gapped rows
    carry no evidence because the gate never inspects them (they are already
    partitioned out before the citation check).
    """
    from irc.fundamentals.types import ThesisEvidence
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    # Dual-leg evidence only for publishable rows; gapped rows are irrelevant.
    if not evidence_gaps:
        thesis_evidence = (
            ThesisEvidence(
                type="filing", source="src",
                url=f"https://x/{instrument_id}/d", date="2024-04-15",
                summary="x", scope="instrument", citation_kind="data",
                owner_instrument_id=instrument_id,
                parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
            ThesisEvidence(
                type="filing", source="src",
                url=f"https://x/{instrument_id}/i", date="2024-04-16",
                summary="x", scope="instrument", citation_kind="information",
                owner_instrument_id=instrument_id,
                parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
        )
    else:
        thesis_evidence = ()
    return OpportunityRow(
        instrument_id=instrument_id, name_cn=name_cn, asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", f"fund_{instrument_id}", name_cn, instrument_id,
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state=opportunity_state,
        opportunity_reason=opportunity_reason,
        evidence_gaps=evidence_gaps,
        fetch_types_attempted=fetch_types_attempted,
        thesis_evidence=thesis_evidence,
    )


def _position():
    from irc.opportunity.discipline import PositionContext
    return PositionContext(
        portfolio_weight=None, target_band_low=None, target_band_high=None,
        drawdown_since_entry=None, is_holding=False,
    )


def test_h3_partition_excludes_gapped_rows_from_thesis_cards(tmp_path):
    """Criterion 17: thesis_cards.yaml contains ZERO entries for gapped rows."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    publishable = _row("005827", opportunity_state="core_dca")
    gapped = _row("005828", evidence_gaps=("qdii_information_unavailable",))
    _write_opportunity_outputs(
        kept_rows=[publishable, gapped],
        positions={"005827": _position(), "005828": _position()},
        qualities={}, roles={"005827": "watchlist", "005828": "watchlist"},
        holdings={}, out_dir=tmp_path, today="2026-05-23",
    )
    body = yaml.safe_load((tmp_path / "thesis_cards.yaml").read_text(encoding="utf-8"))
    card_ids = [c["instrument_id"] for c in (body.get("cards") or [])]
    assert "005828" not in card_ids
    assert "005827" in card_ids


def test_h3_partition_excludes_gapped_rows_from_opportunity_report_rows(tmp_path):
    """Criterion 17: opportunity_report.json `rows` excludes gapped rows."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    publishable = _row("005827")
    gapped = _row("005828", evidence_gaps=("qdii_information_unavailable",))
    _write_opportunity_outputs(
        kept_rows=[publishable, gapped],
        positions={"005827": _position(), "005828": _position()},
        qualities={}, roles={}, holdings={},
        out_dir=tmp_path, today="2026-05-23",
    )
    body = json.loads((tmp_path / "opportunity_report.json").read_text(encoding="utf-8"))
    row_ids = [r["instrument_id"] for r in body.get("rows", [])]
    assert "005828" not in row_ids
    assert "005827" in row_ids


def test_h3_fetch_budget_exhausted_raises_immediately(tmp_path):
    """Criterion 20: fetch_budget_exhausted in evidence_gaps raises RuntimeError."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    bad = _row("005827", evidence_gaps=("fetch_budget_exhausted",))
    with pytest.raises(RuntimeError) as exc_info:
        _write_opportunity_outputs(
            kept_rows=[bad], positions={"005827": _position()},
            qualities={}, roles={}, holdings={},
            out_dir=tmp_path, today="2026-05-23",
        )
    msg = str(exc_info.value)
    assert "fetch_budget_exhausted" in msg
    assert "row-level emission is a programming error" in msg
    # No .tmp files visible.
    assert not list(tmp_path.glob("*.tmp*"))


def test_h3_discipline_report_failure_section_includes_gapped_rows(tmp_path):
    """Criterion 21: gapped rows appear in `## 证据不足 / Failed fetch` section,
    NOT in the publishable bucket sections."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    publishable = _row("005827", opportunity_state="core_dca")
    gapped = _row(
        "005828", name_cn="易方达蓝筹精选",
        evidence_gaps=("qdii_information_unavailable",),
        fetch_types_attempted=("nav",),
    )
    _write_opportunity_outputs(
        kept_rows=[publishable, gapped],
        positions={"005827": _position(), "005828": _position()},
        qualities={}, roles={}, holdings={},
        out_dir=tmp_path, today="2026-05-23",
    )
    text = (tmp_path / "discipline_report.md").read_text(encoding="utf-8")
    # Gapped row appears in failure section
    assert "## 证据不足" in text
    assert "005828 易方达蓝筹精选" in text
    # Gapped row's note_cn / opportunity_state must NOT appear in bucket sections.
    failure_idx = text.index("## 证据不足")
    pre_failure = text[:failure_idx]
    assert "005828" not in pre_failure


def test_h3_rejections_json_lists_all_gapped_funds(tmp_path):
    """Criterion 22: rejections.json entries length == count of gapped rows."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    publishable_a = _row("PUB_A")
    publishable_b = _row("PUB_B")
    publishable_c = _row("PUB_C")
    qdii_1 = _row("Q1", asset_class="qdii_us",
                  evidence_gaps=("qdii_information_unavailable",))
    qdii_2 = _row("Q2", asset_class="qdii_us",
                  evidence_gaps=("qdii_information_unavailable",))
    policy_b = _row("PB", evidence_gaps=("insufficient_info_coverage_top_half",))
    holdings_failed = _row("HF", evidence_gaps=("holdings_fetch_failed",))
    _write_opportunity_outputs(
        kept_rows=[
            publishable_a, publishable_b, publishable_c,
            qdii_1, qdii_2, policy_b, holdings_failed,
        ],
        positions={
            iid: _position() for iid in (
                "PUB_A", "PUB_B", "PUB_C", "Q1", "Q2", "PB", "HF",
            )
        },
        qualities={}, roles={}, holdings={},
        out_dir=tmp_path, today="2026-05-23",
    )
    body = json.loads((tmp_path / "rejections.json").read_text(encoding="utf-8"))
    assert len(body["entries"]) == 4
    gapped_ids = {e["instrument_id"] for e in body["entries"]}
    assert gapped_ids == {"Q1", "Q2", "PB", "HF"}


def test_h3_v1_summary_line_emitted_unconditionally(tmp_path):
    """Criterion 24 + 27: discipline_report.md contains the V1 summary line."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    _write_opportunity_outputs(
        kept_rows=[_row("PUB_A")],
        positions={"PUB_A": _position()},
        qualities={}, roles={}, holdings={},
        out_dir=tmp_path, today="2026-05-23",
    )
    text = (tmp_path / "discipline_report.md").read_text(encoding="utf-8")
    assert "## V1 systematic exclusions: 0 funds excluded" in text


def test_h3_discipline_bucket_sections_exclude_gapped(tmp_path):
    """Criterion 21: bucket sections (今日可定投 etc.) contain ZERO gapped rows."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    gapped = _row("GAPPY", opportunity_state="core_dca",  # would normally route to 今日可定投
                  opportunity_reason="should not leak",
                  evidence_gaps=("incomplete_constituent_data",))
    _write_opportunity_outputs(
        kept_rows=[gapped], positions={"GAPPY": _position()},
        qualities={}, roles={}, holdings={},
        out_dir=tmp_path, today="2026-05-23",
    )
    text = (tmp_path / "discipline_report.md").read_text(encoding="utf-8")
    # GAPPY must NOT appear in any bucket section above the V1 summary.
    failure_idx = text.index("## V1 systematic exclusions")
    pre = text[:failure_idx]
    assert "GAPPY" not in pre
    # GAPPY MUST appear in the failure section.
    post = text[failure_idx:]
    assert "GAPPY" in post
