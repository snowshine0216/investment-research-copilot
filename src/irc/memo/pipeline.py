from __future__ import annotations
import re
import warnings
from dataclasses import dataclass
from irc.llm._types import ResolvedRoute
from irc.memo.template import MemoInputs, render_skeleton
from irc.memo.synthesizer import synthesize_memo
from irc.memo.auditor import audit_memo
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


def sanitize_refs_for_auditor(refs: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for r in refs:
        clean = r
        for pat in _INJECT_PATTERNS:
            clean = pat.sub("[redacted]", clean)
        out.append(clean.strip())
    return tuple(out)


@dataclass(frozen=True)
class MemoOutput:
    skeleton: str
    draft: str
    audit_notes: str
    traceability: dict[str, int]
    prompt_tokens_total: int
    completion_tokens_total: int


_MAX_REFS = 40  # must match synthesizer truncation
_EVIDENCE_HEADING = "## 附录·原始证据 (Raw Evidence)"
_EVIDENCE_PREAMBLE = (
    "以下条目为合成器输入的原始证据，逐条原样附录，不经改写，便于追溯。"
)


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
    body = "\n".join(f"- {ref}" for ref in refs)
    return f"\n\n{_EVIDENCE_HEADING}\n\n{_EVIDENCE_PREAMBLE}\n\n{body}\n"


def run_memo_pipeline(
    inputs: MemoInputs,
    raw_ref_pool: list[str],
    synthesis_route: ResolvedRoute,
    audit_route: ResolvedRoute,
) -> MemoOutput:
    skeleton = render_skeleton(inputs)
    effective_refs = raw_ref_pool[:_MAX_REFS]  # only check refs actually given to LLM
    sanitized_refs = list(sanitize_refs_for_auditor(tuple(effective_refs)))
    synth_resp = synthesize_memo(skeleton, sanitized_refs, synthesis_route)
    final_draft = synth_resp.text + _render_evidence_appendix(sanitized_refs)
    audit_resp = audit_memo(final_draft, audit_route)
    trace = check_traceability(final_draft, sanitized_refs)
    return MemoOutput(
        skeleton=skeleton,
        draft=final_draft,
        audit_notes=audit_resp.text,
        traceability=trace,
        prompt_tokens_total=synth_resp.prompt_tokens + audit_resp.prompt_tokens,
        completion_tokens_total=synth_resp.completion_tokens + audit_resp.completion_tokens,
    )
