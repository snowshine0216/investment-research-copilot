from __future__ import annotations


def _tokenize_ref(ref: str) -> set[str]:
    parts: list[str] = []
    for chunk in ref.replace(":", " ").replace("-", " ").split():
        if len(chunk) >= 3:
            parts.append(chunk.lower())
    return set(parts)


def _ref_match_score(ref: str, memo_lower: str) -> float:
    tokens = _tokenize_ref(ref)
    if not tokens:
        return 0.0
    hit = sum(1 for t in tokens if t in memo_lower)
    return hit / len(tokens)


def check_traceability(memo_text: str, raw_refs: tuple[str, ...] | list[str]) -> dict[str, float]:
    """Coverage ratio = fraction of refs whose tokens substantially appear in memo.
    A ref counts as "covered" when ≥0.6 of its meaningful tokens are present.
    """
    if not raw_refs:
        return {"coverage_ratio": 1.0, "n_refs": 0.0, "n_covered": 0.0}
    memo_lower = memo_text.lower()
    covered = sum(1 for ref in raw_refs if _ref_match_score(ref, memo_lower) >= 0.6)
    return {
        "coverage_ratio": covered / len(raw_refs),
        "n_refs": float(len(raw_refs)),
        "n_covered": float(covered),
    }
