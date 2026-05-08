from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceabilityResult:
    missing_refs: list[str]
    coverage_ratio: float  # 0-1: fraction of picked instruments cited in memo


def check_traceability(memo_text: str, raw_ref_pool: list[str]) -> TraceabilityResult:
    missing = [r for r in raw_ref_pool if r not in memo_text]
    n = len(raw_ref_pool)
    coverage = 1.0 if n == 0 else (n - len(missing)) / n
    return TraceabilityResult(missing_refs=missing, coverage_ratio=coverage)
