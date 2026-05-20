from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch
from irc.commands.run_cmd import run_pipeline, STAGE_NAMES
from irc.pipeline_halt import HaltReason
from irc.commands.ingest_cmd import _china_today


def _recording_runners(called: list[str]) -> dict[str, Callable[[str], int]]:
    def _runner(stage: str):
        def _run(_repo_root: str) -> int:
            called.append(stage)
            return 0
        return _run
    return {stage: _runner(stage) for stage in STAGE_NAMES}


def _producing_runners(called: list[str], out_dir: Path) -> dict[str, Callable[[str], int]]:
    """Recording runners that also write each stage's required outputs into
    `out_dir` — used by tests that exercise stage-selection across the full
    pipeline now that run_pipeline validates artifacts post-stage."""
    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def _runner(stage: str):
        def _run(_repo_root: str) -> int:
            called.append(stage)
            out_dir.mkdir(parents=True, exist_ok=True)
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run
    return {stage: _runner(stage) for stage in STAGE_NAMES}


def test_stage_names_complete():
    assert "ingest" in STAGE_NAMES
    assert "memo" in STAGE_NAMES
    assert "opportunity" in STAGE_NAMES
    # opportunity runs before memo so memo can read opportunity_report.json
    # and render real name_cn instead of falling back to instrument ids.
    assert STAGE_NAMES.index("opportunity") < STAGE_NAMES.index("memo")
    assert len(STAGE_NAMES) == 9  # ingest, research, discover, score, gold, allocate, plan, opportunity, memo


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


def test_default_pipeline_skips_research_when_research_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []
    out_dir = tmp_path / "outputs" / _china_today()

    with patch("irc.commands.run_cmd._runners_map",
               return_value=_producing_runners(called, out_dir)):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0
    assert called == [
        "ingest", "discover", "score", "gold", "allocate", "plan", "opportunity", "memo",
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


def test_only_research_runs_when_explicit_even_if_research_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []
    out_dir = tmp_path / "outputs" / _china_today()

    with patch("irc.commands.run_cmd._runners_map",
               return_value=_producing_runners(called, out_dir)):
        rc = run_pipeline(str(tmp_path), only_stage="research")

    assert rc == 0
    assert called == ["research"]


def test_from_research_runs_research_when_explicit_even_if_research_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    called: list[str] = []
    out_dir = tmp_path / "outputs" / _china_today()

    with patch("irc.commands.run_cmd._runners_map",
               return_value=_producing_runners(called, out_dir)):
        rc = run_pipeline(str(tmp_path), from_stage="research")

    assert rc == 0
    assert called == ["research", "discover", "score", "gold", "allocate", "plan", "opportunity", "memo"]


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


def test_pipeline_halts_when_stage_returns_zero_but_writes_no_outputs(tmp_path: Path):
    """A stage that returns rc=0 without producing its required outputs
    must halt the pipeline and write a halt reason explaining which artifacts
    were missing — this is the C1 regression class from the audit tracker."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    call_order: list[str] = []

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            call_order.append(stage)
            return 0  # success but writes nothing
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 1
    # Pipeline must halt at the first stage with required outputs that's missing them.
    # discover is the first such stage in STAGE_NAMES order; ingest (no required outputs)
    # and research (off by default) precede it.
    assert "discover" in call_order
    assert "score" not in call_order  # downstream stages must not run

    halt_md = (out_dir / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "missing_required_outputs" in halt_md
    assert "discovered_watchlist.csv" in halt_md


def test_pipeline_continues_when_stage_writes_required_outputs(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stub runners that "produce" their required outputs.
    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0


def test_pipeline_accepts_memo_blocked_as_memo_success(tmp_path: Path):
    """`memo_blocked.md` is the legitimate audit-block outcome — must not be flagged."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo_blocked.md").write_text("blocked", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0


def test_halt_writes_pipeline_state_file(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today

    def fail_score(_repo_root: str) -> int:
        return 1

    runners = {s: (lambda r: 0) for s in STAGE_NAMES}
    runners["score"] = fail_score
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), only_stage="score")

    assert rc == 1
    from irc.pipeline_state import read_state
    state = read_state(out_dir)
    assert state is not None
    assert state.status == "halted"
    assert state.failed_stage == "score"
    assert state.reason_kind  # some non-empty string


def test_successful_pipeline_clears_state_and_halt_markdown(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pre-seed stale halt + state files from a hypothetical prior run.
    (out_dir / "PIPELINE_HALTED.md").write_text("stale", encoding="utf-8")
    from irc.pipeline_state import PipelineState, STATE_FILENAME, write_state
    write_state(out_dir, PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    ))

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path))

    assert rc == 0
    assert not (out_dir / STATE_FILENAME).exists()
    assert not (out_dir / "PIPELINE_HALTED.md").exists()


def test_resume_with_no_state_file_returns_error(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), resume=True)
    assert rc == 1


def test_resume_rejects_combined_from_stage(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), from_stage="memo", resume=True)
    assert rc == 1


def test_resume_rejects_combined_only_stage(tmp_path: Path):
    rc = run_pipeline(str(tmp_path), only_stage="memo", resume=True)
    assert rc == 1


def test_resume_derives_from_stage_from_state_file(tmp_path: Path):
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    from irc.pipeline_state import PipelineState, write_state
    write_state(out_dir, PipelineState(
        status="halted", failed_stage="memo",
        halted_at="2026-05-20T10:00:00+08:00", reason_kind="generic",
    ))

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS
    called: list[str] = []

    def runner(stage: str):
        def _run(_repo_root: str) -> int:
            called.append(stage)
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners = {s: runner(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners):
        rc = run_pipeline(str(tmp_path), resume=True)

    assert rc == 0
    # Resume must start at the recorded failed_stage and run only downstream stages.
    # `memo` is the last stage, so only it should have run.
    assert called == ["memo"]


def test_cli_run_resume_flag_invokes_run_pipeline_with_resume_true(tmp_path: Path):
    """The CLI must pass `resume=True` through to run_pipeline when --resume is given."""
    from click.testing import CliRunner
    from irc.cli import main

    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_pipeline(repo_root, from_stage=None, only_stage=None, resume=False):
        captured["repo_root"] = repo_root
        captured["from_stage"] = from_stage
        captured["only_stage"] = only_stage
        captured["resume"] = resume
        return 0

    with patch("irc.commands.run_cmd.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(main, ["run", "--repo-root", str(tmp_path), "--resume"])

    assert result.exit_code == 0
    assert captured["resume"] is True
    assert captured["from_stage"] is None
    assert captured["only_stage"] is None


def test_end_to_end_halt_then_resume_recovers_pipeline(tmp_path: Path):
    """Simulate the C1 failure mode: stage X returns 0 but writes no outputs.
    Pipeline halts; a follow-up `--resume` after the stage is "fixed" picks up
    from X and completes."""
    today = _china_today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS

    # Phase 1: opportunity returns 0 but writes nothing -> halt.
    def runner_broken(stage: str):
        def _run(_repo_root: str) -> int:
            if stage == "opportunity":
                return 0  # silent failure: no outputs written
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            return 0
        return _run

    runners_broken = {s: runner_broken(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners_broken):
        rc1 = run_pipeline(str(tmp_path))
    assert rc1 == 1

    from irc.pipeline_state import STATE_FILENAME, read_state
    state = read_state(out_dir)
    assert state is not None and state.failed_stage == "opportunity"
    assert (out_dir / "PIPELINE_HALTED.md").exists()

    # Phase 2: "fix" opportunity -> resume.
    def runner_fixed(stage: str):
        def _run(_repo_root: str) -> int:
            for name in STAGE_REQUIRED_OUTPUTS.get(stage, ()):
                (out_dir / name).write_text("stub", encoding="utf-8")
            if stage == "memo":
                (out_dir / "memo.md").write_text("memo body", encoding="utf-8")
            return 0
        return _run

    runners_fixed = {s: runner_fixed(s) for s in STAGE_NAMES}
    with patch("irc.commands.run_cmd._runners_map", return_value=runners_fixed):
        rc2 = run_pipeline(str(tmp_path), resume=True)
    assert rc2 == 0
    assert not (out_dir / STATE_FILENAME).exists()
    assert not (out_dir / "PIPELINE_HALTED.md").exists()
    assert (out_dir / "opportunity_report.json").exists()
    assert (out_dir / "memo.md").exists()
