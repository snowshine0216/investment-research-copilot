from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


_SYSTEM = (
    "你是投资合规审核员。检查备忘录是否包含无根据的预测或违规表达，"
    "并给出修改建议。如无问题，回复'审核通过'。"
)


def audit_memo(draft: str, route: ResolvedRoute) -> ChatResponse:
    user_msg = f"请审核以下投资备忘录：\n\n{draft}"
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.1,
    )
