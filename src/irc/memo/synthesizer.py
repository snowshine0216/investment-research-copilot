from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


_SYSTEM = (
    "你是一位专业投资研究员，负责撰写简洁、准确、基于数据的投资决策备忘录。"
    "以中文书写，风格专业简洁，避免套话。"
)


def _sanitize_ref(ref: str) -> str:
    """Strip control characters to prevent prompt injection from external data sources."""
    return ref.replace("\n", " ").replace("\r", " ").strip()[:400]


def synthesize_memo(skeleton: str, raw_ref_pool: list[str], route: ResolvedRoute) -> ChatResponse:
    refs_block = "\n".join(f"- {_sanitize_ref(r)}" for r in raw_ref_pool[:40])
    user_msg = (
        f"以下是备忘录骨架：\n\n{skeleton}\n\n"
        f"以下是相关原始数据摘录（请结合数据充实各章节，勿发明数据）：\n{refs_block}\n\n"
        "请按骨架章节结构输出完整备忘录。"
    )
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.3,
    )
