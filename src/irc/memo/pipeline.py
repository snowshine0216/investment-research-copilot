from __future__ import annotations
from dataclasses import dataclass
from irc.llm._types import ResolvedRoute
from irc.memo.template import MemoInputs, render_skeleton
from irc.memo.synthesizer import synthesize_memo
from irc.memo.auditor import audit_memo
from irc.memo.traceability import TraceabilityResult, check_traceability


@dataclass(frozen=True)
class MemoOutput:
    skeleton: str
    draft: str
    audit_notes: str
    traceability: TraceabilityResult
    prompt_tokens_total: int
    completion_tokens_total: int


def run_memo_pipeline(
    inputs: MemoInputs,
    raw_ref_pool: list[str],
    synthesis_route: ResolvedRoute,
    audit_route: ResolvedRoute,
) -> MemoOutput:
    skeleton = render_skeleton(inputs)
    synth_resp = synthesize_memo(skeleton, raw_ref_pool, synthesis_route)
    audit_resp = audit_memo(synth_resp.text, audit_route)
    trace = check_traceability(synth_resp.text, raw_ref_pool)
    return MemoOutput(
        skeleton=skeleton,
        draft=synth_resp.text,
        audit_notes=audit_resp.text,
        traceability=trace,
        prompt_tokens_total=synth_resp.prompt_tokens + audit_resp.prompt_tokens,
        completion_tokens_total=synth_resp.completion_tokens + audit_resp.completion_tokens,
    )
