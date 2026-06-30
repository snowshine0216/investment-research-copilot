from __future__ import annotations
from pathlib import Path
import pytest
from irc.commands import monitor_cmd


def test_run_forward_eval_invokes_runner(monkeypatch, tmp_path):
    called = {}

    def fake_run(repo_root):
        called["root"] = repo_root
        return 1  # WARN — normal for monitor_forward

    monkeypatch.setattr(monitor_cmd, "_forward_eval_run", fake_run)
    rc = monitor_cmd._run_forward_eval(tmp_path, "2026-06-30")
    assert rc == 1
    assert called["root"] == tmp_path


def test_run_forward_eval_swallows_exception(monkeypatch, tmp_path):
    def boom(repo_root):
        raise RuntimeError("scorer blew up")

    monkeypatch.setattr(monitor_cmd, "_forward_eval_run", boom)
    # MUST NOT raise — Comp 0 containment: a scorer failure never crashes the run
    rc = monitor_cmd._run_forward_eval(tmp_path, "2026-06-30")
    assert rc is None


from irc.monitor.eval.types import PredictivePanelModel
_PANEL_STUB = PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                   metrics=(), review_flag=False)


class _Cfg:
    class history:
        minimum_observations = 2


def _patch_min_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: _Cfg())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: [])
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: {})
    monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "_suite_eval", lambda *a, **k: ((), ()))
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda *a, **k: None)


def test_forward_eval_runs_after_ledger_before_panel(monkeypatch, tmp_path):
    order = []
    monkeypatch.setattr(monitor_cmd, "_write_eval_artifacts",
                        lambda *a, **k: order.append("artifacts"))
    monkeypatch.setattr(monitor_cmd, "_run_forward_eval",
                        lambda root, today: order.append("forward_eval") or 1)
    monkeypatch.setattr(monitor_cmd, "_predictive_panel_model",
                        lambda root, *, today: order.append("panel") or _PANEL_STUB)
    monkeypatch.setattr(monitor_cmd, "_write_outputs", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "_write_drilldown", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    _patch_min_pipeline(monkeypatch, tmp_path)

    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-30")
    assert rc == 0  # scorer WARN (rc 1) MUST NOT change monitor exit code
    assert order == ["artifacts", "forward_eval", "panel"]
