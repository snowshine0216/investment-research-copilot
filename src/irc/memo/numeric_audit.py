"""Programmatic memo auditor: catches numeric-prose disagreements.

Pure-function module. Scans the synthesized memo prose for sentences that
contradict the evidence pool the synthesizer was handed — specifically, the
class of failure caught in the 2026-05-18 audit on 000105 (prose said
"估值便宜 … 适合定投" while the same row's evidence had
`状态=expensive` or `cost_grade=85`).

This is a safety net for the prompt-glossary fix in item 004: even with
the LLM primed, an automated check is needed to catch regressions where
prose silently re-collides with the cost_grade axis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


_INSTRUMENT_PREFIX_RE = re.compile(r"\[([0-9A-Za-z_]{4,12})\s")
_STATE_TOKEN_RE = re.compile(r"状态=([a-z_]+)")
_COST_GRADE_RE = re.compile(r"cost_grade=(\d{1,3})")

# Tokens that mean "the asset is at a low/cheap point in its price history".
_CHEAP_PHRASES: Final[tuple[str, ...]] = (
    "估值便宜", "估值偏低", "估值处于低位", "估值低", "估值合理低估",
    "便宜的估值",
)

# Tokens that mean "the asset is at a high/expensive point in its price history".
_EXPENSIVE_PHRASES: Final[tuple[str, ...]] = (
    "估值偏高", "估值极高", "估值贵", "估值高",
)

_CHEAP_BUCKETS: Final[frozenset[str]] = frozenset({"cheap", "reasonable_low"})
_EXPENSIVE_BUCKETS: Final[frozenset[str]] = frozenset({"expensive", "very_expensive"})


@dataclass(frozen=True)
class NumericFinding:
    instrument_id: str
    kind: str
    prose_excerpt: str
    evidence_excerpt: str


def _parse_evidence_line(line: str) -> tuple[str, str | None, int | None] | None:
    """Parse one evidence-pool line into (instrument_id, valuation_state, cost_grade).

    Returns None when the line doesn't have an instrument prefix.
    """
    prefix = _INSTRUMENT_PREFIX_RE.match(line)
    if prefix is None:
        return None
    iid = prefix.group(1)
    state_match = _STATE_TOKEN_RE.search(line)
    state = state_match.group(1) if state_match else None
    grade_match = _COST_GRADE_RE.search(line)
    try:
        grade = int(grade_match.group(1)) if grade_match else None
    except ValueError:
        grade = None
    return iid, state, grade


def _proximity_excerpt(prose: str, anchor: int, phrase: str, window: int = 80) -> str:
    """Return a short window around the phrase for the finding excerpt."""
    start = max(0, anchor - window)
    end = min(len(prose), anchor + len(phrase) + window)
    return prose[start:end].replace("\n", " ").strip()


def _find_phrase_near_id(
    prose: str, instrument_id: str, phrases: tuple[str, ...], max_gap: int = 200,
) -> tuple[int, str] | None:
    """Find the first occurrence of any phrase in ``phrases`` within ``max_gap``
    characters of an occurrence of ``instrument_id`` in ``prose``. Returns
    ``(anchor_index, phrase)`` or None.
    """
    if instrument_id not in prose:
        return None
    iid_positions = [m.start() for m in re.finditer(re.escape(instrument_id), prose)]
    for phrase in phrases:
        for ph_pos in (m.start() for m in re.finditer(re.escape(phrase), prose)):
            for iid_pos in iid_positions:
                if abs(ph_pos - iid_pos) <= max_gap:
                    return ph_pos, phrase
    return None


def find_prose_data_contradictions(
    prose: str,
    evidence_lines: list[str] | tuple[str, ...],
) -> list[NumericFinding]:
    """Return a list of contradictions between prose and the evidence pool.

    Today we ship one detector: the cheap/expensive prose claim that
    contradicts the underlying ``状态`` bucket AND the ``cost_grade``
    factor. Future detectors can be added here as the audit's findings
    show new failure modes.
    """
    findings: list[NumericFinding] = []
    for line in evidence_lines:
        parsed = _parse_evidence_line(line)
        if parsed is None:
            continue
        iid, state, grade = parsed
        if state is None and grade is None:
            continue

        # Cheap prose claim — must agree with valuation bucket.
        # ``cost_grade`` alone is NOT evidence of cheap; only when it's very
        # high AND the bucket disagrees do we flag.
        cheap_hit = _find_phrase_near_id(prose, iid, _CHEAP_PHRASES)
        if cheap_hit is not None and state is not None and state not in _CHEAP_BUCKETS:
            anchor, phrase = cheap_hit
            if grade is not None and grade >= 70:
                findings.append(NumericFinding(
                    instrument_id=iid,
                    kind="cheap_claim_vs_state",
                    prose_excerpt=_proximity_excerpt(prose, anchor, phrase),
                    evidence_excerpt=line.strip(),
                ))
                continue
            # Also flag when there's no cost_grade carve-out — bucket alone
            # is enough to falsify a cheap claim.
            findings.append(NumericFinding(
                instrument_id=iid,
                kind="cheap_claim_vs_state",
                prose_excerpt=_proximity_excerpt(prose, anchor, phrase),
                evidence_excerpt=line.strip(),
            ))
            continue

        expensive_hit = _find_phrase_near_id(prose, iid, _EXPENSIVE_PHRASES)
        if expensive_hit is not None and state is not None and state in _CHEAP_BUCKETS:
            anchor, phrase = expensive_hit
            findings.append(NumericFinding(
                instrument_id=iid,
                kind="expensive_claim_vs_state",
                prose_excerpt=_proximity_excerpt(prose, anchor, phrase),
                evidence_excerpt=line.strip(),
            ))
    return findings


def render_findings_block(findings: list[NumericFinding]) -> str:
    """Render a markdown block to prepend to the auditor output. Returns the
    empty string when there are no findings (don't pollute the audit log).
    """
    if not findings:
        return ""
    lines = ["### 自动数值审核 (numeric audit)"]
    for f in findings:
        lines.append(
            f"- [{f.instrument_id}] {f.kind}: 文中称\"{f.prose_excerpt}\" — "
            f"但证据条目为 \"{f.evidence_excerpt}\"。"
        )
    return "\n".join(lines) + "\n\n"
