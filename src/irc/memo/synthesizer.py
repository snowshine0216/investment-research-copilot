from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


_SYSTEM = (
    "你是一位专业投资研究员，负责撰写简洁、准确、基于数据的投资决策备忘录。"
    "以中文书写，风格专业简洁，避免套话。"
)


# Glossary prepended to the synthesizer user prompt. Calls out the one
# semantic collision that produced the 2026-05-18 audit finding: the
# ``状态=A/B/C/D`` token and the ``cost_grade`` number look like they both
# measure "valuation", but they are independent axes.
_GLOSSARY = (
    "字段说明（务必遵守，不要混用）：\n"
    "- 状态=A/B/C/D：分别是估值百分位分桶（A）、热度（B）、长期逻辑（C）、产品质量（D）。"
    "其中估值分桶 A ∈ {cheap, reasonable_low, fair, expensive, very_expensive, evidence_insufficient}。\n"
    "- cost_grade：0-100 的持有成本评分（费率 + 折溢价），数值越高表示成本越友好（费率越低）。\n"
    "  cost_grade 与 状态 中的估值分桶是两个独立维度——cost_grade=85 不等于估值高，"
    "也不等于估值低。回避把 cost_grade 解读为「估值贵」或「估值便宜」，必须分别引用 状态 与 cost_grade。\n"
    "- risk / quality / macro_fit / thesis_news：均为 0-100 评分，按各自字面意义解读。"
)


def _sanitize_ref(ref: str) -> str:
    """Strip control characters to prevent prompt injection from external data sources."""
    return ref.replace("\n", " ").replace("\r", " ").strip()[:400]


def synthesize_memo(skeleton: str, raw_ref_pool: list[str], route: ResolvedRoute) -> ChatResponse:
    refs_block = "\n".join(f"- {_sanitize_ref(r)}" for r in raw_ref_pool[:40])
    # When section 7 was prefilled deterministically (marker present), tell
    # the LLM to copy that section verbatim. Otherwise leave today's
    # behavior unchanged — the LLM still fills the placeholder.
    section7_instruction = ""
    if "<!-- IRC_EXECUTION_LINES_BEGIN -->" in skeleton:
        section7_instruction = (
            "第7节『执行要点』的内容已由系统生成（位于 IRC_EXECUTION_LINES_BEGIN/END "
            "标记之间），必须**原样保留**这两个 HTML 注释之间的所有 bullet，"
            "不要改写、合并或扩写其中的任何条目。"
        )
    user_msg = (
        f"{_GLOSSARY}\n\n"
        f"以下是备忘录骨架：\n\n{skeleton}\n\n"
        f"以下是相关原始数据摘录（请结合数据充实各章节，勿发明数据）：\n{refs_block}\n\n"
        f"{section7_instruction}\n\n"
        "请按骨架章节结构输出完整备忘录。"
    )
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.3,
    )
