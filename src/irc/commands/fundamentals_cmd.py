from __future__ import annotations

from pathlib import Path

from irc.fundamentals.snapshot import build_snapshot, write_snapshot


def run_snapshot_rebuild(
    repo_root: str,
    targets: tuple[str, ...],
    top_n: int = 10,
) -> int:
    """Build and cache constituent snapshots for each target.

    Returns 0 for all completed runs (including those with failure_reasons).
    Returns 2 when no targets are specified.
    """
    if not targets:
        print("ERROR: provide at least one --target for snapshot rebuild.")
        return 2

    root = Path(repo_root)
    for target in targets:
        snapshot = build_snapshot(target, top_n=top_n)
        path = write_snapshot(snapshot, root / "data")
        if snapshot.failure_reasons:
            joined = "; ".join(snapshot.failure_reasons)
            print(f"WARNING: {target} snapshot has gaps: {joined}")
        print(f"fundamentals snapshot OK: {target} -> {path}")
    return 0
