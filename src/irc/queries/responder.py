from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse
from irc.queries.parser import ParsedQuery


_SYSTEM = (
    "你是专业投资研究助理，根据提供的上下文（评分、备忘录）回答用户问题。"
    "回答简洁、客观，不超过300字。如上下文不足请说明。"
)


def respond_to_query(
    query: ParsedQuery,
    context: dict[str, str],
    route: ResolvedRoute,
) -> ChatResponse:
    ctx_block = "\n\n".join(
        f"[{k}]\n{v}" for k, v in context.items() if k in query.context_keys
    ) or "无额外上下文"
    user_msg = f"问题：{query.raw}\n\n参考资料：\n{ctx_block}"
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.2,
    )
