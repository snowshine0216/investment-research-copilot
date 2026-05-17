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


def test_default_pipeline_skips_research_when_research_disabled(monkeypatch):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".")

    assert rc == 0
    assert called == [
        "ingest", "discover", "score", "gold", "allocate", "plan", "memo",
    ]


def test_pipeline_fails_fast_on_enabled_research_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
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


def test_only_research_runs_when_explicit_even_if_research_disabled(monkeypatch):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".", only_stage="research")

    assert rc == 0
    assert called == ["research"]


def test_from_research_runs_research_when_explicit_even_if_research_disabled(monkeypatch):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []

    with patch("irc.commands.run_cmd._runners_map", return_value=_recording_runners(called)):
        rc = run_pipeline(".", from_stage="research")

    assert rc == 0
    assert called == ["research", "discover", "score", "gold", "allocate", "plan", "memo"]


from datetime import date as _date
from irc.pipeline_halt import HaltReason
from irc.commands.ingest_cmd import _china_today


def test_run_pipeline_consumes_halt_reason_sidecar(tmp_path: Path):
    """When a stage fails and writes a sidecar, the halt markdown reflects
    the structured reason and the sidecar is deleted afterward."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / ".halt_reason.json"

    def failing_ingest(_repo_root: str) -> int:
        HaltReason.write_sidecar(sidecar, HaltReason(
            kind="akshare_empty", stage="ingest",
            detail="every fetch returned 0 rows",
            stats={"price_attempts": 198, "price_successes": 0},
            first_error="ConnectionResetError: simulated",
        ))
        return 1

    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["ingest"] = failing_ingest
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="ingest")

    assert rc == 1
    halt_md = (out_dir / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "akshare_empty" in halt_md
    assert "every fetch returned 0 rows" in halt_md
    assert "price_attempts" in halt_md and "198" in halt_md
    assert "ConnectionResetError" in halt_md
    assert not sidecar.exists(), "sidecar must be deleted after consumption"


def test_run_pipeline_falls_back_when_no_sidecar(tmp_path: Path):
    """When a stage fails without writing a sidecar, the halt markdown uses
    the legacy generic message — preserves back-compat for other stages."""
    def failing_score(_repo_root: str) -> int:
        return 7  # arbitrary non-zero

    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["score"] = failing_score
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="score")

    assert rc == 7
    today = _china_today()
    halt_md = (tmp_path / "outputs" / today / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "stage exit code 7" in halt_md
    assert "score" in halt_md
