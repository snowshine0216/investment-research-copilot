from __future__ import annotations
import json
from pathlib import Path
from irc.monitor.eval.forward_log import ledger_row, append_ledger, latest_per_key
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M0
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _signal():
    return SignalRecord(fund_id="008986", status="ok", bias="ADD_BIAS", composite=0.3,
                        signal_confidence=0.9, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def _gate():
    return apply_eval_gate(_signal(), health=(StageHealth("monitor_signal", "PASS", ()),),
                           gating_stages=GATING_STAGES_M0)


def test_ledger_row_fields_and_nav_basis_literal():
    row = ledger_row(
        run_date="2026-06-16", fund_id="008986", written_at="2026-06-16T09:00:00+08:00",
        signal=_signal(), nav_acc=2.5, nav_unit=2.0, as_of_date="2026-06-16",
        published_state="ADD_BIAS", gate=_gate(), manifest_versions={"engine": "1"},
    )
    assert row["nav_basis"] == "coalesce(nav_acc,nav)"
    assert row["nav_acc"] == 2.5 and row["nav_unit"] == 2.0
    assert row["raw_status"] == "ok" and row["raw_bias"] == "ADD_BIAS"
    assert row["raw_composite"] == 0.3 and row["published_state"] == "ADD_BIAS"
    for k in ("run_date", "fund_id", "written_at", "signal_confidence",
              "gate_reason", "as_of_date", "manifest_versions"):
        assert k in row


def test_ledger_row_nav_acc_null_for_degraded():
    row = ledger_row(
        run_date="2026-06-16", fund_id="008986", written_at="t",
        signal=_signal(), nav_acc=None, nav_unit=0.0, as_of_date="N/A",
        published_state="EVAL_GATED", gate=_gate(), manifest_versions={"engine": "1"},
    )
    assert row["nav_acc"] is None


def test_append_ledger_is_real_append_not_overwrite(tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    append_ledger(p, [{"run_date": "2026-06-15", "fund_id": "a", "written_at": "1"}])
    append_ledger(p, [{"run_date": "2026-06-16", "fund_id": "b", "written_at": "2"}])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["fund_id"] == "a"
    assert json.loads(lines[1])["fund_id"] == "b"


def test_append_ledger_swallows_write_failure(tmp_path: Path):
    # point at a path whose parent is a FILE → mkdir/open fails; must not raise
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "monitor" / "forward_ledger.jsonl"
    append_ledger(bad, [{"run_date": "x", "fund_id": "y", "written_at": "1"}])  # no exception


def test_latest_per_key_collapses_rerun_to_last_written_at():
    rows = [
        {"run_date": "2026-06-16", "fund_id": "a", "written_at": "2026-06-16T09:00:00", "v": 1},
        {"run_date": "2026-06-16", "fund_id": "a", "written_at": "2026-06-16T10:00:00", "v": 2},
        {"run_date": "2026-06-16", "fund_id": "b", "written_at": "2026-06-16T09:00:00", "v": 3},
    ]
    out = latest_per_key(rows)
    by_key = {(r["run_date"], r["fund_id"]): r["v"] for r in out}
    assert by_key[("2026-06-16", "a")] == 2  # later written_at wins
    assert by_key[("2026-06-16", "b")] == 3
    assert len(out) == 2
