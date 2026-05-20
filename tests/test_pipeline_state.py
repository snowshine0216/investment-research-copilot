from __future__ import annotations
from pathlib import Path
from irc.pipeline_state import (
    PipelineState,
    STATE_FILENAME,
    clear_state,
    read_state,
    write_state,
)


def test_state_file_name_constant():
    assert STATE_FILENAME == ".pipeline_state.json"


def test_write_then_read_round_trip(tmp_path: Path):
    state = PipelineState(
        status="halted",
        failed_stage="memo",
        halted_at="2026-05-20T10:36:44+08:00",
        reason_kind="missing_required_outputs",
    )
    write_state(tmp_path, state)

    loaded = read_state(tmp_path)
    assert loaded == state


def test_read_state_returns_none_when_absent(tmp_path: Path):
    assert read_state(tmp_path) is None


def test_read_state_returns_none_on_malformed_json(tmp_path: Path):
    (tmp_path / STATE_FILENAME).write_text("{not json", encoding="utf-8")
    assert read_state(tmp_path) is None


def test_read_state_returns_none_on_missing_keys(tmp_path: Path):
    (tmp_path / STATE_FILENAME).write_text('{"status": "halted"}', encoding="utf-8")
    assert read_state(tmp_path) is None


def test_clear_state_removes_file(tmp_path: Path):
    state = PipelineState(
        status="halted", failed_stage="score",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    )
    write_state(tmp_path, state)
    assert (tmp_path / STATE_FILENAME).exists()

    clear_state(tmp_path)
    assert not (tmp_path / STATE_FILENAME).exists()


def test_clear_state_is_idempotent(tmp_path: Path):
    clear_state(tmp_path)  # no file — must not raise
    clear_state(tmp_path)


def test_read_state_returns_none_on_unreadable_file(tmp_path: Path, monkeypatch):
    """A PermissionError (or any OSError) reading the state file must surface as
    None, not propagate a traceback out of `irc run --resume`."""
    (tmp_path / STATE_FILENAME).write_text('{"status": "halted"}', encoding="utf-8")

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == STATE_FILENAME:
            raise PermissionError("simulated chmod 000")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)
    assert read_state(tmp_path) is None


def test_pipeline_state_is_frozen():
    state = PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    )
    import dataclasses
    assert dataclasses.is_dataclass(state)
    try:
        state.failed_stage = "score"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("PipelineState must be frozen")
