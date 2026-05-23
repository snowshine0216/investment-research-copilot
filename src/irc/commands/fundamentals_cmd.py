from __future__ import annotations

from pathlib import Path

from irc.fundamentals.snapshot import (
    build_snapshot,
    registered_snapshot_targets,
    write_snapshot,
)
from irc.opportunity.types import LookthroughTarget


def _expand_targets(targets: tuple[str, ...]) -> tuple[str, ...]:
    stripped = tuple(t.strip() for t in targets if t.strip())
    if not stripped:
        return ()
    expanded: list[str] = []
    for target in stripped:
        if target.lower() == "all":
            expanded.extend(registered_snapshot_targets())
        else:
            expanded.append(target)
    return tuple(dict.fromkeys(expanded))


def run_snapshot_rebuild(
    repo_root: str,
    targets: tuple[str, ...],
    top_n: int = 10,
) -> int:
    """Build and cache constituent snapshots for each target.

    Returns 0 for all completed runs (including those with failure_reasons).
    Returns 2 when no targets are specified.
    """
    expanded_targets = _expand_targets(targets)
    if not expanded_targets:
        print("ERROR: provide at least one --target for snapshot rebuild.")
        return 2

    root = Path(repo_root)
    for target in expanded_targets:
        lt = LookthroughTarget(
            kind="broad_index", key=target, display_cn=target,
        )
        snapshot = build_snapshot(lt, top_n=top_n)
        path = write_snapshot(snapshot, root / "data")
        if snapshot.failure_reasons:
            joined = "; ".join(snapshot.failure_reasons)
            print(f"WARNING: {target} snapshot has gaps: {joined}")
        print(f"fundamentals snapshot OK: {target} -> {path}")
    return 0
