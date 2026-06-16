"""PURE narrative scorers (M1 §3.2). f(cases, outputs) -> float in [0,1].
No I/O, no network, no LLM. Narrative output shape matches
narrative._build_messages: three *_commentary fields of claim dicts."""
from __future__ import annotations
import re

_FIELDS = ("price_action_commentary", "signal_rationale_commentary", "risk_commentary")
_BANNED_VERBS = ("主因", "导致", "由于")  # narrative._banned_verb_present, verbatim
_DIGIT = re.compile(r"\d")
_REF = re.compile(r"\[ref:[0-9a-f]{16}\]")


def _frac(numer: int, denom: int) -> float:
    return numer / denom if denom else 1.0


def _all_claims(output: dict) -> list[dict]:
    return [c for f in _FIELDS for c in output.get(f, [])]


def _pool_cids(case: dict) -> set[str]:
    return {e["citation_id"] for e in case.get("evidence_pool", [])}


def _banned_verb_present(text: str) -> bool:
    return any(v in text for v in _BANNED_VERBS)


def citation_resolution(cases: list[dict], outputs: list[dict]) -> float:
    total = resolved = 0
    for c, o in zip(cases, outputs):
        pool = _pool_cids(c)
        for claim in _all_claims(o):
            for cid in claim.get("citation_ids", ()):
                total += 1
                resolved += 1 if cid in pool else 0
    return _frac(resolved, total)


def entailment_ablation_pass(cases: list[dict], outputs: list[dict]) -> float:
    pairs = [(c, o) for c, o in zip(cases, outputs)
             if c["category"] == "entailment-ablation"]
    if not pairs:
        return 1.0
    hits = 0
    for c, o in pairs:
        exp = c["expected"]
        item_present = exp["present_iff_item"] in _pool_cids(c)
        probe_present = any(exp["claim_probe"] in claim.get("claim", "")
                            for claim in _all_claims(o))
        hits += 1 if probe_present == item_present else 0
    return _frac(hits, len(pairs))


def attribution_honesty(cases: list[dict], outputs: list[dict]) -> float:
    pairs = [(c, o) for c, o in zip(cases, outputs)
             if c["category"] == "attribution-honesty"]
    if not pairs:
        return 1.0
    hits = 0
    for _c, o in pairs:
        ok = all(
            not _banned_verb_present(claim.get("claim", ""))
            or claim.get("attribution_strength") == "supported_attribution"
            for claim in _all_claims(o)
        )
        hits += 1 if ok else 0
    return _frac(hits, len(pairs))


def hallucination_rate(cases: list[dict], outputs: list[dict]) -> float:
    pairs = [(c, o) for c, o in zip(cases, outputs) if c["category"] == "no-numbers"]
    if not pairs:
        return 0.0
    total = bad = 0
    for _c, o in pairs:
        for claim in _all_claims(o):
            text = claim.get("claim", "")
            total += 1
            bad += 1 if (_DIGIT.search(text) or _REF.search(text)) else 0
    # Finding 3: cases present but all outputs degraded (total==0) → FAIL (1.0)
    return _frac(bad, total) if total else 1.0
