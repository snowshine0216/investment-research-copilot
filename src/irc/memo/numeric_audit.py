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

# Item 009 v1: actionable-keyword set for find_uncited_conclusions paragraph audit.
# Frozen list; v2 extension requires a producer-side change.
_ACTIONABLE_KEYWORDS: Final[tuple[str, ...]] = (
    "加速定投", "正常定投", "减速定投", "暂停加仓", "禁止买入",
    "回避", "建仓", "加仓", "减仓", "止损",
)

# Asset-class section header → asset_class string. Used by AC8(c)/(d) only.
_SECTION_HEADER_RE = re.compile(
    r"^##\s+(?P<label>CN权益基金|CN债券基金|黄金|CN ETF|US\w*|HK\w*)\b",
    re.MULTILINE,
)
_SECTION_LABEL_TO_ASSET_CLASS: Final[dict[str, str]] = {
    "CN权益基金": "cn_equity_fund",
    "CN债券基金": "cn_bond_fund",
    "黄金": "gold",
    "CN ETF": "cn_etf",
}

# Sub-section header that names an instrument_id explicitly:
#   "### 易方达蓝筹精选 (005827)"
# Used by AC19 for multi-owner constituent disambiguation.
_SUBSECTION_INSTRUMENT_RE = re.compile(
    r"^###\s+.+?\((?P<iid>[A-Za-z0-9_]{4,12})\)", re.MULTILINE,
)

_MARKER_RE = re.compile(r"\[ref:([0-9a-f]{16})\]")

_PUBLISHABLE_SCOPES_MEMO: Final[frozenset[str]] = frozenset({"instrument", "constituent"})


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


# ── Item 007 D1c — find_uncited_conclusions stub ─────────────────────────────
# The full body lands in item 009 (paragraph-level instrument/constituent
# reference detection + multi-owner disambiguation + per-mention strict gate).
# Item 007's irreducible contribution is the empty-map RuntimeError raise —
# it closes the most likely failure mode where build_alias_maps did not run
# and every prose mention silently looks like "no instrument referenced".


def find_uncited_conclusions(
    prose: str,
    cited_map: dict,
    instrument_aliases: dict,
    constituent_aliases: dict,
    constituent_cited_map: dict,
    *,
    strict_empty_alias_check: bool = False,
) -> list[NumericFinding]:
    """Paragraph-level audit: every actionable conclusion must be cited.

    Per AC3:
      (a) instrument references → require dual-leg [ref:...] markers from
          the same paragraph (or its immediate predecessor);
      (b) multi-owner constituent references → resolve via the nearest
          preceding `### {name} ({iid})` sub-header; emit
          `ambiguous_constituent_reference` when unresolvable;
      (c) actionable keyword with zero alias hits → asset-class section
          context drives `uncited_portfolio_conclusion`;
      (d) marker present but resolves to wrong owner_instrument_id →
          `wrong_instrument_citation`.

    `strict_empty_alias_check=True` (Q3) raises RuntimeError when
    instrument_aliases is empty AND prose is non-empty — closes the wiring
    bug where `build_alias_maps` was forgotten. Default False preserves the
    all-gapped pipeline state semantic from item 007.
    """
    if not prose or not prose.strip():
        return []
    if strict_empty_alias_check and not instrument_aliases:
        raise RuntimeError(
            "empty instrument_aliases — D1c builder did not run; "
            "check memo_cmd wiring"
        )
    if not instrument_aliases:
        # Permissive path (item 007 all-gapped semantic): no aliases → no audit.
        return []

    paragraphs = prose.split("\n\n")
    findings: list[NumericFinding] = []

    # Pre-scan for section/sub-section context as cumulative state.
    section_spans = _build_section_spans(prose)
    subsection_spans = _build_subsection_spans(prose)

    paragraph_offset = 0
    prev_markers: tuple[str, ...] = ()
    for para in paragraphs:
        para_start = paragraph_offset
        paragraph_offset += len(para) + 2  # +2 for the "\n\n" separator

        if not any(kw in para for kw in _ACTIONABLE_KEYWORDS):
            prev_markers = tuple(_MARKER_RE.findall(para))
            continue

        current_markers = tuple(_MARKER_RE.findall(para))
        scope_markers = current_markers + prev_markers
        asset_class = _section_at(section_spans, para_start)
        owner_iid = _subsection_at(subsection_spans, para_start)

        instrument_hits = _instrument_alias_hits(para, instrument_aliases)
        constituent_hits = _constituent_alias_hits(para, constituent_aliases)

        if not instrument_hits and not constituent_hits:
            # AC8(d) — portfolio-class conclusion path.
            if not scope_markers:
                findings.append(NumericFinding(
                    instrument_id=asset_class or "<portfolio>",
                    kind="uncited_portfolio_conclusion",
                    prose_excerpt=_excerpt(para),
                    evidence_excerpt=asset_class or "<no_section>",
                ))
            prev_markers = current_markers
            continue

        for iid in sorted(instrument_hits):
            findings.extend(_check_instrument_citation(
                iid=iid, markers=scope_markers,
                cited_map=cited_map, paragraph=para,
            ))

        for ck, owner_pairs in sorted(constituent_hits.items()):
            if len(owner_pairs) > 1 and owner_iid not in {iid for iid, _ in owner_pairs}:
                findings.append(NumericFinding(
                    instrument_id="<ambiguous>",
                    kind="ambiguous_constituent_reference",
                    prose_excerpt=ck,
                    evidence_excerpt=f"owners={sorted(owner_pairs)}",
                ))
                continue
            # Resolved: either single-owner OR section header disambiguates.
            resolved = next(
                (pair for pair in owner_pairs if pair[0] == owner_iid),
                next(iter(sorted(owner_pairs))),
            )
            iid, c_key = resolved
            findings.extend(_check_constituent_citation(
                iid=iid, c_key=c_key, markers=scope_markers,
                constituent_cited_map=constituent_cited_map, paragraph=para,
            ))

        prev_markers = current_markers

    return findings


def _build_section_spans(prose: str) -> list[tuple[int, str]]:
    """Return list of (offset, asset_class) sorted ascending by offset."""
    spans: list[tuple[int, str]] = []
    for m in _SECTION_HEADER_RE.finditer(prose):
        label = m.group("label")
        ac = _SECTION_LABEL_TO_ASSET_CLASS.get(label, label.lower())
        spans.append((m.start(), ac))
    return spans


def _build_subsection_spans(prose: str) -> list[tuple[int, str]]:
    """Return list of (offset, instrument_id) for `### {name} ({iid})` headers."""
    return [
        (m.start(), m.group("iid"))
        for m in _SUBSECTION_INSTRUMENT_RE.finditer(prose)
    ]


def _section_at(spans: list[tuple[int, str]], offset: int) -> str | None:
    """Return the asset_class of the most-recent section header before offset."""
    current = None
    for start, ac in spans:
        if start <= offset:
            current = ac
        else:
            break
    return current


def _subsection_at(spans: list[tuple[int, str]], offset: int) -> str | None:
    current = None
    for start, iid in spans:
        if start <= offset:
            current = iid
        else:
            break
    return current


def _instrument_alias_hits(paragraph: str, instrument_aliases: dict) -> set[str]:
    return {
        iid for alias, iid in instrument_aliases.items()
        if alias and alias in paragraph
    }


def _constituent_alias_hits(
    paragraph: str, constituent_aliases: dict,
) -> dict[str, frozenset[tuple[str, str]]]:
    return {
        alias: owners
        for alias, owners in constituent_aliases.items()
        if alias and alias in paragraph
    }


def _check_instrument_citation(
    *, iid: str, markers: tuple[str, ...], cited_map: dict, paragraph: str,
) -> list[NumericFinding]:
    """Return findings for the instrument-citation rule on one paragraph."""
    findings: list[NumericFinding] = []
    per_iid = cited_map.get(iid, {})
    has_data = False
    has_info = False
    wrong_owner_seen = False
    for cid in markers:
        meta = per_iid.get(cid)
        if meta is None:
            # Try to find this cid under another owner — wrong instrument.
            for owner, mp in cited_map.items():
                if cid in mp and owner != iid:
                    findings.append(NumericFinding(
                        instrument_id=iid,
                        kind="wrong_instrument_citation",
                        prose_excerpt=_excerpt(paragraph),
                        evidence_excerpt=(
                            f"citation_id={cid} resolves to owner={owner!r}, "
                            f"not {iid!r}"
                        ),
                    ))
                    wrong_owner_seen = True
                    break
            continue
        if meta.scope not in _PUBLISHABLE_SCOPES_MEMO:
            continue
        if meta.citation_kind == "data":
            has_data = True
        elif meta.citation_kind == "information":
            has_info = True
    if wrong_owner_seen:
        # Wrong-owner finding is the dominant diagnosis; skip uncited duplication.
        return findings
    if not has_data or not has_info:
        findings.append(NumericFinding(
            instrument_id=iid,
            kind="uncited_conclusion",
            prose_excerpt=_excerpt(paragraph),
            evidence_excerpt=(
                f"has_data={has_data} has_info={has_info} "
                f"markers={list(markers)}"
            ),
        ))
    return findings


def _check_constituent_citation(
    *, iid: str, c_key: str, markers: tuple[str, ...],
    constituent_cited_map: dict, paragraph: str,
) -> list[NumericFinding]:
    findings: list[NumericFinding] = []
    per_iid = constituent_cited_map.get(iid, {})
    per_c = per_iid.get(c_key, {})
    has_data = any(
        per_c.get(cid) and per_c[cid].citation_kind == "data" for cid in markers
    )
    has_info = any(
        per_c.get(cid) and per_c[cid].citation_kind == "information" for cid in markers
    )
    if not has_data or not has_info:
        findings.append(NumericFinding(
            instrument_id=iid,
            kind="uncited_conclusion",
            prose_excerpt=f"constituent={c_key}",
            evidence_excerpt=f"has_data={has_data} has_info={has_info}",
        ))
    return findings


def _excerpt(paragraph: str, *, limit: int = 120) -> str:
    s = paragraph.replace("\n", " ").strip()
    return s[:limit]


# ── Item 009 D2a — find_missing_pick_citations ──────────────────────────────
# Structural per-pick dual-leg + owner-provenance check. Runs against the
# pre-filtered top-3 citations returned by select_citations(cap=3).

def find_missing_pick_citations(
    pick_rows,
    cited_map: dict,
) -> list[NumericFinding]:
    """Return findings for PickRows that fail the dual-leg or owner check.

    Three failure modes:
      - empty `pick_row.citations` → kind="missing_pick_citations" (single finding)
      - non-empty but no `citation_kind == "data"` entry → "missing_data_citation"
      - non-empty but no `citation_kind == "information"` entry → "missing_information_citation"
      - any entry with `owner_instrument_id != pick_row.instrument_id` → "wrong_instrument_citation"
    """
    findings: list[NumericFinding] = []
    for pick in pick_rows:
        if not pick.citations:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_pick_citations",
                prose_excerpt="citations=()",
                evidence_excerpt=pick.opportunity_state,
            ))
            continue
        for ev in pick.citations:
            if ev.owner_instrument_id != pick.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=pick.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"owner_instrument_id={ev.owner_instrument_id!r} "
                        f"!= pick.instrument_id={pick.instrument_id!r}"
                    ),
                ))
        kinds = {ev.citation_kind for ev in pick.citations
                 if ev.owner_instrument_id == pick.instrument_id}
        if "data" not in kinds:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_data_citation",
                prose_excerpt="leg:data",
                evidence_excerpt=pick.opportunity_state,
            ))
        if "information" not in kinds:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_information_citation",
                prose_excerpt="leg:information",
                evidence_excerpt=pick.opportunity_state,
            ))
    return findings


# ── Item 009 D2a — find_uncited_discipline_rows ─────────────────────────────
# Structural per-row dual-leg + owner + parent_fund check on DisciplineRow.
# No [ref:...] marker check on note_cn — the structural check is authoritative.

def find_uncited_discipline_rows(
    discipline_rows,
    cited_map: dict,
) -> list[NumericFinding]:
    """Return findings for DisciplineRows that fail dual-leg or provenance.

    Per AC4:
      (i) require ≥1 data + ≥1 information entry in `row.thesis_evidence`;
      (ii) require `entry.owner_instrument_id == row.instrument_id`;
           for constituent-scoped entries, also `entry.parent_fund_id == row.instrument_id`.
    """
    findings: list[NumericFinding] = []
    for row in discipline_rows:
        own_data_present = False
        own_info_present = False
        for ev in row.thesis_evidence:
            if ev.owner_instrument_id != row.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"owner_instrument_id={ev.owner_instrument_id!r} "
                        f"!= row.instrument_id={row.instrument_id!r}"
                    ),
                ))
                continue
            if ev.scope == "constituent" and ev.parent_fund_id != row.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"parent_fund_id={ev.parent_fund_id!r} "
                        f"!= row.instrument_id={row.instrument_id!r}"
                    ),
                ))
                continue
            if ev.citation_kind == "data":
                own_data_present = True
            elif ev.citation_kind == "information":
                own_info_present = True
        if not own_data_present:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_data_citation",
                prose_excerpt="leg:data",
                evidence_excerpt=row.opportunity_state,
            ))
        if not own_info_present:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_information_citation",
                prose_excerpt="leg:information",
                evidence_excerpt=row.opportunity_state,
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
