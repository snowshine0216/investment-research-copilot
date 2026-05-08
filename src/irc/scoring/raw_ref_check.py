from __future__ import annotations


def reachability_rate(refs: tuple[str, ...], index: set[str]) -> float:
    """Pure: fraction of refs present in the index. Empty refs → 1.0."""
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in index) / len(refs)
