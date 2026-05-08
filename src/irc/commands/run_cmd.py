from __future__ import annotations
from pathlib import Path
from irc.commands.ingest_cmd import run_ingest
from irc.commands.discover_cmd import run_discover
from irc.commands.score_cmd import run_score
from irc.commands.gold_cmd import run_gold
from irc.commands.allocate_cmd import run_allocate
from irc.commands.plan_cmd import run_plan
from irc.commands.memo_cmd import run_memo

STAGE_NAMES: tuple[str, ...] = ("ingest", "discover", "score", "gold", "allocate", "plan", "memo")


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
    for stage in stages:
        fn = _runners_map()[stage]
        rc = fn(repo_root)
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            return rc
    print(f"pipeline OK: ran {stages}")
    return 0


def _runners_map() -> dict[str, object]:
    return {
        "ingest":   lambda r: run_ingest(r),
        "discover": lambda r: run_discover(r),
        "score":    lambda r: run_score(r),
        "gold":     lambda r: run_gold(r),
        "allocate": lambda r: run_allocate(r),
        "plan":     lambda r: run_plan(r),
        "memo":     lambda r: run_memo(r),
    }
