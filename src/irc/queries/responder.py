from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse
from irc.queries.parser import ParsedQuery


_SYSTEM = (
    "你是专业投资研究助理，必须基于提供的上下文（评分、备忘录、黄金 regime/band、决策报告）"
    "直接给出明确观点。要求："
    "1. 先给一句话明确结论（建议加仓/维持/暂停/减仓/观望）。"
    "2. 引用具体数据支撑（如 regime、zone、valuation_cost、score、价格区间），"
    "   能用上下文里的数字就用数字，不要写空话。"
    "3. 简述 1-3 条主要风险或前提条件。"
    "4. 全文不超过 300 字，客观、务实，不要回避问题。"
    "只有当上下文确实完全没有相关数据时才说明信息不足，"
    "否则必须基于已有数据给出方向性判断。"
)


def respond_to_query(
    query: ParsedQuery,
    context: dict[str, str],
    route: ResolvedRoute,
) -> ChatResponse:
    sections = [f"[{k}]\n{v}" for k, v in context.items() if k in query.context_keys]
    ctx_block = "\n\n".join(sections) if sections else "无额外上下文"
    user_msg = f"问题：{query.raw}\n\n参考资料：\n{ctx_block}"
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.2,
    )
