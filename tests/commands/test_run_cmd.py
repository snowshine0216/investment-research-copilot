from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.run_cmd import run_pipeline, STAGE_NAMES


def _recording_runners(called: list[str]) -> dict[str, Callable[[str], int]]:
    def _runner(stage: str):
        def _run(_repo_root: str) -> int:
            called.append(stage)
            return 0
        return _run
    return {stage: _runner(stage) for stage in STAGE_NAMES}


def test_stage_names_complete():
    assert "ingest" in STAGE_NAMES
    assert "memo" in STAGE_NAMES
    assert len(STAGE_NAMES) == 8  # ingest, research, discover, score, gold, allocate, plan, memo


def test_only_stage_runs_single():
    called = []
    def fake_stage(r: str) -> int:
        called.append("memo")
        return 0
    with patch("irc.commands.run_cmd._runners_map", return_value={s: (lambda r: 0) for s in STAGE_NAMES} | {"memo": fake_stage}):
        rc = run_pipeline(".", only_stage="memo")
    assert rc == 0
    assert called == ["memo"]


def test_pipeline_stops_on_failure():
    call_order: list[str] = []
    def fail_ingest(r: str) -> int:
        call_order.append("ingest")
        return 1
    runners = {s: (lambda r: (call_order.append(s), 0)[1]) for s in STAGE_NAMES}
    runners["ingest"] = fail_ingest
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(".")
    assert rc == 1
    assert "discover" not in call_order


def test_invalid_from_stage_returns_error():
    rc = run_pipeline(".", from_stage="nonexistent_stage")
    assert rc == 1


def test_invalid_only_stage_returns_error():
    rc = run_pipeline(".", only_stage="nonexistent_stage")
    assert rc == 1


def test_default_pipeline_skips_research_when_ldr_disabled(monkeypatch):
    monkeypatch.delenv("LDR_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".")

    assert rc == 0
    assert called == [
        "ingest", "discover", "score", "gold", "allocate", "plan", "memo",
    ]


def test_pipeline_fails_fast_on_enabled_research_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("LDR_ENABLED", "true")
    called: list[str] = []
    runners = _recording_runners(called)

    def fail_research(_repo_root: str) -> int:
        called.append("research")
        return 2

    runners["research"] = fail_research
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 2
    assert called == ["ingest", "research"]


def test_only_research_runs_when_explicit_even_if_ldr_disabled(monkeypatch):
    monkeypatch.delenv("LDR_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".", only_stage="research")

    assert rc == 0
    assert called == ["research"]


def test_from_research_runs_research_when_explicit_even_if_ldr_disabled(monkeypatch):
    monkeypatch.delenv("LDR_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".", from_stage="research")

    assert rc == 0
    assert called == ["research", "discover", "score", "gold", "allocate", "plan", "memo"]
