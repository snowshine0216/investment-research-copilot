"""`run` run-kind: promotion fields flow from decision_report.json summary
through _build_outcome into the classifier's action page."""
from __future__ import annotations

import json
from pathlib import Path

from irc.commands.notify_cmd import _build_outcome, _china_today
from irc.notify.classify import classify_run_outcome


def _write_report(tmp_path: Path, summary: dict) -> Path:
    out = tmp_path / "outputs" / _china_today().isoformat()
    out.mkdir(parents=True)
    (out / "decision_report.json").write_text(
        json.dumps({"summary": summary}), encoding="utf-8"
    )
    return out


def _write_healthy_gold_regime(out: Path) -> None:
    """A gold_regime.json with no stale macro drivers — `weekly_health` sees
    this as clean (no items). Task 4 wired `_build_outcome` to always attach
    `read_weekly_health` for `run_kind == "weekly"`; an absent gold_regime.json
    now reads as `health_unknown` (warn) and would escalate these tests'
    asserted severities. A real weekly run always writes gold_regime.json (the
    gold stage runs before decision_report.json), so this fixture models the
    realistic co-present artifact set and keeps these tests scoped to
    promotion counting, not health escalation."""
    (out / "gold_regime.json").write_text(
        json.dumps({"macro_snapshots": [], "drivers_unavailable": []}), encoding="utf-8"
    )


def test_promotions_in_summary_page_as_action(tmp_path: Path) -> None:
    out = _write_report(tmp_path, {
        "actionable_buy_count": 0, "trim_count": 0, "exit_count": 0,
        "review_count": 0, "promotion_count": 1, "promotion_ids": ["161903"],
    })
    _write_healthy_gold_regime(out)
    outcome = _build_outcome(tmp_path, run_kind="weekly", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "action"
    assert "161903" in decision.body


def test_garbage_promotion_fields_degrade_to_zero(tmp_path: Path) -> None:
    """Corrupt-but-parseable summary fields must never crash _build_outcome:
    a non-numeric promotion_count, a non-list promotion_ids (int OR bare
    string — the latter would otherwise iterate per-character) all degrade
    to the 0/() defaults. (silent-failure review note, 2026-07-03)"""
    _write_report(tmp_path, {
        "actionable_buy_count": 0, "trim_count": 0, "exit_count": 0,
        "review_count": 0, "promotion_count": "x", "promotion_ids": "161903",
    })
    outcome = _build_outcome(tmp_path, run_kind="weekly", last_exit_code=0)
    assert outcome.promotion_count == 0
    assert outcome.promotion_ids == ()


def test_summary_without_promotion_keys_stays_clean(tmp_path: Path) -> None:
    """Back-compat: pre-promotions decision reports classify exactly as before."""
    out = _write_report(tmp_path, {
        "actionable_buy_count": 0, "trim_count": 0, "exit_count": 0,
        "review_count": 0,
    })
    _write_healthy_gold_regime(out)
    outcome = _build_outcome(tmp_path, run_kind="weekly", last_exit_code=0)
    assert outcome.promotion_count == 0
    assert outcome.promotion_ids == ()
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "clean"
