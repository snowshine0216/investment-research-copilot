from __future__ import annotations


_REQUIRED_SECTIONS = (
    "## TL;DR", "## 1. 当前组合", "## 2. 推荐动作", "## 3. 推导",
    "## 4. 因子分解", "## 5. 风险与证伪", "## 6. 数据完整性", "## 7. 用户覆盖记录",
)


def seven_sections_present(memo_text: str) -> float:
    found = sum(1 for s in _REQUIRED_SECTIONS if s in memo_text)
    return found / len(_REQUIRED_SECTIONS)


def raw_ref_reachability_in_memo(memo_text: str, refs: tuple[str, ...]) -> float:
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in memo_text) / len(refs)


def auditor_no_factual_flags(audit_result: dict) -> float:
    """Return 1.0 if no factual flags, else fraction of non-flagged claims."""
    flags = audit_result.get("factual_flags", [])
    total_claims = audit_result.get("total_claims", len(flags))
    if total_claims == 0:
        return 1.0
    return max(0.0, (total_claims - len(flags)) / total_claims)


def length_drift_vs_baseline(memo_text: str, baseline_chars: int) -> float:
    """Ratio of current memo length to baseline. 1.0 = no drift."""
    if baseline_chars <= 0:
        return 1.0
    return len(memo_text) / baseline_chars
