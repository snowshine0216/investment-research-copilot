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
