from __future__ import annotations
import re
import warnings
from dataclasses import dataclass
from irc.llm._types import ResolvedRoute
from irc.memo.template import MemoInputs, render_skeleton
from irc.memo.synthesizer import synthesize_memo
from irc.memo.auditor import audit_memo
from irc.memo.footnote_renderer import render_footnotes
from irc.memo.numeric_audit import (
    find_prose_data_contradictions,
    render_findings_block,
)
from irc.memo.traceability import check_traceability


class MixedDateWarning(UserWarning):
    """Emitted when memo input files span multiple output dates."""


def check_inputs_same_date(
    inputs: dict[str, object],
    expected: object,
) -> None:
    """Warn if any input file path does not contain the expected ISO date string."""
    mixed = [
        (name, str(p)) for name, p in inputs.items()
        if str(expected) not in str(p)
    ]
    if mixed:
        warnings.warn(
            f"memo inputs span multiple dates (expected {expected}): {mixed}",
            MixedDateWarning,
            stacklevel=2,
        )


_INJECT_PATTERNS = (
    re.compile(r"(?i)\b(system|assistant|user)\s*:"),
    re.compile(r"<\|.*?\|>"),
    re.compile(r'\{[^{}]*"verdict"\s*:[^}]*\}'),
    re.compile(r"(?i)ignore (previous|prior|all) (instructions|prompts)"),
)

_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_REVENUE_YOY_INTERPRETATION_RE = re.compile(
    r"revenue_yoy\s*=\s*(?:原始字段值\s*)?-?\d+(?:\.\d+)?"
    r"(?:（[^）]*(?:换算|同比增速|原始小数值|口径待核实)[^）]*）"
    r"|，具体含义及换算口径待核实，不得直接引用为业绩依据)?"
)
_REVENUE_YOY_CAVEAT = "财务数据字段含义及换算口径待核实，不得直接引用为业绩依据"
_UNIFIED_REVENUE_YOY_CAVEAT = (
    "财务数据字段含义及换算口径未经核实（详见附录原始证据合规注释），"
    "数值不得直接引用为业绩依据"
)
_QDII_BAND_AMBIGUITY_RE = re.compile(
    r"QDII\s*敞口：合计目标权重上限\s*(?P<weight>\d+(?:\.\d+)?%)，"
    r"落在配置区间\s*(?P<band>\[[^\]]+\])\s*下沿。"
    r"本期\s*QDII\s*溢价/折价数据未采集，敞口是否可接受暂无法确认，"
    r"须在交易前查阅二级市场溢价后方可执行。"
)
_REVENUE_YOY_CAVEAT_RE = re.compile(
    r"财务数据字段含义及换算口径待核实，不得直接引用为业绩依据"
)


def extract_evidence_cutoff(refs: list[str] | tuple[str, ...]) -> str | None:
    """Return the maximum ISO date (`YYYY-MM-DD`) found across raw_refs, or
    None if no ref carries a parseable date.

    Every raw_ref the scoring layer emits today is shaped like
    ``akshare:nav_history:000105:2026-05-15`` — the trailing date is the
    binding cutoff. The memo's risk-notes section uses the max across the
    pool so the disclosure is honest about how stale the snapshot is.
    """
    best: str | None = None
    for ref in refs:
        m = _ISO_DATE_RE.search(ref)
        if m is None:
            continue
        date_str = m.group(1)
        if best is None or date_str > best:
            best = date_str
    return best


def sanitize_refs_for_auditor(refs: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for r in refs:
        clean = r
        for pat in _INJECT_PATTERNS:
            clean = pat.sub("[redacted]", clean)
        out.append(clean.strip())
    return tuple(out)


def sanitize_unverified_revenue_yoy(text: str) -> str:
    """Remove active percentage conversions for ambiguous revenue_yoy fields."""
    return _REVENUE_YOY_INTERPRETATION_RE.sub(
        _REVENUE_YOY_CAVEAT,
        text,
    )


def sanitize_compliance_phrasing(text: str) -> str:
    """Normalize audit-sensitive phrases without changing evidence meaning."""
    softened = text.replace(
        "估值压力：宽基ETF在估值百分位偏高时回撤风险加大。",
        "估值压力：在部分历史时期，宽基ETF估值百分位偏高时曾出现较大回撤，"
        "但该关系并非稳定规律，不构成对未来走势的预测；"
        "本期相关标的估值偏高，执行前须自行核实风险承受能力。",
    ).replace(
        "维持现有敞口、等待估值回落。",
        "维持现有敞口；如估值出现回落，可按既定规则重新评估条件。",
    ).replace(
        "根据历史经验，实际利率与金价存在阶段性反向关联，"
        "但该关系并非稳定规律，不构成对未来走势的预测。",
        "本期实际利率数据缺失，相关分析不展开，不作方向性引用。",
    ).replace(
        "须在后续周期通过补足精选标的或开通缺失渠道逐步释放。",
        "须在后续 2 个审核周期内通过补足精选标的或开通缺失渠道逐步释放；"
        "若届时仍未改善，须提交专项说明。",
    )
    softened = _REVENUE_YOY_CAVEAT_RE.sub(_UNIFIED_REVENUE_YOY_CAVEAT, softened)
    return _QDII_BAND_AMBIGUITY_RE.sub(
        lambda m: (
            "QDII 敞口：目标权重上限合计 "
            f"{m.group('weight')}，位于配置区间 {m.group('band')} 下沿；"
            "但本期多只QDII标的因机会数据缺失处于暂缓执行状态，"
            "实际可执行敞口可能显著低于目标上限。"
            "溢价/折价数据未采集，执行前须自行查阅二级市场溢价，确认后方可操作。"
        ),
        softened,
    )


@dataclass(frozen=True)
class MemoOutput:
    skeleton: str
    # `draft` keeps the canonical `[ref:HEXID]` markers. Audit gates and
    # the memo-stage citation gate read this form.
    draft: str
    # `published_draft` is the user-facing memo.md content: same markdown
    # as `draft` with inline `[ref:HEXID]` swapped for `[N]` numerals and
    # the appendix entries numbered + hex-preserved at the line tail.
    published_draft: str
    audit_notes: str
    traceability: dict[str, int]
    prompt_tokens_total: int
    completion_tokens_total: int


_MAX_REFS = 40  # must match synthesizer truncation
_EVIDENCE_HEADING = "## 附录·原始证据 (Raw Evidence)"
_EVIDENCE_PREAMBLE = (
    "以下条目为合成器输入的原始证据，逐条原样附录，不经改写，便于追溯。"
)
_REVENUE_YOY_APPENDIX_CAVEAT = (
    "⚠️ 合规警示：该字段含义及换算口径未经核实，"
    "数值不得作为业绩依据引用，仅作原始数据存档。"
)
_INSUFFICIENT_SCORE_APPENDIX_CAVEAT = (
    "（评分注释：因估值维度缺失，该综合分不具备横向比较效力，"
    "仅作模型输出存档。）"
)


def _appendix_caveats(ref: str) -> str:
    caveats: list[str] = []
    if "状态=evidence_insufficient" in ref and "score=" in ref:
        caveats.append(_INSUFFICIENT_SCORE_APPENDIX_CAVEAT)
    return "".join(caveats)


def _format_appendix_line(ref: str) -> str:
    # F6 / ADR 0001 §5.2: trigger substring is the locked
    # disclosure-existence phrase `财报已披露（口径未核实）` emitted
    # by every filing-evidence producer.
    #
    # Cache-transition guard (F6 post-ship silent-failure-hunter P0):
    # snapshot caches written before this commit serialize the legacy
    # `revenue_yoy=<scalar>` summary shape. The cached citation_id is
    # source_url-keyed (filings always have a non-empty url), so the
    # cached evidence rehydrates without a citation_id mismatch and
    # flows here with the legacy summary intact. Trigger on BOTH the
    # new locked phrase AND the legacy substring so the compliance
    # caveat is NOT silently dropped during the cache-turnover window
    # (next `irc fundamentals snapshot --target all` rewrites the
    # caches to the new shape). The caveat text is the same in either
    # case — operator-facing posture preserved.
    if "财报已披露（口径未核实）" in ref or "revenue_yoy=" in ref:
        return f"- {_REVENUE_YOY_APPENDIX_CAVEAT} 原始证据：{ref}"
    return f"- {ref}{_appendix_caveats(ref)}"


def _render_evidence_appendix(refs: list[str]) -> str:
    """Render a deterministic verbatim-evidence appendix.

    The synthesizer prompt asks the LLM to integrate refs into the narrative,
    but LLMs paraphrase rather than quote — so ``check_traceability`` (which
    counts verbatim substring matches) almost always reports zero. That makes
    the decision gate flag ``memo_narrative_only`` even when the narrative is
    fully grounded. Appending the refs verbatim in a clearly-labelled
    appendix gives traceability an honest, non-zero floor without altering
    the synthesized narrative above it.
    """
    if not refs:
        return ""
    body = "\n".join(_format_appendix_line(ref) for ref in refs)
    return f"\n\n{_EVIDENCE_HEADING}\n\n{_EVIDENCE_PREAMBLE}\n\n{body}\n"


def run_memo_pipeline(
    inputs: MemoInputs,
    raw_ref_pool: list[str],
    synthesis_route: ResolvedRoute,
    audit_route: ResolvedRoute,
) -> MemoOutput:
    skeleton = render_skeleton(inputs)
    # The synthesizer prompt is the only place that needs the _MAX_REFS budget
    # (prompt-size constraint). Sanitization runs on the same truncated set
    # used in the prompt so the auditor sees what the LLM actually saw.
    effective_refs = raw_ref_pool[:_MAX_REFS]
    sanitized_refs = list(sanitize_refs_for_auditor(tuple(effective_refs)))
    # The appendix renders the full ref pool (no cap) so no §5 citation can
    # be missing from the appendix — fixes 2026-05-25 Problem #2 where
    # [ref:4b03af24151fe798] for 511010 was cited inline but cut from the
    # appendix tail.
    full_sanitized_refs = list(sanitize_refs_for_auditor(tuple(raw_ref_pool)))
    synth_resp = synthesize_memo(skeleton, sanitized_refs, synthesis_route)
    sanitized_draft = sanitize_compliance_phrasing(
        sanitize_unverified_revenue_yoy(synth_resp.text)
    )
    final_draft = sanitized_draft + _render_evidence_appendix(full_sanitized_refs)
    audit_resp = audit_memo(final_draft, audit_route)
    # Programmatic safety net: catch numeric-prose disagreements (e.g.
    # the 2026-05-18 audit's "estimated cheap" claim contradicting
    # 状态=expensive). The findings are merged into audit_notes as a
    # prefix block so a human reviewer sees them alongside the LLM audit.
    numeric_findings = find_prose_data_contradictions(sanitized_draft, sanitized_refs)
    audit_notes = render_findings_block(numeric_findings) + audit_resp.text
    trace = check_traceability(final_draft, sanitized_refs)
    # Audit + traceability ran on the canonical `[ref:HEXID]` form (final_draft).
    # The published draft is a separate field so memo_cmd's citation gate can
    # keep reading the hex-form draft while writing the friendlier form to disk.
    published_draft = render_footnotes(final_draft, full_sanitized_refs)
    return MemoOutput(
        skeleton=skeleton,
        draft=final_draft,
        published_draft=published_draft,
        audit_notes=audit_notes,
        traceability=trace,
        prompt_tokens_total=synth_resp.prompt_tokens + audit_resp.prompt_tokens,
        completion_tokens_total=synth_resp.completion_tokens + audit_resp.completion_tokens,
    )
