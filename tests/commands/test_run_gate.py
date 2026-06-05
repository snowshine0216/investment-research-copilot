from pathlib import Path
from irc.commands import run_cmd


def test_run_pipeline_stops_before_stages_when_gate_blocks(monkeypatch, tmp_path):
    calls = {"stages": 0}
    monkeypatch.setattr(run_cmd, "_run_stage_loop", lambda *a, **k: calls.__setitem__("stages", calls["stages"] + 1) or 0)
    monkeypatch.setattr(run_cmd, "_gate", lambda repo_root, stages: 5)  # blocked
    rc = run_cmd.run_pipeline(repo_root=str(tmp_path))
    assert rc == 5
    assert calls["stages"] == 0   # never entered the stage loop
