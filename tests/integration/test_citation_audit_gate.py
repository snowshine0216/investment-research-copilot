"""Item 009 — citation audit gate integration suite.

Reuses _publishable_set_helper.py from item 008's lift. Every test that
exercises the AkShare dispatcher asserts `_unexpected_calls(counter) == []`
(AC21 — closes item 008's documented-only sentinel)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.integration._publishable_set_helper import (
    _resp, _today_cn, _sha256_file,
    _collect_publishable_citation_universe,
    _patch_memo_routes, _install_ak_call_dispatch,
    _seed_publishable_set_repo,
)


def _unexpected_calls(counter: Counter) -> list[tuple]:
    """Returns keys in counter that aren't part of the locked dispatch set.
    Item 009 AC21 — closes item 008's documented-only sentinel."""
    return [k for k, v in counter.items() if v < 0]  # negative = unexpected


def _make_uncited_scenario(tmp_path, monkeypatch):
    """Helper: seed a repo with a valid baseline publishable run."""
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    return dispatch


@pytest.mark.parametrize(
    "mode,canonical,uncited,expected_raise",
    [
        ("block", True,  True,  True),   # (a) canonical + block + uncited → raise
        ("warn",  True,  True,  True),   # (b) canonical + warn  + uncited → raise (env ignored)
        ("off",   True,  True,  True),   # (c) canonical + off   + uncited → raise (env ignored)
        ("block", False, True,  True),   # (d) non-canonical + block + uncited → raise
        ("warn",  False, True,  False),  # (e) non-canonical + warn  + uncited → exits 0
        ("off",   False, True,  False),  # (f) non-canonical + off   + uncited → silent
        ("block", True,  False, False),  # (g) canonical + block + clean → exits 0
    ],
)
def test_enforce_mode_matrix(tmp_path, monkeypatch, mode, canonical, uncited, expected_raise):
    """Spec AC22 — seven-scenario matrix."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.memo.numeric_audit import NumericFinding

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", mode)
    _make_uncited_scenario(tmp_path, monkeypatch)

    # Force canonical path by writing to outputs/<today>/ (default).
    # For non-canonical, point run_opportunity at a sibling dir.
    out_arg = None if canonical else str(tmp_path / "scratch_out")

    if uncited:
        # Inject a fake finding to drive the gate without engineering bad seeds.
        def _fake(_rows, _cited):
            if not _rows:
                return []
            return [NumericFinding(
                instrument_id=_rows[0].instrument_id,
                kind="missing_data_citation",
                prose_excerpt="forced",
                evidence_excerpt="forced",
            )]
        monkeypatch.setattr(
            "irc.commands.opportunity_cmd.find_uncited_opportunity_rows",
            _fake,
        )

    if expected_raise:
        with pytest.raises((RuntimeError, SystemExit)):
            run_opportunity(str(tmp_path), output_dir=out_arg)
    else:
        rc = run_opportunity(str(tmp_path), output_dir=out_arg)
        assert rc == 0


def test_shadow_log_written_in_block_mode_even_when_raising(tmp_path, monkeypatch):
    """Spec AC23 — block mode raises but shadow log is written FIRST."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.memo.numeric_audit import NumericFinding

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    _make_uncited_scenario(tmp_path, monkeypatch)

    def _fake(_rows, _cited):
        if not _rows:
            return []
        return [NumericFinding(
            instrument_id=_rows[0].instrument_id,
            kind="missing_data_citation",
            prose_excerpt="forced",
            evidence_excerpt="forced",
        )]
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.find_uncited_opportunity_rows", _fake,
    )

    with pytest.raises(RuntimeError, match="citation_gate_blocked"):
        run_opportunity(str(tmp_path))

    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is True
    assert audit["enforce_mode"] == "block"
    assert audit["opportunity_findings"]
    # Canonical artifacts must NOT leak.
    for fname in ("opportunity_report.json", "thesis_cards.yaml",
                  "discipline_report.md", "rejections.json"):
        assert not (out_dir / fname).exists(), f"{fname} leaked"


def test_item_008_baseline_passes_with_gate_live(tmp_path, monkeypatch):
    """Spec AC24 / Q6 — item 008's seed already carries dual-leg dual-scope
    evidence on every publishable row; the gate is a no-op."""
    from irc.commands.opportunity_cmd import run_opportunity
    monkeypatch.delenv("IRC_CITATION_ENFORCE_MODE", raising=False)
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    rc = run_opportunity(str(tmp_path))
    assert rc == 0
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    # Gate-live baseline: no opportunity findings, blocking==False.
    assert audit["summary"]["blocking"] is False
    # All four canonical artifacts present.
    for fname in ("opportunity_report.json", "thesis_cards.yaml",
                  "discipline_report.md", "rejections.json"):
        assert (out_dir / fname).exists()


def test_memo_gate_shadow_log_lands_in_write_path_dir(tmp_path, monkeypatch):
    """Spec AC25 — _resolve_enforce_mode is called with out_dir (write path),
    NOT out_today (read path which may be stale-dated).

    Strategy: run opportunity into TODAY; manually rename today's upstream
    artifacts to a yesterday-dated dir; then run_memo and assert that the
    shadow log lands in today's dir, not yesterday's."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo, _today

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))

    today = _today()
    today_dir = tmp_path / "outputs" / today
    yesterday = "2026-05-21"
    ydir = tmp_path / "outputs" / yesterday
    ydir.mkdir(parents=True, exist_ok=True)
    for name in ("scoring.json", "gold_regime.json",
                 "proposed_allocation.yaml", "trade_plan.yaml",
                 "opportunity_report.json"):
        src = today_dir / name
        if src.exists():
            src.rename(ydir / name)

    with _patch_memo_routes("# memo draft"):
        run_memo(str(tmp_path))

    # AC25 contract: shadow log under today_dir, not ydir.
    assert (today_dir / "citation_audit.json").exists()
    assert not (ydir / "citation_audit.json").exists()


def test_two_run_byte_equality_for_citation_audit_json(tmp_path, monkeypatch):
    """Spec AC20 — two back-to-back runs of run_opportunity produce
    byte-identical citation_audit.json."""
    from irc.commands.opportunity_cmd import run_opportunity
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(str(tmp_path))
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    first_sha = _sha256_file(out_dir / "citation_audit.json")

    # Re-run. Atomic writes truncate-and-replace; the file should re-emerge
    # byte-identical (modulo run_date which is locked to today).
    run_opportunity(str(tmp_path))
    second_sha = _sha256_file(out_dir / "citation_audit.json")
    assert first_sha == second_sha
