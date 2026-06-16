from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from irc.commands import eval_cmd


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


@pytest.mark.parametrize("stage", ["monitor_impact", "monitor_narrative"])
def test_skipped_rc3_and_no_runner_import(tmp_path: Path, monkeypatch, stage, capsys):  # AC14
    monkeypatch.delenv("IRC_RUN_LIVE_LLM_EVAL", raising=False)
    called: list[str] = []

    def fake_import(name: str):
        called.append(name)
        raise AssertionError(f"runner {name} must not import on SKIPPED path")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage=stage, all_stages=False)
    assert rc == 3 and called == []
    out = capsys.readouterr().out.lower()
    assert "not executed" in out
    report = tmp_path / "outputs" / _today() / "evals" / stage / "report.json"
    assert json.loads(report.read_text(encoding="utf-8"))["overall"] == "SKIPPED"


@pytest.mark.parametrize("stage", ["monitor_impact", "monitor_narrative"])
def test_gate_blocks_before_runner(tmp_path: Path, monkeypatch, stage):  # AC15
    monkeypatch.setenv("IRC_RUN_LIVE_LLM_EVAL", "1")
    seen = {}
    monkeypatch.setattr(eval_cmd, "preflight_gate",
                        lambda repo_root, command, **kw: seen.update({"c": command}) or 5)

    def fake_import(name: str):
        raise AssertionError(f"runner {name} must not import when gate blocks")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage=stage, all_stages=False)
    assert rc == 5 and seen["c"] == "eval-live"


def test_all_suite_excludes_live_stages(tmp_path: Path, capsys):  # AC16
    rc = eval_cmd.run_eval(str(tmp_path), stage=None, all_stages=True)
    out = (capsys.readouterr().out + "").lower()
    assert "monitor_impact" not in out
    assert "monitor_narrative" not in out
    assert rc == 2  # no inputs → active stages FAIL, but live ones never appear
