from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceabilityResult:
    missing_refs: list[str]
    coverage_ratio: float  # 0-1: fraction of picked instruments cited in memo


def check_traceability(memo_text: str, raw_ref_pool: list[str]) -> TraceabilityResult:
    """Exact-copy lower bound: counts raw_ref strings that appear verbatim in memo_text.

    The LLM typically paraphrases rather than copies, so coverage_ratio is near 0
    in normal runs. This is intentional — it measures minimum verbatim citation,
    not semantic coverage. A proper fuzzy citation scorer is deferred to Plan 4.
    """
    missing = [r for r in raw_ref_pool if r not in memo_text]
    n = len(raw_ref_pool)
    coverage = 1.0 if n == 0 else (n - len(missing)) / n
    return TraceabilityResult(missing_refs=missing, coverage_ratio=coverage)
