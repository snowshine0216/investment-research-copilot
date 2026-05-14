from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
from typing import Callable
from irc.commands.ingest_cmd import run_ingest
from irc.commands.discover_cmd import run_discover
from irc.commands.score_cmd import run_score
from irc.commands.gold_cmd import run_gold
from irc.commands.allocate_cmd import run_allocate
from irc.commands.plan_cmd import run_plan
from irc.commands.memo_cmd import run_memo
from irc.commands.research_cmd import run_research

STAGE_NAMES: tuple[str, ...] = ("ingest", "research", "discover", "score", "gold", "allocate", "plan", "memo")
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_ENV_VALUES


def _explicit_research_requested(from_stage: str | None, only_stage: str | None) -> bool:
    return only_stage == "research" or from_stage == "research"


def _without_disabled_optional_stages(
    stages: list[str], from_stage: str | None, only_stage: str | None,
) -> list[str]:
    if _env_flag_enabled("LDR_ENABLED") or _explicit_research_requested(from_stage, only_stage):
        return stages
    if "research" in stages:
        print("research skipped: set LDR_ENABLED=true to run LDR research")
    return [stage for stage in stages if stage != "research"]


def run_pipeline(repo_root: str, from_stage: str | None = None, only_stage: str | None = None) -> int:
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
    total = len(stages)
    from irc.observability import stage_banner
    for index, stage in enumerate(stages, start=1):
        with stage_banner(stage, index, total):
            fn = _runners_map()[stage]
            rc = fn(repo_root)
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted
            today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
            write_halted(
                repo_root=Path(repo_root), date=today, stage=stage,
                reason=f"stage exit code {rc}",
                remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
            )
            return rc
    print(f"pipeline OK: ran {stages}")
    return 0


def _runners_map() -> dict[str, Callable[[str], int]]:
    return {
        "ingest":   run_ingest,
        "research": run_research,
        "discover": run_discover,
        "score":    run_score,
        "gold":     run_gold,
        "allocate": run_allocate,
        "plan":     run_plan,
        "memo":     run_memo,
    }
