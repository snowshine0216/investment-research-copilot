"""Item 009 — _write_opportunity_outputs gate-wiring unit tests."""
from __future__ import annotations

import json

import pytest


def _make_row(*, iid="005827", legs=("data", "information"), gaps=()):
    """OpportunityRow with one data + one info evidence by default."""
    from irc.fundamentals.types import LookthroughTarget, ThesisEvidence
    from irc.opportunity.types import OpportunityRow
    evs = tuple(
        ThesisEvidence(
            type="filing", source="src",
            url=f"https://x/{i}", date=f"2024-04-{15 + i:02d}",
            summary="x", scope="instrument", citation_kind=leg,
            owner_instrument_id=iid, parent_fund_id=None,
            constituent_key=None, holding_weight_pct=None,
        )
        for i, leg in enumerate(legs)
    )
    return OpportunityRow(
        instrument_id=iid, name_cn="X", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid,
            display_cn="X", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=gaps,
        thesis_evidence=evs,
        contributing_dimensions=frozenset({"valuation"}),
        constituent_analyses=(),
    )


def _make_position():
    from irc.opportunity.discipline import PositionContext
    return PositionContext(
        portfolio_weight=None,
        target_band_low=None,
        target_band_high=None,
        drawdown_since_entry=None,
        is_holding=False,
    )


def _write_outputs(rows, tmp_path, *, today="2026-05-22", pending_verdicts=None):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    out_dir = tmp_path / "outputs_scratch"
    positions = {r.instrument_id: _make_position() for r in rows}
    qualities = {r.instrument_id: object() for r in rows}
    roles = {r.instrument_id: "core" for r in rows}
    _write_opportunity_outputs(
        rows, positions, qualities, roles, {},
        out_dir, today,
        pending_verdicts=pending_verdicts,
        plan_hash="x",
        snapshot_cache_by_instrument=None,
    )
    return out_dir


def test_gate_clean_publishable_row_passes(tmp_path, monkeypatch):
    """AC9 — dual-leg row passes the gate; opportunity_report.json is written."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    rows = [_make_row()]
    out_dir = _write_outputs(rows, tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is False


def test_gate_step_2a_blocks_uncited_row_block_mode(tmp_path, monkeypatch):
    """AC9 + AC12 — info-only row → row dropped + RuntimeError raised in block mode."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    info_only = _make_row(legs=("information",))
    with pytest.raises(RuntimeError, match="citation_gate_blocked"):
        _write_outputs([info_only], tmp_path)


def test_gate_step_2a_warn_mode_writes_artifacts(tmp_path, monkeypatch, capsys):
    """AC12 — warn mode logs to stderr, writes shadow log, emits artifacts."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    info_only = _make_row(legs=("information",))
    out_dir = _write_outputs([info_only], tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    err = capsys.readouterr().err
    assert "WARN citation-audit" in err
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is False  # warn ≠ blocking


def test_gate_step_2a_off_mode_silent(tmp_path, monkeypatch, capsys):
    """AC12 — off mode is silent, writes shadow log, emits artifacts."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    info_only = _make_row(legs=("information",))
    out_dir = _write_outputs([info_only], tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    err = capsys.readouterr().err
    assert "WARN citation-audit" not in err


def test_gate_step_2b_pure_failure_constituent_raises_unconditionally(
    tmp_path, monkeypatch,
):
    """AC9 Step 2b — pure-failure constituent raises even in off mode."""
    from irc.fundamentals.types import ConstituentAnalysis
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    bad = ConstituentAnalysis(
        symbol="600519", name_cn="X", weight_pct=5.0,
        evidence=(), failure_reasons=("timeout",), one_line_view="",
    )
    row = _make_row()
    from dataclasses import replace as _replace
    row = _replace(row, constituent_analyses=(bad,))
    with pytest.raises(RuntimeError, match="constituent_failure_in_publishable_row"):
        _write_outputs([row], tmp_path)


def test_gate_step_2b_rule_2_5_publishable_constituent_failure_exempt(
    tmp_path, monkeypatch,
):
    """Policy B rule 2.5 publishable funds (foreign-heavy short-circuit) must
    NOT trip the Step 2b pure-failure gate: their foreign constituents'
    pure-failures are expected (ADR 0003 §7), so the row is exempt and the
    canonical artifacts are written."""
    from dataclasses import replace as _replace

    from irc.fundamentals.types import ConstituentAnalysis
    from irc.opportunity.policy_b import PolicyBVerdict

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    bad = ConstituentAnalysis(
        symbol="00998", name_cn="中信银行", weight_pct=9.0,
        evidence=(), failure_reasons=("filing_empty:00998",), one_line_view="",
    )
    row = _replace(_make_row(iid="006809"), constituent_analyses=(bad,))
    verdict = PolicyBVerdict(
        gap_codes=(), audit_errors=(),
        decision_rule="foreign-heavy (share=100%); fund-level NAV+announcements accepted",
        fired_rule="2.5",
    )
    out_dir = _write_outputs(
        [row], tmp_path, pending_verdicts={"006809": verdict},
    )
    assert (out_dir / "opportunity_report.json").exists()
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["constituent_findings"] == []
    assert audit["summary"]["blocking"] is False


def test_gate_step_2b_non_2_5_verdict_does_not_exempt(tmp_path, monkeypatch):
    """A publishable verdict that did NOT fire rule 2.5 grants no exemption —
    a pure-failure constituent on such a row still raises unconditionally."""
    from dataclasses import replace as _replace

    from irc.fundamentals.types import ConstituentAnalysis
    from irc.opportunity.policy_b import PolicyBVerdict

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    bad = ConstituentAnalysis(
        symbol="600519", name_cn="X", weight_pct=5.0,
        evidence=(), failure_reasons=("timeout",), one_line_view="",
    )
    row = _replace(_make_row(), constituent_analyses=(bad,))
    verdict = PolicyBVerdict(
        gap_codes=(), audit_errors=(),
        decision_rule="info-leg quorum 5 of 10; 5 satisfied (publishable)",
        fired_rule="",
    )
    with pytest.raises(RuntimeError, match="constituent_failure_in_publishable_row"):
        _write_outputs([row], tmp_path, pending_verdicts={"005827": verdict})


def test_gate_step_1_fetch_budget_exhausted_still_raises(tmp_path, monkeypatch):
    """AC10 — fetch_budget_exhausted Step 1 raise is unchanged."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    row = _make_row(gaps=("fetch_budget_exhausted",))
    with pytest.raises(RuntimeError, match="fetch_budget_exhausted"):
        _write_outputs([row], tmp_path)


def test_gate_shadow_log_written_in_block_mode_before_raise(tmp_path, monkeypatch):
    """AC13 + AC23 — block-mode raise still writes the shadow log first."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    info_only = _make_row(legs=("information",))
    with pytest.raises(RuntimeError):
        _write_outputs([info_only], tmp_path)
    # Compute out_dir as the helper did: tmp_path/'outputs_scratch'
    out_dir = tmp_path / "outputs_scratch"
    audit_path = out_dir / "citation_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["summary"]["blocking"] is True
    # Canonical artifacts should NOT have leaked.
    assert not (out_dir / "opportunity_report.json").exists()
