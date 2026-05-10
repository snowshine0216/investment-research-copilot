from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.run_cmd import run_pipeline, STAGE_NAMES


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
