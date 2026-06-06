from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
from typing import Callable
from irc.commands.ingest_cmd import run_ingest, _china_today
from irc.commands.discover_cmd import run_discover
from irc.commands.score_cmd import run_score
from irc.commands.gold_cmd import run_gold
from irc.commands.allocate_cmd import run_allocate
from irc.commands.plan_cmd import run_plan
from irc.commands.memo_cmd import run_memo
from irc.commands.opportunity_cmd import run_opportunity
from irc.commands.research_cmd import run_research
from irc.commands.decision_cmd import run_decision

STAGE_NAMES: tuple[str, ...] = (
    "ingest", "research", "discover", "score", "gold",
    "allocate", "plan", "opportunity", "memo", "decision",
)
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_ENV_VALUES


def _explicit_research_requested(from_stage: str | None, only_stage: str | None) -> bool:
    return only_stage == "research" or from_stage == "research"


def _without_disabled_optional_stages(
    stages: list[str], from_stage: str | None, only_stage: str | None,
) -> list[str]:
    if _env_flag_enabled("RESEARCH_ENABLED") or _explicit_research_requested(from_stage, only_stage):
        return stages
    if "research" in stages:
        print(
            "research skipped: set RESEARCH_ENABLED=true to run web research "
            "(requires TAVILY_API_KEY, BRAVE_API_KEY, or BOCHA_API_KEY)"
        )
    return [stage for stage in stages if stage != "research"]


def run_pipeline(
    repo_root: str,
    from_stage: str | None = None,
    only_stage: str | None = None,
    resume: bool = False,
) -> int:
    # Capture today's date once at function entry so a pipeline that straddles
    # the China-midnight boundary reads + writes state under the same date.
    today = _china_today()
    out_dir = Path(repo_root) / "outputs" / today
    if resume:
        if from_stage is not None or only_stage is not None:
            print("ERROR: --resume cannot be combined with --from or --only.")
            return 1
        from irc.pipeline_state import read_state
        state = read_state(out_dir)
        if state is None:
            print(
                f"ERROR: no halted pipeline state found for {today}; "
                f"nothing to resume. Run `irc run --repo-root {repo_root}` to start a new pipeline."
            )
            return 1
        if state.failed_stage not in STAGE_NAMES:
            print(
                f"ERROR: state file references unknown stage '{state.failed_stage}'. "
                f"Delete `outputs/{today}/.pipeline_state.json` and start over."
            )
            return 1
        from_stage = state.failed_stage
        print(
            f"resuming from stage '{from_stage}' (halted at {state.halted_at}, "
            f"reason: {state.reason_kind})"
        )
    if only_stage is not None:
        if only_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{only_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        stages = [only_stage]
    elif from_stage is not None:
        if from_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{from_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        idx = STAGE_NAMES.index(from_stage)
        stages = list(STAGE_NAMES[idx:])
    else:
        stages = list(STAGE_NAMES)
    stages = _without_disabled_optional_stages(stages, from_stage, only_stage)
    gate_rc = _gate(repo_root, stages, out_dir)
    if gate_rc != 0:
        return gate_rc
    return _run_stage_loop(repo_root, stages, out_dir, today)


def _gate(repo_root: str, stages: list[str], out_dir: Path) -> int:
    """Preflight spend/balance gate seam. Returns 0 to proceed, 5 to stop the run
    before any stage does paid work. Kept as a module-level function so tests can
    monkeypatch it."""
    from irc.commands.spend_cmd import preflight_gate
    return preflight_gate(repo_root, "run", stages=tuple(stages),
                          out_dir=out_dir, write_estimate=True)


def _run_stage_loop(repo_root: str, stages: list[str], out_dir: Path, today: str) -> int:
    total = len(stages)
    from irc.observability import stage_banner
    from irc.pipeline_outputs import missing_outputs

    class _StageFailed(Exception):
        pass

    for index, stage in enumerate(stages, start=1):
        rc = 0
        stage_error: BaseException | None = None
        try:
            with stage_banner(stage, index, total):
                fn = _runners_map()[stage]
                rc = fn(repo_root)
                if rc != 0:
                    raise _StageFailed(stage, rc)
        except _StageFailed:
            pass  # stage_banner already printed FAILED; rc is set correctly
        except KeyboardInterrupt:
            raise
        except SystemExit as exc:
            # A stage that raises SystemExit (opportunity's budget/lock gates
            # do this) must halt like any other failure so resume state gets
            # written — not propagate out of run_pipeline and leave nothing to
            # resume from.
            code = exc.code
            rc = code if isinstance(code, int) else 1
            stage_error = exc if rc != 0 else None
        except Exception as exc:
            rc = 1
            stage_error = exc
        if rc == 0:
            missing = missing_outputs(out_dir, stage)
            if missing:
                from irc.pipeline_halt import HaltReason
                sidecar = out_dir / ".halt_reason.json"
                HaltReason.write_sidecar(sidecar, HaltReason(
                    kind="missing_required_outputs",
                    stage=stage,
                    detail=(
                        f"stage exited 0 but did not produce: "
                        f"{', '.join(missing)}"
                    ),
                    stats={"missing_count": len(missing)},
                    first_error=None,
                ))
                rc = 1
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason
            from irc.pipeline_state import PipelineState, write_state
            sidecar = out_dir / ".halt_reason.json"
            structured = HaltReason.read_sidecar(sidecar)
            if structured is not None:
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=structured)
                sidecar.unlink(missing_ok=True)
                reason_kind = structured.kind
            elif stage_error is not None:
                reason = HaltReason(
                    kind="stage_exception",
                    stage=stage,
                    detail=f"{type(stage_error).__name__}: {stage_error}",
                    first_error=str(stage_error),
                )
                write_halted_structured(repo_root=Path(repo_root), date=today,
                                        reason=reason)
                reason_kind = "stage_exception"
            else:
                write_halted(
                    repo_root=Path(repo_root), date=today, stage=stage,
                    reason=f"stage exit code {rc}",
                    remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
                )
                reason_kind = "generic"
            write_state(out_dir, PipelineState(
                status="halted",
                failed_stage=stage,
                halted_at=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                reason_kind=reason_kind,
            ))
            return rc
    from irc.pipeline_state import clear_state
    clear_state(out_dir)
    (out_dir / "PIPELINE_HALTED.md").unlink(missing_ok=True)
    print(f"pipeline OK: ran {stages}")
    return 0


def _runners_map() -> dict[str, Callable[[str], int]]:
    return {
        "ingest":      run_ingest,
        "research":    run_research,
        "discover":    run_discover,
        "score":       run_score,
        "gold":        run_gold,
        "allocate":    run_allocate,
        "plan":        run_plan,
        "opportunity": run_opportunity,
        "memo":        run_memo,
        "decision":    run_decision,
    }
