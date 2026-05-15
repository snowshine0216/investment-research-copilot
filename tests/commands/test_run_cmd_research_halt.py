from __future__ import annotations
import os
from pathlib import Path


def test_run_pipeline_halts_at_research_when_gate_fails(tmp_path, monkeypatch):
    """When research returns rc=2, the pipeline must halt before later stages."""
    from irc.commands import run_cmd

    called: list[str] = []

    def _ok(repo_root: str) -> int:
        called.append("ingest")
        return 0

    def _research_fail(repo_root: str) -> int:
        called.append("research")
        return 2

    def _later(name: str):
        def _fn(repo_root: str) -> int:
            called.append(name)
            return 0
        return _fn

    monkeypatch.setattr(run_cmd, "run_ingest", _ok)
    monkeypatch.setattr(run_cmd, "run_research", _research_fail)
    monkeypatch.setattr(run_cmd, "run_discover", _later("discover"))
    monkeypatch.setattr(run_cmd, "run_score", _later("score"))
    monkeypatch.setattr(run_cmd, "run_gold", _later("gold"))
    monkeypatch.setattr(run_cmd, "run_allocate", _later("allocate"))
    monkeypatch.setattr(run_cmd, "run_plan", _later("plan"))
    monkeypatch.setattr(run_cmd, "run_memo", _later("memo"))
    monkeypatch.setenv("RESEARCH_ENABLED", "true")

    rc = run_cmd.run_pipeline(str(tmp_path))

    assert rc == 2
    assert called == ["ingest", "research"], f"stages called: {called}"
    # PIPELINE_HALTED.md must be written
    halted_files = list((tmp_path / "outputs").rglob("PIPELINE_HALTED.md"))
    assert halted_files, "PIPELINE_HALTED.md must be written when a stage fails"
    body = halted_files[0].read_text(encoding="utf-8")
    assert "research" in body
